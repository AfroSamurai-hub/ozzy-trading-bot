import unittest

from market_context import evaluate_market_context


class MarketContextGateTests(unittest.TestCase):
    def test_bnb_sell_above_ema_is_shadowed(self):
        live = {
            "close": 655.77,
            "ema200": 654.06,
            "supertrend_direction": "short",
            "rsi": 38.93,
        }

        decision = evaluate_market_context("BNBUSDT", "SELL", 656.62, live, strategy="pullback")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "shadow")
        self.assertIn("above EMA200 support", decision.reason)

    def test_bnb_sell_below_ema_is_allowed_when_context_is_bearish(self):
        live = {
            "close": 650.0,
            "ema200": 654.0,
            "supertrend_direction": "short",
            "rsi": 42.0,
        }

        decision = evaluate_market_context("BNBUSDT", "SELL", 650.0, live, strategy="pullback")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.verdict, "allow")

    def test_momentum_buy_below_ema_is_shadowed(self):
        live = {
            "close": 0.39,
            "ema200": 0.41,
            "supertrend_direction": "long",
            "rsi": 58.0,
        }

        decision = evaluate_market_context("ONDOUSDT", "BUY", 0.39, live, strategy="momentum")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "shadow")
        self.assertIn("against EMA200 side", decision.reason)

    def test_alert_bias_conflict_is_shadowed(self):
        live = {
            "close": 660.0,
            "ema200": 655.0,
            "supertrend_direction": "short",
            "rsi": 44.0,
        }

        decision = evaluate_market_context(
            "ETHUSDT",
            "SELL",
            660.0,
            live,
            strategy="pullback",
            alert_bias="bullish",
            alert_structure="bullish",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "shadow")
        self.assertIn("conflicts with alert bias", decision.reason)

    def test_binance_structure_conflict_is_shadowed_without_tradingview_bias(self):
        live = {
            "close": 660.0,
            "ema200": 655.0,
            "supertrend_direction": "short",
            "rsi": 44.0,
            "market_structure": "bullish_bos",
            "support": 650.0,
            "resistance": 659.0,
        }

        decision = evaluate_market_context("ETHUSDT", "SELL", 660.0, live, strategy="pullback")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "shadow")
        self.assertIn("Binance structure bullish_bos", decision.reason)

    def test_sell_after_bullish_liquidity_sweep_is_shadowed(self):
        live = {
            "close": 650.0,
            "ema200": 655.0,
            "supertrend_direction": "short",
            "rsi": 42.0,
            "market_structure": "range",
            "liquidity_sweep": "bullish_sweep",
        }

        decision = evaluate_market_context("ETHUSDT", "SELL", 650.0, live, strategy="pullback")

        self.assertFalse(decision.allowed)
        self.assertIn("bullish liquidity sweep", decision.reason)

    def test_sell_near_range_low_is_shadowed(self):
        live = {
            "close": 650.0,
            "ema200": 655.0,
            "supertrend_direction": "short",
            "rsi": 42.0,
            "market_structure": "bearish",
            "range_position_pct": 9.0,
        }

        decision = evaluate_market_context("ETHUSDT", "SELL", 650.0, live, strategy="pullback")

        self.assertFalse(decision.allowed)
        self.assertIn("near range low", decision.reason)

    def test_trend_continuation_sell_mid_range_is_shadowed(self):
        live = {
            "close": 61328.0,
            "ema200": 66513.24,
            "supertrend_direction": "short",
            "rsi": 43.85,
            "market_structure": "bearish_bos",
            "prior_structure_bias": "range",
            "support": 61577.12,
            "resistance": 62332.0,
            "support_distance_pct": -0.4046,
            "resistance_distance_pct": -1.6107,
            "range_position_pct": 57.38,
            "liquidity_sweep": "none",
            "wick_rejection": "none",
        }

        decision = evaluate_market_context("BTCUSDT", "SELL", 61460.7, live, strategy="trend_continuation")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.verdict, "shadow")
        self.assertIn("trend continuation SELL blocked below range trigger", decision.reason)

    def test_trend_continuation_sell_upper_range_is_allowed(self):
        live = {
            "close": 61850.0,
            "ema200": 66513.24,
            "supertrend_direction": "short",
            "rsi": 43.85,
            "market_structure": "bearish_bos",
            "prior_structure_bias": "range",
            "support": 61577.12,
            "resistance": 62332.0,
            "support_distance_pct": 0.4432,
            "resistance_distance_pct": -0.7732,
            "range_position_pct": 70.0,
            "liquidity_sweep": "none",
            "wick_rejection": "none",
        }

        decision = evaluate_market_context("BTCUSDT", "SELL", 61850.0, live, strategy="trend_continuation")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.verdict, "allow")

    def test_xau_sell_sweep_continuation_exception_allows_early_momentum_short(self):
        live = {
            "close": 4513.55,
            "ema200": 4533.06,
            "supertrend_direction": "short",
            "rsi": 45.61,
            "market_structure": "range",
            "liquidity_sweep": "bullish_sweep",
            "wick_rejection": "none",
            "range_position_pct": 26.86,
            "displacement_score": 1.748,
            "volume_expansion": 0.76,
        }

        decision = evaluate_market_context(
            "XAUUSDT",
            "SELL",
            4516.35,
            live,
            strategy="momentum",
            alert_bias="bearish",
            alert_structure="bearish_bos",
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.verdict, "allow")
        self.assertEqual(decision.details["liquidity_sweep_exception"], "xau_sweep_continuation_v1")

    def test_xau_sell_sweep_continuation_exception_still_blocks_late_range_low_chase(self):
        live = {
            "close": 4500.54,
            "ema200": 4532.6,
            "supertrend_direction": "short",
            "rsi": 39.67,
            "market_structure": "bearish_bos",
            "liquidity_sweep": "bullish_sweep",
            "wick_rejection": "none",
            "range_position_pct": 13.53,
            "displacement_score": 1.707,
            "volume_expansion": 1.34,
        }

        decision = evaluate_market_context(
            "XAUUSDT",
            "SELL",
            4500.54,
            live,
            strategy="momentum",
        )

        self.assertFalse(decision.allowed)
        self.assertIn("bullish liquidity sweep", decision.reason)

    def test_xau_sell_sweep_continuation_exception_blocks_weak_displacement(self):
        live = {
            "close": 4513.55,
            "ema200": 4533.06,
            "supertrend_direction": "short",
            "rsi": 45.61,
            "market_structure": "range",
            "liquidity_sweep": "bullish_sweep",
            "wick_rejection": "none",
            "range_position_pct": 26.86,
            "displacement_score": 1.2,
            "volume_expansion": 0.76,
        }

        decision = evaluate_market_context("XAUUSDT", "SELL", 4516.35, live, strategy="momentum")

        self.assertFalse(decision.allowed)
        self.assertIn("bullish liquidity sweep", decision.reason)

    def test_buy_bearish_rejection_wick_is_shadowed(self):
        live = {
            "close": 660.0,
            "ema200": 655.0,
            "supertrend_direction": "long",
            "rsi": 55.0,
            "market_structure": "bullish",
            "wick_rejection": "bearish_rejection",
        }

        decision = evaluate_market_context("ETHUSDT", "BUY", 660.0, live, strategy="pullback")

        self.assertFalse(decision.allowed)
        self.assertIn("bearish rejection wick", decision.reason)


if __name__ == "__main__":
    unittest.main()
