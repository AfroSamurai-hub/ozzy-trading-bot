import unittest

from position_context import evaluate_position_context


class PositionContextTests(unittest.TestCase):
    def test_sell_position_detects_opposite_reversal_and_exit_required_label(self):
        result = evaluate_position_context(
            {"symbol": "ETHUSDT", "type": "SELL", "openPrice": 2000.0, "currentPrice": 2010.0},
            {"sl": 2020.0, "risk_dollars": 5.0, "peak_pnl": 3.0},
            {"liquidity_sweep": "bullish_sweep", "range_position_pct": 20.0, "support": 1980.0},
        )

        self.assertEqual(result.trend_thesis, "broken")
        self.assertEqual(result.management_label, "EXIT_REQUIRED")
        self.assertTrue(result.opposite_reversal_signal)

    def test_profitable_giveback_labels_reduce_risk(self):
        result = evaluate_position_context(
            {"symbol": "ETHUSDT", "type": "BUY", "openPrice": 100.0, "currentPrice": 101.0},
            {"sl": 95.0, "risk_dollars": 10.0, "peak_pnl": 20.0},
            {"supertrend_direction": "long"},
        )

        self.assertEqual(result.management_label, "REDUCE_RISK")
        self.assertGreaterEqual(result.giveback_pct, 80)

    def test_positive_r_labels_protect(self):
        result = evaluate_position_context(
            {"symbol": "ETHUSDT", "type": "BUY", "openPrice": 100.0, "currentPrice": 103.0},
            {"sl": 95.0, "risk_dollars": 10.0, "peak_pnl": 4.0},
            {"supertrend_direction": "long"},
        )

        self.assertEqual(result.management_label, "PROTECT")


if __name__ == "__main__":
    unittest.main()
