from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "systemd" / "ozzybot-daily-edge-report.service"
TIMER = ROOT / "systemd" / "ozzybot-daily-edge-report.timer"


class DailyEdgeSystemdTests(unittest.TestCase):
    def test_service_runs_daily_edge_report_against_unified_db(self):
        text = SERVICE.read_text()

        self.assertIn("scripts/report_daily_edge.py --hours 24", text)
        self.assertIn("--report-dir /home/rick/ozzy-bot/reports", text)
        self.assertIn("ozzybot-webhook.service", text)
        self.assertNotIn("127.0.0.1:5000", text)
        self.assertNotIn("trades_live.db", text)

    def test_timer_runs_on_four_hour_regime_cycle(self):
        text = TIMER.read_text()

        self.assertIn("OnUnitActiveSec=4h", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("Unit=ozzybot-daily-edge-report.service", text)


if __name__ == "__main__":
    unittest.main()
