import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.macro_scout import MacroScoutAgent
from core.trend_executor import TrendExecutorAgent


class OpenClawMomentumV2Tests(unittest.TestCase):
    def test_directional_bias_requires_4h_and_1d_alignment(self):
        bullish_4h = {"close": 110, "ema200": 100, "supertrend_direction": "long"}
        bullish_1d = {"close": 120, "ema200": 100, "supertrend_direction": "long"}
        bearish_1d = {"close": 90, "ema200": 100, "supertrend_direction": "short"}

        self.assertEqual(MacroScoutAgent._directional_bias(bullish_4h, bullish_1d), "UP")
        self.assertEqual(MacroScoutAgent._directional_bias(bullish_4h, bearish_1d), "MIXED")

    def test_trend_executor_keeps_raw_mixed_bias_non_directional(self):
        self.assertEqual(TrendExecutorAgent._side_from_bias("UP"), "BUY")
        self.assertEqual(TrendExecutorAgent._side_from_bias("DOWN"), "SELL")
        self.assertIsNone(TrendExecutorAgent._side_from_bias("MIXED"))

    def test_trend_executor_arms_mixed_macro_breakout_from_4h_metrics_as_b_lane(self):
        plan = TrendExecutorAgent._blueprint_plan(
            strategy="4H_MACRO_BREAKOUT",
            configured_lane="Macro",
            data={
                "directional_bias": "MIXED",
                "metrics": {"close": 110, "ema200": 100, "supertrend_direction": "long"},
            },
        )

        self.assertEqual(plan["side"], "BUY")
        self.assertEqual(plan["entry_setup_label"], "OPENCLAW_BREAKOUT_B_MIXED")
        self.assertEqual(plan["regime_label"], "OPENCLAW_4H_MACRO_BREAKOUT_MIXED")

    def test_trend_executor_arms_moderate_trend_retest_from_4h_metrics_as_c_lane(self):
        plan = TrendExecutorAgent._blueprint_plan(
            strategy="4H_MODERATE_TREND",
            configured_lane="Macro",
            data={
                "directional_bias": "UP",
                "metrics": {"close": 95, "ema200": 100, "supertrend_direction": "short"},
            },
        )

        self.assertEqual(plan["side"], "SELL")
        self.assertEqual(plan["entry_setup_label"], "OPENCLAW_RETEST_C_MODERATE")
        self.assertEqual(plan["regime_label"], "OPENCLAW_4H_MODERATE_TREND")

    def test_all_17_symbols_have_openclaw_personality_profiles(self):
        from config import get_all_openclaw_symbols, get_symbol_strategy_profile

        expected = {
            "SOLUSDT": ("impulsive_trender", "BREAKOUT", "CONTINUATION"),
            "HYPEUSDT": ("impulsive_trender", "BREAKOUT", "CONTINUATION"),
            "SEIUSDT": ("impulsive_trender", "BREAKOUT", "CONTINUATION"),
            "RENDERUSDT": ("impulsive_trender", "BREAKOUT", "CONTINUATION"),
            "SUIUSDT": ("impulsive_trender", "BREAKOUT", "RETEST"),
            "ONDOUSDT": ("steady_trend_rider", "CONTINUATION", "RETEST"),
            "NEARUSDT": ("steady_trend_rider", "CONTINUATION", "RETEST"),
            "BNBUSDT": ("steady_trend_rider", "RETEST", "PULLBACK"),
            "LINKUSDT": ("steady_trend_rider", "RETEST", "PULLBACK"),
            "INJUSDT": ("steady_trend_rider", "CONTINUATION", "RETEST"),
            "BTCUSDT": ("mean_reverting_pullback", "PULLBACK", "RETEST"),
            "ETHUSDT": ("mean_reverting_pullback", "PULLBACK", "RETEST"),
            "WLDUSDT": ("mean_reverting_pullback", "PULLBACK", "BREAKOUT"),
            "XAUUSDT": ("mean_reverting_pullback", "PULLBACK", "RETEST"),
            "ZECUSDT": ("bench_watch", "SHADOW_ONLY", "BREAKOUT"),
            "DRIFTUSDT": ("bench_watch", "SHADOW_ONLY", "RETEST"),
            "ENAUSDT": ("bench_watch", "SHADOW_ONLY", "BREAKOUT"),
        }

        self.assertEqual(set(get_all_openclaw_symbols()), set(expected.keys()))
        for symbol, (personality, primary, secondary) in expected.items():
            profile = get_symbol_strategy_profile(symbol)
            self.assertEqual(profile.get("openclaw_personality"), personality, symbol)
            self.assertEqual(profile.get("openclaw_primary_setup"), primary, symbol)
            self.assertEqual(profile.get("openclaw_secondary_setup"), secondary, symbol)
            self.assertIsInstance(profile.get("openclaw_personality_reason"), str, symbol)
            self.assertGreater(len(profile.get("openclaw_personality_reason", "")), 10, symbol)

    def test_trend_executor_setup_profile_for_symbol_uses_personality_catalog(self):
        hype = TrendExecutorAgent._setup_profile_for_symbol("HYPEUSDT")
        btc = TrendExecutorAgent._setup_profile_for_symbol("BTCUSDT")
        zec = TrendExecutorAgent._setup_profile_for_symbol("ZECUSDT")

        self.assertEqual(hype["assigned_setup_type"], "BREAKOUT")
        self.assertEqual(hype["secondary_setup_type"], "CONTINUATION")
        self.assertEqual(btc["assigned_setup_type"], "PULLBACK")
        self.assertEqual(btc["secondary_setup_type"], "RETEST")
        self.assertEqual(zec["assigned_setup_type"], "SHADOW_ONLY")
        self.assertEqual(zec["openclaw_personality"], "bench_watch")
        self.assertGreater(len(zec["personality_reason"]), 10)


if __name__ == "__main__":
    unittest.main()
