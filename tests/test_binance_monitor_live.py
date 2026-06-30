import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import binance_monitor
import binance_connector
import config


class TestBinanceMonitorModuleSmokeTests(unittest.TestCase):
    def test_module_loads(self):
        self.assertTrue(hasattr(binance_monitor, "run"))

    def test_connector_exports_active_functions(self):
        for name in {
            "_get_client",
            "get_open_positions",
            "get_balance",
            "place_trade",
            "close_position",
            "close_position_qty",
            "move_sl_to_breakeven",
            "has_exchange_protection",
            "confirm_exchange_protection",
            "verify_protection_order",
            "get_post_fill_protection_mode",
            "check_order_book_spread",
        }:
            self.assertTrue(hasattr(binance_connector, name), msg=f"missing {name}")

    def test_testnet_mode_is_respected_by_config(self):
        self.assertIsInstance(config.BINANCE_TESTNET, bool)

    def test_live_helpers_are_callable(self):
        self.assertTrue(callable(binance_connector._get_client))
        self.assertTrue(callable(binance_connector.check_order_book_spread))


if __name__ == "__main__":
    unittest.main()
