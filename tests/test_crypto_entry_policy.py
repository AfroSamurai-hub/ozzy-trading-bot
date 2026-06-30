import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crypto_entry_policy import classify_crypto_entry


class CryptoEntryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "pullback_max_ema_distance_pct": 3.0,
            "pullback_rsi_buy_max": 65.0,
            "pullback_rsi_sell_min": 35.0,
            "momentum_enabled": True,
            "momentum_max_ema_distance_pct": 8.0,
            "momentum_min_volume_ratio": 1.10,
            "momentum_rsi_buy_max": 80.0,
            "momentum_rsi_sell_min": 20.0,
            "grade_a_min_volume_ratio": 1.20,
            "grade_b_min_volume_ratio": 0.90,
        }

    def test_pullback_buy_near_ema_is_classified_as_pullback_grade_b(self):
        live = {
            "ema200": 2300.0,
            "rsi": 58.0,
            "volume": 950.0,
            "volume_avg20": 1000.0,
            "supertrend_direction": "long",
        }
        result = classify_crypto_entry("BUY", 2315.0, live, self.cfg, requested_strategy="pullback")
        self.assertEqual(result["mode"], "pullback")
        self.assertEqual(result["grade"], "B")
        self.assertAlmostEqual(result["volume_ratio"], 0.95, places=2)

    def test_pullback_buy_that_is_too_far_but_strong_volume_becomes_momentum_grade_a(self):
        live = {
            "ema200": 2300.0,
            "rsi": 72.0,
            "volume": 1400.0,
            "volume_avg20": 1000.0,
            "supertrend_direction": "long",
        }
        result = classify_crypto_entry("BUY", 2450.0, live, self.cfg, requested_strategy="pullback")
        self.assertEqual(result["mode"], "momentum")
        self.assertEqual(result["grade"], "A")
        self.assertGreater(result["ema_distance_pct"], 3.0)

    def test_breakout_with_weak_volume_is_rejected(self):
        live = {
            "ema200": 2300.0,
            "rsi": 70.0,
            "volume": 1000.0,
            "volume_avg20": 1000.0,
            "supertrend_direction": "long",
        }
        result = classify_crypto_entry("BUY", 2450.0, live, self.cfg, requested_strategy="pullback")
        self.assertEqual(result["mode"], "reject")
        self.assertIn("volume", " ".join(result["reasons"]).lower())

    def test_signal_conflict_with_live_trend_is_rejected(self):
        live = {
            "ema200": 2300.0,
            "rsi": 58.0,
            "volume": 1200.0,
            "volume_avg20": 1000.0,
            "supertrend_direction": "short",
        }
        result = classify_crypto_entry("BUY", 2315.0, live, self.cfg, requested_strategy="pullback")
        self.assertEqual(result["mode"], "reject")
        self.assertIn("trend", " ".join(result["reasons"]).lower())

    def test_sell_momentum_can_be_classified_cleanly(self):
        live = {
            "ema200": 2350.0,
            "rsi": 28.0,
            "volume": 1500.0,
            "volume_avg20": 1000.0,
            "supertrend_direction": "short",
        }
        result = classify_crypto_entry("SELL", 2210.0, live, self.cfg, requested_strategy="momentum")
        self.assertEqual(result["mode"], "momentum")
        self.assertEqual(result["grade"], "A")
        self.assertLess(result["ema_distance_pct"], 0)


if __name__ == "__main__":
    unittest.main()
