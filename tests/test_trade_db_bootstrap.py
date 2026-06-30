import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import trade_db
import loss_cooldowns


class TradeDbBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.cooldown_patch = patch.object(loss_cooldowns, "COOLDOWN_FILE", Path(self.tempdir.name) / "loss_cooldowns.json")
        self.journal_patch = patch.object(trade_db, "_journal_event")
        self.db_patch.start()
        self.cooldown_patch.start()
        self.journal_patch.start()

    def tearDown(self):
        self.journal_patch.stop()
        self.cooldown_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def _closed_trade(
        self,
        symbol: str,
        pnl: float,
        exit_reason: str,
        *,
        sl: float | None = 101.0,
        risk_dollars: float = 5.0,
    ) -> int:
        trade_id = trade_db.log_trade(
            None,
            symbol,
            "SELL",
            entry_price=100.0,
            qty=1.0,
            mode="live",
            sl=sl,
            risk_dollars=risk_dollars,
        )
        trade_db.close_trade(trade_id, exit_price=101.0, pnl=pnl, exit_reason=exit_reason)
        return trade_id

    def test_live_daily_loss_state_splits_strategy_full_losses_and_safety_incidents(self):
        self._closed_trade("ETHUSDT", -4.90, "sl")
        self._closed_trade("LINKUSDT", 0.0, "protection_truth_failed")
        self._closed_trade("LINKUSDT", 0.50, "tp")

        state = trade_db.get_live_daily_loss_state(target_loss_at_sl_usd=5.0)

        self.assertAlmostEqual(state["daily_realized_loss_usd"], 4.90)
        self.assertEqual(state["daily_strategy_full_losses"], 1)
        self.assertEqual(state["daily_safety_incidents"], 1)
        self.assertEqual(state["closed_live_trades"], 3)

    def test_get_live_daily_loss_state_calculates_consecutive_losses(self):
        # 1. First trade: loss
        self._closed_trade("ETHUSDT", -1.0, "sl")
        # 2. Second trade: loss
        self._closed_trade("LINKUSDT", -0.5, "sl")
        # 3. Third trade: win
        self._closed_trade("BTCUSDT", 2.0, "tp")
        # 4. Fourth trade: loss
        self._closed_trade("RENDERUSDT", -0.1, "sl")
        # 5. Fifth trade: loss
        self._closed_trade("SOLUSDT", -0.2, "sl")

        state = trade_db.get_live_daily_loss_state(target_loss_at_sl_usd=5.0)

        self.assertEqual(state["daily_trades_count"], 5)
        self.assertEqual(state["daily_consecutive_losses"], 2)

    def test_tiny_dust_close_is_not_full_loss_unless_it_is_safety_fail_close(self):
        self._closed_trade("ETHUSDT", -0.09, "opposite")
        self._closed_trade("LINKUSDT", -0.09, "execution_failed")

        state = trade_db.get_live_daily_loss_state(target_loss_at_sl_usd=5.0)

        self.assertAlmostEqual(state["daily_realized_loss_usd"], 0.18)
        self.assertEqual(state["daily_strategy_full_losses"], 0)
        self.assertEqual(state["daily_safety_incidents"], 1)

    def test_notification_only_incident_counts_as_neither_without_db_state(self):
        state = trade_db.get_live_daily_loss_state(target_loss_at_sl_usd=5.0)

        self.assertEqual(state["daily_strategy_full_losses"], 0)
        self.assertEqual(state["daily_safety_incidents"], 0)
        self.assertEqual(state["daily_realized_loss_usd"], 0.0)

    def test_rearmed_trade_safety_fail_close_is_after_rearm(self):
        self._closed_trade("ETHUSDT", 0.0, "protection_truth_failed")
        trade_db.authorize_live_rearm("unit test")
        rearmed_trade = trade_db.log_trade(
            None,
            "LINKUSDT",
            "SELL",
            entry_price=100.0,
            qty=1.0,
            mode="live",
            sl=101.0,
            risk_dollars=2.5,
        )
        trade_db.consume_live_rearm(rearmed_trade)
        trade_db.close_trade(rearmed_trade, exit_price=100.0, pnl=0.0, exit_reason="execution_failed")

        state = trade_db.get_live_daily_loss_state(target_loss_at_sl_usd=5.0)

        self.assertEqual(state["rearm_used_count"], 1)
        self.assertEqual(state["daily_safety_incidents_after_rearm"], 1)

    def test_close_trade_does_not_relabel_already_closed_row(self):
        trade_id = self._closed_trade("ETHUSDT", -0.20, "execution_failed")

        trade_db.close_trade(trade_id, exit_price=95.0, pnl=5.0, exit_reason="opposite")
        row = trade_db.get_trade_by_id(trade_id)

        self.assertEqual(row["exit_reason"], "execution_failed")
        self.assertAlmostEqual(row["pnl"], -0.20)

    def test_close_trade_derives_realized_r_from_pnl_and_risk(self):
        trade_id = self._closed_trade("ETHUSDT", -2.50, "momentum_exit", risk_dollars=5.0)

        row = trade_db.get_trade_by_id(trade_id)

        self.assertAlmostEqual(row["r_multiple"], -0.5)

    def test_realized_exit_pnl_sums_milestone_cash(self):
        trade_id = trade_db.log_trade(
            None,
            "ETHUSDT",
            "SELL",
            entry_price=100.0,
            qty=1.0,
            risk_dollars=5.0,
            mode="live",
        )
        trade_db.log_exit(trade_id, "milestone_0", pnl_contribution=0.75, qty_pct=0.25)
        trade_db.log_exit(trade_id, "milestone_1", pnl_contribution=1.50, qty_pct=0.5)
        trade_db.log_exit(trade_id, "trail", pnl_contribution=None, qty_pct=1.0)

        self.assertAlmostEqual(trade_db.get_realized_exit_pnl(trade_id), 2.25)

    def test_open_trade_cannot_confirm_without_sl_anchor(self):
        trade_id = trade_db.log_trade(
            None,
            "ETHUSDT",
            "SELL",
            entry_price=100.0,
            qty=1.0,
            sl=None,
            mode="live",
            execution_state="protection_pending",
        )

        self.assertFalse(trade_db.confirm_trade(trade_id))
        self.assertEqual(trade_db.get_trade_by_id(trade_id)["execution_state"], "protection_pending")

    def test_trade_risk_updates_after_broker_reduces_size(self):
        trade_id = trade_db.log_trade(
            None,
            "LINKUSDT",
            "BUY",
            entry_price=9.89,
            qty=35.8,
            sl=9.75,
            tp=10.24,
            rr=2.5,
            risk_dollars=5.0,
            reward_dollars=12.5,
            mode="live",
        )

        trade_db.update_trade_risk(trade_id, 3.84, 9.60)
        row = trade_db.get_trade_by_id(trade_id)

        self.assertAlmostEqual(row["risk_dollars"], 3.84)
        self.assertAlmostEqual(row["reward_dollars"], 9.60)

    def test_planned_trade_persists_entry_protection_and_risk_before_fill(self):
        trade_id = trade_db.log_trade(
            None,
            "ETHUSDT",
            "SELL",
            entry_price=2140.0,
            qty=0.2,
            sl=2165.0,
            tp=2077.5,
            setup_grade="B",
            risk_dollars=2.5,
            mode="live",
            execution_state="planned_entry",
        )

        row = trade_db.get_trade_by_id(trade_id)

        self.assertEqual(row["execution_state"], "planned_entry")
        self.assertEqual(row["symbol"], "ETHUSDT")
        self.assertEqual(row["direction"], "SELL")
        self.assertEqual(row["setup_grade"], "B")
        self.assertAlmostEqual(row["sl"], 2165.0)
        self.assertAlmostEqual(row["tp"], 2077.5)
        self.assertAlmostEqual(row["risk_dollars"], 2.5)

    def test_trade_label_columns_bootstrap_and_persist(self):
        signal_id = trade_db.log_signal(
            "ETHUSDT",
            "BUY",
            entry_price=2000.0,
            strategy_label="15M_REVERSAL_CAPTURE",
            entry_setup_label="BULLISH_SWEEP_RECLAIM",
            regime_label="SMC_PRO_BEARISH_REVERSAL",
            source_service="testnet_15m_reversal_capture",
            webhook_port=5000,
            execution_mode="TESTNET",
        )
        trade_id = trade_db.log_trade(
            signal_id,
            "ETHUSDT",
            "BUY",
            entry_price=2000.0,
            qty=0.01,
            strategy="reversal_capture",
            timeframe="15",
            mode="live",
            strategy_label="15M_REVERSAL_CAPTURE",
            entry_setup_label="BULLISH_SWEEP_RECLAIM",
            regime_label="SMC_PRO_BEARISH_REVERSAL",
            source_service="testnet_15m_reversal_capture",
            webhook_port=5000,
            execution_mode="TESTNET",
            context={"reversal_evidence": {"liquidity_sweep": "bullish_sweep"}},
        )

        with trade_db._connect() as conn:
            signal = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        row = trade_db.get_trade_by_id(trade_id)

        self.assertEqual(signal["strategy_label"], "15M_REVERSAL_CAPTURE")
        self.assertEqual(signal["webhook_port"], 5000)
        self.assertEqual(signal["execution_mode"], "TESTNET")
        self.assertEqual(row["strategy_label"], "15M_REVERSAL_CAPTURE")
        self.assertEqual(row["source_service"], "testnet_15m_reversal_capture")
        self.assertIn("reversal_evidence", row["context_json"])

    def test_schema_backfills_supertrend_trade_and_linked_signal_labels(self):
        signal_id = trade_db.log_signal("BTCUSDT", "SELL", timeframe="60")
        trade_id = trade_db.log_trade(
            signal_id,
            "BTCUSDT",
            "SELL",
            entry_price=100.0,
            qty=1.0,
            strategy="supertrend",
            timeframe="60",
        )

        row = trade_db.get_trade_by_id(trade_id)
        with trade_db._connect() as conn:
            signal = conn.execute("SELECT strategy_label FROM signals WHERE id = ?", (signal_id,)).fetchone()

        self.assertEqual(row["strategy_label"], "1H_TREND_CONTINUATION")
        self.assertEqual(signal["strategy_label"], "1H_TREND_CONTINUATION")

    def test_zero_fill_price_does_not_overwrite_planned_entry(self):
        trade_id = trade_db.log_trade(
            None,
            "ETHUSDT",
            "SELL",
            entry_price=2140.0,
            qty=0.2,
            sl=2165.0,
            mode="live",
            execution_state="planned_entry",
        )

        trade_db.update_trade_fill(trade_id, entry_price=0.0, qty=0.23)
        row = trade_db.get_trade_by_id(trade_id)

        self.assertAlmostEqual(row["entry_price"], 2140.0)
        self.assertAlmostEqual(row["qty"], 0.23)

    def test_daily_trade_count_uses_sast_day_and_skips_migrated_rows(self):
        now_utc = datetime.now(ZoneInfo("Africa/Johannesburg")).astimezone(UTC)
        today_utc = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        yesterday_utc = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        current_trade = trade_db.log_trade(None, "ETHUSDT", "SELL", entry_price=100.0, qty=1.0)
        old_trade = trade_db.log_trade(None, "LINKUSDT", "SELL", entry_price=100.0, qty=1.0)
        migrated_trade = trade_db.log_trade(None, "LINKUSDT", "SELL", entry_price=100.0, qty=1.0)
        with trade_db._connect() as conn:
            conn.execute("UPDATE trades SET ts = ? WHERE id = ?", (today_utc, current_trade))
            conn.execute("UPDATE trades SET ts = ? WHERE id = ?", (yesterday_utc, old_trade))
            conn.execute("UPDATE trades SET ts = ?, source = 'migrated' WHERE id = ?", (today_utc, migrated_trade))
            conn.commit()

        self.assertEqual(trade_db.count_trades_opened_today_sast(), 1)

    def test_symbol_milestones_seed_lane_aware_exit_profile(self):
        trade_db.seed_milestone_thresholds()

        milestones = trade_db.get_milestone_config("LINKUSDT")

        self.assertEqual(milestones[0]["gate_name"], "milestone_0")
        self.assertAlmostEqual(milestones[0]["threshold"], 0.25)
        self.assertAlmostEqual(milestones[0]["close_pct"], 0.25)
        self.assertEqual(milestones[1]["gate_name"], "milestone_1")
        self.assertAlmostEqual(milestones[1]["threshold"], 0.5)
        self.assertAlmostEqual(milestones[1]["close_pct"], 0.35)
        self.assertEqual(milestones[2]["gate_name"], "milestone_2")
        self.assertAlmostEqual(milestones[2]["threshold"], 1.0)
        self.assertAlmostEqual(milestones[2]["close_pct"], 0.25)
        self.assertEqual(len(milestones), 3)


if __name__ == "__main__":
    unittest.main()
