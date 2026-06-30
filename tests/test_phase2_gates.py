import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import binance_connector
import live_gating
import trade_db
import webhook
from binance_connector import check_order_book_spread


class TimeoutClient:
    def futures_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": "100.0"}

    def futures_order_book(self, symbol, limit=5):
        raise TimeoutError("order book timed out")


class EmptyBookClient:
    def futures_order_book(self, symbol, limit=5):
        return {"bids": [], "asks": []}


class TickerClient:
    def __init__(self, price):
        self.price = price

    def futures_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": str(self.price)}


class Phase2GatesTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(trade_db, "DB_PATH", Path(self.tempdir.name) / "trades.db")
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_entry_spread_timeout_fails_closed_with_structured_reason(self):
        result = check_order_book_spread(TimeoutClient(), "ETHUSDT", is_entry=True)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "timeout")
        self.assertFalse(result.fail_open)
        self.assertEqual(tuple(result), (False, 0.0, 0.0, 0.0))

    def test_exit_spread_timeout_fails_open_with_structured_reason(self):
        result = check_order_book_spread(TimeoutClient(), "ETHUSDT", is_entry=False)

        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "timeout")
        self.assertTrue(result.fail_open)

    def test_entry_empty_order_book_fails_closed(self):
        result = check_order_book_spread(EmptyBookClient(), "ETHUSDT", is_entry=True)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "empty_order_book")

    @patch("binance_connector._get_client")
    @patch("binance_connector.get_balance")
    def test_execute_trade_blocks_when_entry_spread_check_times_out(self, mock_balance, mock_get_client):
        mock_get_client.return_value = TimeoutClient()
        mock_balance.return_value = {"equity": 500.0, "available": 500.0}

        with self.assertRaises(ValueError) as context:
            binance_connector._execute_trade("BUY", "ETHUSDT", 0.01, 50.0, 2.5)

        self.assertIn("entry spread check failed", str(context.exception))
        self.assertIn("timeout", str(context.exception))

    def test_buy_favorable_drift_is_allowed(self):
        result = webhook._check_entry_drift(
            client=TickerClient(99.80),
            symbol="ETHUSDT",
            signal="BUY",
            alert_price=100.0,
            max_drift_pct=0.15,
        )

        self.assertTrue(result["allowed"])
        self.assertFalse(result["adverse"])
        self.assertAlmostEqual(result["drift_pct"], 0.2)

    def test_buy_adverse_drift_is_blocked(self):
        result = webhook._check_entry_drift(
            client=TickerClient(100.20),
            symbol="ETHUSDT",
            signal="BUY",
            alert_price=100.0,
            max_drift_pct=0.15,
        )

        self.assertFalse(result["allowed"])
        self.assertTrue(result["adverse"])
        self.assertEqual(result["reason"], "adverse_entry_drift_exceeded")

    def test_sell_favorable_drift_is_allowed(self):
        result = webhook._check_entry_drift(
            client=TickerClient(100.20),
            symbol="ETHUSDT",
            signal="SELL",
            alert_price=100.0,
            max_drift_pct=0.15,
        )

        self.assertTrue(result["allowed"])
        self.assertFalse(result["adverse"])

    def test_sell_adverse_drift_is_blocked(self):
        result = webhook._check_entry_drift(
            client=TickerClient(99.80),
            symbol="ETHUSDT",
            signal="SELL",
            alert_price=100.0,
            max_drift_pct=0.15,
        )

        self.assertFalse(result["allowed"])
        self.assertTrue(result["adverse"])
        self.assertEqual(result["reason"], "adverse_entry_drift_exceeded")

    def test_signal_age_expiration_blocks_old_alert(self):
        result = webhook._check_signal_age(time.time() - 120, max_age_seconds=90)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "signal_too_old")

    def test_signal_age_allows_fresh_millisecond_timestamp(self):
        now = time.time()
        result = webhook._check_signal_age((now - 30) * 1000, max_age_seconds=90, now=now)

        self.assertTrue(result["allowed"])
        self.assertLess(result["age_seconds"], 31)

    def test_trade_db_strategy_filter_returns_normalized_r_stats(self):
        for strategy, pnl in [("momentum", -10.0), ("momentum", 20.0), ("pullback", 100.0)]:
            trade_id = trade_db.log_trade(
                signal_id=None,
                symbol="ETHUSDT",
                direction="BUY",
                entry_price=100.0,
                strategy=strategy,
                setup_grade="A",
                risk_dollars=10.0,
            )
            with trade_db._connect() as conn:
                conn.execute(
                    "UPDATE trades SET exit_price = ?, pnl = ? WHERE id = ?",
                    (110.0, pnl, trade_id),
                )
                conn.commit()

        stats = trade_db.get_recent_closed_trade_stats(
            symbol="ETHUSDT",
            direction="BUY",
            setup_grade="A",
            strategy="momentum",
            limit=10,
        )

        self.assertEqual(stats["sample_size"], 2)
        self.assertEqual(stats["r_sample_size"], 2)
        self.assertAlmostEqual(stats["total_r"], 1.0)
        self.assertAlmostEqual(stats["avg_r"], 0.5)

    def test_precise_lane_block_uses_normalized_r_and_shadow_recovery_threshold(self):
        for _ in range(3):
            trade_id = trade_db.log_trade(
                signal_id=None,
                symbol="ETHUSDT",
                direction="BUY",
                entry_price=100.0,
                strategy="momentum",
                setup_grade="A",
                risk_dollars=10.0,
            )
            with trade_db._connect() as conn:
                conn.execute(
                    "UPDATE trades SET exit_price = ?, pnl = ?, r_multiple = ? WHERE id = ?",
                    (95.0, -10.0, -1.0, trade_id),
                )
                conn.commit()

        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating, "LANE_BLOCK_MIN_TRADES", 3),
            patch.object(live_gating, "LANE_BLOCK_AVG_R_FLOOR", -0.35),
            patch.object(live_gating, "LANE_BLOCK_TOTAL_R_FLOOR", -2.0),
            patch.object(live_gating, "LANE_BLOCK_RECOVERY_SHADOW_SAMPLES", 2),
            patch.object(live_gating, "LANE_BLOCK_RECOVERY_AVG_R", 0.2),
        ):
            decision = live_gating.evaluate_precise_lane_block("ETHUSDT", "BUY", "A", "momentum")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "blocked")
        self.assertEqual(decision.details["lane_key"], "ETHUSDT|BUY|A|momentum")
        self.assertEqual(decision.details["block_thresholds"]["recovery_shadow_samples"], 2)


if __name__ == "__main__":
    unittest.main()
