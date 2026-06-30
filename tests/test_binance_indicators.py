import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from binance_indicators import calculate_indicators


class BinanceIndicatorsClosedCandleTests(unittest.TestCase):
    def test_confirmed_volume_uses_last_closed_candle_not_new_forming_candle(self):
        rows = []
        for i in range(220):
            rows.append({
                "open": float(100 + i - 0.2),
                "close": float(100 + i),
                "high": float(101 + i),
                "low": float(99 + i),
                "volume": 1000.0,
            })

        # Simulate webhook firing right after bar close: Binance has already opened
        # a new candle with tiny early volume, which must NOT drive confirmed checks.
        rows[-2]["volume"] = 900.0
        rows[-1]["close"] = rows[-2]["close"] + 0.5
        rows[-1]["high"] = rows[-2]["high"] + 0.5
        rows[-1]["low"] = rows[-2]["low"] + 0.5
        rows[-1]["volume"] = 5.0

        df = pd.DataFrame(rows)

        result = calculate_indicators(df)

        self.assertEqual(result["volume"], 900.0)
        self.assertGreater(result["volume_avg20"], 800.0)
        self.assertLess(result["volume_avg20"], 1000.0)

    def test_confirmed_candle_context_fields_are_calculated(self):
        rows = []
        for i in range(220):
            rows.append({
                "open": 118.0,
                "close": 118.2,
                "high": 121.0,
                "low": 116.0,
                "volume": 1000.0,
            })
        rows[-2].update({"open": 120.0, "close": 119.0, "high": 121.0, "low": 115.0, "volume": 1500.0})
        rows[-1].update({"open": 119.0, "close": 119.1, "high": 119.2, "low": 118.9, "volume": 10.0})

        result = calculate_indicators(pd.DataFrame(rows))

        self.assertEqual(result["open"], 120.0)
        self.assertEqual(result["close"], 119.0)
        self.assertEqual(result["liquidity_sweep"], "bullish_sweep")
        self.assertEqual(result["wick_rejection"], "bullish_rejection")
        self.assertIn("range_position_pct", result)
        self.assertIn("support_distance_pct", result)
        self.assertIn("displacement_score", result)


if __name__ == "__main__":
    unittest.main()
