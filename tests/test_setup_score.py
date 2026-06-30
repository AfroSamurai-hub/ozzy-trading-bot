import unittest

from setup_score import score_crypto_setup


class SetupScoreTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "pullback_max_ema_distance_pct": 3.0,
            "pullback_rsi_buy_max": 65.0,
            "pullback_rsi_sell_min": 35.0,
            "momentum_max_ema_distance_pct": 8.0,
            "grade_a_min_volume_ratio": 1.10,
            "grade_b_min_volume_ratio": 0.75,
            "grade_c_min_volume_ratio": 0.50,
        }

    def test_grade_a_clean_setup(self):
        live = {"supertrend_direction": "long", "ema200": 100.0, "rsi": 55.0, "volume": 120, "volume_avg20": 100}
        result = score_crypto_setup("BUY", 102.0, live, "pullback", self.cfg)
        self.assertEqual(result["grade"], "A")
        self.assertEqual(result["risk_multiplier"], 1.0)

    def test_grade_b_low_volume(self):
        live = {"supertrend_direction": "long", "ema200": 100.0, "rsi": 55.0, "volume": 80, "volume_avg20": 100}
        result = score_crypto_setup("BUY", 102.0, live, "pullback", self.cfg)
        self.assertEqual(result["grade"], "B")
        self.assertEqual(result["risk_multiplier"], 0.5)

    def test_grade_c_shadow_volume(self):
        live = {"supertrend_direction": "long", "ema200": 100.0, "rsi": 55.0, "volume": 60, "volume_avg20": 100}
        result = score_crypto_setup("BUY", 102.0, live, "pullback", self.cfg)
        self.assertEqual(result["grade"], "C")
        self.assertEqual(result["risk_multiplier"], 0.0)

    def test_grade_d_hard_trend_conflict(self):
        live = {"supertrend_direction": "short", "ema200": 100.0, "rsi": 55.0, "volume": 120, "volume_avg20": 100}
        result = score_crypto_setup("BUY", 102.0, live, "pullback", self.cfg)
        self.assertEqual(result["grade"], "D")


if __name__ == "__main__":
    unittest.main()
