import unittest

import telegram_command_bot


class TelegramCommandBotTests(unittest.TestCase):
    def test_help_alias_parses_without_unknown_fallback(self):
        cmd_type, kwargs = telegram_command_bot.parse_command("/help")

        self.assertEqual(cmd_type, "help")
        self.assertEqual(kwargs, {})

    def test_error_sanitizer_redacts_bot_token_urls(self):
        telegram_command_bot.TELEGRAM_TOKEN = "123456:secret"

        text = telegram_command_bot._safe_error_text(
            "https://api.telegram.org/bot123456:secret/getUpdates failed"
        )

        self.assertNotIn("123456:secret", text)
        self.assertIn("/bot<redacted>", text)

    def test_cooldowns_command_parses_correctly(self):
        for cmd in ("/cooldowns", "cooldowns", "active cooldowns", "loss cooldowns"):
            cmd_type, kwargs = telegram_command_bot.parse_command(cmd)
            self.assertEqual(cmd_type, "cooldowns")
            self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
