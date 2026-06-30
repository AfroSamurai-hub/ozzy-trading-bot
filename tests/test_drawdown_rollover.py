import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import webhook
import telegram_client


class DrawdownRolloverTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "day_equity.json"
        self.path_patch = patch.object(webhook, "_DAY_EQUITY_FILE", str(self.path))
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tempdir.cleanup()

    def test_trading_date_uses_johannesburg_timezone(self):
        instant = datetime(2026, 6, 27, 22, 30, tzinfo=UTC)

        self.assertEqual(webhook._trading_date(instant).isoformat(), "2026-06-28")

    def test_day_equity_round_trip_uses_johannesburg_trading_date(self):
        with patch.object(webhook, "_trading_date", return_value=date(2026, 6, 28)):
            self.assertTrue(webhook._save_day_equity(8444.80))
            start_equity, is_today = webhook._load_day_equity()

        self.assertEqual(start_equity, 8444.80)
        self.assertTrue(is_today)
        self.assertEqual(json.loads(self.path.read_text())["date"], "2026-06-28")

    def test_real_five_percent_drawdown_remains_blocked(self):
        self.path.write_text(
            json.dumps(
                {
                    "date": webhook._trading_date().isoformat(),
                    "start_equity": 10000.0,
                }
            )
        )

        with (
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "DAILY_DRAWDOWN_LIMIT", 5.0),
            patch.object(webhook, "_get_live_equity", return_value=9500.0),
        ):
            status = webhook._check_live_drawdown(detailed=True)

        self.assertTrue(status["blocked"])
        self.assertTrue(status["drawdown_blocked"])
        self.assertFalse(status["baseline_unavailable"])
        self.assertEqual(status["reason"], "Daily drawdown limit -5.0% reached")

    def test_previous_day_baseline_is_replaced_before_drawdown_check(self):
        self.path.write_text(json.dumps({"date": "2026-06-27", "start_equity": 9000.0}))

        with (
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "_get_live_equity", return_value=8444.80),
        ):
            status = webhook._check_live_drawdown(detailed=True)

        self.assertFalse(status["blocked"])
        self.assertEqual(status["drawdown_pct"], 0.0)
        self.assertEqual(json.loads(self.path.read_text())["date"], webhook._trading_date().isoformat())

    def test_corrupt_baseline_recovers_from_current_equity(self):
        self.path.write_text("not-json")

        with (
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "_get_live_equity", return_value=8444.80),
        ):
            status = webhook._check_live_drawdown(detailed=True)

        self.assertFalse(status["blocked"])
        self.assertEqual(status["drawdown_pct"], 0.0)
        self.assertEqual(json.loads(self.path.read_text())["start_equity"], 8444.80)

    def test_unwritable_missing_baseline_fails_closed_without_claiming_drawdown(self):
        with (
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "_save_day_equity", return_value=False),
            patch.object(webhook, "_get_live_equity", return_value=8444.80),
        ):
            status = webhook._check_live_drawdown(detailed=True)

        self.assertTrue(status["blocked"])
        self.assertFalse(status["drawdown_blocked"])
        self.assertTrue(status["baseline_unavailable"])
        self.assertIn("baseline unavailable", status["reason"].lower())

    def test_current_baseline_does_not_halt_when_equity_cache_is_temporarily_empty(self):
        self.path.write_text(
            json.dumps(
                {
                    "date": webhook._trading_date().isoformat(),
                    "start_equity": 10000.0,
                }
            )
        )

        with (
            patch.object(webhook, "PAPER_MODE", False),
            patch.object(webhook, "_get_live_equity", return_value=None),
        ):
            status = webhook._check_live_drawdown(detailed=True)

        self.assertFalse(status["blocked"])
        self.assertIsNone(status["reason"])

    def test_entry_stop_preserves_baseline_failure_reason(self):
        drawdown = {
            "blocked": True,
            "drawdown_blocked": False,
            "baseline_unavailable": True,
            "reason": "Daily drawdown baseline unavailable — snapshot persistence failed",
            "drawdown_pct": None,
        }
        unified = {
            "live_trading_blocked_for_day": False,
            "live_blocked_for_day": False,
            "reason": None,
        }

        with (
            patch.object(webhook, "DAILY_DRAWDOWN_ENABLED", True),
            patch.object(webhook, "_unified_daily_stop_status", return_value=unified),
            patch.object(webhook, "_check_live_drawdown", return_value=drawdown) as check,
        ):
            status = webhook._entry_daily_stop_status()

        check.assert_called_once_with(detailed=True)
        self.assertTrue(status["live_trading_blocked_for_day"])
        self.assertFalse(status["drawdown_blocked"])
        self.assertTrue(status["baseline_unavailable"])
        self.assertEqual(status["reason"], drawdown["reason"])

    def test_baseline_failure_notification_does_not_claim_percentage_drawdown(self):
        reason = "Daily drawdown baseline unavailable — snapshot persistence failed"

        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_daily_risk_halt(reason)

        message = send.call_args.args[0]
        self.assertIn("baseline unavailable", message.lower())
        self.assertNotIn("drawdown hit", message.lower())

    def test_periodic_rollover_does_not_log_success_when_snapshot_write_fails(self):
        with (
            patch.object(webhook, "_load_day_equity", return_value=(9000.0, False)),
            patch.object(webhook, "_get_live_equity", return_value=8444.80),
            patch.object(webhook, "_save_day_equity", return_value=False),
            patch.object(webhook, "plain_log") as log,
        ):
            webhook._check_day_equity_rollover()

        self.assertFalse(any(call.args[0] == "DAY_EQUITY_ROLLOVER" for call in log.call_args_list))

    def test_same_halt_reason_notifies_once_per_trading_day(self):
        webhook._daily_halt_alerts.clear()

        self.assertTrue(webhook._should_send_daily_halt_alert("Daily drawdown limit -5.0% reached"))
        self.assertFalse(webhook._should_send_daily_halt_alert("Daily drawdown limit -5.0% reached"))

    def test_new_day_or_reason_can_notify_again(self):
        webhook._daily_halt_alerts.clear()
        day_one = date(2026, 6, 28)
        day_two = date(2026, 6, 29)

        self.assertTrue(webhook._should_send_daily_halt_alert("drawdown", trading_day=day_one))
        self.assertTrue(webhook._should_send_daily_halt_alert("baseline unavailable", trading_day=day_one))
        self.assertTrue(webhook._should_send_daily_halt_alert("drawdown", trading_day=day_two))

    def test_daily_stop_notification_dispatches_once_without_changing_block_state(self):
        webhook._daily_halt_alerts.clear()
        stop = {"drawdown_blocked": True, "baseline_unavailable": False}
        reason = "Daily drawdown limit -5.0% reached"

        with patch.object(webhook.telegram_client, "notify_drawdown_halt") as notify:
            self.assertTrue(webhook._notify_daily_stop(stop, reason))
            self.assertFalse(webhook._notify_daily_stop(stop, reason))

        notify.assert_called_once_with(webhook.DAILY_DRAWDOWN_LIMIT)
        self.assertTrue(stop["drawdown_blocked"])

    def test_baseline_stop_dispatches_accurate_notification(self):
        webhook._daily_halt_alerts.clear()
        stop = {"drawdown_blocked": False, "baseline_unavailable": True}
        reason = "Daily drawdown baseline unavailable — snapshot persistence failed"

        with patch.object(webhook.telegram_client, "notify_daily_risk_halt") as notify:
            self.assertTrue(webhook._notify_daily_stop(stop, reason))

        notify.assert_called_once_with(reason)


if __name__ == "__main__":
    unittest.main()
