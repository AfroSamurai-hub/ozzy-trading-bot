import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live_reconcile


def protected_orders(symbol="ETHUSDT"):
    return [
        {"symbol": symbol, "type": "STOP_MARKET", "reduceOnly": True},
        {"symbol": symbol, "type": "TAKE_PROFIT_MARKET", "reduceOnly": True},
    ]


class LiveReconcileTests(unittest.TestCase):
    def test_exchange_position_without_open_db_trade_is_critical(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[{"symbol": "ETHUSDT"}],
            normal_orders=protected_orders(),
            algo_orders=[],
            db_open_trades=[],
            order_states=[],
        )

        self.assertFalse(result["healthy"])
        self.assertIn("exchange position ETHUSDT has no open DB trade", result["critical_mismatches"])

    def test_db_open_trade_without_exchange_position_is_warning(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[],
            normal_orders=[],
            algo_orders=[],
            db_open_trades=[{"symbol": "LINKUSDT"}],
            order_states=[],
        )

        self.assertTrue(result["healthy"])
        self.assertIn("DB open trade LINKUSDT has no exchange position", result["warnings"])

    def test_position_without_verified_stop_is_critical(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[{"symbol": "LINKUSDT"}],
            normal_orders=[{"symbol": "LINKUSDT", "type": "TAKE_PROFIT_MARKET", "reduceOnly": True}],
            algo_orders=[],
            db_open_trades=[{"symbol": "LINKUSDT"}],
            order_states=[],
        )

        self.assertFalse(result["healthy"])
        self.assertIn("missing protection SL=False TP=True", result["critical_mismatches"][0])

    def test_position_with_verified_stop_and_missing_tp_is_warning(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[{"symbol": "LINKUSDT"}],
            normal_orders=[{"symbol": "LINKUSDT", "type": "STOP_MARKET", "reduceOnly": True}],
            algo_orders=[],
            db_open_trades=[{"symbol": "LINKUSDT"}],
            order_states=[],
        )

        self.assertTrue(result["healthy"])
        self.assertIn("exchange position LINKUSDT missing TP while SL is verified", result["warnings"])

    def test_healthy_snapshot_accepts_algo_protection(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[{"symbol": "ETHUSDT"}],
            normal_orders=[],
            algo_orders=[
                {"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "reduceOnly": "true"},
                {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "closePosition": "true"},
            ],
            db_open_trades=[{"symbol": "ETHUSDT"}],
            order_states=[{"symbol": "ETHUSDT"}],
        )

        self.assertTrue(result["healthy"])
        self.assertEqual(result["algo_open_order_count"], 2)
        self.assertEqual(result["stale_algo_order_count"], 0)

    def test_stale_reduce_only_algo_protection_without_position_is_warning(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[],
            normal_orders=[],
            algo_orders=[
                {
                    "symbol": "ETHUSDT",
                    "algoId": "sl-1",
                    "orderType": "STOP_MARKET",
                    "reduceOnly": "true",
                }
            ],
            db_open_trades=[],
            order_states=[],
        )

        self.assertTrue(result["healthy"])
        self.assertEqual(result["algo_open_order_count"], 1)
        self.assertEqual(result["stale_algo_order_count"], 1)
        self.assertEqual(result["stale_algo_orders"][0]["severity"], "warning")
        self.assertIn("stale algo order ETHUSDT STOP_MARKET has no exchange position", result["warnings"])

    def test_stale_non_reduce_only_algo_order_without_position_is_critical(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[],
            normal_orders=[],
            algo_orders=[
                {
                    "symbol": "LINKUSDT",
                    "algoId": "entry-1",
                    "orderType": "STOP_MARKET",
                    "reduceOnly": False,
                }
            ],
            db_open_trades=[],
            order_states=[],
        )

        self.assertFalse(result["healthy"])
        self.assertEqual(result["algo_open_order_count"], 1)
        self.assertEqual(result["stale_algo_order_count"], 1)
        self.assertEqual(result["stale_algo_orders"][0]["severity"], "critical")
        self.assertIn(
            "unsafe stale algo order LINKUSDT STOP_MARKET has no exchange position",
            result["critical_mismatches"],
        )

    def test_stale_close_position_non_protection_algo_order_is_critical(self):
        result = live_reconcile.reconcile_snapshot(
            equity=34.0,
            positions=[],
            normal_orders=[],
            algo_orders=[
                {
                    "symbol": "ETHUSDT",
                    "algoId": "trail-1",
                    "orderType": "TRAILING_STOP_MARKET",
                    "closePosition": "true",
                }
            ],
            db_open_trades=[],
            order_states=[],
        )

        self.assertFalse(result["healthy"])
        self.assertEqual(result["stale_algo_orders"][0]["order_type"], "TRAILING_STOP_MARKET")
        self.assertEqual(result["stale_algo_orders"][0]["severity"], "critical")

    def test_fail_soft_timeout_uses_cached_authoritative_snapshot(self):
        cached = {
            "healthy": True,
            "equity_usd": 100.0,
            "critical_mismatches": [],
            "warnings": [],
            "positions": ["ETHUSDT"],
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
            "checked_at": "2026-06-15T00:00:00+00:00",
            "dry_run": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "live_reconcile_state.json"
            with (
                patch.object(live_reconcile, "RECONCILE_CACHE_PATH", cache_path),
                patch.object(live_reconcile, "_last_reconcile", cached),
                patch.object(live_reconcile, "get_balance", side_effect=TimeoutError("Binance API timeout")),
            ):
                result = live_reconcile.reconcile_live_state(dry_run=True, fail_soft=True)

        self.assertTrue(result["healthy"])
        self.assertTrue(result["reconciliation_is_stale"])
        self.assertEqual(result["positions"], ["ETHUSDT"])
        self.assertEqual(result["reconciliation_refresh_error"], "Binance API timeout")

    def test_fail_soft_timeout_without_cache_is_degraded_unknown_not_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "live_reconcile_state.json"
            with (
                patch.object(live_reconcile, "RECONCILE_CACHE_PATH", cache_path),
                patch.object(live_reconcile, "_last_reconcile", None),
                patch.object(live_reconcile, "get_balance", side_effect=TimeoutError("Binance API timeout")),
            ):
                result = live_reconcile.reconcile_live_state(dry_run=True, fail_soft=True)

        self.assertIsNone(result["healthy"])
        self.assertEqual(result["critical_mismatches"], [])
        self.assertTrue(result["data_unavailable"])
        self.assertTrue(result["transient_exchange_error"])

    def test_default_reconcile_still_fails_closed_on_timeout(self):
        with patch.object(live_reconcile, "get_balance", side_effect=TimeoutError("Binance API timeout")):
            result = live_reconcile.reconcile_live_state(dry_run=True)

        self.assertFalse(result["healthy"])
        self.assertIn("reconciliation unavailable", result["critical_mismatches"][0])


if __name__ == "__main__":
    unittest.main()
