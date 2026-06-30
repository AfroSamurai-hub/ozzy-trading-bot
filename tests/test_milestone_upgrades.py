import unittest
from unittest.mock import MagicMock, patch
import time
from datetime import datetime, timezone
from pathlib import Path

# We append the project root path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import binance_monitor
from binance_monitor import (
    _get_state,
    _check_time_decay_exit,
    _check_milestone_exits,
    _recover_state_from_db,
    _refresh_remaining_protection_after_partial,
    _repair_missing_protection_if_needed,
)

class TestMilestoneUpgrades(unittest.TestCase):

    def setUp(self):
        # Reset position memory state before each test
        binance_monitor._position_state.clear()
        self.telegram_patch = patch.object(binance_monitor, "_send_telegram")
        self.log_patch = patch.object(binance_monitor, "plain_log")
        self.paper_patch = patch.object(binance_monitor, "PAPER_MODE", True)
        self.client_patch = patch.object(binance_monitor, "_get_client")
        self.telegram_patch.start()
        self.log_patch.start()
        self.paper_patch.start()
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        self.paper_patch.stop()
        self.log_patch.stop()
        self.telegram_patch.stop()
        
    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.move_sl_to_breakeven')
    @patch('binance_monitor._get_client')
    @patch('binance_monitor._trade_open_age_hours')
    @patch('binance_monitor._send_telegram')
    def test_check_time_decay_exit_success(self, mock_send_telegram, mock_age_hours, mock_get_client, mock_move_sl, mock_trade_db):
        """Verify that a 15m trade open for >= 60m with profit > 0 triggers time-decay trim and breakeven."""
        symbol = "BNBUSDT"
        
        # Initialize state
        state = _get_state(symbol)
        state["trade_id"] = 101
        state["timeframe"] = "15"
        state["original_qty"] = 1.0
        
        # Setup mocks
        mock_age_hours.return_value = 1.2  # 1.2 hours (> 60m)
        mock_trade_db.milestone_exists.return_value = False
        
        # Position mock
        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "openPrice": 600.0,
            "currentPrice": 610.0,
            "profit": 10.0,  # in profit
            "volume": 1.0,
            "type": "BUY",
        }
        
        # Run check
        with patch('binance_monitor.PAPER_MODE', True):
            _check_time_decay_exit(position)
            
        # Assertions
        self.assertTrue(state["decay_trimmed"])
        self.assertTrue(state["breakeven_moved"])
        mock_move_sl.assert_called_once_with(symbol, 600.0)
        mock_trade_db.log_exit.assert_called_once()
        self.assertEqual(mock_trade_db.log_exit.call_args[1]["exit_type"], "15m_time_decay_trim")
        self.assertAlmostEqual(mock_trade_db.log_exit.call_args.kwargs["qty_pct"], 0.15, delta=1e-12)
        self.assertIn("qty_source=paper_simulated", mock_trade_db.log_exit.call_args.kwargs["notes"])

    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.move_sl_to_breakeven')
    @patch('binance_monitor._trade_open_age_hours')
    def test_check_time_decay_exit_no_profit(self, mock_age_hours, mock_move_sl, mock_trade_db):
        """Verify that time-decay trim does not trigger if the trade is in loss."""
        symbol = "BNBUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 101
        state["timeframe"] = "15"
        state["original_qty"] = 1.0
        
        mock_age_hours.return_value = 1.2
        
        position = {
            "symbol": symbol,
            "openPrice": 600.0,
            "currentPrice": 595.0,
            "profit": -5.0,  # in loss
            "volume": 1.0,
            "type": "BUY",
        }
        
        _check_time_decay_exit(position)
        self.assertFalse(state.get("decay_trimmed", False))
        self.assertFalse(state.get("breakeven_moved", False))
        mock_move_sl.assert_not_called()

    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.move_sl_to_breakeven')
    @patch('binance_monitor._trade_open_age_hours')
    def test_check_time_decay_exit_too_young(self, mock_age_hours, mock_move_sl, mock_trade_db):
        """Verify that time-decay trim does not trigger if the trade is under 60 minutes old."""
        symbol = "BNBUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 101
        state["timeframe"] = "15"
        state["original_qty"] = 1.0
        
        mock_age_hours.return_value = 0.5  # 30 minutes (< 60m)
        
        position = {
            "symbol": symbol,
            "openPrice": 600.0,
            "currentPrice": 610.0,
            "profit": 10.0,
            "volume": 1.0,
            "type": "BUY",
        }
        
        _check_time_decay_exit(position)
        self.assertFalse(state.get("decay_trimmed", False))
        self.assertFalse(state.get("breakeven_moved", False))
        mock_move_sl.assert_not_called()

    @patch('binance_monitor.trade_db')
    @patch('binance_monitor._get_client')
    @patch('binance_monitor._send_telegram')
    def test_check_milestone_exits_choppy_regime(self, mock_send_telegram, mock_get_client, mock_trade_db):
        """Verify that a 1h trade in a choppy market (ADX < 25) triggers dynamic chop Milestone at 0.3R."""
        symbol = "BTCUSDT"
        
        # Initialize state
        state = _get_state(symbol)
        state["trade_id"] = 202
        mock_trade_db.get_trade_by_id.return_value = {"id": 202, "direction": "BUY"}
        state["timeframe"] = "60"
        state["original_qty"] = 100.0
        state["milestone_config"] = [
            {"gate_name": "milestone_1", "threshold": 1.5, "close_pct": 0.50}
        ]
        
        # 100 points SL distance, current price moved 30 points in profit (0.3R)
        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "openPrice": 70000.0,
            "currentPrice": 70030.0,  # 30 points profit
            "volume": 75.0,
            "type": "BUY",
            "profit": 30.0,
        }
        
        # Mock ADX to choppy
        indicator_module = MagicMock()
        indicator_module.calculate_adx.return_value = 20.0  # < 25
        
        # Mock CC State original stop loss distance to 100
        cc_state = binance_monitor._get_position_state(symbol)
        cc_state["original_sl_distance"] = 100.0
        
        # Run check
        with patch('binance_monitor.PAPER_MODE', True), patch.dict(sys.modules, {"binance_indicators": indicator_module}):
            _check_milestone_exits(position)
            
        # Assertions
        self.assertIn("regime_aware_chop_profit_taken", state["milestones_hit"])
        mock_trade_db.log_exit.assert_called_once()
        self.assertEqual(mock_trade_db.log_exit.call_args[1]["exit_type"], "regime_aware_chop_profit_taken")
        self.assertAlmostEqual(mock_trade_db.log_exit.call_args.kwargs["qty_pct"], 0.1875, delta=1e-12)

    @patch('binance_monitor.trade_db')
    @patch('binance_indicators.calculate_adx')
    def test_check_milestone_exits_trending_regime(self, mock_adx, mock_trade_db):
        """Verify that a 1h trade in a trending market (ADX >= 25) does NOT trigger the 0.3R chop milestone."""
        symbol = "BTCUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 202
        mock_trade_db.get_trade_by_id.return_value = {"id": 202, "direction": "BUY"}
        state["timeframe"] = "60"
        state["original_qty"] = 1.0
        state["milestone_config"] = [
            {"gate_name": "milestone_1", "threshold": 1.5, "close_pct": 0.50}
        ]
        
        position = {
            "symbol": symbol,
            "openPrice": 70000.0,
            "currentPrice": 70030.0,  # 0.3R
            "volume": 1.0,
            "type": "BUY",
            "profit": 30.0,
        }
        
        mock_adx.return_value = 30.0  # Trending (> 25)
        
        cc_state = binance_monitor._get_position_state(symbol)
        cc_state["original_sl_distance"] = 100.0
        
        _check_milestone_exits(position)
        self.assertNotIn("regime_aware_chop_profit_taken", state.get("milestones_hit", []))

    @patch('binance_monitor.trade_db')
    @patch('binance_indicators.calculate_adx')
    def test_adx_caching_ttl(self, mock_adx, mock_trade_db):
        """Verify that calculate_adx is cached and not queried repeatedly inside the 5-minute window."""
        symbol = "BTCUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 202
        mock_trade_db.get_trade_by_id.return_value = {"id": 202, "direction": "BUY"}
        state["timeframe"] = "60"
        state["original_qty"] = 1.0
        state["milestone_config"] = []
        
        position = {
            "symbol": symbol,
            "openPrice": 70000.0,
            "currentPrice": 70030.0,
            "volume": 1.0,
            "type": "BUY",
            "profit": 30.0,
        }
        
        mock_adx.return_value = 20.0
        cc_state = binance_monitor._get_position_state(symbol)
        cc_state["original_sl_distance"] = 100.0
        
        # 1st run: queries ADX
        _check_milestone_exits(position)
        self.assertEqual(mock_adx.call_count, 1)
        self.assertEqual(state["adx_value"], 20.0)
        
        # 2nd run (immediate): uses cached value, doesn't increment call count
        _check_milestone_exits(position)
        self.assertEqual(mock_adx.call_count, 1)
        
        # Modify fetch time to exceed 5 minutes
        state["adx_fetched_at"] = time.time() - 301
        
        # 3rd run (expired): queries again
        _check_milestone_exits(position)
        self.assertEqual(mock_adx.call_count, 2)

    @patch('binance_monitor.trade_db')
    def test_milestone_exits_use_db_risk_when_sl_state_missing(self, mock_trade_db):
        """Verify that milestone partials still fire when runtime SL-distance state is missing."""
        symbol = "LINKUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 32
        state["original_qty"] = 400.0
        state["milestone_config"] = [
            {"gate_name": "milestone_0", "threshold": 0.5, "close_pct": 0.50}
        ]
        mock_trade_db.get_trade_by_id.return_value = {
            "id": 32,
            "direction": "BUY",
            "entry_price": 7.672,
            "sl": 7.4695,
            "qty": 400.0,
            "risk_dollars": 80.0,
        }
        mock_trade_db.get_binance_order_state.return_value = None

        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "openPrice": 7.672,
            "currentPrice": 7.78,
            "volume": 200.0,
            "type": "BUY",
            "profit": 43.2,
        }

        _check_milestone_exits(position)

        self.assertIn("milestone_0", state["milestones_hit"])
        mock_trade_db.log_exit.assert_called_once()
        self.assertEqual(mock_trade_db.log_exit.call_args[1]["exit_type"], "milestone_0")
        self.assertAlmostEqual(mock_trade_db.log_exit.call_args.kwargs["qty_pct"], 0.25, delta=1e-12)

    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.has_exchange_protection')
    @patch('binance_monitor._place_sl_tp_order')
    @patch('binance_monitor._get_client')
    def test_partial_close_refreshes_remaining_protection_before_canceling_old(
        self, mock_get_client, mock_place_order, mock_has_protection, mock_trade_db
    ):
        symbol = "LINKUSDT"
        client = MagicMock()
        client.futures_get_open_orders.return_value = [
            {"symbol": symbol, "orderId": 10, "type": "STOP_MARKET"},
        ]
        client.futures_get_open_algo_orders.return_value = [
            {"symbol": symbol, "algoId": 20, "orderType": "TAKE_PROFIT_MARKET"},
        ]
        mock_get_client.return_value = client
        mock_place_order.side_effect = [
            {"success": True, "orderId": "new_sl"},
            {"success": True, "orderId": "new_tp"},
        ]
        mock_has_protection.return_value = (True, {"has_sl": True, "has_tp": True})

        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "type": "SELL",
            "stopLoss": 9.52,
            "takeProfit": 9.031,
        }

        with patch('binance_monitor.PAPER_MODE', False):
            ok = _refresh_remaining_protection_after_partial(position, 8.96)

        self.assertTrue(ok)
        self.assertEqual(mock_place_order.call_count, 2)
        mock_place_order.assert_any_call(
            client=client,
            symbol=symbol,
            side="BUY",
            order_type="STOP_MARKET",
            stop_price=9.52,
            quantity=8.96,
            position_side="SHORT",
        )
        mock_place_order.assert_any_call(
            client=client,
            symbol=symbol,
            side="BUY",
            order_type="TAKE_PROFIT_MARKET",
            stop_price=9.031,
            quantity=8.96,
            position_side="SHORT",
        )
        mock_has_protection.assert_called_once()
        client.futures_cancel_order.assert_called_once_with(symbol=symbol, orderId=10)
        client.futures_cancel_algo_order.assert_called_once_with(symbol=symbol, algoId=20)
        mock_trade_db.upsert_binance_order_state.assert_called_once()

    @patch('binance_monitor.has_exchange_protection')
    @patch('binance_monitor._place_sl_tp_order')
    @patch('binance_monitor._get_client')
    def test_partial_close_keeps_old_protection_when_refresh_unverified(
        self, mock_get_client, mock_place_order, mock_has_protection
    ):
        symbol = "LINKUSDT"
        client = MagicMock()
        client.futures_get_open_orders.return_value = [
            {"symbol": symbol, "orderId": 10, "type": "STOP_MARKET"},
        ]
        client.futures_get_open_algo_orders.return_value = [
            {"symbol": symbol, "algoId": 20, "orderType": "TAKE_PROFIT_MARKET"},
        ]
        mock_get_client.return_value = client
        mock_place_order.side_effect = [
            {"success": True, "orderId": "new_sl"},
            {"success": True, "orderId": "new_tp"},
        ]
        mock_has_protection.return_value = (False, {"has_sl": True, "has_tp": False})

        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "type": "SELL",
            "stopLoss": 9.52,
            "takeProfit": 9.031,
        }

        with patch('binance_monitor.PAPER_MODE', False):
            ok = _refresh_remaining_protection_after_partial(position, 8.96)

        self.assertFalse(ok)
        client.futures_cancel_order.assert_not_called()
        client.futures_cancel_algo_order.assert_not_called()

    @patch('binance_monitor.get_post_fill_protection_mode', return_value="repair")
    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.has_exchange_protection')
    @patch('binance_monitor._place_sl_tp_order')
    @patch('binance_monitor._get_client')
    def test_monitor_repairs_missing_live_protection_after_verification(
        self, mock_get_client, mock_place_order, mock_has_protection, mock_trade_db, _mock_mode
    ):
        symbol = "LINKUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 777

        trade_row = {
            "sl": 9.52,
            "tp": 9.031,
        }
        mock_trade_db.get_trade_by_id.return_value = trade_row

        client = MagicMock()
        client.futures_get_open_orders.side_effect = [
            [],
            [],
            [{"symbol": symbol, "orderId": "new_sl", "type": "STOP_MARKET", "side": "BUY", "reduceOnly": True}],
        ]
        client.futures_get_open_algo_orders.side_effect = [
            [],
            [],
            [{"symbol": symbol, "algoId": "new_tp", "orderType": "TAKE_PROFIT_MARKET", "side": "BUY", "reduceOnly": True}],
        ]
        mock_get_client.return_value = client
        mock_has_protection.side_effect = [
            (False, {"has_sl": False, "has_tp": False}),
            (True, {"has_sl": True, "has_tp": True}),
        ]
        mock_place_order.side_effect = [
            {"success": True, "orderId": "new_sl"},
            {"success": True, "orderId": "new_tp"},
        ]

        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "type": "SELL",
            "volume": 8.96,
        }

        with patch('binance_monitor.PAPER_MODE', False):
            ok = _repair_missing_protection_if_needed(position)

        self.assertTrue(ok)
        self.assertEqual(mock_place_order.call_count, 2)
        mock_place_order.assert_any_call(
            client=client,
            symbol=symbol,
            side="BUY",
            order_type="STOP_MARKET",
            stop_price=9.52,
            quantity=8.96,
            position_side="SHORT",
        )
        mock_place_order.assert_any_call(
            client=client,
            symbol=symbol,
            side="BUY",
            order_type="TAKE_PROFIT_MARKET",
            stop_price=9.031,
            quantity=8.96,
            position_side="SHORT",
        )
        mock_trade_db.upsert_binance_order_state.assert_called_once()

    @patch('binance_monitor.get_post_fill_protection_mode', return_value="repair")
    @patch('binance_monitor.trade_db')
    @patch('binance_monitor.has_exchange_protection')
    @patch('binance_monitor._place_sl_tp_order')
    @patch('binance_monitor._get_client')
    def test_monitor_does_not_cancel_old_protection_when_repair_unverified(
        self, mock_get_client, mock_place_order, mock_has_protection, mock_trade_db, _mock_mode
    ):
        symbol = "LINKUSDT"
        state = _get_state(symbol)
        state["trade_id"] = 778
        mock_trade_db.get_trade_by_id.return_value = {"sl": 9.52, "tp": 9.031}

        client = MagicMock()
        client.futures_get_open_orders.side_effect = [
            [{"symbol": symbol, "orderId": 10, "type": "STOP_MARKET"}],
            [{"symbol": symbol, "orderId": 10, "type": "STOP_MARKET"}],
            [{"symbol": symbol, "orderId": 10, "type": "STOP_MARKET"}],
        ]
        client.futures_get_open_algo_orders.side_effect = [
            [{"symbol": symbol, "algoId": 20, "orderType": "TAKE_PROFIT_MARKET"}],
            [{"symbol": symbol, "algoId": 20, "orderType": "TAKE_PROFIT_MARKET"}],
            [{"symbol": symbol, "algoId": 20, "orderType": "TAKE_PROFIT_MARKET"}],
        ]
        mock_get_client.return_value = client
        mock_has_protection.side_effect = [
            (False, {"has_sl": False, "has_tp": False}),
            (False, {"has_sl": True, "has_tp": False}),
        ]
        mock_place_order.side_effect = [
            {"success": True, "orderId": "new_sl"},
            {"success": True, "orderId": "new_tp"},
        ]

        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "type": "SELL",
            "volume": 8.96,
        }

        with patch('binance_monitor.PAPER_MODE', False):
            ok = _repair_missing_protection_if_needed(position)

        self.assertFalse(ok)
        client.futures_cancel_order.assert_not_called()
        client.futures_cancel_algo_order.assert_not_called()

    @patch('binance_monitor.trade_db')
    def test_partial_aware_milestone_close_uses_remaining_qty(self, mock_trade_db):
        """Verify that milestone close quantity is based on live exchange position qty (volume), not original_qty."""
        symbol = "WLDUSDT"
        
        # Initialize state
        state = _get_state(symbol)
        state["trade_id"] = 1001
        state["direction"] = "BUY"
        state["original_qty"] = 1000.0  # Stale/original qty is 1000
        state["milestone_config"] = [
            {"gate_name": "milestone_0", "threshold": 0.5, "close_pct": 0.25}
        ]
        
        mock_trade_db.get_trade_by_id.return_value = {"id": 1001, "direction": "BUY"}
        
        # Live position volume is 500.0 (already reduced/partial)
        position = {
            "symbol": symbol,
            "tv_symbol": symbol,
            "openPrice": 10.0,
            "currentPrice": 12.0,  # Moved in profit direction
            "volume": 500.0,       # Live remaining qty is 500.0
            "type": "BUY",
            "profit": 1000.0,
        }
        
        # Set original_sl_distance to 1.0 (so 2.0 profit / 1.0 = 2.0R, triggering milestone_0)
        cc_state = binance_monitor._get_position_state(symbol)
        cc_state["original_sl_distance"] = 1.0
        
        # Run check
        with patch('binance_monitor.PAPER_MODE', True), \
             patch('binance_monitor.plain_log') as mock_log:
            _check_milestone_exits(position)
            
            # Assertions
            # PAPER_MILESTONE should log a close qty of 125.0 (500.0 * 0.25) rather than 250.0 (1000.0 * 0.25)
            paper_logs = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "PAPER_MILESTONE"]
            self.assertEqual(len(paper_logs), 1)
            self.assertEqual(paper_logs[0]["qty"], 125.0) # 500 * 0.25 = 125
            self.assertEqual(paper_logs[0]["remaining"], 375.0)


if __name__ == "__main__":
    unittest.main()
