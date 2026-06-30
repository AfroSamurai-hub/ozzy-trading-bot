import unittest
from pathlib import Path

ROOT = Path("/home/rick/ozzy-bot")
REPO_UNIT = ROOT / "systemd" / "ozzybot-openclaw-breakout-executor.service"
USER_UNIT = Path.home() / ".config" / "systemd" / "user" / "ozzybot-openclaw-breakout-executor.service"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class OpenClawSystemdRoutingTests(unittest.TestCase):
    def test_repo_breakout_executor_routes_to_unified_testnet_webhook(self):
        text = _read(REPO_UNIT)

        self.assertIn("Description=OzzyBot OpenClaw Breakout Executor (UNIFIED TESTNET)", text)
        self.assertIn("After=network-online.target ozzybot-webhook.service", text)
        self.assertIn("EnvironmentFile=/home/rick/ozzy-bot/config/live-micro.env", text)
        self.assertIn("HERMES_OPENCLAW_BREAKOUT_WEBHOOK_URL=http://127.0.0.1:5001/webhook", text)
        self.assertNotIn("127.0.0.1:5000/webhook", text)

    def test_installed_breakout_executor_routes_to_unified_testnet_webhook(self):
        text = _read(USER_UNIT)

        self.assertIn("Description=OzzyBot OpenClaw Breakout Executor (UNIFIED TESTNET)", text)
        self.assertIn("After=network-online.target ozzybot-webhook.service", text)
        self.assertIn("EnvironmentFile=/home/rick/ozzy-bot/config/live-micro.env", text)
        self.assertIn("HERMES_OPENCLAW_BREAKOUT_WEBHOOK_URL=http://127.0.0.1:5001/webhook", text)
        self.assertNotIn("127.0.0.1:5000/webhook", text)


if __name__ == "__main__":
    unittest.main()
