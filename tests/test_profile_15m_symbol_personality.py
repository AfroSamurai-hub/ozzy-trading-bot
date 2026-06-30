import importlib.util
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROFILER_PATH = ROOT / "scripts" / "profile_15m_symbol_personality.py"


def load_profiler():
    spec = importlib.util.spec_from_file_location("profile_15m_symbol_personality", PROFILER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PersonalityProfilerTests(unittest.TestCase):
    def setUp(self):
        self.profiler = load_profiler()

    def _frame(self):
        rows = []
        base = pd.Timestamp("2026-05-01T00:00:00Z")
        close = 100.0
        for idx in range(80):
            if idx == 30:
                open_price, high, low, close = 100.0, 101.0, 92.0, 98.0
            elif idx == 31:
                open_price, high, low, close = 98.0, 105.0, 97.0, 104.0
            elif idx == 50:
                open_price, high, low, close = 104.0, 115.0, 103.0, 114.0
            elif idx == 51:
                open_price, high, low, close = 114.0, 118.0, 112.0, 117.0
            else:
                open_price = close
                close = close + (0.4 if idx % 3 == 0 else -0.2)
                high = max(open_price, close) + 1.0
                low = min(open_price, close) - 1.0
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(minutes=15 * idx),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1000 + idx,
                }
            )
        return pd.DataFrame(rows)

    def test_profile_symbol_returns_expected_sections(self):
        profile = self.profiler.profile_symbol("ETHUSDT", self._frame(), btc_df=None)

        self.assertEqual(profile["symbol"], "ETHUSDT")
        self.assertIn("atr_pct", profile)
        self.assertIn("mean_reversion_to_middle_bb", profile)
        self.assertIn("breakout_follow_through_rate", profile)
        self.assertIn("fakeout_rate", profile)
        self.assertIn("mfe_mae_by_setup_type", profile)

    def test_btc_correlation_uses_aligned_returns(self):
        df = self.profiler.enrich_indicators(self._frame())
        corr = self.profiler.btc_correlation(df, df)

        self.assertEqual(corr, 1.0)

    def test_klines_to_frame_sorts_and_casts(self):
        rows = [
            [2, "1", "3", "0.5", "2", "10", 0, 0, 0, 0, 0, 0],
            [1, "1", "2", "0.5", "1.5", "8", 0, 0, 0, 0, 0, 0],
        ]
        df = self.profiler.klines_to_frame(rows)

        self.assertEqual(list(df["close"]), [1.5, 2.0])
        self.assertEqual(float(df["volume"].iloc[0]), 8.0)


if __name__ == "__main__":
    unittest.main()
