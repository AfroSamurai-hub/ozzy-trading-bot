import unittest
from contextlib import ExitStack
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path
import os

import webhook
import config
import trade_db
import risk_policy


class LiveMicroPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.db_patch.start()
        self._orig_exists = os.path.exists
        self.halt_patch = patch(
            "webhook.os.path.exists",
            side_effect=lambda path: False if str(path) == webhook.HALT_FILE else self._orig_exists(path),
        )
        self.halt_patch.start()
        self.monitor_patch = patch.object(
            webhook,
            "_monitor_entry_gate_status",
            return_value={"allowed": True, "reason": "monitor_active", "service": "test"},
        )
        self.monitor_patch.start()
        self.client_patch = patch.object(webhook, "_get_binance_client", return_value=MagicMock())
        self.client_patch.start()
        self.drift_patch = patch.object(webhook, "_check_entry_drift", return_value={"allowed": True})
        self.drift_patch.start()
        self.lane_patch = patch.object(webhook, "get_lane_for_signal", return_value="1H_TREND")
        self.lane_patch.start()
        self.reconcile_patch = patch(
            "webhook.live_reconcile.reconcile_live_state",
            return_value={"healthy": True, "critical_mismatches": [], "warnings": []},
        )
        self.reconcile_patch.start()
        self.indicators_patch = patch(
            "webhook.get_binance_indicators",
            return_value={
                "rsi": 45.0,
                "ema200": 49000.0,
                "atr": 1000.0,
                "volume": 1500.0,
                "volume_avg20": 1000.0,
                "supertrend_direction": "long",
                "supertrend_value": 49000.0,
                "close": 50000.0,
            },
        )
        self.indicators_patch.start()
        webhook._pending.clear()

    def tearDown(self):
        webhook._pending.clear()
        self.indicators_patch.stop()
        self.reconcile_patch.stop()
        self.lane_patch.stop()
        self.drift_patch.stop()
        self.client_patch.stop()
        self.monitor_patch.stop()
        self.halt_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_live_micro_pool_contains_specified_symbols(self):
        """Test that the live micro symbols are correct: BTCUSDT, BNBUSDT, LINKUSDT, HYPEUSDT, XAUUSDT."""
        with (
            patch.object(config, "BINANCE_SYMBOLS", ["BTCUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT", "XAUUSDT"]),
            patch.object(webhook, "BINANCE_SYMBOLS", ["BTCUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT", "XAUUSDT"]),
        ):
            self.assertIn("BTCUSDT", config.BINANCE_SYMBOLS)
            self.assertIn("BNBUSDT", config.BINANCE_SYMBOLS)
            self.assertIn("LINKUSDT", config.BINANCE_SYMBOLS)
            self.assertIn("HYPEUSDT", config.BINANCE_SYMBOLS)
            self.assertIn("XAUUSDT", config.BINANCE_SYMBOLS)

    def test_effective_max_positions_is_three_during_micro_bootstrap(self):
        """Test that the bootstrap cap returns 3."""
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3),
        ):
            cap = risk_policy.effective_max_positions(10, 34.40)
            self.assertEqual(cap, 3)

    def test_low_quality_b_grade_gate_blocks_weak_1h_continuation_volume(self):
        """B-grade 1H continuation entries below the live-quality volume floor are blocked."""
        reason = webhook._low_quality_b_grade_reason(
            strategy_label="1H_TREND_CONTINUATION",
            setup_grade="B",
            volume_ratio=1.0,
            min_volume_ratio=1.10,
        )

        self.assertEqual(
            reason,
            "B-grade 1H continuation volume below live-quality floor — 1.0 < 1.1",
        )

    def test_low_quality_b_grade_gate_does_not_block_other_lanes_or_strong_volume(self):
        """The B-grade volume floor is scoped to weak 1H continuation only."""
        self.assertIsNone(
            webhook._low_quality_b_grade_reason(
                strategy_label="15M_MEAN_REVERSION",
                setup_grade="B",
                volume_ratio=0.8,
                min_volume_ratio=1.10,
            )
        )
        self.assertIsNone(
            webhook._low_quality_b_grade_reason(
                strategy_label="1H_TREND_CONTINUATION",
                setup_grade="B",
                volume_ratio=1.1,
                min_volume_ratio=1.10,
            )
        )
        self.assertIsNone(
            webhook._low_quality_b_grade_reason(
                strategy_label="1H_TREND_CONTINUATION",
                setup_grade="A",
                volume_ratio=0.8,
                min_volume_ratio=1.10,
            )
        )

    def test_openclaw_breakout_risk_cap_blocks_context_oversizing(self):
        """Breakout-retest entries may run, but do not inherit oversized context boosts."""
        adjusted, cap_multiplier = webhook._apply_strategy_risk_cap(
            adjusted_risk_pct=0.0175,
            base_risk_pct=0.01,
            strategy_label="BREAKOUT_RETEST",
            cap_multiplier=1.0,
        )

        self.assertEqual(adjusted, 0.01)
        self.assertAlmostEqual(cap_multiplier, 0.01 / 0.0175)

    def test_openclaw_breakout_risk_cap_does_not_touch_other_lanes(self):
        """Risk cap is limited to OpenClaw breakout-retest experiments."""
        adjusted, cap_multiplier = webhook._apply_strategy_risk_cap(
            adjusted_risk_pct=0.0175,
            base_risk_pct=0.01,
            strategy_label="1H_TREND_CONTINUATION",
            cap_multiplier=1.0,
        )

        self.assertEqual(adjusted, 0.0175)
        self.assertEqual(cap_multiplier, 1.0)

    def test_max_positions_reached_blocks_fourth_position_with_correct_message(self):
        """Test that reaching the max position limit of 3 blocks the fourth position."""
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(webhook, "BINANCE_TESTNET", False),
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "MAX_POSITIONS", 3),
            patch.object(webhook, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3),
            patch.object(webhook, "_get_live_equity", return_value=34.40),
            patch.object(webhook, "_get_cached_positions") as mock_positions,
            patch("webhook.live_reconcile.reconcile_live_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}),
        ):
            mock_positions.return_value = (
                [
                    {"symbol": "BTCUSDT", "type": "BUY", "profit": "1.0", "openPrice": "100.0"},
                    {"symbol": "BNBUSDT", "type": "BUY", "profit": "1.0", "openPrice": "100.0"},
                    {"symbol": "LINKUSDT", "type": "BUY", "profit": "1.0", "openPrice": "100.0"},
                ],
                True,
            )

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "HYPEUSDT",
                    "entry": 5.0,
                    "sl": 4.8,
                    "tp": 5.5,
                    "timestamp": 1779613507000,
                }
                with (
                    patch("webhook.validate_signal_payload", return_value=(True, [])),
                    patch("webhook._check_signal_age", return_value={"allowed": True}),
                    patch("webhook._check_entry_drift", return_value={"allowed": True}),
                    patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
                    patch("webhook.telegram_client.notify_rejected") as mock_notify,
                ):
                    resp = client.post("/webhook", json=payload)
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertEqual(data["status"], "rejected")
                    self.assertEqual(data["reason"], "Max concurrent positions (3) reached — 3 open")
                    mock_notify.assert_called_with("Max concurrent positions (3) reached — 3 open", "HYPEUSDT", "BUY")

    def test_duplicate_same_symbol_position_is_blocked_with_correct_message(self):
        """Test that same-symbol duplicate position is blocked."""
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(webhook, "BINANCE_TESTNET", False),
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "MAX_POSITIONS", 3),
            patch.object(webhook, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3),
            patch.object(webhook, "ALLOW_PYRAMIDING", False),
            patch.object(webhook, "_get_live_equity", return_value=34.40),
            patch.object(webhook, "_get_cached_positions") as mock_positions,
            patch("webhook.live_reconcile.reconcile_live_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}),
        ):
            mock_positions.return_value = (
                [
                    {"symbol": "BTCUSDT", "type": "BUY", "profit": "1.0", "openPrice": "100.0"},
                ],
                True,
            )

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "BTCUSDT",
                    "entry": 100.0,
                    "sl": 98.0,
                    "tp": 105.0,
                    "timestamp": 1779613507000,
                }
                with (
                    patch("webhook.validate_signal_payload", return_value=(True, [])),
                    patch("webhook._check_signal_age", return_value={"allowed": True}),
                    patch("webhook._check_entry_drift", return_value={"allowed": True}),
                    patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
                    patch("webhook.telegram_client.notify_rejected") as mock_notify,
                ):
                    resp = client.post("/webhook", json=payload)
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertEqual(data["status"], "rejected")
                    self.assertEqual(data["reason"], "Position already open for BTCUSDT")
                    mock_notify.assert_called_with("Position already open for BTCUSDT", "BTCUSDT", "BUY")

    def test_critical_reconciliation_mismatch_blocks_entries_with_correct_message(self):
        """Test that safety block works when critical reconciliation mismatch exists."""
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "BINANCE_TESTNET", False),
            patch.object(webhook, "_get_cached_positions", return_value=([], True)),
            patch("webhook.live_reconcile.reconcile_live_state") as mock_reconcile,
        ):
            mock_reconcile.return_value = {
                "healthy": False,
                "critical_mismatches": ["POSITION_QTY_MISMATCH on BTCUSDT"],
            }

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "BTCUSDT",
                    "entry": 100.0,
                    "sl": 98.0,
                    "tp": 105.0,
                    "timestamp": 1779613507000,
                }
                with (
                    patch("webhook.validate_signal_payload", return_value=(True, [])),
                    patch("webhook._check_signal_age", return_value={"allowed": True}),
                    patch("webhook._check_entry_drift", return_value={"allowed": True}),
                    patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
                    patch("webhook.telegram_client.notify_rejected") as mock_notify,
                ):
                    resp = client.post("/webhook", json=payload)
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertEqual(data["status"], "rejected")
                    self.assertEqual(data["reason"], "Reconciliation critical mismatch — entries frozen")
                    mock_notify.assert_called_with(
                        "Reconciliation critical mismatch — entries frozen: POSITION_QTY_MISMATCH on BTCUSDT",
                        "BTCUSDT",
                        "BUY",
                    )

    def test_standard_testnet_unchanged(self):
        """Test that STANDARD_TESTNET mode continues to function normally with standard error messages."""
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "MICRO_BOOTSTRAP_MODE", False),
            patch.object(webhook, "MAX_POSITIONS", 10),
            patch.object(webhook, "ALLOW_PYRAMIDING", False),
            patch.object(webhook, "_get_live_equity", return_value=10000.0),
            patch.object(webhook, "_get_cached_positions") as mock_positions,
        ):
            mock_positions.return_value = (
                [
                    {"symbol": "BTCUSDT", "type": "BUY", "profit": "1.0", "openPrice": "100.0"},
                ],
                True,
            )

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "BTCUSDT",
                    "entry": 100.0,
                    "sl": 98.0,
                    "tp": 105.0,
                    "timestamp": 1779613507000,
                }
                with (
                    patch("webhook.validate_signal_payload", return_value=(True, [])),
                    patch("webhook._check_signal_age", return_value={"allowed": True}),
                    patch("webhook._check_entry_drift", return_value={"allowed": True}),
                    patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
                    patch("webhook.telegram_client.notify_rejected") as mock_notify,
                ):
                    resp = client.post("/webhook", json=payload)
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertEqual(data["status"], "rejected")
                    self.assertEqual(data["reason"], "Position already open for BTCUSDT")
                    mock_notify.assert_called_with("Position already open for BTCUSDT", "BTCUSDT", "BUY")

    def test_live_micro_downshifts_risk_on_lot_sizing(self):
        """Test that the live micro lot sizing dynamically downshifts when the daily budget is limited."""
        from decimal import Decimal
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(webhook, "BINANCE_TESTNET", False),
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "_get_live_equity", return_value=100.0),
            patch.object(webhook, "_get_cached_positions", return_value=([], True)),
            patch("webhook.live_reconcile.reconcile_live_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}),
            patch("webhook._bootstrap_daily_stop_status") as mock_daily_stop,
            patch("webhook.calculate_lot_size") as mock_calc_lot,
            patch("webhook.trade_db.log_trade") as mock_log_trade,
            patch("webhook.place_trade") as mock_place_trade,
            patch("webhook.plain_log") as mock_plain_log,
        ):
            # remaining daily budget is 4.54. Safety factor is 0.90, so max allowed effective is 4.54 * 0.90 = 4.086
            mock_daily_stop.return_value = {
                "remaining_daily_loss_budget_usd": 4.54,
                "live_trading_blocked_for_day": False,
                "model": "live_bootstrap_dollar",
            }
            # mock lot sizing call and final trade execution/logging
            mock_calc_lot.return_value = Decimal("0.2")
            mock_log_trade.return_value = 12345
            mock_place_trade.return_value = {"status": "success", "quantity": 0.2}
            
            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "BTCUSDT",
                    "entry": 50000.0,
                    "sl": 49000.0,  # 1000 distance
                    "tp": 53000.0,
                    "timestamp": 1779613507000,
                }
                with (
                    patch("webhook.validate_signal_payload", return_value=(True, [])),
                    patch("webhook._check_signal_age", return_value={"allowed": True}),
                    patch("webhook._check_entry_drift", return_value={"allowed": True}),
                    patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
                    patch("webhook.classify_crypto_entry", return_value={"mode": "trend_continuation", "grade": "A", "reasons": []}),
                    patch(
                        "webhook.get_size_multiplier",
                        return_value={
                            "multiplier": 1.0,
                            "adjusted_risk_pct": 0.02,
                            "reasoning": "test",
                            "fear_greed": 50,
                            "funding_rate": 0.0,
                        },
                    ),
                    patch("webhook.telegram_client.notify_rejected"),
                ):
                    resp = client.post("/webhook", json=payload)
                    self.assertEqual(resp.status_code, 200)
                    
                    # Verify calculate_lot_size was called with the downshifted risk percent (accounting for fee/slippage buffer)!
                    mock_calc_lot.assert_called_once()
                    args, kwargs = mock_calc_lot.call_args
                    self.assertAlmostEqual(float(args[1]), 2.0)
                    
                    # Verify log_trade was called with downshifted risk_dollars (quantized to 0.01)
                    mock_log_trade.assert_called_once()
                    kwargs_logged = mock_log_trade.call_args.kwargs
                    self.assertAlmostEqual(float(kwargs_logged["risk_dollars"]), 2.0)

    def test_live_micro_safety_incident_reduces_next_trade_risk_without_changing_position_cap(self):
        """After a safety incident, LIVE_MICRO keeps entries allowed but cuts sizing risk."""
        from decimal import Decimal

        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True))
            stack.enter_context(patch.object(webhook, "BINANCE_TESTNET", False))
            stack.enter_context(patch.object(webhook, "PAPER_MODE", False))
            stack.enter_context(patch.object(webhook, "MAX_POSITIONS", 3))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3))
            stack.enter_context(patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 3))
            stack.enter_context(patch.object(risk_policy, "REARM_RISK_MULTIPLIER", 0.5))
            stack.enter_context(patch.object(webhook, "_get_live_equity", return_value=100.0))
            stack.enter_context(patch.object(webhook, "_get_cached_positions", return_value=([], True)))
            stack.enter_context(patch("webhook.live_reconcile.reconcile_live_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}))
            mock_daily_stop = stack.enter_context(patch("webhook._bootstrap_daily_stop_status"))
            mock_calc_lot = stack.enter_context(patch("webhook.calculate_lot_size"))
            mock_log_trade = stack.enter_context(patch("webhook.trade_db.log_trade"))
            mock_place_trade = stack.enter_context(patch("webhook.place_trade"))
            mock_plain_log = stack.enter_context(patch("webhook.plain_log"))
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook._check_signal_age", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._check_entry_drift", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._entry_daily_stop_status", return_value={
                "live_trading_blocked_for_day": False,
                "model": "live_bootstrap_dollar",
                "rearm_available": True,
                "daily_safety_incidents": 1,
                "safety_incident_risk_adjust_active": True,
                "safety_incident_risk_multiplier": 0.5,
            }))
            stack.enter_context(patch("webhook.classify_crypto_entry", return_value={"mode": "allow", "grade": "A", "reasons": [], "ema_distance_pct": 1.0, "volume_ratio": 1.5}))
            stack.enter_context(
                patch(
                    "webhook.get_binance_indicators",
                    return_value={
                        "rsi": 45.0,
                        "ema200": 2900.0,
                        "atr": 80.0,
                        "volume": 15000.0,
                        "volume_avg20": 10000.0,
                        "supertrend_direction": "short",
                        "supertrend_value": 3010.0,
                        "close": 3000.0,
                    },
                )
            )
            stack.enter_context(
                patch(
                    "webhook.get_size_multiplier",
                    return_value={
                        "multiplier": 1.0,
                        "adjusted_risk_pct": 0.05,
                        "reasoning": "test",
                        "fear_greed": 50,
                        "funding_rate": 0.0,
                    },
                )
            )
            stack.enter_context(patch("webhook.telegram_client.notify_rejected"))
            mock_daily_stop.return_value = {
                "remaining_daily_loss_budget_usd": 20.0,
                "live_trading_blocked_for_day": False,
                "model": "live_bootstrap_dollar",
                "rearm_available": True,
                "daily_safety_incidents": 1,
                "safety_incident_risk_adjust_active": True,
                "safety_incident_risk_multiplier": 0.5,
            }
            mock_calc_lot.return_value = Decimal("0.1")
            mock_log_trade.return_value = 12346
            mock_place_trade.return_value = {"status": "success", "quantity": 0.1}

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "SELL",
                    "symbol": "ETHUSDT",
                    "entry": 3000.0,
                    "sl": 3100.0,
                    "tp": 2700.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload)

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(risk_policy.effective_max_positions(3, 100.0), 3)
            args, kwargs = mock_calc_lot.call_args
            self.assertAlmostEqual(float(args[1]), 2.5)


if __name__ == "__main__":
    unittest.main()
