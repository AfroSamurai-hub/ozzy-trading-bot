import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path("/home/rick/ozzy-bot")
SERVICE = ROOT / "systemd" / "ozzybot-derivatives-shadow-report.service"
TIMER = ROOT / "systemd" / "ozzybot-derivatives-shadow-report.timer"
LEGACY_SHADOW = ROOT / "systemd" / "ozzy-shadow.service"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class DerivativesShadowSystemdTests(unittest.TestCase):
    def test_derivatives_shadow_report_service_is_oneshot_report_generator(self):
        text = _read(SERVICE)

        self.assertIn("Description=OzzyBot Derivatives Shadow Report", text)
        self.assertIn("Type=oneshot", text)
        self.assertIn("WorkingDirectory=/home/rick/ozzy-bot", text)
        self.assertIn("ExecStart=/home/rick/ozzy-bot/venv/bin/python /home/rick/ozzy-bot/scripts/report_derivatives_shadow.py", text)
        self.assertIn("--since-days 14", text)
        self.assertIn("--tolerance-minutes 180", text)
        self.assertIn("--out-dir /home/rick/ozzy-bot/reports", text)
        self.assertIn("Environment=PYTHONPATH=/home/rick/ozzy-bot", text)
        self.assertNotIn("shadow_monitor.py", text)
        self.assertNotIn("Restart=always", text)

    def test_derivatives_shadow_report_timer_runs_every_six_hours(self):
        text = _read(TIMER)

        self.assertIn("Description=Run OzzyBot Derivatives Shadow Report every 6 hours", text)
        self.assertIn("OnBootSec=5min", text)
        self.assertIn("OnUnitActiveSec=6h", text)
        self.assertIn("AccuracySec=5min", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("Unit=ozzybot-derivatives-shadow-report.service", text)
        self.assertIn("WantedBy=timers.target", text)

    def test_legacy_shadow_service_remains_separate_virtual_trade_daemon(self):
        text = _read(LEGACY_SHADOW)

        self.assertIn("Virtual Shadow Trade Exit Tracker Daemon", text)
        self.assertIn("scripts/shadow_monitor.py", text)
        self.assertNotIn("report_derivatives_shadow.py", text)


if __name__ == "__main__":
    unittest.main()
