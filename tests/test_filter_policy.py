import unittest

from filter_policy import volume_below_threshold, rsi_exhausted


class FilterPolicyTests(unittest.TestCase):
    def test_buy_rsi_7341_is_not_exhausted_under_looser_threshold(self):
        self.assertIsNone(rsi_exhausted("BUY", 73.41, buy_max=78.0, sell_min=22.0))

    def test_sell_rsi_21_is_exhausted_under_looser_threshold(self):
        reason = rsi_exhausted("SELL", 21.0, buy_max=78.0, sell_min=22.0)
        self.assertIn("below 22.0", reason)

    def test_volume_ratio_090_passes_looser_threshold(self):
        self.assertFalse(volume_below_threshold(900.0, 1000.0, min_ratio=0.85))

    def test_volume_ratio_070_fails_looser_threshold(self):
        self.assertTrue(volume_below_threshold(700.0, 1000.0, min_ratio=0.85))


if __name__ == "__main__":
    unittest.main()
