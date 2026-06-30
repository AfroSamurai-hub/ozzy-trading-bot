#!/usr/bin/env python3
"""
Tests for cleanup_stale_algo_orders.py
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the project root to the path so we can import the script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.cleanup_stale_algo_orders import (
    _truthy,
    _algo_order_type,
    _is_reduce_only_stop_or_tp,
    get_stale_algo_orders_for_symbol,
)


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions."""

    def test_truthy(self):
        """Test _truthy function."""
        self.assertTrue(_truthy(True))
        self.assertTrue(_truthy("true"))
        self.assertTrue(_truthy("TRUE"))
        self.assertTrue(_truthy("True"))
        self.assertFalse(_truthy(False))
        self.assertFalse(_truthy("false"))
        self.assertFalse(_truthy("False"))
        self.assertFalse(_truthy(""))
        self.assertFalse(_truthy(None))
        self.assertFalse(_truthy(0))

    def test_algo_order_type(self):
        """Test _algo_order_type function."""
        self.assertEqual(_algo_order_type({"type": "STOP_MARKET"}), "STOP_MARKET")
        self.assertEqual(_algo_order_type({"orderType": "TAKE_PROFIT_MARKET"}), "TAKE_PROFIT_MARKET")
        self.assertEqual(_algo_order_type({"type": "LIMIT"}), "LIMIT")
        self.assertEqual(_algo_order_type({}), "")
        self.assertEqual(_algo_order_type({"type": None}), "")

    def test_is_reduce_only_stop_or_tp(self):
        """Test _is_reduce_only_stop_or_tp function."""
        # STOP_MARKET with reduceOnly=True
        self.assertTrue(_is_reduce_only_stop_or_tp({
            "type": "STOP_MARKET",
            "reduceOnly": True
        }))
        # STOP_MARKET with reduceOnly="true"
        self.assertTrue(_is_reduce_only_stop_or_tp({
            "type": "STOP_MARKET",
            "reduceOnly": "true"
        }))
        # STOP_MARKET with closePosition=True
        self.assertTrue(_is_reduce_only_stop_or_tp({
            "type": "STOP_MARKET",
            "closePosition": True
        }))
        # STOP_MARKET with closePosition="true"
        self.assertTrue(_is_reduce_only_stop_or_tp({
            "type": "STOP_MARKET",
            "closePosition": "true"
        }))
        # TAKE_PROFIT_MARKET with reduceOnly=True
        self.assertTrue(_is_reduce_only_stop_or_tp({
            "type": "TAKE_PROFIT_MARKET",
            "reduceOnly": True
        }))
        # Not reduce-only
        self.assertFalse(_is_reduce_only_stop_or_tp({
            "type": "STOP_MARKET",
            "reduceOnly": False,
            "closePosition": False
        }))
        # Wrong order type
        self.assertFalse(_is_reduce_only_stop_or_tp({
            "type": "LIMIT",
            "reduceOnly": True
        }))
        self.assertFalse(_is_reduce_only_stop_or_tp({
            "type": "MARKET",
            "reduceOnly": True
        }))
        # Missing type
        self.assertFalse(_is_reduce_only_stop_or_tp({
            "reduceOnly": True
        }))


class TestGetStaleAlgoOrdersForSymbol(unittest.TestCase):
    """Test get_stale_algo_orders_for_symbol function."""

    def setUp(self):
        """Set up test data."""
        self.positions = [
            {"symbol": "ETHUSDT", "positionAmt": "0.5"},
            {"symbol": "BTCUSDT", "positionAmt": "0.1"}
        ]
        self.normal_orders = [
            {"symbol": "ETHUSDT", "orderId": "1", "type": "LIMIT"},
            {"symbol": "LINKUSDT", "orderId": "2", "type": "LIMIT"}
        ]
        self.algo_orders = [
            # ETHUSDT reduce-only STOP_MARKET (should be stale if no position/trade)
            {
                "symbol": "ETHUSDT",
                "orderId": "10",
                "algoId": "sl-algo-1",
                "type": "STOP_MARKET",
                "reduceOnly": True
            },
            # ETHUSDT reduce-only TAKE_PROFIT_MARKET (should be stale if no position/trade)
            {
                "symbol": "ETHUSDT",
                "orderId": "11",
                "algoId": "tp-algo-1",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": "true"
            },
            # ETHUSDT non-reduce-only STOP_MARKET (should NOT be stale)
            {
                "symbol": "ETHUSDT",
                "orderId": "12",
                "algoId": "sl-algo-2",
                "type": "STOP_MARKET",
                "reduceOnly": False,
                "closePosition": False
            },
            # LINKUSDT reduce-only STOP_MARKET (should be stale if no position/trade)
            {
                "symbol": "LINKUSDT",
                "orderId": "13",
                "algoId": "sl-algo-3",
                "type": "STOP_MARKET",
                "reduceOnly": True
            },
            # BTCUSDT reduce-only STOP_MARKET (has position, should NOT be stale)
            {
                "symbol": "BTCUSDT",
                "orderId": "14",
                "algoId": "sl-algo-4",
                "type": "STOP_MARKET",
                "reduceOnly": True
            }
            # Note: No XRPUSDT entry here - we want to test a symbol not in algo_orders
        ]
        # DB open trades: ETHUSDT has an open trade, LINKUSDT does not
        self.db_open_trades = [
            {"symbol": "ETHUSDT", "id": "100"},
            {"symbol": "BTCUSDT", "id": "101"}
        ]
        self.order_states = []  # Not used in this function but required by signature

    def test_ethusdt_has_position_and_db_trade_no_stale(self):
        """Test ETHUSDT with both position and DB trade returns no stale orders."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="ETHUSDT",
            positions=self.positions,
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=self.db_open_trades,
            order_states=self.order_states
        )
        self.assertEqual(len(stale), 0)

    def test_ethusdt_has_position_no_db_trade_no_stale(self):
        """Test ETHUSDT with position but no DB trade returns no stale orders."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="ETHUSDT",
            positions=self.positions,
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=[{"symbol": "BTCUSDT", "id": "101"}],  # No ETHUSDT
            order_states=self.order_states
        )
        self.assertEqual(len(stale), 0)

    def test_ethusdt_no_position_has_db_trade_no_stale(self):
        """Test ETHUSDT with no position but has DB trade returns stale orders (ignores DB trade)."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="ETHUSDT",
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}],  # No ETHUSDT
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=self.db_open_trades,  # Has ETHUSDT trade
            order_states=self.order_states
        )
        # Should return all three ETHUSDT orders (ignoring DB open trade)
        self.assertEqual(len(stale), 3)
        order_ids = {o["orderId"] for o in stale}
        self.assertIn("10", order_ids)
        self.assertIn("11", order_ids)
        self.assertIn("12", order_ids)

    def test_ethusdt_no_position_no_db_trade_returns_stale(self):
        """Test ETHUSDT with no position and no DB trade returns stale orders."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="ETHUSDT",
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}],  # No ETHUSDT
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=[{"symbol": "BTCUSDT", "id": "101"}],  # No ETHUSDT trade
            order_states=self.order_states
        )
        # Should return all three ETHUSDT orders
        self.assertEqual(len(stale), 3)
        order_ids = {o["orderId"] for o in stale}
        self.assertIn("10", order_ids)
        self.assertIn("11", order_ids)
        self.assertIn("12", order_ids)

    def test_linkusdt_no_position_no_db_trade_returns_stale(self):
        """Test LINKUSDT with no position and no DB trade returns stale orders."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="LINKUSDT",
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}],  # No LINKUSDT
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=[{"symbol": "BTCUSDT", "id": "101"}],  # No LINKUSDT trade
            order_states=self.order_states
        )
        # Should return the one reduce-only LINKUSDT order
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["orderId"], "13")

    def test_btcusdt_has_position_no_stale(self):
        """Test BTCUSDT with position returns no stale orders even if no DB trade."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="BTCUSDT",
            positions=self.positions,  # Has BTCUSDT position
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=[{"symbol": "ETHUSDT", "id": "100"}],  # No BTCUSDT trade
            order_states=self.order_states
        )
        self.assertEqual(len(stale), 0)

    def test_zzzusdt_not_in_any_orders_returns_empty(self):
        """Test symbol not in any orders returns empty list."""
        stale = get_stale_algo_orders_for_symbol(
            symbol="ZZZUSDT",
            positions=self.positions,
            normal_orders=self.normal_orders,
            algo_orders=self.algo_orders,
            db_open_trades=self.db_open_trades,
            order_states=self.order_states
        )
        self.assertEqual(len(stale), 0)


class TestCleanupMain(unittest.TestCase):
    """Test cleanup main execution path."""

    @patch("live_reconcile.reconcile_live_state")
    @patch("binance_connector._get_client")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_execute_uses_correct_client_import(self, mock_parse_args, mock_get_client, mock_reconcile):
        """Test that main execution path with --execute uses the correct client factory and does not crash on importing a nonexistent client."""
        # Mock reconcile result
        mock_reconcile.return_value = {
            "stale_algo_orders": [
                {
                    "symbol": "LINKUSDT",
                    "order_type": "STOP_MARKET",
                    "algo_id": 4000001377468961,
                    "client_algo_id": "client-algo-1",
                    "reduce_only": True,
                    "close_position": False,
                    "severity": "warning",
                }
            ]
        }

        # Mock argparse arguments
        mock_args = MagicMock()
        mock_args.symbols = "LINKUSDT"
        mock_args.execute = True
        mock_args.dry_run = False
        mock_parse_args.return_value = mock_args

        # Mock binance client
        mock_binance_client = MagicMock()
        mock_get_client.return_value = mock_binance_client
        mock_binance_client.futures_cancel_algo_order.return_value = {"status": "SUCCESS"}

        # Run main and ensure no ImportError (like cannot import client) is raised
        from scripts.cleanup_stale_algo_orders import main
        try:
            main()
        except SystemExit as e:
            self.assertEqual(e.code, 0)
        
        # Verify that _get_client was called and futures_cancel_algo_order was called
        mock_get_client.assert_called_once()
        mock_binance_client.futures_cancel_algo_order.assert_called_once_with(
            symbol="LINKUSDT", algoId=4000001377468961
        )


if __name__ == '__main__':
    unittest.main()