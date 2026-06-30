import unittest
import binance_connector
from config import ASSETS, LANES, LIVE_MICRO_SYMBOLS, TESTNET_SYMBOLS, get_lane_config, get_lane_for_signal
from lane_labels import ONE_HOUR_TREND, canonical_strategy_label, derive_strategy_label


class TestLanes(unittest.TestCase):
    def test_supertrend_uses_canonical_one_hour_label(self):
        self.assertEqual(derive_strategy_label("supertrend", "60"), ONE_HOUR_TREND)
        self.assertEqual(canonical_strategy_label("signal_generator", "supertrend", "60"), ONE_HOUR_TREND)

    def test_signal_generator_maps_to_1h_trend(self):
        self.assertEqual(get_lane_for_signal("signal_generator"), "1H_TREND")

    def test_unknown_source_returns_none(self):
        self.assertIsNone(get_lane_for_signal("unknown_source"))

    def test_disabled_lane_not_selected(self):
        LANES["1H_TREND"].enabled = False
        try:
            self.assertIsNone(get_lane_for_signal("signal_generator"))
        finally:
            LANES["1H_TREND"].enabled = True

    def test_lane_config_returns_symbols(self):
        cfg = get_lane_config("1H_TREND")
        self.assertIsNotNone(cfg)
        self.assertIn("ETHUSDT", cfg.symbols)

    def test_live_micro_universe_has_expected_17_symbols(self):
        expected = {
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "HYPEUSDT",
            "XAUUSDT", "NEARUSDT", "BNBUSDT", "ONDOUSDT", "WLDUSDT", "ZECUSDT",
            "DRIFTUSDT", "INJUSDT", "RENDERUSDT", "ENAUSDT", "SEIUSDT",
        }
        self.assertEqual(set(LIVE_MICRO_SYMBOLS), expected)
        self.assertEqual(set(TESTNET_SYMBOLS), expected)

    def test_live_micro_symbols_have_execution_metadata(self):
        for symbol in LIVE_MICRO_SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, ASSETS)
                self.assertIn(symbol, binance_connector.BINANCE_LEVERAGE)
                self.assertIn(symbol, binance_connector.BINANCE_MIN_NOTIONAL)
                self.assertIn(symbol, binance_connector.PRICE_PRECISION)
                self.assertIn(symbol, binance_connector.TV_TO_BINANCE)

    def test_macro_and_openclaw_lanes_cover_live_micro_universe(self):
        for lane_name in ("1H_TREND", "OPENCLAW_BREAKOUT"):
            with self.subTest(lane_name=lane_name):
                cfg = get_lane_config(lane_name)
                self.assertIsNotNone(cfg)
                self.assertEqual(set(cfg.symbols), set(LIVE_MICRO_SYMBOLS))


if __name__ == "__main__":
    unittest.main()
