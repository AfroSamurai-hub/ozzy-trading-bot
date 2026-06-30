import unittest
from unittest.mock import patch

from sentiment_filter import check_sentiment_conflict


class SentimentFilterTests(unittest.TestCase):

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "off")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {})
    def test_off_mode_allows_everything(self):
        self.assertIsNone(check_sentiment_conflict("US500", "BUY"))
        self.assertIsNone(check_sentiment_conflict("US500", "SELL"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "directional")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "bearish"})
    def test_bearish_blocks_buy_allows_sell(self):
        reason = check_sentiment_conflict("US500", "BUY")
        self.assertIsNotNone(reason)
        self.assertIn("bearish", reason)
        self.assertIsNone(check_sentiment_conflict("US500", "SELL"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "directional")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "bullish"})
    def test_bullish_blocks_sell_allows_buy(self):
        reason = check_sentiment_conflict("US500", "SELL")
        self.assertIsNotNone(reason)
        self.assertIn("bullish", reason)
        self.assertIsNone(check_sentiment_conflict("US500", "BUY"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "directional")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "neutral"})
    def test_neutral_allows_both(self):
        self.assertIsNone(check_sentiment_conflict("US500", "BUY"))
        self.assertIsNone(check_sentiment_conflict("US500", "SELL"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "extreme_only")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "bearish"})
    def test_extreme_only_allows_moderate_bearish(self):
        # Moderate bearish should NOT block in extreme_only mode
        self.assertIsNone(check_sentiment_conflict("US500", "BUY"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "extreme_only")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "strong_bearish"})
    def test_extreme_only_blocks_strong_bearish_buy(self):
        reason = check_sentiment_conflict("US500", "BUY")
        self.assertIsNotNone(reason)
        self.assertIn("strong_bearish", reason)

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "extreme_only")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {"US500": "strong_bearish"})
    def test_extreme_only_allows_sell_on_strong_bearish(self):
        self.assertIsNone(check_sentiment_conflict("US500", "SELL"))

    @patch("sentiment_filter.SENTIMENT_FILTER_MODE", "directional")
    @patch("sentiment_filter.SENTIMENT_OVERRIDES", {})
    def test_missing_symbol_defaults_neutral(self):
        self.assertIsNone(check_sentiment_conflict("EURUSD", "BUY"))
        self.assertIsNone(check_sentiment_conflict("EURUSD", "SELL"))


if __name__ == "__main__":
    unittest.main()
