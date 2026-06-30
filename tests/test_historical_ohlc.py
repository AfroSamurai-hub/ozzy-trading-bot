import unittest

from historical_ohlc import evaluate_outcome_from_candles, provider_reliability_map


class HistoricalOHLCtests(unittest.TestCase):
    def test_provider_reliability_marks_crypto_only(self):
        data = provider_reliability_map(["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US500"])
        self.assertTrue(data["BTCUSD"]["reliable"])
        self.assertTrue(data["ETHUSD"]["reliable"])
        self.assertTrue(data["XAUUSD"]["reliable"])
        self.assertFalse(data["US500"]["reliable"])

    def test_buy_outcome_hits_tp_before_sl(self):
        candles = [
            {"ts": "2026-04-17 10:01:00", "open": 100, "high": 101, "low": 99.7, "close": 100.8},
            {"ts": "2026-04-17 10:02:00", "open": 100.8, "high": 103.1, "low": 100.5, "close": 102.9},
        ]
        outcome = evaluate_outcome_from_candles("BUY", 100.0, 98.0, 103.0, candles)
        self.assertEqual(outcome["outcome"], "win")
        self.assertEqual(outcome["exit_reason"], "tp_hit")
        self.assertEqual(outcome["r_multiple"], 1.5)

    def test_sell_outcome_hits_sl_before_tp(self):
        candles = [
            {"ts": "2026-04-17 10:01:00", "open": 100, "high": 101.2, "low": 99.5, "close": 100.9},
        ]
        outcome = evaluate_outcome_from_candles("SELL", 100.0, 101.0, 98.0, candles)
        self.assertEqual(outcome["outcome"], "loss")
        self.assertEqual(outcome["exit_reason"], "sl_hit")
        self.assertEqual(outcome["r_multiple"], -1.0)

    def test_same_candle_both_hit_is_ambiguous(self):
        candles = [
            {"ts": "2026-04-17 10:01:00", "open": 100, "high": 103.5, "low": 97.5, "close": 101.0},
        ]
        outcome = evaluate_outcome_from_candles("BUY", 100.0, 98.0, 103.0, candles)
        self.assertEqual(outcome["outcome"], "ambiguous")
        self.assertEqual(outcome["exit_reason"], "same_candle_both_hit")


if __name__ == "__main__":
    unittest.main()
