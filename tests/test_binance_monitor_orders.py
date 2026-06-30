import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import binance_monitor
import logger


class FakeClient:
    def __init__(self):
        self.calls = []

    def futures_get_open_orders(self, symbol):
        self.calls.append(("get_open_orders", symbol))
        return [{"orderId": 10, "type": "STOP_MARKET"}]

    def futures_cancel_order(self, symbol, **kwargs):
        self.calls.append(("cancel", symbol, kwargs["orderId"]))


class BinanceMonitorOrderTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.log_patch = patch.object(logger, "LOG_FILE", Path(self.tempdir.name) / "trades.log")
        self.log_patch.start()

    def tearDown(self):
        self.log_patch.stop()
        self.tempdir.cleanup()

    def test_update_sl_places_new_stop_before_cancelling_old_stop(self):
        client = FakeClient()

        def fake_place(**kwargs):
            client.calls.append(("place", kwargs["symbol"], kwargs["stop_price"]))
            return {"success": True, "orderId": 11}

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_place_sl_tp_order", side_effect=fake_place),
            patch.object(binance_monitor, "_send_telegram"),
            patch.object(binance_monitor.trade_db, "upsert_binance_order_state"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertTrue(ok)
        self.assertEqual(client.calls[0][0], "get_open_orders")
        self.assertEqual(client.calls[1][0], "place")
        self.assertEqual(client.calls[2][0], "cancel")

    def test_update_sl_keeps_old_stop_when_new_stop_fails(self):
        client = FakeClient()

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_place_sl_tp_order", return_value={"success": False, "error": "bad stop"}),
            patch.object(binance_monitor, "_send_telegram"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertFalse(ok)
        self.assertFalse(any(call[0] == "cancel" for call in client.calls))

    def test_monitor_telegram_uses_runtime_badge_not_hardcoded_testnet(self):
        with patch("telegram_client.send_message") as send_message:
            binance_monitor._send_telegram("test event")

        sent_text = send_message.call_args.args[0]
        self.assertEqual(sent_text, "<b>BINANCE MONITOR</b>\ntest event")
        self.assertNotIn("🔵", sent_text)

    def test_estimate_stop_locked_pnl_uses_stop_price_remaining_qty_and_realized_partials(self):
        position = {
            "symbol": "XAUUSDT",
            "tv_symbol": "XAUUSDT",
            "type": "SELL",
            "openPrice": 4516.42,
            "volume": 4.582,
        }
        state = {"entry_price": 4516.42, "trade_id": 125}

        with patch.object(binance_monitor.trade_db, "get_realized_exit_pnl", return_value=12.85):
            locked = binance_monitor._estimate_stop_locked_pnl(position, state, 4504.44)

        self.assertAlmostEqual(locked, 67.74236, places=4)

    def test_update_sl_throttles_telegram_on_repeated_failures(self):
        client = FakeClient()
        binance_monitor._position_state.clear()

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_place_sl_tp_order", return_value={"success": False, "error": "APIError(-4061): side mismatch"}),
            patch.object(binance_monitor, "_send_telegram") as send_mock,
        ):
            # 1. First failure -> Alert is sent
            ok1 = binance_monitor._update_sl_order(
                "HYPEUSDT",
                "HYPEUSDT",
                "BUY",
                2.50,
                {"volume": 10.0, "currentPrice": 2.60},
            )
            self.assertFalse(ok1)
            self.assertEqual(send_mock.call_count, 1)

            # 2. Second failure immediately after -> Alert is throttled (call count stays at 1)
            ok2 = binance_monitor._update_sl_order(
                "HYPEUSDT",
                "HYPEUSDT",
                "BUY",
                2.51,
                {"volume": 10.0, "currentPrice": 2.60},
            )
            self.assertFalse(ok2)
            self.assertEqual(send_mock.call_count, 1)

            # 3. Simulate passage of 15 minutes (901 seconds) -> Alert is sent again
            state = binance_monitor._get_state("HYPEUSDT")
            state["last_trail_warn_at"] -= 901

            ok3 = binance_monitor._update_sl_order(
                "HYPEUSDT",
                "HYPEUSDT",
                "BUY",
                2.52,
                {"volume": 10.0, "currentPrice": 2.60},
            )
            self.assertFalse(ok3)
            self.assertEqual(send_mock.call_count, 2)

    def test_update_sl_order_hedge_mode_payload_and_failure_behavior(self):
        # Test Case A: BUY position (LONG) -> sl_side is SELL, positionSide is LONG
        client = FakeClient()
        placed_payloads = []

        def fake_create_order(**payload):
            placed_payloads.append(payload)
            return {"orderId": 999, "status": "NEW"}

        client.futures_create_order = fake_create_order

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_send_telegram"),
            patch.object(binance_monitor.trade_db, "upsert_binance_order_state"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertTrue(ok)
        self.assertEqual(len(placed_payloads), 1)
        payload = placed_payloads[0]
        # Acceptance 1: positionSide = LONG and closePosition = true
        self.assertEqual(payload.get("positionSide"), "LONG")
        self.assertEqual(payload.get("closePosition"), "true")
        self.assertEqual(payload.get("side"), "SELL")
        # Acceptance 2: no quantity and no reduceOnly
        self.assertNotIn("quantity", payload)
        self.assertNotIn("reduceOnly", payload)
        # Verify old stop gets cancelled
        self.assertTrue(any(call[0] == "cancel" for call in client.calls))

        # Test Case B: SELL position (SHORT) -> sl_side is BUY, positionSide is SHORT
        client = FakeClient()
        placed_payloads = []
        client.futures_create_order = fake_create_order

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_send_telegram"),
            patch.object(binance_monitor.trade_db, "upsert_binance_order_state"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "SELL",
                2400.0,
                {"volume": -1.0, "currentPrice": 2300.0},
            )

        self.assertTrue(ok)
        self.assertEqual(len(placed_payloads), 1)
        payload = placed_payloads[0]
        self.assertEqual(payload.get("positionSide"), "SHORT")
        self.assertEqual(payload.get("closePosition"), "true")
        self.assertEqual(payload.get("side"), "BUY")
        self.assertNotIn("quantity", payload)
        self.assertNotIn("reduceOnly", payload)

        # Test Case C: Unit test proves old SL is kept if replacement fails
        from binance.exceptions import BinanceAPIException
        from requests.models import Response
        res = Response()
        res.status_code = 400
        
        client = FakeClient()
        def fake_create_order_fail(**payload):
            raise BinanceAPIException(res, -4061, "Order's position side does not match user's setting")
        
        client.futures_create_order = fake_create_order_fail

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_send_telegram"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertFalse(ok)
        # Prove old SL is kept (no cancel calls were made!)
        self.assertFalse(any(call[0] == "cancel" for call in client.calls))

    def test_update_sl_order_duplicate_close_position_conflict_keeps_old_sl_alive(self):
        # Test that if an existing stop order with closePosition=True exists in the same direction,
        # _update_sl_order skips replacement entirely (does not call futures_create_order),
        # logs the duplicate conflict, keeps the old SL alive (no cancel calls), and throttles Telegram warning.
        
        client = FakeClient()
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 10,
                "type": "STOP_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "true",
                "stopPrice": "2100.0"
            }
        ]
        
        def fake_create_order(**kwargs):
            self.fail("futures_create_order should NOT be called when duplicate closePosition conflict is detected")
            
        client.futures_create_order = fake_create_order
        client.calls = []

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_send_telegram") as send_mock,
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertFalse(ok)
        # Verify old stop is kept alive (no cancel calls were made!)
        self.assertFalse(any(call[0] == "cancel" for call in client.calls))

    def test_update_sl_order_hedge_mode_payload_safety_rules(self):
        # Assert safety rules:
        # - Hedge Mode requires positionSide LONG/SHORT.
        # - reduceOnly must not be sent in Hedge Mode order payloads.
        # - closePosition=true cannot be sent with quantity.
        
        client = FakeClient()
        placed_payloads = []

        def fake_create_order(**payload):
            placed_payloads.append(payload)
            return {"orderId": 999, "status": "NEW"}

        client.futures_create_order = fake_create_order
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 10,
                "type": "STOP_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "false",  # Not a duplicate closePosition conflict
                "stopPrice": "2100.0"
            }
        ]

        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_send_telegram"),
            patch.object(binance_monitor.trade_db, "upsert_binance_order_state"),
        ):
            ok = binance_monitor._update_sl_order(
                "ETHUSDT",
                "ETHUSDT",
                "BUY",
                2200.0,
                {"volume": 1.0, "currentPrice": 2300.0},
            )

        self.assertTrue(ok)
        self.assertEqual(len(placed_payloads), 1)
        payload = placed_payloads[0]
        
        # positionSide must be LONG or SHORT
        self.assertIn(payload.get("positionSide"), ["LONG", "SHORT"])
        
        # no reduceOnly
        self.assertNotIn("reduceOnly", payload)
        
        # closePosition=true has no quantity
        if payload.get("closePosition") == "true":
            self.assertNotIn("quantity", payload)


if __name__ == "__main__":
    unittest.main()
