import unittest
from unittest.mock import patch

import signal_generator
from config import build_crypto_entry_config, DYNAMIC_THRESHOLDS, get_signal_strategy_for_symbol


class SignalGeneratorExitTests(unittest.TestCase):
    def test_clean_no_signal_scan_returns_success_exit_code(self):
        with (
            patch.object(signal_generator, "run", return_value=([], [])),
            patch.object(signal_generator, "print_report"),
            patch.object(signal_generator.sys, "argv", ["signal_generator.py"]),
        ):
            self.assertEqual(signal_generator.main(), 0)

    def test_hype_uses_trend_continuation_profile(self):
        result = signal_generator.evaluate_symbol(
            "HYPEUSDT",
            {
                "close": 110.0,
                "ema200": 100.0,
                "supertrend_direction": "long",
                "rsi": 74.0,
                "volume": 80.0,
                "volume_avg20": 100.0,
            },
            dry_run=True,
        )

        self.assertTrue(result["conditions_met"])
        self.assertEqual(result["strategy"], "trend_continuation")

    def test_ondo_uses_momentum_profile(self):
        result = signal_generator.evaluate_symbol(
            "ONDOUSDT",
            {
                "close": 1.10,
                "ema200": 1.0,
                "supertrend_direction": "long",
                "rsi": 69.0,
                "volume": 80.0,
                "volume_avg20": 100.0,
            },
            dry_run=True,
        )

        self.assertTrue(result["conditions_met"])
        self.assertEqual(result["strategy"], "momentum")

    def test_pullback_profile_rejects_link_when_too_far_from_ema(self):
        result = signal_generator.evaluate_symbol(
            "LINKUSDT",
            {
                "close": 22.0,
                "ema200": 20.0,
                "supertrend_direction": "long",
                "rsi": 55.0,
                "volume": 100.0,
                "volume_avg20": 100.0,
            },
            dry_run=True,
        )

        self.assertFalse(result["conditions_met"])
        self.assertTrue(any("pullback too far" in reason for reason in result["reasons"]))

    def test_payload_uses_closed_loop_profile_strategy(self):
        payload = signal_generator.build_payload("HYPEUSDT", "BUY", 42.0)

        self.assertEqual(payload["strategy"], "trend_continuation")
        self.assertEqual(payload["source"], "signal_generator")
        self.assertEqual(payload["strategy_label"], "1H_TREND_CONTINUATION")
        self.assertEqual(payload["entry_setup_label"], "TREND_CONTINUATION")
        self.assertIn(payload["execution_mode"], {"LIVE", "TESTNET"})

    def test_new_scouting_assets_have_profile_roles(self):
        self.assertEqual(get_signal_strategy_for_symbol("WLDUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("DRIFTUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("ZECUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("INJUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("RENDERUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("ENAUSDT"), "supertrend")
        self.assertEqual(get_signal_strategy_for_symbol("SEIUSDT"), "supertrend")

    def test_drift_scouting_profile_keeps_sniper_volume_floor(self):
        cfg = build_crypto_entry_config(DYNAMIC_THRESHOLDS, "DRIFTUSDT")

        self.assertEqual(cfg["trend_continuation_min_volume_ratio"], 0.75)
        self.assertEqual(cfg["trend_continuation_max_ema_distance_pct"], 25.0)

    def test_profile_proximity_uses_classifier_rejection_reasons(self):
        prox = signal_generator._analyze_proximity(
            "BTCUSDT",
            close=75935.08,
            ema200=77093.32,
            st_dir="short",
            rsi=32.25,
            volume_ratio=1.616,
            strategy="trend_continuation",
            rejection_reasons=[
                "SELL: trend continuation not extended enough — 1.5% vs min 2.0%",
            ],
        )

        self.assertIsNotNone(prox)
        self.assertEqual(prox["gates_away"], 1)
        self.assertIn("trend continuation not extended", prox["blocking_gate"])

    def test_profile_proximity_suppresses_more_than_two_profile_blocks(self):
        prox = signal_generator._analyze_proximity(
            "BTCUSDT",
            close=75935.08,
            ema200=77093.32,
            st_dir="short",
            rsi=32.25,
            volume_ratio=1.616,
            strategy="trend_continuation",
            rejection_reasons=["a", "b", "c"],
        )

        self.assertIsNone(prox)


if __name__ == "__main__":
    unittest.main()
