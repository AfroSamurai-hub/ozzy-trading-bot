import unittest
from unittest.mock import patch
import json as jsonlib

import telegram_client
import ozzy_context_observer
import config


class TelegramClientTests(unittest.TestCase):
    def test_legacy_message_gets_environment_badge(self):
        with patch.dict("os.environ", {"HERMES_INSTANCE_NAME": "LIVE MICRO"}):
            text = telegram_client._ensure_env_badge("💓 <b>Hermes Heartbeat</b>")

        self.assertTrue(text.startswith("🔴 <b>LIVE MICRO</b>"))
        self.assertIn("Hermes Heartbeat", text)

    def test_card_message_is_not_double_badged(self):
        text = "🔵 <b>TESTNET</b>  ✅ <b>STARTED</b>"

        self.assertEqual(telegram_client._ensure_env_badge(text), text)

    def test_reconciled_trade_without_sl_is_not_clean_confirmed(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_trade_reconciled("ETHUSDT", "SELL", "new_ETHUSDT", 2139.89, None, None)

        sent = send.call_args.args[0]
        self.assertIn("PROTECTION VERIFYING", sent)
        self.assertNotIn("TRADE CONFIRMED", sent)

    def test_protection_confirmed_without_sl_downgrades_to_verifying(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_protection_confirmed("SELL", "ETHUSDT", 2139.89, None, 2100.0)

        sent = send.call_args.args[0]
        self.assertIn("PROTECTION VERIFYING", sent)
        self.assertNotIn("TRADE CONFIRMED", sent)

    def test_testnet_shadow_warning_keeps_test_trade_open(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_testnet_protection_shadow_warning(
                "SELL",
                "ETHUSDT",
                "LIVE would fail-close",
            )

        sent = send.call_args.args[0]
        self.assertIn("TESTNET SHADOW WARNING", sent)
        self.assertIn("TESTNET trade kept open", sent)

    def test_timeout_reconciled_flat_is_not_fail_closed_language(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_execution_timeout_reconciled_flat(
                "SELL",
                "ETHUSDT",
                "timeout reconciled flat",
            )

        sent = send.call_args.args[0]
        self.assertIn("EXECUTION TIMEOUT", sent)
        self.assertIn("RECONCILED FLAT", sent)
        self.assertNotIn("FAIL-CLOSED", sent)

    def test_hour_summary_uses_sent_not_fire_language(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_hour_summary(
                [
                    {
                        "symbol": "BNBUSDT",
                        "status": "FIRE",
                        "signal": "SELL",
                        "strategy": "pullback",
                        "grade": "B",
                    }
                ],
                "20:05",
            )

        sent = send.call_args.args[0]
        self.assertIn("SENT", sent)
        self.assertIn("sent to webhook", sent)
        self.assertIn("wait for webhook approval/confirmation", sent)

    def test_trail_update_separates_current_and_stop_locked_pnl(self):
        with patch.object(telegram_client, "send_message") as send:
            telegram_client.notify_trail_update("XAUUSDT", "SELL", 4504.44, 92.10, 67.74, 92.10)

        sent = send.call_args.args[0]
        self.assertIn("Current PnL", sent)
        self.assertIn("$92.10", sent)
        self.assertIn("Stop-Locked PnL est.", sent)
        self.assertIn("$67.74", sent)
        self.assertNotIn("Locked PnL:</b>", sent)

    def test_normalize_giveback_pct_accepts_ratio_or_percent(self):
        self.assertAlmostEqual(telegram_client._normalize_giveback_pct(0.25), 25.0, places=4)
        self.assertAlmostEqual(telegram_client._normalize_giveback_pct(25), 25.0, places=4)

    def test_mfe_guard_notification_formats_ratio_as_percent(self):
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def getcode(self):
                return 200

        def _fake_urlopen(req, timeout=5):
            captured["payload"] = jsonlib.loads(req.data.decode("utf-8"))
            return _Resp()

        alert = {
            "symbol": "LINKUSDT",
            "side": "LONG",
            "trade_id": 10,
            "current_pnl": -1.0,
            "mfe_pnl": 4.0,
            "giveback_pct": 0.25,
            "mfe_guard_state": "WATCH",
            "alert_id": "A1",
        }
        with (
            patch.object(config, "TELEGRAM_TOKEN", "tok"),
            patch.object(config, "TELEGRAM_CHAT_ID", "chat"),
            patch("urllib.request.urlopen", side_effect=_fake_urlopen),
        ):
            self.assertTrue(ozzy_context_observer.send_mfe_guard_notification(alert))
        self.assertIn("25.0%", captured["payload"]["text"])

    def test_mfe_guard_notification_keeps_percent_value(self):
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def getcode(self):
                return 200

        def _fake_urlopen(req, timeout=5):
            captured["payload"] = jsonlib.loads(req.data.decode("utf-8"))
            return _Resp()

        alert = {
            "symbol": "LINKUSDT",
            "side": "LONG",
            "trade_id": 11,
            "current_pnl": -1.0,
            "mfe_pnl": 4.0,
            "giveback_pct": 25.0,
            "mfe_guard_state": "WATCH",
            "alert_id": "A2",
        }
        with (
            patch.object(config, "TELEGRAM_TOKEN", "tok"),
            patch.object(config, "TELEGRAM_CHAT_ID", "chat"),
            patch("urllib.request.urlopen", side_effect=_fake_urlopen),
        ):
            self.assertTrue(ozzy_context_observer.send_mfe_guard_notification(alert))
        self.assertIn("25.0%", captured["payload"]["text"])
        self.assertNotIn("2500.0%", captured["payload"]["text"])


if __name__ == "__main__":
    unittest.main()
