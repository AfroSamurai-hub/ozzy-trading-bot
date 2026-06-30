import unittest

from paper_tracker import build_summary


class PaperTrackerSummaryTests(unittest.TestCase):
    def test_build_summary_groups_by_symbol(self):
        trades = [
            {"symbol": "ETHUSD", "status": "win", "pnl_points": 48.5, "risk_dollars": 250, "reward_dollars": 625},
            {"symbol": "ETHUSD", "status": "loss", "pnl_points": -19.2, "risk_dollars": 250, "reward_dollars": 625},
            {"symbol": "BTCUSD", "status": "pending", "pnl_points": None, "risk_dollars": 250, "reward_dollars": 625},
        ]

        summary = build_summary(trades)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["wins"], 1)
        self.assertEqual(summary["losses"], 1)
        self.assertEqual(summary["by_symbol"]["ETHUSD"]["total"], 2)
        self.assertEqual(summary["by_symbol"]["ETHUSD"]["wins"], 1)
        self.assertEqual(summary["by_symbol"]["ETHUSD"]["losses"], 1)
        self.assertAlmostEqual(summary["by_symbol"]["ETHUSD"]["net_pnl_points"], 29.3, places=4)
        self.assertEqual(summary["by_symbol"]["ETHUSD"]["net_pnl_dollars"], 375.0)
        self.assertEqual(summary["by_symbol"]["BTCUSD"]["pending"], 1)


if __name__ == "__main__":
    unittest.main()
