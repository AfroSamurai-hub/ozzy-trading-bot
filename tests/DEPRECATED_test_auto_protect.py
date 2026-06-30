import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import binance_monitor


def _trade_row(*, setup_grade="A", direction="BUY", risk_dollars=100.0):
    return {
        "id": 123,
        "symbol": "HYPEUSDT",
        "direction": direction,
        "setup_grade": setup_grade,
        "risk_dollars": risk_dollars,
        "qty": 10.0,
        "entry_price": 100.0,
        "sl": 95.0,
        "exit_price": None,
        "execution_state": "open",
    }


def _position(*, current_price=96.0, side="BUY"):
    return {
        "symbol": "HYPEUSDT",
        "tv_symbol": "HYPEUSDT",
        "type": side,
        "openPrice": 100.0,
        "currentPrice": current_price,
        "volume": 10.0,
        "profit": -40.0,
    }


class TestnetAutoProtectExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.observer_dir = Path(self.tmp.name)
        self.actions_path = self.observer_dir / "auto_protect_actions.json"
        state = binance_monitor._get_state("HYPEUSDT")
        state.clear()
        state.update({"trade_id": 123, "peak_pnl": 0.0, "_peak_r": 0.0, "entry_price": 100.0})

    def tearDown(self):
        binance_monitor._position_state.clear()
        binance_monitor._adaptive_profile_cache.clear()
        binance_monitor._adaptive_profile_cache.update({"loaded_at": 0.0, "profile": None})
        self.tmp.cleanup()

    def _run(
        self,
        *,
        env: dict,
        trade=None,
        safe_detail=None,
        position=None,
        enabled=True,
        dry_run=True,
        forced_decision=None,
    ):
        trade = trade or _trade_row()
        position = position or _position()
        safe_detail = safe_detail or {"exchange_qty": 10.0, "side": position["type"], "trade": trade}
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", enabled))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", dry_run))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_trade_open_age_hours", return_value=3.0))
            stack.enter_context(patch.object(binance_monitor, "_roundtrip_guard_safe_context", return_value=(True, safe_detail)))
            if forced_decision is not None:
                stack.enter_context(patch.object(binance_monitor, "_auto_protect_rule", return_value=forced_decision))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "partial_closed"}))
            refresh = stack.enter_context(patch.object(binance_monitor, "_refresh_remaining_protection_after_partial", return_value=True))
            stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))
            binance_monitor._check_testnet_auto_protect(position)
        return close_qty, refresh

    def test_live_mode_refuses_execution(self):
        close_qty, refresh = self._run(
            env={"HERMES_INSTANCE_NAME": "LIVE MICRO"},
            forced_decision=("roundtrip_winner", "PROTECT"),
        )
        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["reason"], "live_mode_alert_only")
        self.assertEqual(rows[0]["live_behavior"], "alert_only")

    def test_webhook_5001_refuses_execution(self):
        close_qty, refresh = self._run(
            env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET", "WEBHOOK_PORT": "5001"},
            forced_decision=("roundtrip_winner", "PROTECT"),
        )
        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["reason"], "webhook_port_5001_refused")

    def test_flag_disabled_reports_only(self):
        close_qty, refresh = self._run(
            env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"},
            enabled=False,
            dry_run=True,
            forced_decision=("roundtrip_winner", "PROTECT"),
        )
        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["reason"], "testnet_auto_protect_disabled_report_only")

    def test_dry_run_true_does_not_call_order_connector(self):
        with patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", True):
            close_qty, refresh = self._run(
                env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"},
                forced_decision=("roundtrip_winner", "PROTECT"),
            )
        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertTrue(rows[0]["dry_run"])
        self.assertFalse(rows[0]["executed"])

    def test_grade_b_no_progress_creates_exit_required(self):
        trade = _trade_row(setup_grade="B")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 10.0
        state["_peak_r"] = 0.1
        self._run(env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, trade=trade, position=_position(current_price=96.0))
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["intended_action"], "EXIT_REQUIRED")
        self.assertEqual(rows[0]["rule"], "grade_b_no_progress")

    def test_roundtrip_winner_creates_protect_not_full_close(self):
        trade = _trade_row(setup_grade="A")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 40.0
        state["_peak_r"] = 0.4
        self._run(env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, trade=trade, position=_position(current_price=99.5))
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["intended_action"], "PROTECT")

    def test_recent_successful_protect_refresh_is_idempotent(self):
        trade = _trade_row(setup_grade="A")
        position = _position(current_price=99.5)
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 40.0
        state["_peak_r"] = 0.4
        self.actions_path.write_text(
            json.dumps(
                [
                    {
                        "action_id": "previous-protect",
                        "created_at": "2026-06-03T10:00:00+00:00",
                        "mode": "TESTNET",
                        "instance": "STANDARD_TESTNET",
                        "symbol": "HYPEUSDT",
                        "side": "BUY",
                        "trade_id": 123,
                        "rule": "roundtrip_winner",
                        "intended_action": "PROTECT",
                        "executed": True,
                        "reason": "protection_refreshed",
                    }
                ]
            )
        )

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_trade_open_age_hours", return_value=3.0))
            stack.enter_context(
                patch.object(
                    binance_monitor,
                    "_roundtrip_guard_safe_context",
                    return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade}),
                )
            )
            stack.enter_context(
                patch.object(binance_monitor, "_auto_protect_rule", return_value=("roundtrip_winner", "PROTECT"))
            )
            stack.enter_context(patch.object(binance_monitor, "_action_age_seconds", return_value=60.0))
            refresh = stack.enter_context(patch.object(binance_monitor, "_refresh_remaining_protection_after_partial"))
            send = stack.enter_context(patch.object(binance_monitor, "_send_telegram"))
            log = stack.enter_context(patch.object(binance_monitor, "plain_log"))

            binance_monitor._check_testnet_auto_protect(position)

        refresh.assert_not_called()
        send.assert_not_called()
        self.assertTrue(any(call.args[0] == "AUTO_PROTECT_PROTECT_COOLDOWN" for call in log.call_args_list))
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "previous-protect")

    def test_strong_roundtrip_creates_reduce_risk(self):
        trade = _trade_row(setup_grade="A")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 60.0
        state["_peak_r"] = 0.6
        self._run(env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, trade=trade, position=_position(current_price=99.0))
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["intended_action"], "REDUCE_RISK")

    def test_recent_reduce_risk_action_suppresses_retry(self):
        self.actions_path.write_text(
            json.dumps(
                [
                    {
                        "action_id": "previous-reduce",
                        "created_at": "2099-06-03T10:00:00+00:00",
                        "mode": "TESTNET",
                        "instance": "STANDARD_TESTNET",
                        "symbol": "HYPEUSDT",
                        "side": "BUY",
                        "trade_id": 123,
                        "rule": "strong_roundtrip",
                        "intended_action": "REDUCE_RISK",
                        "executed": False,
                        "reason": "error",
                    }
                ]
            )
        )
        trade = _trade_row(setup_grade="A")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 60.0
        state["_peak_r"] = 0.6

        close_qty, refresh = self._run(
            env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"},
            trade=trade,
            position=_position(current_price=99.0),
            enabled=True,
            dry_run=False,
            forced_decision=("strong_roundtrip", "REDUCE_RISK"),
        )

        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "previous-reduce")

    def test_severe_roundtrip_creates_exit_required(self):
        trade = _trade_row(setup_grade="A")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 90.0
        state["_peak_r"] = 0.9
        self._run(env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, trade=trade, position=_position(current_price=99.8))
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["intended_action"], "EXIT_REQUIRED")
        self.assertEqual(rows[0]["rule"], "severe_roundtrip")

    def test_hedge_mode_close_reduce_requires_position_side_and_no_reduce_only_payload(self):
        trade = _trade_row(setup_grade="A")
        state = binance_monitor._get_state("HYPEUSDT")
        state["peak_pnl"] = 60.0
        state["_peak_r"] = 0.6
        close_qty, _ = self._run(
            env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"},
            trade=trade,
            position=_position(current_price=99.0),
            enabled=True,
            dry_run=False,
        )
        close_qty.assert_called_once()
        call = close_qty.call_args
        self.assertIn("position_side", call.kwargs)
        self.assertIn(call.kwargs["position_side"], {"LONG", "SHORT"})
        self.assertNotIn("reduceOnly", call.kwargs)

    def test_action_log_is_written(self):
        self._run(
            env={"HERMES_INSTANCE_NAME": "STANDARD TESTNET"},
            forced_decision=("roundtrip_winner", "PROTECT"),
        )
        self.assertTrue(self.actions_path.exists())
        rows = json.loads(self.actions_path.read_text())
        self.assertGreaterEqual(len(rows), 1)

    def test_auto_protect_heartbeat_logs_disabled_state(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", False))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", False))
            stack.enter_context(patch.object(binance_monitor, "LIVE_AUTO_PROTECT_ENABLED", False))
            log = stack.enter_context(patch.object(binance_monitor, "plain_log"))

            binance_monitor._log_auto_protect_heartbeat(open_positions=2, candidates_created=0)

        log.assert_called_once()
        event, payload = log.call_args.args
        self.assertEqual(event, "AUTO_PROTECT_HEARTBEAT")
        self.assertEqual(payload["mode"], "TESTNET")
        self.assertTrue(payload["binance_testnet"])
        self.assertFalse(payload["enabled"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["cash_ratchet_enabled"])
        self.assertFalse(payload["live_auto_protect_enabled"])
        self.assertEqual(payload["open_positions"], 2)
        self.assertEqual(payload["candidates_created"], 0)
        self.assertEqual(payload["reason"], "testnet_auto_protect_disabled")

    def test_auto_protect_heartbeat_logs_enabled_state(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "LIVE_AUTO_PROTECT_ENABLED", False))
            log = stack.enter_context(patch.object(binance_monitor, "plain_log"))

            binance_monitor._log_auto_protect_heartbeat(open_positions=3, candidates_created=1)

        log.assert_called_once()
        event, payload = log.call_args.args
        self.assertEqual(event, "AUTO_PROTECT_HEARTBEAT")
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["cash_ratchet_enabled"])
        self.assertEqual(payload["open_positions"], 3)
        self.assertEqual(payload["candidates_created"], 1)
        self.assertIsNone(payload["reason"])

    def test_cash_ratchet_dry_run_creates_candidate_without_order_call(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.6)
        position["profit"] = 26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", True))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_roundtrip_guard_safe_context", return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade})))
            stack.enter_context(patch.object(binance_monitor, "plain_log"))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "partial_closed"}))
            refresh = stack.enter_context(patch.object(binance_monitor, "_refresh_remaining_protection_after_partial", return_value=True))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_not_called()
        refresh.assert_not_called()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["rule"], "cash_ratchet_025r")
        self.assertEqual(rows[0]["intended_action"], "CASH_RATCHET_PARTIAL")
        self.assertTrue(rows[0]["dry_run"])
        self.assertFalse(rows[0]["executed"])
        self.assertEqual(rows[0]["reason"], "dry_run_enabled")

    def test_cash_ratchet_below_first_tier_does_not_log(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.4)
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_not_called()
        self.assertFalse(self.actions_path.exists())

    def test_cash_ratchet_execution_uses_position_side_and_no_reduce_only(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.6)
        position["profit"] = 26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_roundtrip_guard_safe_context", return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade})))
            stack.enter_context(patch.object(binance_monitor, "plain_log"))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "partial_closed"}))
            stack.enter_context(patch.object(binance_monitor, "_refresh_remaining_protection_after_partial", return_value=True))
            stack.enter_context(patch.object(binance_monitor, "_verify_post_action_state", return_value={"ok": True, "remaining_qty": 8.0}))
            stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_called_once()
        call = close_qty.call_args
        self.assertEqual(call.kwargs["position_side"], "LONG")
        self.assertNotIn("reduceOnly", call.kwargs)
        rows = json.loads(self.actions_path.read_text())
        self.assertTrue(rows[0]["executed"])
        self.assertEqual(rows[0]["close_qty"], 2.0)

    def test_adaptive_cash_ratchet_adds_earlier_tier_after_green_to_red_behavior(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=101.6)
        position["profit"] = 16.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        adaptive = {
            "enabled": True,
            "symbol": "HYPEUSDT",
            "tighten_cash_ratchet": True,
            "tighten_no_progress": False,
            "reason": "symbol_green_to_red=1",
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_adaptive_symbol_decision", return_value=adaptive))
            stack.enter_context(
                patch.object(
                    binance_monitor,
                    "_roundtrip_guard_safe_context",
                    return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade}),
                )
            )
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "partial_closed"}))
            stack.enter_context(patch.object(binance_monitor, "_refresh_remaining_protection_after_partial", return_value=True))
            stack.enter_context(patch.object(binance_monitor, "_verify_post_action_state", return_value={"ok": True, "remaining_qty": 7.5}))
            stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_called_once()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["rule"], "cash_ratchet_adaptive_015r")
        self.assertEqual(rows[0]["close_qty"], 2.5)
        self.assertTrue(rows[0]["adaptive"]["tighten_cash_ratchet"])

    def test_cash_ratchet_existing_exit_prevents_duplicate_tier(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.6)
        position["profit"] = 26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(
                patch.object(
                    binance_monitor.trade_db,
                    "get_exits_for_trade",
                    return_value=[{"exit_type": "cash_ratchet_025r"}],
                )
            )
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_not_called()
        self.assertFalse(self.actions_path.exists())

    def test_cash_ratchet_recent_error_backoff_prevents_order_spam(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.6)
        position["profit"] = 26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0
        self.actions_path.write_text(
            json.dumps(
                [
                    {
                        "action_id": "STANDARD_TESTNET::HYPEUSDT::123::cash_ratchet_025r",
                        "created_at": "2026-06-03T10:00:00+00:00",
                        "reason": "error",
                        "executed": False,
                        "execution_result": {
                            "error": "APIError(code=-1007): Timeout waiting for response from backend server. Send status unknown"
                        },
                    }
                ]
            )
        )

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_CASH_RATCHET_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_exits_for_trade", return_value=[]))
            stack.enter_context(patch.object(binance_monitor, "_cash_ratchet_recent_backoff", return_value=(True, {"reason": "error"})))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty"))
            log = stack.enter_context(patch.object(binance_monitor, "plain_log"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_not_called()
        self.assertTrue(any(call.args[0] == "CASH_RATCHET_BACKOFF" for call in log.call_args_list))

    def test_cash_ratchet_live_mode_is_noop(self):
        trade = _trade_row(risk_dollars=100.0)
        position = _position(current_price=102.6)
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"}, clear=False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty"))

            binance_monitor._check_testnet_cash_ratchet(position)

        close_qty.assert_not_called()
        self.assertFalse(self.actions_path.exists())

    def test_remaining_qty_resolver_anchors_to_exchange_when_exit_qty_pct_is_noisy(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_binance_order_state", return_value=None))
            stack.enter_context(
                patch.object(
                    binance_monitor.trade_db,
                    "get_exits_for_trade",
                    return_value=[
                        {"qty_pct": 0.7, "exit_type": "exchange_bracket_fill"},
                        {"qty_pct": 0.6, "exit_type": "cash_ratchet_025r"},
                    ],
                )
            )
            upsert = stack.enter_context(patch.object(binance_monitor.trade_db, "upsert_binance_order_state"))

            detail = binance_monitor._resolve_expected_remaining_qty(
                symbol="HYPEUSDT",
                trade_id=123,
                original_qty=10.0,
                exchange_qty=2.0,
            )

        self.assertEqual(detail["expected_qty"], 2.0)
        self.assertTrue(detail["accounting_noisy"])
        self.assertTrue(detail["accepted_exchange_qty"])
        upsert.assert_called_once_with(symbol="HYPEUSDT", remaining_qty=2.0)

    def test_no_progress_guard_exits_testnet_trade_that_never_proved(self):
        trade = _trade_row(setup_grade="A", risk_dollars=100.0)
        position = _position(current_price=97.4)
        position["profit"] = -26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0
        state["peak_pnl"] = 8.0
        state["_peak_r"] = 0.08

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_trade_open_age_hours", return_value=1.0))
            stack.enter_context(
                patch.object(
                    binance_monitor,
                    "_roundtrip_guard_safe_context",
                    return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade}),
                )
            )
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}))
            stack.enter_context(patch.object(binance_monitor, "_verify_post_action_state", return_value={"ok": True, "remaining_qty": 0.0}))
            log_exit = stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))

            binance_monitor._check_testnet_no_progress_guard(position)

        close_qty.assert_called_once()
        self.assertEqual(close_qty.call_args.kwargs["position_side"], "LONG")
        self.assertEqual(close_qty.call_args.kwargs["reason"], "testnet_no_progress_guard")
        log_exit.assert_called_once()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["rule"], "testnet_no_progress_guard")
        self.assertTrue(rows[0]["executed"])

    def test_no_progress_guard_does_not_exit_if_peak_r_proved_thesis(self):
        trade = _trade_row(setup_grade="A", risk_dollars=100.0)
        position = _position(current_price=97.4)
        position["profit"] = -26.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0
        state["peak_pnl"] = 30.0
        state["_peak_r"] = 0.3

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_trade_open_age_hours", return_value=1.0))
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty"))

            binance_monitor._check_testnet_no_progress_guard(position)

        close_qty.assert_not_called()

    def test_adaptive_no_progress_guard_exits_earlier_after_recent_no_progress_behavior(self):
        trade = _trade_row(setup_grade="A", risk_dollars=100.0)
        position = _position(current_price=98.4)
        position["profit"] = -16.0
        state = binance_monitor._get_state("HYPEUSDT")
        state["trade_id"] = 123
        state["entry_price"] = 100.0
        state["original_sl_distance"] = 10.0
        state["peak_pnl"] = 5.0
        state["_peak_r"] = 0.05
        adaptive = {
            "enabled": True,
            "symbol": "HYPEUSDT",
            "tighten_cash_ratchet": False,
            "tighten_no_progress": True,
            "reason": "symbol_no_progress=1",
        }

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            stack.enter_context(patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir)))
            stack.enter_context(patch.object(binance_monitor, "AUTO_PROTECT_ACTIONS_FILE", str(self.actions_path)))
            stack.enter_context(patch.object(binance_monitor, "BINANCE_TESTNET", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_ENABLED", True))
            stack.enter_context(patch.object(binance_monitor, "TESTNET_AUTO_PROTECT_DRY_RUN", False))
            stack.enter_context(patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade))
            stack.enter_context(patch.object(binance_monitor, "_trade_open_age_hours", return_value=0.5))
            stack.enter_context(patch.object(binance_monitor, "_adaptive_symbol_decision", return_value=adaptive))
            stack.enter_context(
                patch.object(
                    binance_monitor,
                    "_roundtrip_guard_safe_context",
                    return_value=(True, {"exchange_qty": 10.0, "side": "BUY", "trade": trade}),
                )
            )
            close_qty = stack.enter_context(patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}))
            stack.enter_context(patch.object(binance_monitor, "_verify_post_action_state", return_value={"ok": True, "remaining_qty": 0.0}))
            stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))

            binance_monitor._check_testnet_no_progress_guard(position)

        close_qty.assert_called_once()
        rows = json.loads(self.actions_path.read_text())
        self.assertEqual(rows[0]["rule"], "testnet_no_progress_guard")
        self.assertTrue(rows[0]["thresholds"]["adaptive"])
        self.assertEqual(rows[0]["thresholds"]["exit_r"], -0.15)


if __name__ == "__main__":
    unittest.main()
