import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, '/home/rick/ozzy-bot')

import logger
import telegram_command_bot
import command_center
from command_center import CommandType, cmd_regime
import binance_connector
from binance_connector import check_order_book_spread, _execute_trade, close_position, close_position_qty, get_open_positions
import trade_db


class FakeClient:
    """Minimal Binance futures stub for unit tests.

    All methods that touch the network are implemented as no-ops or
    return deterministic test data.  Critically, ``futures_get_order``
    and ``futures_get_algo_order`` are included so that the protection
    verifier (``verify_protection_order``) never raises AttributeError
    against this stub.
    """

    def __init__(self):
        self.orders = []
        self.events = []
        self.canceled_orders = []
        self.canceled_algo_orders = []
        self.cancel_all_symbols = []
        self.positions = []
        self.open_orders = []
        self.open_algo_orders = []
        self.order_statuses = {}
        self.algo_statuses = {}
        self.market_avg_price = "75000"
        self.spread_bids = [["75000.00", "1.0"]]
        self.spread_asks = [["75037.50", "1.0"]]  # 0.05% spread

    def futures_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": "75000"}

    def futures_order_book(self, symbol, limit=5):
        return {
            "bids": self.spread_bids,
            "asks": self.spread_asks,
        }

    def futures_create_order(self, **kwargs):
        self.events.append(("create", kwargs.get("type"), kwargs.get("symbol")))
        order_id = len(self.orders) + 1
        self.orders.append(kwargs)
        avg_price = self.market_avg_price if kwargs.get("type") == "MARKET" else "75000"
        order = {
            "orderId": order_id,
            "avgPrice": avg_price,
            "symbol": kwargs.get("symbol"),
            "side": kwargs.get("side"),
            "type": kwargs.get("type"),
            "status": "NEW",
            "stopPrice": kwargs.get("stopPrice", "0"),
            "reduceOnly": kwargs.get("reduceOnly", False),
        }
        self.order_statuses[str(order_id)] = order
        if kwargs.get("type") == "MARKET" and kwargs.get("reduceOnly"):
            for pos in self.positions:
                if pos.get("symbol") == kwargs.get("symbol"):
                    pos["positionAmt"] = "0"
        return {"orderId": order_id, "avgPrice": avg_price}

    def futures_position_information(self, symbol=None):
        return self.positions

    def futures_get_open_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_orders if o.get("symbol") == symbol]
        return self.open_orders

    def futures_get_open_algo_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_algo_orders if o.get("symbol") == symbol]
        return self.open_algo_orders

    def futures_cancel_order(self, symbol, orderId):
        self.events.append(("cancel", orderId, symbol))
        self.canceled_orders.append(orderId)
        self.open_orders = [o for o in self.open_orders if o.get("orderId") != orderId]
        return {"status": "CANCELED", "orderId": orderId}

    def futures_cancel_algo_order(self, symbol, algoId):
        self.events.append(("cancel_algo", algoId, symbol))
        self.canceled_algo_orders.append(algoId)
        self.open_algo_orders = [o for o in self.open_algo_orders if o.get("algoId") != algoId]
        return {"status": "SUCCESS", "algoId": algoId}

    def futures_cancel_all_open_orders(self, symbol):
        self.events.append(("cancel_all", symbol))
        self.cancel_all_symbols.append(symbol)
        return {"status": "CANCELED", "symbol": symbol}

    def futures_get_order(self, symbol, **kwargs):
        """Look up a placed order by orderId — required by verify_protection_order."""
        order_id = kwargs.get("orderId")
        return self.order_statuses.get(
            str(order_id),
            {
                "symbol": symbol,
                "orderId": order_id,
                "status": "NEW",
                "type": "STOP_MARKET",
                "side": "SELL",
                "stopPrice": "0",
                "reduceOnly": True,
            },
        )

    def futures_get_algo_order(self, symbol, **kwargs):
        """Look up a placed algo order by algoId — required by verify_protection_order."""
        algo_id = str(kwargs.get("algoId", ""))
        return self.algo_statuses.get(
            algo_id,
            {
                "symbol": symbol,
                "algoStatus": "WORKING",
                "type": "STOP_MARKET",
                "side": "SELL",
                "triggerPrice": "0",
                "reduceOnly": True,
            },
        )


class TestAuditUpgrades(unittest.TestCase):
    """
    Isolation contract
    ------------------
    Every test in this class must be completely hermetic with respect to
    the host filesystem and Telegram transport:

    * ``logger.LOG_FILE`` is redirected to a throwaway temp file so that
      no test output ever lands in the real trades.log or in the
      live_micro/trades_live.log path (regardless of what ``HERMES_LOG_FILE``
      is set to in the environment when the test runner is invoked).
    * ``trade_db.DB_PATH`` is redirected to a temp SQLite file so we never
      touch the production or live-micro database.
    * ``telegram_client.send_message`` is stubbed out so the bot never
      fires real Telegram notifications during tests.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        # Redirect log output away from any real log file.
        self.log_patch = patch.object(
            logger, "LOG_FILE", str(Path(self.tempdir.name) / "trades_test.log")
        )
        # Redirect DB away from production/live-micro databases.
        self.db_patch = patch.object(
            trade_db, "DB_PATH", Path(self.tempdir.name) / "trades_test.db"
        )
        # Silence Telegram transport entirely.
        self.telegram_patch = patch("telegram_client.send_message")
        self.log_patch.start()
        self.db_patch.start()
        self.telegram_patch.start()

    def tearDown(self):
        self.telegram_patch.stop()
        self.db_patch.stop()
        self.log_patch.stop()
        self.tempdir.cleanup()

    def test_parse_command_regime(self):
        """Test that /regime command parses correctly with different formats."""
        # 1. Standard slash command
        cmd, kwargs = telegram_command_bot.parse_command("/regime BTCUSDT")
        self.assertEqual(cmd, "regime")
        self.assertEqual(kwargs["symbol"], "BTCUSDT")
        self.assertEqual(kwargs["interval"], "1h")

        # 2. Slash command with custom interval
        cmd, kwargs = telegram_command_bot.parse_command("/regime ETHUSDT 15m")
        self.assertEqual(cmd, "regime")
        self.assertEqual(kwargs["symbol"], "ETHUSDT")
        self.assertEqual(kwargs["interval"], "15m")

        # 3. Natural language variants
        cmd, kwargs = telegram_command_bot.parse_command("what is the current regime of btc?")
        self.assertEqual(cmd, "regime")
        self.assertEqual(kwargs["symbol"], "BTCUSDT")
        self.assertEqual(kwargs["interval"], "1h")

        cmd, kwargs = telegram_command_bot.parse_command("show me market condition for SOL on 4h timeframe")
        self.assertEqual(cmd, "regime")
        self.assertEqual(kwargs["symbol"], "SOLUSDT")
        self.assertEqual(kwargs["interval"], "4h")

    @patch("binance_connector._get_client")
    @patch("binance_connector.PAPER_MODE", False)
    def test_get_open_positions_skips_zero_and_dust(self, mock_get_client):
        client = FakeClient()
        client.positions = [
            {"symbol": "ETHUSDT", "positionAmt": "0"},
            {"symbol": "BTCUSDT", "positionAmt": "0.000000001"},
            {"symbol": "SOLUSDT", "positionAmt": "1.25"},
            {"symbol": "LINKUSDT", "positionAmt": "-2.5"},
        ]
        mock_get_client.return_value = client

        rows = get_open_positions()
        symbols = [r["symbol"] for r in rows]
        self.assertEqual(symbols, ["SOLUSDT", "LINKUSDT"])
        self.assertEqual(rows[0]["type"], "BUY")
        self.assertEqual(rows[1]["type"], "SELL")

    @patch('command_center._get_client')
    @patch('binance_indicators.calculate_adx')
    @patch('binance_indicators.get_live_indicators')
    def test_cmd_regime_trending_success(self, mock_get_live, mock_adx, mock_get_client):
        """Test cmd_regime returns premium trending regime report when ADX >= 25."""
        # Setup mock client & responses
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.futures_symbol_ticker.return_value = {"symbol": "BTCUSDT", "price": "75000.00"}

        mock_adx.return_value = 32.5  # Trending
        mock_get_live.return_value = {
            "atr": 1500.0,
            "close": 75000.0
        }

        res = cmd_regime("BTCUSDT", "1h")
        self.assertTrue(res.success)
        self.assertEqual(res.command, "regime")
        self.assertIn("TRENDING", res.message)
        self.assertIn("32.50", res.message)
        self.assertIn("1500.00", res.message)
        self.assertIn("2.00%", res.message)  # 1500 / 75000 = 2%

    @patch('command_center._get_client')
    @patch('binance_indicators.calculate_adx')
    @patch('binance_indicators.get_live_indicators')
    def test_cmd_regime_choppy_success(self, mock_get_live, mock_adx, mock_get_client):
        """Test cmd_regime returns premium choppy regime report when ADX < 25."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.futures_symbol_ticker.return_value = {"symbol": "ETHUSDT", "price": "3000.00"}

        mock_adx.return_value = 18.2  # Choppy
        mock_get_live.return_value = {
            "atr": 90.0,
            "close": 3000.0
        }

        res = cmd_regime("ETHUSDT", "1h")
        self.assertTrue(res.success)
        self.assertIn("CHOPPY / RANGE", res.message)
        self.assertIn("18.20", res.message)
        self.assertIn("90.00", res.message)
        self.assertIn("3.00%", res.message)  # 90 / 3000 = 3%

    def test_check_order_book_spread_calculation(self):
        """Test check_order_book_spread computes correct spread pct and returns expected results."""
        client = FakeClient()
        
        # Test normal spread (0.05% < 0.15%)
        client.spread_bids = [["1000.00", "5.0"]]
        client.spread_asks = [["1000.50", "2.0"]]
        is_ok, spread_pct, bid, ask = check_order_book_spread(client, "ETHUSDT")
        self.assertTrue(is_ok)
        self.assertAlmostEqual(spread_pct, 0.05)
        self.assertEqual(bid, 1000.0)
        self.assertEqual(ask, 1000.5)

        # Test wide spread (0.80% > 0.55%)
        client.spread_bids = [["1000.00", "5.0"]]
        client.spread_asks = [["1008.00", "2.0"]]
        is_ok, spread_pct, bid, ask = check_order_book_spread(client, "ETHUSDT")
        self.assertFalse(is_ok)
        self.assertAlmostEqual(spread_pct, 0.80)

    @patch('binance_connector._get_client')
    @patch('binance_connector.get_balance')
    @patch('binance_connector._set_leverage')
    def test_execute_trade_slippage_protection_blocks(self, mock_leverage, mock_balance, mock_get_client):
        """Verify that pre-trade slippage checks throw a ValueError when spread is too wide."""
        client = FakeClient()
        mock_get_client.return_value = client
        mock_balance.return_value = {"equity": 200.0, "available": 200.0}

        # Setup wide spread
        client.spread_bids = [["75000.00", "1.0"]]
        client.spread_asks = [["75600.00", "1.0"]]  # 0.80% spread > 0.55% max

        with self.assertRaises(ValueError) as context:
            _execute_trade(
                signal="BUY",
                tv_symbol="BTCUSDT",
                lot=0.002,
                sl_distance=500.0,
                rr=2.0
            )

        self.assertIn("Slippage Protection", str(context.exception))
        self.assertIn("0.8000%", str(context.exception))
        self.assertEqual(len(client.orders), 0)

    @patch('binance_connector._get_client')
    @patch('binance_connector.get_balance')
    @patch('binance_connector._set_leverage')
    @patch('trade_db.upsert_binance_order_state')
    def test_execute_trade_slippage_protection_passes(self, mock_upsert, mock_leverage, mock_balance, mock_get_client):
        """Verify that pre-trade slippage checks pass when spread is tight."""
        client = FakeClient()
        mock_get_client.return_value = client
        mock_balance.return_value = {"equity": 200.0, "available": 200.0}

        # Setup tight spread (0.05%)
        client.spread_bids = [["75000.00", "1.0"]]
        client.spread_asks = [["75037.50", "1.0"]]

        # Run execute trade with observe mode to avoid repair lookup side effects in full test suite
        with (
            patch.object(binance_connector, "POST_FILL_PROTECTION_TESTNET_MODE", "observe"),
            patch.object(binance_connector, "POST_FILL_PROTECTION_LIVE_MODE", "observe"),
        ):
            res = _execute_trade(
                signal="BUY",
                tv_symbol="BTCUSDT",
                lot=0.002,
                sl_distance=500.0,
                rr=2.0
            )
        self.assertEqual(res["order_id"], 1)
        self.assertGreaterEqual(len(client.orders), 1)

    @patch('binance_connector._get_client')
    def test_close_position_bypasses_wide_spread_block(self, mock_get_client):
        """Verify that position close exits proceed and are never blocked, even under wide spread conditions."""
        client = FakeClient()
        mock_get_client.return_value = client
        
        # Position info shows an active BTC position of 0.002 BTC
        client.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.002"}]

        # Setup wide spread
        client.spread_bids = [["75000.00", "1.0"]]
        client.spread_asks = [["75600.00", "1.0"]]  # 0.80%

        # Run position close — should complete successfully instead of throwing
        res = close_position("BTCUSDT")
        self.assertEqual(res["status"], "closed")
        self.assertEqual(res["order_id"], 1)
        self.assertEqual(len(client.orders), 1)

    @patch("command_center.PAPER_MODE", False)
    @patch("command_center._get_client")
    def test_cmd_panic_closes_then_cancels_only_after_flat_confirmation(self, mock_get_client):
        """Panic closes positions and cancels leftovers only after exchange confirms flat."""
        client = FakeClient()
        client.positions = [{"symbol": "ETHUSDT", "positionAmt": "0.5"}]
        mock_get_client.return_value = client

        with (
            patch.object(command_center, "HALT_FILE", str(Path(self.tempdir.name) / "HALT")),
            patch("command_center.close_position", side_effect=lambda sym: client.futures_create_order(
                symbol=sym,
                side="SELL",
                type="MARKET",
                quantity=0.5,
                reduceOnly=True,
            ) or {"status": "closed"}),
        ):
            result = command_center.cmd_panic()

        self.assertTrue(result.success)
        self.assertEqual(result.details["closed_symbols"], ["ETHUSDT"])
        self.assertEqual(result.details["cancelled_symbols"], ["ETHUSDT"])
        self.assertEqual(client.events[-1], ("cancel_all", "ETHUSDT"))

    @patch("command_center.PAPER_MODE", False)
    @patch("command_center._get_client")
    @patch("telegram_client.notify_system_event")
    def test_cmd_panic_keeps_orders_when_position_remains_open(self, mock_notify, mock_get_client):
        """Panic must not cancel protective orders if close does not flatten the position."""
        client = FakeClient()
        client.positions = [{"symbol": "ETHUSDT", "positionAmt": "0.5"}]
        mock_get_client.return_value = client

        with (
            patch.object(command_center, "HALT_FILE", str(Path(self.tempdir.name) / "HALT")),
            patch("command_center.close_position", return_value={"status": "error", "error": "boom"}),
        ):
            result = command_center.cmd_panic()

        self.assertFalse(result.success)
        self.assertEqual(result.details["cancelled_symbols"], [])
        self.assertEqual(client.cancel_all_symbols, [])
        self.assertIn("protective orders retained", result.details["errors"][0])
        mock_notify.assert_called()

    @patch("command_center.PAPER_MODE", False)
    @patch("command_center._get_client")
    @patch("command_center.get_open_positions")
    def test_cmd_update_sl_verifies_new_stop_before_canceling_old_standard_and_algo(self, mock_positions, mock_get_client):
        """Manual SL replacement places and verifies new stop before old standard/ALGO stops are canceled."""
        client = FakeClient()
        client.open_orders = [{"symbol": "ETHUSDT", "type": "STOP_MARKET", "orderId": 101}]
        client.open_algo_orders = [{"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "algoId": 202}]
        mock_get_client.return_value = client
        mock_positions.return_value = [{
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "type": "BUY",
            "openPrice": 2000.0,
            "currentPrice": 2020.0,
            "volume": 0.5,
        }]

        result = command_center.cmd_update_sl("ETHUSDT", price=1990.0)

        self.assertTrue(result.success)
        self.assertEqual(client.events[0], ("create", "STOP_MARKET", "ETHUSDT"))
        self.assertIn(("cancel", 101, "ETHUSDT"), client.events)
        self.assertIn(("cancel_algo", 202, "ETHUSDT"), client.events)

    @patch("command_center.PAPER_MODE", False)
    @patch("command_center._get_client")
    @patch("command_center.get_open_positions")
    @patch("command_center.verify_protection_order")
    def test_cmd_update_sl_keeps_old_orders_when_verification_fails(
        self,
        mock_verify,
        mock_positions,
        mock_get_client,
    ):
        """Manual SL replacement must retain old orders when the replacement cannot be verified."""
        client = FakeClient()
        client.open_orders = [{"symbol": "ETHUSDT", "type": "STOP_MARKET", "orderId": 101}]
        client.open_algo_orders = [{"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "algoId": 202}]
        mock_get_client.return_value = client
        mock_verify.return_value = (False, {"reason": "not live"})
        mock_positions.return_value = [{
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "type": "BUY",
            "openPrice": 2000.0,
            "currentPrice": 2020.0,
            "volume": 0.5,
        }]

        result = command_center.cmd_update_sl("ETHUSDT", price=1990.0)

        self.assertFalse(result.success)
        self.assertEqual(client.canceled_orders, [])
        self.assertEqual(client.canceled_algo_orders, [])
        self.assertIn("old protection was kept live", result.message)

    @patch("command_center.PAPER_MODE", False)
    @patch("command_center._get_client")
    @patch("command_center.get_open_positions")
    @patch("command_center._place_sl_tp_order")
    def test_cmd_update_tp_keeps_old_orders_when_new_order_fails(
        self,
        mock_place,
        mock_positions,
        mock_get_client,
    ):
        """Manual TP replacement must retain old TP orders when placement fails."""
        client = FakeClient()
        client.open_orders = [{"symbol": "ETHUSDT", "type": "TAKE_PROFIT_MARKET", "orderId": 301}]
        client.open_algo_orders = [{"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "algoId": 402}]
        mock_get_client.return_value = client
        mock_place.return_value = {"success": False, "error": "bad tp"}
        mock_positions.return_value = [{
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "type": "BUY",
            "openPrice": 2000.0,
            "currentPrice": 2020.0,
            "volume": 0.5,
        }]

        result = command_center.cmd_update_tp("ETHUSDT", price=2050.0)

        self.assertFalse(result.success)
        self.assertEqual(client.canceled_orders, [])
        self.assertEqual(client.canceled_algo_orders, [])
        self.assertIn("old protection was kept live", result.message)

    def test_legacy_twelvedata_provider_is_removed(self):
        self.assertFalse((Path(__file__).resolve().parents[1] / "twelvedata_client.py").exists())


if __name__ == '__main__':
    unittest.main()
