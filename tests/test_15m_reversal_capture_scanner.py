import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = ROOT / "scripts" / "15m_reversal_capture_scanner.py"


def load_scanner():
    os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("HERMES_BINANCE_TESTNET", "true")
    os.environ.setdefault("HERMES_WEBHOOK_URL", "http://127.0.0.1:5001/webhook")
    spec = importlib.util.spec_from_file_location("scanner_15m_reversal_capture", SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReversalCaptureScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = load_scanner()

    def _one_hour(self):
        return {
            "supertrend_direction": "short",
            "prior_structure_bias": "bearish",
            "range_position_pct": 15.0,
            "liquidity_sweep": "bullish_sweep",
            "wick_rejection": "bullish_rejection",
            "retest_quality": "support_retest_hold",
            "market_structure": "bearish_bos",
            "volume_expansion": 1.2,
        }

    def _fifteen(self):
        return {
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

    def test_valid_reversal_capture_allows_buy(self):
        result = self.scanner.evaluate_reversal_capture("ETHUSDT", self._one_hour(), self._fifteen())

        self.assertTrue(result["allowed"])
        self.assertEqual(result["signal"], "BUY")

    def test_blocks_without_lower_range_location(self):
        one_hour = self._one_hour()
        one_hour["range_position_pct"] = 50.0

        result = self.scanner.evaluate_reversal_capture("ETHUSDT", one_hour, self._fifteen())

        self.assertFalse(result["allowed"])
        self.assertIn("1h range position not in lower quartile", result["reasons"])

    def test_safety_requires_testnet_and_live_micro_port(self):
        with patch.dict(os.environ, {"HERMES_BINANCE_TESTNET": "false"}):
            safe, _ = self.scanner._validate_testnet_safety("http://127.0.0.1:5001/webhook")
        self.assertFalse(safe)

        with patch.dict(os.environ, {"HERMES_BINANCE_TESTNET": "true"}):
            safe, _ = self.scanner._validate_testnet_safety("http://127.0.0.1:5001/webhook")
        self.assertTrue(safe)


if __name__ == "__main__":
    unittest.main()
