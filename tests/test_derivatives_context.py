import unittest

import sys
sys.path.insert(0, "/home/rick/ozzy-bot")

from derivatives_context import evaluate_derivatives_positioning, taker_buy_ratio_from_kline


class DerivativesContextTests(unittest.TestCase):
    def test_buy_is_supportive_when_price_oi_and_aggressive_buying_align(self):
        result = evaluate_derivatives_positioning(
            direction="BUY",
            price_change_pct=0.9,
            open_interest_delta_pct=3.2,
            funding_rate=0.0002,
            taker_buy_ratio=0.63,
        )

        self.assertEqual(result["verdict"], "supportive")
        self.assertGreaterEqual(result["score"], 2)
        self.assertIn("oi_confirms_new_longs", result["reasons"])
        self.assertIn("aggressive_buy_flow", result["reasons"])

    def test_buy_flags_weak_squeeze_when_price_rises_but_oi_falls(self):
        result = evaluate_derivatives_positioning(
            direction="BUY",
            price_change_pct=1.1,
            open_interest_delta_pct=-2.0,
            funding_rate=0.0001,
            taker_buy_ratio=0.58,
        )

        self.assertEqual(result["verdict"], "mixed")
        self.assertIn("price_up_oi_down_possible_short_squeeze", result["reasons"])

    def test_buy_flags_crowded_when_funding_is_extremely_positive(self):
        result = evaluate_derivatives_positioning(
            direction="BUY",
            price_change_pct=0.4,
            open_interest_delta_pct=1.0,
            funding_rate=0.0012,
            taker_buy_ratio=0.55,
        )

        self.assertEqual(result["verdict"], "crowded")
        self.assertIn("positive_funding_crowded_longs", result["reasons"])

    def test_sell_is_supportive_when_price_falls_oi_rises_and_sellers_are_aggressive(self):
        result = evaluate_derivatives_positioning(
            direction="SELL",
            price_change_pct=-0.8,
            open_interest_delta_pct=2.4,
            funding_rate=-0.0002,
            taker_buy_ratio=0.37,
        )

        self.assertEqual(result["verdict"], "supportive")
        self.assertGreaterEqual(result["score"], 2)
        self.assertIn("oi_confirms_new_shorts", result["reasons"])
        self.assertIn("aggressive_sell_flow", result["reasons"])

    def test_missing_data_returns_unavailable_without_blocking(self):
        result = evaluate_derivatives_positioning(
            direction="BUY",
            price_change_pct=None,
            open_interest_delta_pct=None,
            funding_rate=None,
            taker_buy_ratio=None,
        )

        self.assertEqual(result["verdict"], "unavailable")
        self.assertEqual(result["score"], 0)
        self.assertIn("derivatives_data_unavailable", result["reasons"])

    def test_taker_buy_ratio_from_binance_kline_payload(self):
        # Binance kline indexes: volume at [5], taker-buy base volume at [9]
        ratio = taker_buy_ratio_from_kline([0, "100", "105", "99", "104", "1000", 0, "0", 0, "620", "0", "0"])

        self.assertEqual(ratio, 0.62)


if __name__ == "__main__":
    unittest.main()
