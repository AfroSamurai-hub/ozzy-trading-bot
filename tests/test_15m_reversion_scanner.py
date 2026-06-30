import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = ROOT / "scripts" / "15m_reversion_scanner.py"


def load_scanner():
    os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
    spec = importlib.util.spec_from_file_location("scanner_15m_reversion", SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MeanReversionScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = load_scanner()

    def test_midband_long_signal_requires_webhook_compatible_rr(self):
        indicators = {
            "open": 101.0,
            "high": 102.0,
            "low": 95.0,
            "close": 99.0,
            "lbb": 98.0,
            "mbb": 112.0,
            "ubb": 122.0,
            "rsi": 34.0,
            "atr": 1.0,
            "volume_ratio": 1.0,
            "bottom_wick_pct": 0.55,
            "top_wick_pct": 0.05,
        }

        result = self.scanner.evaluate_mean_reversion("BNBUSDT", indicators)

        self.assertTrue(result["conditions_met"])
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["tp"], 112.0)
        self.assertGreaterEqual(result["rr"], self.scanner.MR_MIN_RR)

    def test_midband_signal_is_rejected_when_rr_is_too_small(self):
        indicators = {
            "open": 101.0,
            "high": 102.0,
            "low": 95.0,
            "close": 99.0,
            "lbb": 98.0,
            "mbb": 103.0,
            "ubb": 122.0,
            "rsi": 34.0,
            "atr": 1.0,
            "volume_ratio": 1.0,
            "bottom_wick_pct": 0.55,
            "top_wick_pct": 0.05,
        }

        result = self.scanner.evaluate_mean_reversion("BNBUSDT", indicators)

        self.assertFalse(result["conditions_met"])
        self.assertIn("mid-band RR", result["reasons"][0])

    def test_webhook_payload_uses_mean_reversion_strategy(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"status": "approved", "reason": "ok"}

        with (
            patch.object(self.scanner.requests, "post", return_value=Response()) as post_mock,
            patch.object(self.scanner, "plain_log"),
        ):
            sent = self.scanner.send_webhook_signal("BNBUSDT", "BUY", 100.0, 96.0, 110.0, 2.5)

        self.assertTrue(sent)
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["strategy"], "mean_reversion")
        self.assertEqual(payload["strategy_label"], "15M_MEAN_REVERSION")
        self.assertEqual(payload["entry_setup_label"], "BOLLINGER_RSI_MIDBAND")
        self.assertEqual(payload["source_service"], "15m_mean_reversion_scanner")
        self.assertEqual(payload["webhook_port"], 5001)
        self.assertEqual(payload["execution_mode"], "TESTNET")
        self.assertEqual(payload["source"], "signal_generator")
        self.assertEqual(payload["timeframe"], "15")

    def test_default_live_lanes_allow_link_both_ways_and_bnb_buy_only(self):
        self.assertTrue(self.scanner.is_live_lane_enabled("LINKUSDT", "BUY"))
        self.assertTrue(self.scanner.is_live_lane_enabled("LINKUSDT", "SELL"))
        self.assertTrue(self.scanner.is_live_lane_enabled("BNBUSDT", "BUY"))
        self.assertFalse(self.scanner.is_live_lane_enabled("BNBUSDT", "SELL"))
        self.assertFalse(self.scanner.is_live_lane_enabled("BTCUSDT", "BUY"))

    def test_profile_context_keeps_non_reversion_assets_out_of_live_lanes(self):
        hype_context = self.scanner._profile_context("HYPEUSDT")
        link_context = self.scanner._profile_context("LINKUSDT")

        self.assertEqual(hype_context["strategy"], "trend_continuation")
        self.assertEqual(hype_context["mean_reversion_live_lanes"], [])
        self.assertFalse(self.scanner.is_live_lane_enabled("HYPEUSDT", "BUY"))
        self.assertEqual(link_context["strategy"], "pullback")
        self.assertEqual(set(link_context["mean_reversion_live_lanes"]), {"BUY", "SELL"})


if __name__ == "__main__":
    unittest.main()
