import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_UNIT = ROOT / "systemd" / "ozzybot-openclaw-breakout-executor.service"
USER_UNIT = Path.home() / ".config" / "systemd" / "user" / "ozzybot-openclaw-breakout-executor.service"
SHADOW_REPO_UNIT = ROOT / "systemd" / "ozzybot-openclaw-shadow-executor.service"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class OpenClawSystemdRoutingTests(unittest.TestCase):
    def test_shadow_executor_uses_isolated_breakout_state(self):
        text = _read(SHADOW_REPO_UNIT)

        self.assertIn(
            "Environment=HERMES_OPENCLAW_BREAKOUT_STATE=/home/rick/ozzy-bot/shared/openclaw_shadow_state.json",
            text,
        )

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
