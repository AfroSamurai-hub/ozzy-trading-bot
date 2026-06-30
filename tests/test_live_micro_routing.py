import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path
import os
import json
from contextlib import ExitStack

import webhook
import config
import trade_db
import risk_policy
from dynamic_config import get_param


class LiveMicroRoutingTests(unittest.TestCase):
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

    def tearDown(self):
        self.reconcile_patch.stop()
        self.lane_patch.stop()
        self.drift_patch.stop()
        self.client_patch.stop()
        self.monitor_patch.stop()
        self.halt_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_ethusdt_live_micro_signal_allowed_when_safety_passes(self):
        """Test that ETHUSDT live micro signal passes symbol routing and reaches trade placement when all safety gates pass."""
        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True))
            stack.enter_context(patch.object(webhook, "BINANCE_FUTURES_MODE", True))
            stack.enter_context(patch.object(webhook, "PAPER_MODE", False))
            stack.enter_context(patch.object(webhook, "BINANCE_TESTNET", False))
            stack.enter_context(patch.object(webhook, "_get_live_equity", return_value=34.40))
            stack.enter_context(patch.object(webhook, "_get_cached_positions", return_value=([], True)))
            # Mock dynamic config active_symbols
            stack.enter_context(patch("dynamic_config.get_param", side_effect=lambda key, default: 
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT"] if key == "active_symbols" else default
            ))
            # Mock all safety gates
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook._check_signal_age", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._check_entry_drift", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}))
            stack.enter_context(patch("webhook.telegram_client.notify_rejected"))
            stack.enter_context(patch("webhook.live_reconcile.reconcile_live_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}))
            stack.enter_context(patch("webhook.live_reconcile.get_last_reconcile_state", return_value={"healthy": True, "critical_mismatches": [], "warnings": []}))
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
            # Mock the entry policy so strategy thresholds don't block
            stack.enter_context(patch("webhook.classify_crypto_entry", return_value={"mode": "allow", "grade": "A", "reasons": [], "ema_distance_pct": 1.0, "volume_ratio": 1.5}))
            # Mock the place_trade execution at the end so it returns a filled status
            stack.enter_context(patch("webhook.place_trade", return_value={"status": "filled", "orderId": 12345, "exec_price": 3000.0, "quantity": 0.01}))
            # Mock other external check or database state
            stack.enter_context(patch("webhook.is_trading_allowed", return_value=True))
            stack.enter_context(patch("webhook.NEWS_PAUSE", False))
            # Ensure trade_db.log_trade doesn't break
            stack.enter_context(patch("trade_db.log_trade", return_value=123))
            stack.enter_context(patch("trade_db.update_execution_state"))

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "SELL",  # SELL is allowed for ETH (BUY is blocked by ETH_LONG_BLOCKED)
                    "symbol": "ETHUSDT",
                    "entry": 3000.0,
                    "sl": 3100.0,
                    "tp": 2700.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                # Verify that it didn't reject due to symbol routing, and was placed successfully!
                self.assertEqual(data.get("status"), "approved")

    def test_disabled_exness_route_does_not_block_binance_route(self):
        """Test that disabled Exness route (e.g. XAUUSD) is blocked, but valid Binance route (e.g. ETHUSDT) is not."""
        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True))
            stack.enter_context(patch.object(webhook, "BINANCE_FUTURES_MODE", True))
            stack.enter_context(patch("dynamic_config.get_param", side_effect=lambda key, default: 
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT"] if key == "active_symbols" else default
            ))
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook.telegram_client.notify_rejected"))
            stack.enter_context(patch("webhook._check_signal_age", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._check_entry_drift", return_value={"allowed": True}))

            with webhook.app.test_client() as client:
                # 1. Exness-only symbol XAUUSD should be blocked with "Exness on hold" message
                payload_exness = {
                    "secret": "test_secret",
                    "signal": "SELL",
                    "symbol": "XAUUSD",
                    "entry": 2000.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload_exness)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["status"], "rejected")
                self.assertIn("disabled — Exness on hold, Binance-only routing active", data["reason"])

                # 2. Binance symbol ETHUSDT is not blocked by the Exness routing logic itself (it will proceed past it)
                # We can verify it bypasses the symbol routing block (we can check that the reason is NOT "Exness on hold")
                payload_binance = {
                    "secret": "test_secret",
                    "signal": "BUY",  # Let it get blocked by subsequent ETH_LONG_BLOCKED to show it passed routing!
                    "symbol": "ETHUSDT",
                    "entry": 3000.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload_binance)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["status"], "rejected")
                # Assert that it bypassed symbol routing check and reached the ETH Long blocker gate!
                self.assertEqual(data["reason"], "ETH_LONG_BLOCKED")

    def test_unknown_symbols_still_rejected(self):
        """Test that completely unknown or inactive symbols are still rejected."""
        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", True))
            stack.enter_context(patch.object(webhook, "BINANCE_FUTURES_MODE", True))
            stack.enter_context(patch("dynamic_config.get_param", side_effect=lambda key, default: 
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT"] if key == "active_symbols" else default
            ))
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook.telegram_client.notify_rejected"))

            with webhook.app.test_client() as client:
                # Completely unknown symbol not in ASSETS
                payload_unknown = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "UNKNOWNUSDT",
                    "entry": 1.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload_unknown)
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertEqual(data["status"], "error")
                self.assertIn("missing from ASSETS config", data["reason"])

                # Known in ASSETS but not active in dynamic config (e.g. NEARUSDT)
                payload_inactive = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "NEARUSDT",
                    "entry": 5.0,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload_inactive)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["status"], "rejected")
                self.assertIn("disabled — Exness on hold, Binance-only routing active", data["reason"])

    def test_standard_testnet_unchanged(self):
        """Test that STANDARD_TESTNET mode continues to function normally with standard symbol lists and logic."""
        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", False)) # STANDARD_TESTNET
            stack.enter_context(patch.object(webhook, "BINANCE_FUTURES_MODE", True))
            stack.enter_context(patch.object(webhook, "ALLOW_PYRAMIDING", False))
            stack.enter_context(patch.object(webhook, "_get_live_equity", return_value=10000.0))
            stack.enter_context(patch.object(webhook, "_get_cached_positions", return_value=([
                {"symbol": "NEARUSDT", "type": "BUY", "profit": "1.0", "openPrice": "5.0"}
            ], True)))
            # active symbols for standard testnet includes NEARUSDT
            stack.enter_context(patch("dynamic_config.get_param", side_effect=lambda key, default: 
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LINKUSDT", "HYPEUSDT", "NEARUSDT"] if key == "active_symbols" else default
            ))
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook._check_signal_age", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._check_entry_drift", return_value={"allowed": True}))
            stack.enter_context(patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}))
            mock_notify = stack.enter_context(patch("webhook.telegram_client.notify_rejected"))

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "BUY",
                    "symbol": "NEARUSDT",
                    "entry": 5.0,
                    "sl": 4.8,
                    "tp": 5.5,
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["status"], "rejected")
                # Standard testnet duplicate rejection message
                self.assertEqual(data["reason"], "Position already open for NEARUSDT")
                mock_notify.assert_called_with("Position already open for NEARUSDT", "NEARUSDT", "BUY")


if __name__ == "__main__":
    unittest.main()
