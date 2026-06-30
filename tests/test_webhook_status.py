import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import dynamic_config
import logger
import webhook


class WebhookStatusTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.log_patch = patch.object(logger, "LOG_FILE", Path(self.tempdir.name) / "trades.log")
        self.log_patch.start()

    def tearDown(self):
        self.log_patch.stop()
        self.tempdir.cleanup()

    def test_module_import_does_not_start_runtime_cache_thread(self):
        self.assertIsNone(webhook._cache_thread)

    def test_status_exposes_execution_mode_and_risk_fields(self):
        with webhook.app.test_client() as client:
            resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("backend", data)
        self.assertIn("binance_testnet", data)
        self.assertIn("risk_pct", data)
        self.assertIn("effective_max_positions", data)
        self.assertIn("micro_bootstrap_mode", data)
        self.assertIn("micro_bootstrap_active", data)
        self.assertIn("micro_bootstrap_risk_usd", data)
        self.assertIn("micro_bootstrap_equity_ceiling_usd", data)
        self.assertIn("micro_bootstrap_max_positions", data)
        self.assertIn("data_driven_live_gating", data)
        self.assertIn("data_gating_db", data)
        self.assertIn("grade_health", data)
        self.assertIn("symbol_heat", data)
        self.assertIn("red_max_avg_pnl", data["grade_health"])
        self.assertIn("red_max_avg_pnl", data["symbol_heat"])
        self.assertIn("live_min_opportunity", data)
        self.assertIn("gemini_advisor", data)
        self.assertFalse(data["gemini_advisor"]["broker_actions_allowed"])
        self.assertIn("protection_truth_required", data)
        self.assertIn("post_fill_protection_finalizer", data)
        self.assertEqual(data["post_fill_protection_finalizer"]["testnet_mode"], "repair")
        self.assertEqual(data["post_fill_protection_finalizer"]["live_mode"], "repair")
        self.assertIn("daily_drawdown_limit", data)
        self.assertIn("daily_drawdown_enabled", data)
        self.assertIn("monitor_gate", data)
        self.assertIn("max_positions", data)
        self.assertIn("max_positions_per_symbol", data)
        self.assertIn("small_cap_launch_mode", data)
        self.assertIn("doge_shadow_only", data)
        self.assertIn("active_symbols", data)
        self.assertIn("cache_age_seconds", data)
        self.assertIn("risk", data)
        self.assertIn("daily_stop", data)
        self.assertIn("target_loss_at_sl_usd", data["risk"])
        self.assertIn("effective_risk_usd", data["risk"])
        self.assertIn("model", data["daily_stop"])
        self.assertIn("reconciliation", data)
        self.assertIn("stale_algo_order_count", data["reconciliation"])
        self.assertIn("stale_algo_orders", data["reconciliation"])
        self.assertIn("product_sync_health", data)
        self.assertIn("memory_sync", data)
        self.assertIn("scanner_state", data)

    def test_testnet_daily_drawdown_gate_defaults_disabled(self):
        with patch.object(webhook, "BINANCE_TESTNET", True), patch.object(webhook, "DAILY_DRAWDOWN_ENABLED", False):
            status = webhook._entry_daily_stop_status()

        self.assertEqual(status["model"], "percentage_drawdown_disabled")
        self.assertFalse(status["live_trading_blocked_for_day"])
        self.assertFalse(status["enabled"])

    def test_status_exposes_bootstrap_rearm_state(self):
        with webhook.app.test_client() as client:
            data = client.get("/status").get_json()

        for key in (
            "daily_strategy_full_losses",
            "daily_safety_incidents",
            "daily_realized_loss_usd",
            "live_paused_for_safety",
            "live_blocked_for_day",
            "rearm_available",
            "rearm_used_count",
        ):
            self.assertIn(key, data)
            self.assertIn(key, data["daily_stop"])
        self.assertIn("rearm_risk_multiplier", data["daily_stop"])

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_daily_block_reasons_appear_in_status(self, mock_get_last, mock_reconcile_live):
        mock_get_last.return_value = {
            "healthy": True,
            "checked_at": None,
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        mock_reconcile_live.return_value = mock_get_last.return_value
        daily_stop = {
            "model": "micro_bootstrap",
            "live_trading_blocked_for_day": True,
            "live_blocked_for_day": True,
            "reason": "daily realised-loss cap breached",
        }
        with (
            patch.object(webhook, "_bootstrap_daily_stop_status", return_value=daily_stop),
            patch.object(webhook, "binance_get_positions", return_value=[]),
        ):
            with webhook.app.test_client() as client:
                data = client.get("/status").get_json()

        live_micro = data["live_micro"]
        self.assertFalse(live_micro["new_entries_enabled"])
        self.assertFalse(live_micro["no_new_entries_flag"])
        self.assertTrue(live_micro["daily_block_active"])
        self.assertFalse(live_micro["live_auto_protect_enabled"])
        self.assertIn("daily realised-loss cap breached", live_micro["entry_block_reasons"])

    def test_status_exposes_testnet_auto_protect_simulation_availability(self):
        with patch("status_summary.Path.glob", return_value=[Path("reports/auto_protect_simulation_20260602.md")]):
            with webhook.app.test_client() as client:
                data = client.get("/status").get_json()

        self.assertTrue(data["testnet"]["auto_protect_simulation_available"])
        self.assertIn("auto_protect_enabled", data["testnet"])
        self.assertIn("auto_protect_dry_run", data["testnet"])
        self.assertIn("recent_auto_protect_actions", data["testnet"])

    def test_status_exposes_recent_auto_protect_actions_and_live_hard_false(self):
        fake_actions = [
            {"action_id": f"a{i}", "created_at": f"2026-06-02T0{i}:00:00+00:00", "symbol": "ETHUSDT"}
            for i in range(7)
        ]
        with patch("status_summary.recent_auto_protect_actions", return_value=fake_actions[:5]):
            with webhook.app.test_client() as client:
                data = client.get("/status").get_json()

        self.assertEqual(len(data["testnet"]["recent_auto_protect_actions"]), 5)
        self.assertFalse(data["live_micro"]["live_auto_protect_enabled"])

    def test_live_status_does_not_show_testnet_recent_actions(self):
        with (
            patch.object(webhook, "BINANCE_TESTNET", False),
            patch.object(webhook, "get_execution_mode", return_value="LIVE"),
            patch("status_summary.recent_auto_protect_actions", return_value=[]),
        ):
            with webhook.app.test_client() as client:
                data = client.get("/status").get_json()

        self.assertEqual(data["execution_mode"], "LIVE")
        self.assertEqual(data["testnet"]["recent_auto_protect_actions"], [])

    def test_research_symbols_available_in_default_status(self):
        testnet_config = Path(__file__).resolve().parents[1] / "config" / "dynamic_config_testnet.json"
        with patch.dict(os.environ, {"HERMES_DYNAMIC_CONFIG": str(testnet_config)}):
            dynamic_config._CACHE = {}
            dynamic_config._LAST_LOADED_TIME = 0.0
            dynamic_config._LAST_MTIME = 0.0
            with webhook.app.test_client() as client:
                resp = client.get("/status")
        data = resp.get_json()
        self.assertIn("SUIUSDT", data["active_symbols"])
        self.assertIn("HYPEUSDT", data["active_symbols"])
        self.assertIn("WLDUSDT", data["active_symbols"])
        self.assertIn("ZECUSDT", data["active_symbols"])
        self.assertIn("DRIFTUSDT", data["active_symbols"])
        self.assertIn("INJUSDT", data["active_symbols"])

    def test_startup_mode_check_fails_closed_when_credentials_missing(self):
        with patch.object(webhook, "validate_binance_credentials", return_value=(False, "missing")):
            self.assertFalse(webhook._startup_mode_check())

    def test_trade_router_returns_binance_execution_result(self):
        expected = {"symbol": "LINKUSDT", "quantity": 31.33}
        with patch.object(webhook, "binance_place_trade", return_value=expected):
            result = webhook.place_trade("SELL", "LINKUSDT", 31.33, 0.15, 2.5)

        self.assertEqual(result, expected)

    def test_monitor_entry_gate_fails_closed_when_service_inactive(self):
        inactive = {
            "allowed": False,
            "reason": "monitor_not_active",
            "service": "ozzybot-live-micro-monitor.service",
            "active_state": "inactive",
        }
        original_exists = os.path.exists
        with (
            patch("webhook.WEBHOOK_SECRET", "test_secret"),
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "BINANCE_FUTURES_MODE", True),
            patch(
                "webhook.os.path.exists",
                side_effect=lambda path: False if str(path) == webhook.HALT_FILE else original_exists(path),
            ),
            patch.object(webhook, "_monitor_entry_gate_status", return_value=inactive),
            patch.object(webhook, "_get_live_equity", return_value=10000.0),
            patch.object(webhook, "_get_cached_positions", return_value=([], True)),
            patch("dynamic_config.get_param", side_effect=lambda key, default: ["BTCUSDT"] if key == "active_symbols" else default),
            patch("webhook.validate_signal_payload", return_value=(True, [])),
            patch("webhook._check_signal_age", return_value={"allowed": True}),
            patch("webhook._check_entry_drift", return_value={"allowed": True}),
            patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False, "model": "test"}),
            patch("webhook.telegram_client.notify_rejected") as notify_rejected,
        ):
            with webhook.app.test_client() as client:
                resp = client.post(
                    "/webhook",
                    json={
                        "secret": "test_secret",
                        "signal": "SELL",
                        "symbol": "BTCUSDT",
                        "entry": 50000.0,
                        "timestamp": 1779613507000,
                        "source": "signal_generator",
                    },
                )

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["reason"], "monitor not running")
        notify_rejected.assert_called_once()

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_status_exposes_monitor_gate_blocker(self, mock_get_last, mock_reconcile_live):
        inactive = {
            "allowed": False,
            "reason": "monitor_not_active",
            "service": "ozzybot-live-micro-monitor.service",
            "active_state": "inactive",
        }
        mock_get_last.return_value = {
            "healthy": True,
            "checked_at": None,
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        mock_reconcile_live.return_value = mock_get_last.return_value
        with (
            patch.object(webhook, "_monitor_entry_gate_status", return_value=inactive),
            patch.object(webhook, "binance_get_positions", return_value=[]),
        ):
            with webhook.app.test_client() as client:
                data = client.get("/status").get_json()

        self.assertEqual(data["monitor_gate"], inactive)
        self.assertTrue(data["scanner_state"]["entries_blocked"])
        self.assertIn("monitor gate: monitor_not_active", data["scanner_state"]["entry_block_reasons"])

    def test_daily_trade_count_uses_runtime_trade_db_not_log_events(self):
        with patch.object(webhook.trade_db, "count_trades_opened_today_sast", return_value=3) as count_rows:
            self.assertEqual(webhook._count_trades_logged_today_sast(), 3)

        count_rows.assert_called_once_with()

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_status_reconciliation_fresh_cache(self, mock_get_last, mock_reconcile_live):
        """Test that /status does not refresh reconciliation if checked_at is under 30 seconds old."""
        from datetime import datetime, UTC

        mock_get_last.return_value = {
            "healthy": True,
            "checked_at": datetime.now(UTC).isoformat(),
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        with webhook.app.test_client() as client:
            resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        mock_reconcile_live.assert_not_called()

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_status_reconciliation_stale_cache(self, mock_get_last, mock_reconcile_live):
        """Test that /status refreshes reconciliation if checked_at is >= 30 seconds old."""
        from datetime import datetime, UTC, timedelta

        mock_get_last.return_value = {
            "healthy": True,
            "checked_at": (datetime.now(UTC) - timedelta(seconds=35)).isoformat(),
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        mock_reconcile_live.return_value = {
            "healthy": True,
            "checked_at": datetime.now(UTC).isoformat(),
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        with webhook.app.test_client() as client:
            resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        mock_reconcile_live.assert_called_once()

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_status_reconciliation_missing_checked_at(self, mock_get_last, mock_reconcile_live):
        """Test that /status refreshes reconciliation if checked_at is missing."""
        from datetime import datetime, UTC

        mock_get_last.return_value = {
            "healthy": True,
            "checked_at": None,
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        mock_reconcile_live.return_value = {
            "healthy": True,
            "checked_at": datetime.now(UTC).isoformat(),
            "stale_algo_order_count": 0,
            "stale_algo_orders": [],
        }
        with webhook.app.test_client() as client:
            resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        mock_reconcile_live.assert_called_once()

    @patch("live_reconcile.reconcile_live_state")
    @patch("live_reconcile.get_last_reconcile_state")
    def test_status_reconciliation_refresh_failure_fallback(self, mock_get_last, mock_reconcile_live):
        """Test that /status fails soft and returns cached state with error context on refresh exception."""
        from datetime import datetime, UTC

        cached_state = {
            "healthy": True,
            "checked_at": None,
            "stale_algo_order_count": 2,
            "stale_algo_orders": ["order1", "order2"],
        }
        mock_get_last.return_value = cached_state
        mock_reconcile_live.side_effect = RuntimeError("Binance API timeout")

        with webhook.app.test_client() as client:
            resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertIn("reconciliation", data)
        recon = data["reconciliation"]
        self.assertEqual(recon["stale_algo_order_count"], 2)
        self.assertTrue(recon.get("reconciliation_is_stale"))
        self.assertEqual(recon.get("reconciliation_refresh_error"), "Binance API timeout")


if __name__ == "__main__":
    unittest.main()
