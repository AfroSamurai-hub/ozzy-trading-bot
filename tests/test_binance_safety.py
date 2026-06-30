import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import binance_connector
import logger
import trade_db


class FakeClient:
    def __init__(self):
        self.orders = []
        self.positions = []
        self.open_orders = []
        self.order_statuses = {}
        self.algo_statuses = {}
        self.market_avg_price = "100"
        self.market_price = "100"
        self.xau_reject_cap_notional = None
        self.exchange_info_payload = {
            "symbols": [
                {
                    "symbol": "XAUUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                    ],
                }
            ]
        }
        self.leverage_bracket_payload = [
            {
                "symbol": "XAUUSDT",
                "brackets": [
                    {"initialLeverage": 20, "notionalCap": 50000},
                ],
            }
        ]

    def futures_symbol_ticker(self, symbol):
        return {"price": str(self.market_price)}

    def futures_order_book(self, symbol, limit=5):
        return {"bids": [["99.95", "10"]], "asks": [["100.00", "10"]]}

    def futures_create_order(self, **kwargs):
        if (
            kwargs.get("symbol") == "XAUUSDT"
            and kwargs.get("type") == "MARKET"
            and self.xau_reject_cap_notional is not None
        ):
            qty = float(kwargs.get("quantity") or 0.0)
            if qty * float(self.market_price) > float(self.xau_reject_cap_notional):
                raise RuntimeError("APIError(code=-2027): Exceeded the maximum allowable position at current leverage.")
        order_id = len(self.orders) + 1
        self.orders.append(kwargs)
        self.order_statuses[str(order_id)] = {
            "symbol": kwargs.get("symbol"),
            "orderId": order_id,
            "status": "NEW",
            "type": kwargs.get("type"),
            "side": kwargs.get("side"),
            "stopPrice": kwargs.get("stopPrice"),
            "reduceOnly": kwargs.get("reduceOnly"),
        }
        avg_price = self.market_avg_price if kwargs.get("type") == "MARKET" else "100"
        return {"orderId": order_id, "avgPrice": avg_price}

    def futures_position_information(self, symbol=None):
        if symbol:
            return [p for p in self.positions if p.get("symbol") == symbol]
        return self.positions

    def futures_get_open_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_orders if o.get("symbol") == symbol]
        return self.open_orders

    def futures_get_open_algo_orders(self, symbol=None):
        return []

    def futures_get_order(self, symbol, **kwargs):
        order_id = kwargs["orderId"]
        return self.order_statuses.get(
            str(order_id),
            {"symbol": symbol, "orderId": order_id, "status": "NEW", "type": "STOP_MARKET"},
        )

    def futures_get_algo_order(self, symbol, **kwargs):
        algo_id = kwargs.get("algoId")
        return self.algo_statuses[str(algo_id)]

    def futures_exchange_info(self):
        return self.exchange_info_payload

    def futures_leverage_bracket(self, symbol=None):
        if symbol:
            return [b for b in self.leverage_bracket_payload if b.get("symbol") == symbol]
        return self.leverage_bracket_payload


class QuantityCloseClient:
    def __init__(self, create_order, queried_order=None, fills=None):
        self.create_order = create_order
        self.queried_order = queried_order or {}
        self.fills = fills or []
        self.create_payload = None

    def futures_position_information(self, symbol):
        return [{"symbol": symbol, "positionSide": "SHORT", "positionAmt": "-10"}]

    def futures_create_order(self, **payload):
        self.create_payload = payload
        return self.create_order

    def futures_get_order(self, symbol, orderId):
        return self.queried_order

    def futures_account_trades(self, symbol, orderId):
        return self.fills


class BinanceSafetyTests(unittest.TestCase):
    def setUp(self):
        # Unit tests intentionally drive execution and fail-close branches.
        # Keep those notification paths off the real Telegram transport.
        self.tempdir = tempfile.TemporaryDirectory()
        self.telegram_patch = patch("telegram_client.send_message")
        self.log_patch = patch.object(logger, "LOG_FILE", Path(self.tempdir.name) / "trades.log")
        self.db_patch = patch.object(trade_db, "DB_PATH", Path(self.tempdir.name) / "trades.db")
        self.telegram_patch.start()
        self.log_patch.start()
        self.db_patch.start()
        binance_connector._xau_rules_cache = {"fetched_at": 0.0, "rules": None}
        import binance_monitor
        if hasattr(binance_monitor, "_logged_unmapped_tps"):
            binance_monitor._logged_unmapped_tps.clear()

    def tearDown(self):
        self.db_patch.stop()
        self.log_patch.stop()
        self.telegram_patch.stop()
        self.tempdir.cleanup()

    def test_min_notional_skip_blocks_oversized_floor_order(self):
        client = FakeClient()
        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "MIN_NOTIONAL_RISK_OVERRIDE_MODE", "skip"),
            patch.object(binance_connector, "MIN_NOTIONAL_MAX_RISK_MULT", 1.25),
            self.assertRaises(ValueError),
        ):
            binance_connector._execute_trade("BUY", "ETHUSDT", lot=0.0, sl_distance=50, rr=2.5)
        self.assertEqual(client.orders, [])

    def test_selected_credentials_must_match_execution_mode(self):
        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "BINANCE_TESTNET", True),
            patch.object(binance_connector, "BINANCE_DEMO_API_KEY", ""),
            patch.object(binance_connector, "BINANCE_DEMO_API_SECRET", ""),
        ):
            ok, reason = binance_connector.validate_binance_credentials()
        self.assertFalse(ok)
        self.assertIn("testnet", reason)

    def test_research_symbol_metadata_exists(self):
        self.assertEqual(binance_connector._map_symbol("SUIUSDT"), "SUIUSDT")
        self.assertEqual(binance_connector._map_symbol("HYPEUSDT"), "HYPEUSDT")
        self.assertEqual(binance_connector._map_symbol("WLDUSDT"), "WLDUSDT")
        self.assertEqual(binance_connector._map_symbol("ZECUSDT"), "ZECUSDT")
        self.assertEqual(binance_connector._map_symbol("DRIFTUSDT"), "DRIFTUSDT")
        self.assertEqual(binance_connector._map_symbol("INJUSDT"), "INJUSDT")
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["SUIUSDT"], 5)
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["HYPEUSDT"], 5)
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["WLDUSDT"], 5)
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["ZECUSDT"], 5)
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["DRIFTUSDT"], 5)
        self.assertEqual(binance_connector.BINANCE_MIN_NOTIONAL["INJUSDT"], 5)
        self.assertEqual(binance_connector.PRICE_PRECISION["SUIUSDT"], 4)
        self.assertEqual(binance_connector.PRICE_PRECISION["HYPEUSDT"], 3)
        self.assertEqual(binance_connector.PRICE_PRECISION["WLDUSDT"], 4)
        self.assertEqual(binance_connector.PRICE_PRECISION["ZECUSDT"], 2)
        self.assertEqual(binance_connector.PRICE_PRECISION["DRIFTUSDT"], 5)
        self.assertEqual(binance_connector.PRICE_PRECISION["INJUSDT"], 3)

    def test_research_symbol_quantity_precision(self):
        self.assertEqual(binance_connector._format_quantity("SUIUSDT", 1.26), 1.3)
        self.assertEqual(binance_connector._format_quantity("HYPEUSDT", 1.234), 1.23)
        self.assertEqual(binance_connector._format_quantity("WLDUSDT", 1.8), 2.0)
        self.assertEqual(binance_connector._format_quantity("ZECUSDT", 1.2345), 1.234)
        self.assertEqual(binance_connector._format_quantity("DRIFTUSDT", 1.8), 2.0)
        self.assertEqual(binance_connector._format_quantity("INJUSDT", 1.26), 1.3)

    def test_stop_orders_use_symbol_price_precision(self):
        client = FakeClient()
        result = binance_connector._place_sl_tp_order(
            client,
            symbol="SUIUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            stop_price=1.23456,
            quantity=1.2,
        )
        self.assertTrue(result["success"])
        self.assertEqual(client.orders[0]["stopPrice"], "1.2346")

    def test_standard_protection_ack_with_algo_id_is_classified_as_algo(self):
        client = FakeClient()

        def create_algo_ack(**kwargs):
            client.orders.append(kwargs)
            return {"algoId": 44, "algoStatus": "NEW"}

        client.futures_create_order = create_algo_ack
        result = binance_connector._place_sl_tp_order(
            client,
            symbol="ETHUSDT",
            side="BUY",
            order_type="STOP_MARKET",
            stop_price=2160.0,
            quantity=0.2,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["order_class"], "ALGO")
        self.assertEqual(result["protection_ref"]["algo_id"], "44")
        self.assertIsNone(result["protection_ref"]["order_id"])

    def test_close_position_qty_uses_reduce_only_correct_side_and_quantity(self):
        client = FakeClient()
        client.positions = [{"symbol": "ETHUSDT", "positionAmt": "-3.57"}]

        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "_get_client", return_value=client),
        ):
            result = binance_connector.close_position_qty("ETHUSDT", 1.25, reason="unit_test")

        self.assertEqual(result["status"], "partial_closed")
        self.assertEqual(client.orders[0]["symbol"], "ETHUSDT")
        self.assertEqual(client.orders[0]["side"], "BUY")
        self.assertEqual(client.orders[0]["quantity"], 1.25)
        self.assertTrue(client.orders[0]["reduceOnly"])

    def test_close_position_qty_prefers_result_executed_qty(self):
        client = QuantityCloseClient({
            "orderId": 41,
            "status": "FILLED",
            "executedQty": "2.49",
            "cumQty": "2.49",
        })
        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "_get_client", return_value=client),
        ):
            result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

        self.assertEqual(client.create_payload["newOrderRespType"], "RESULT")
        self.assertEqual(result["quantity"], 2.49)
        self.assertEqual(result["requested_quantity"], 2.5)
        self.assertEqual(result["quantity_source"], "create_response.executedQty")
        self.assertTrue(result["accounting_confirmed"])

    def test_close_position_qty_queries_order_before_fills(self):
        client = QuantityCloseClient(
            {"orderId": 42, "status": "NEW", "executedQty": "0"},
            {"orderId": 42, "status": "FILLED", "executedQty": "2.48"},
            [{"id": 901, "orderId": 42, "qty": "2.47"}],
        )
        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "_get_client", return_value=client),
        ):
            result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

        self.assertEqual(result["quantity"], 2.48)
        self.assertEqual(result["quantity_source"], "order_query.executedQty")
        self.assertEqual(result["fill_ids"], [])

    def test_close_position_qty_aggregates_same_order_fills(self):
        client = QuantityCloseClient(
            {"orderId": 43, "status": "NEW", "executedQty": "0"},
            {"orderId": 43, "status": "NEW", "executedQty": "0"},
            [
                {"id": 902, "orderId": 43, "qty": "1.20"},
                {"id": 903, "orderId": 43, "qty": "1.29"},
                {"id": 904, "orderId": 99, "qty": "8.00"},
            ],
        )
        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "_get_client", return_value=client),
        ):
            result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

        self.assertEqual(result["quantity"], 2.49)
        self.assertEqual(result["quantity_source"], "account_trade_qty_sum")
        self.assertEqual(result["fill_ids"], ["902", "903"])

    def test_close_position_qty_labels_unconfirmed_rounded_fallback(self):
        client = QuantityCloseClient(
            {"orderId": 44, "status": "NEW", "executedQty": "0"},
            {"orderId": 44, "status": "NEW", "executedQty": "0"},
            [],
        )
        with (
            patch.object(binance_connector, "PAPER_MODE", False),
            patch.object(binance_connector, "_get_client", return_value=client),
        ):
            result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

        self.assertEqual(result["quantity"], 2.5)
        self.assertEqual(result["quantity_source"], "requested_rounded_unconfirmed")
        self.assertFalse(result["accounting_confirmed"])

    def test_quantity_step_size_uses_exchange_lot_size_and_cache(self):
        client = MagicMock()
        client.futures_exchange_info.return_value = {
            "symbols": [{
                "symbol": "BNBUSDT",
                "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.01"}],
            }]
        }
        binance_connector._quantity_step_cache.clear()

        self.assertEqual(binance_connector.get_quantity_step_size("BNBUSDT", client=client), 0.01)
        self.assertEqual(binance_connector.get_quantity_step_size("BNBUSDT", client=client), 0.01)
        client.futures_exchange_info.assert_called_once()

    def test_order_state_persists_risk_when_lot_param_is_used(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 500}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(trade_db, "upsert_binance_order_state") as upsert,
        ):
            result = binance_connector._execute_trade("SELL", "ETHUSDT", lot=0.5, sl_distance=20, rr=2.5)

        self.assertEqual(result["quantity"], 0.5)
        self.assertEqual(upsert.call_args.kwargs["raw_state"]["risk_pct"], binance_connector.RISK_PCT)
        self.assertEqual(upsert.call_args.kwargs["raw_state"]["risk_dollars"], 500 * binance_connector.RISK_PCT)

    def test_margin_cap_reduces_quantity_before_live_entry_submission(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 30.0, "available": 10.0}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_ENTRY_MARGIN_UTILIZATION", 0.9),
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("BUY", "LINKUSDT", lot=35.8, sl_distance=0.16, rr=2.5)

        market_order = client.orders[0]
        self.assertEqual(market_order["type"], "MARKET")
        self.assertEqual(market_order["quantity"], 0.9)
        self.assertEqual(result["quantity"], 0.9)
        self.assertAlmostEqual(result["risk_dollars"], 0.144)
        self.assertGreater(result["target_risk_dollars"], result["risk_dollars"])
        self.assertEqual(result["margin_cap"]["capped_quantity"], 0.9)

    def test_xau_notional_preflight_downshifts_above_bracket_cap(self):
        client = FakeClient()
        client.market_price = "4500"

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 1000, "available": 20000}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "XAUUSDT", lot=15.08, sl_distance=15.0, rr=2.0)

        market_order = client.orders[0]
        self.assertEqual(market_order["symbol"], "XAUUSDT")
        self.assertEqual(market_order["type"], "MARKET")
        self.assertEqual(market_order["quantity"], 10.0)
        self.assertEqual(result["quantity"], 10.0)

    def test_xau_downshift_respects_exchange_step_size(self):
        client = FakeClient()
        client.market_price = "4509.53"
        client.leverage_bracket_payload = [
            {"symbol": "XAUUSDT", "brackets": [{"initialLeverage": 20, "notionalCap": 34123}]}
        ]
        with patch.object(binance_connector, "_xau_rules_cache", {"fetched_at": 0.0, "rules": None}):
            qty, detail = binance_connector._xau_notional_preflight(client, "XAUUSDT", 7.55, 4509.53)

        self.assertIsNotNone(detail)
        self.assertAlmostEqual(qty * 1000, round(qty * 1000), places=6)
        self.assertLessEqual(qty * 4509.53, detail["safe_cap_notional"] + 1e-9)

    def test_xau_downshift_stays_above_min_notional(self):
        client = FakeClient()
        client.market_price = "4500"
        client.leverage_bracket_payload = [
            {"symbol": "XAUUSDT", "brackets": [{"initialLeverage": 20, "notionalCap": 6000}]}
        ]
        with patch.object(binance_connector, "_xau_rules_cache", {"fetched_at": 0.0, "rules": None}):
            qty, detail = binance_connector._xau_notional_preflight(client, "XAUUSDT", 5.0, 4500.0)

        self.assertGreaterEqual(qty * 4500.0, detail["min_notional"])

    def test_xau_preflight_rejects_when_downsized_qty_below_min_qty(self):
        client = FakeClient()
        client.market_price = "4500"
        client.exchange_info_payload = {
            "symbols": [
                {
                    "symbol": "XAUUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.01", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                    ],
                }
            ]
        }
        client.leverage_bracket_payload = [
            {"symbol": "XAUUSDT", "brackets": [{"initialLeverage": 20, "notionalCap": 30}]}
        ]
        with patch.object(binance_connector, "_xau_rules_cache", {"fetched_at": 0.0, "rules": None}):
            with self.assertRaises(ValueError):
                binance_connector._xau_notional_preflight(client, "XAUUSDT", 1.0, 4500.0)

    def test_xau_preflight_avoids_simulated_binance_2027(self):
        client = FakeClient()
        client.market_price = "4500"
        client.xau_reject_cap_notional = 50000 * 0.9

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 1000, "available": 20000}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("BUY", "XAUUSDT", lot=15.08, sl_distance=15.0, rr=2.0)

        self.assertEqual(result["quantity"], 10.0)
        self.assertEqual(client.orders[0]["quantity"], 10.0)

    def test_non_xau_symbols_are_not_notional_prefight_downshifted(self):
        client = FakeClient()
        with (
            patch.object(binance_connector, "_xau_rules_cache", {"fetched_at": 0.0, "rules": None}),
            patch.object(binance_connector, "_fetch_xau_symbol_rules") as fetch_rules,
        ):
            qty, detail = binance_connector._xau_notional_preflight(client, "ETHUSDT", 1.5, 2500.0)
        self.assertEqual(qty, 1.5)
        self.assertIsNone(detail)
        fetch_rules.assert_not_called()

    def test_market_order_zero_avg_price_keeps_ticker_entry_anchor(self):
        client = FakeClient()
        client.market_avg_price = "0"

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 500}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "ETHUSDT", lot=0.5, sl_distance=20, rr=2.5)

        self.assertEqual(result["exec_price"], 100.0)

    def test_has_exchange_protection_requires_reduce_only_sl_and_tp(self):
        client = FakeClient()
        client.open_orders = [
            {"symbol": "ETHUSDT", "type": "STOP_MARKET", "reduceOnly": True},
            {"symbol": "ETHUSDT", "type": "TAKE_PROFIT_MARKET", "reduceOnly": "true"},
        ]

        with patch.object(binance_connector, "_get_client", return_value=client):
            protected, detail = binance_connector.has_exchange_protection("ETHUSDT")

        self.assertTrue(protected)
        self.assertTrue(detail["has_sl"])
        self.assertTrue(detail["has_tp"])

    def test_has_exchange_protection_can_require_current_side_qty_and_prices(self):
        client = FakeClient()
        client.open_orders = [
            {
                "symbol": "LINKUSDT",
                "type": "STOP_MARKET",
                "side": "SELL",
                "origQty": "17.9",
                "stopPrice": "9.52",
                "reduceOnly": True,
            },
            {
                "symbol": "LINKUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "origQty": "17.9",
                "stopPrice": "9.031",
                "reduceOnly": True,
            },
        ]

        with patch.object(binance_connector, "_get_client", return_value=client):
            protected, detail = binance_connector.has_exchange_protection(
                "LINKUSDT",
                expected_side="BUY",
                expected_qty=17.9,
                expected_sl=9.52,
                expected_tp=9.031,
            )

        self.assertFalse(protected)
        self.assertFalse(detail["has_sl"])
        self.assertFalse(detail["has_tp"])

    def test_confirm_exchange_protection_retries_before_fail_closed(self):
        client = FakeClient()
        calls = {"count": 0}

        def delayed_open_orders(symbol=None):
            calls["count"] += 1
            if calls["count"] < 3:
                return []
            return [
                {"symbol": "LINKUSDT", "type": "STOP_MARKET", "reduceOnly": True},
                {"symbol": "LINKUSDT", "type": "TAKE_PROFIT_MARKET", "reduceOnly": True},
            ]

        client.futures_get_open_orders = delayed_open_orders

        with patch.object(binance_connector, "_get_client", return_value=client):
            protected, detail = binance_connector.confirm_exchange_protection(
                "LINKUSDT",
                attempts=3,
                delay_seconds=0,
            )

        self.assertTrue(protected)
        self.assertEqual(detail["attempt"], 3)

    def test_verify_normal_protection_reference_checks_expected_shape(self):
        client = FakeClient()
        ref = binance_connector.ProtectionOrderRef(
            symbol="ETHUSDT",
            kind="SL",
            order_class="NORMAL",
            order_id="55",
            client_order_id=None,
            algo_id=None,
            client_algo_id=None,
            expected_side="BUY",
            expected_position_side=None,
            expected_stop_price=2160.0,
            expected_qty=0.2,
            close_position=False,
            reduce_only=True,
        )
        client.order_statuses["55"] = {
            "symbol": "ETHUSDT",
            "side": "BUY",
            "type": "STOP_MARKET",
            "status": "NEW",
            "stopPrice": "2160.0",
            "reduceOnly": True,
        }

        ok, detail = binance_connector.verify_protection_order(client, ref)

        self.assertTrue(ok)
        self.assertEqual(detail["type"], "STOP_MARKET")

    def test_verify_algo_protection_reference_uses_algo_lookup(self):
        client = FakeClient()
        ref = binance_connector.ProtectionOrderRef(
            symbol="LINKUSDT",
            kind="TP",
            order_class="ALGO",
            order_id=None,
            client_order_id=None,
            algo_id="88",
            client_algo_id=None,
            expected_side="BUY",
            expected_position_side=None,
            expected_stop_price=9.25,
            expected_qty=31.33,
            close_position=False,
            reduce_only=True,
        )
        client.algo_statuses["88"] = {
            "symbol": "LINKUSDT",
            "side": "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "algoStatus": "WORKING",
            "triggerPrice": "9.25",
            "reduceOnly": "true",
        }

        ok, detail = binance_connector.verify_protection_order(client, ref)

        self.assertTrue(ok)
        self.assertEqual(detail["status"], "WORKING")

    def test_verify_protection_reference_rejects_wrong_side(self):
        client = FakeClient()
        ref = binance_connector.ProtectionOrderRef(
            symbol="ETHUSDT",
            kind="SL",
            order_class="NORMAL",
            order_id="56",
            client_order_id=None,
            algo_id=None,
            client_algo_id=None,
            expected_side="BUY",
            expected_position_side=None,
            expected_stop_price=2160.0,
            expected_qty=0.2,
            close_position=False,
            reduce_only=True,
        )
        client.order_statuses["56"] = {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "status": "NEW",
            "stopPrice": "2160.0",
            "reduceOnly": True,
        }

        ok, detail = binance_connector.verify_protection_order(client, ref)

        self.assertFalse(ok)
        self.assertIn("wrong side", detail["failures"])

    def test_confirm_placed_protection_falls_back_to_visible_orders_after_lookup_lag(self):
        client = FakeClient()
        client.open_orders = [
            {"symbol": "LINKUSDT", "type": "STOP_MARKET", "reduceOnly": True},
            {"symbol": "LINKUSDT", "type": "TAKE_PROFIT_MARKET", "reduceOnly": True},
        ]

        with patch.object(client, "futures_get_order", side_effect=RuntimeError("lookup lag")):
            ok, detail = binance_connector.confirm_placed_protection(
                client,
                "LINKUSDT",
                "10",
                "11",
                attempts=1,
                delay_seconds=0,
            )

        self.assertTrue(ok)
        self.assertTrue(detail["has_sl"])
        self.assertTrue(detail["has_tp"])

    def test_confirm_placed_protection_rejects_wrong_side_fallback_orders(self):
        client = FakeClient()
        client.open_orders = [
            {
                "symbol": "LINKUSDT",
                "type": "STOP_MARKET",
                "side": "SELL",
                "origQty": "17.9",
                "stopPrice": "9.52",
                "reduceOnly": True,
            },
            {
                "symbol": "LINKUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "origQty": "17.9",
                "stopPrice": "9.031",
                "reduceOnly": True,
            },
        ]
        sl_ref = {
            "symbol": "LINKUSDT",
            "kind": "SL",
            "order_class": "NORMAL",
            "order_id": "10",
            "client_order_id": None,
            "algo_id": None,
            "client_algo_id": None,
            "expected_side": "BUY",
            "expected_stop_price": 9.52,
            "expected_qty": 17.9,
            "close_position": False,
            "reduce_only": True,
        }
        tp_ref = {
            **sl_ref,
            "kind": "TP",
            "order_id": "11",
            "expected_stop_price": 9.031,
        }

        with patch.object(client, "futures_get_order", side_effect=RuntimeError("lookup lag")):
            ok, detail = binance_connector.confirm_placed_protection(
                client,
                "LINKUSDT",
                sl_ref,
                tp_ref,
                attempts=1,
                delay_seconds=0,
            )

        self.assertFalse(ok)
        self.assertFalse(detail["has_sl"])
        self.assertFalse(detail["has_tp"])

    def test_execute_trade_closes_when_sl_missing_after_protection_retries(self):
        client = FakeClient()
        client.positions = [{"symbol": "LINKUSDT", "positionAmt": "-31.33"}]

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(
                binance_connector,
                "confirm_placed_protection",
                return_value=(False, {"symbol": "LINKUSDT", "has_sl": False, "has_tp": True}),
            ),
            patch.object(
                binance_connector,
                "verify_protection_order",
                return_value=(False, {"reason": "unit_test_missing_protection_order"}),
            ),
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_protection_confirmed") as clean_confirmed,
            patch("telegram_client.notify_confirmed_with_protection_warning") as warning_confirmed,
            self.assertRaises(ValueError),
        ):
            binance_connector._execute_trade("SELL", "LINKUSDT", lot=31.33, sl_distance=0.16, rr=2.5)

        close_orders = [o for o in client.orders if o.get("reduceOnly")]
        self.assertTrue(close_orders)
        self.assertEqual(close_orders[-1]["side"], "BUY")
        clean_confirmed.assert_not_called()
        warning_confirmed.assert_not_called()

    def test_execute_trade_repairs_missing_sl_before_confirming(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(
                binance_connector,
                "confirm_placed_protection",
                side_effect=[
                    (False, {"symbol": "LINKUSDT", "has_sl": False, "has_tp": True}),
                    (True, {"symbol": "LINKUSDT", "has_sl": True, "has_tp": True}),
                ],
            ),
            patch.object(binance_connector, "close_position") as close_position,
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_protection_confirmed") as confirmed,
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "LINKUSDT", lot=31.33, sl_distance=0.16, rr=2.5)

        self.assertEqual(result["status"], "protection_verified")
        close_position.assert_not_called()
        confirmed.assert_called_once()

    def test_execute_trade_keeps_position_when_sl_visible_but_tp_missing(self):
        client = FakeClient()

        def fake_verify_protection_order(_client, ref):
            kind = getattr(ref, "kind", None)
            if kind == "SL":
                return True, {"reason": "unit_test_sl_visible_by_ref", "kind": kind}
            return False, {"reason": "unit_test_missing_tp_order", "kind": kind}

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(
                binance_connector,
                "confirm_placed_protection",
                return_value=(False, {"symbol": "LINKUSDT", "has_sl": True, "has_tp": False}),
            ),
            patch.object(
                binance_connector,
                "verify_protection_order",
                side_effect=fake_verify_protection_order,
            ),
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_protection_confirmed") as clean_confirmed,
            patch("telegram_client.notify_confirmed_with_protection_warning") as warning_confirmed,
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "LINKUSDT", lot=31.33, sl_distance=0.16, rr=2.5)

        self.assertEqual(result["symbol"], "LINKUSDT")
        reduce_market_closes = [
            o for o in client.orders if o.get("type") == "MARKET" and o.get("reduceOnly")
        ]
        self.assertEqual(reduce_market_closes, [])
        clean_confirmed.assert_not_called()
        warning_confirmed.assert_called_once()
        self.assertEqual(result["status"], "sl_verified_tp_warning")

    def test_execute_trade_repairs_missing_tp_before_confirming(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(
                binance_connector,
                "confirm_placed_protection",
                side_effect=[
                    (False, {"symbol": "LINKUSDT", "has_sl": True, "has_tp": False}),
                    (True, {"symbol": "LINKUSDT", "has_sl": True, "has_tp": True}),
                ],
            ),
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_protection_confirmed") as clean_confirmed,
            patch("telegram_client.notify_confirmed_with_protection_warning") as warning_confirmed,
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "LINKUSDT", lot=31.33, sl_distance=0.16, rr=2.5)

        self.assertEqual(result["status"], "protection_verified")
        clean_confirmed.assert_called_once()
        warning_confirmed.assert_not_called()

    def test_execute_trade_confirms_protection_by_order_id_when_open_orders_lag(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch("telegram_client.notify_entry_protection_verifying") as verifying,
            patch("telegram_client.notify_protection_confirmed") as confirmed,
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            result = binance_connector._execute_trade("SELL", "LINKUSDT", lot=31.33, sl_distance=0.16, rr=2.5)

        self.assertEqual(result["symbol"], "LINKUSDT")
        self.assertEqual(result["status"], "protection_verified")
        verifying.assert_called_once()
        confirmed.assert_called_once()
        reduce_market_closes = [
            o for o in client.orders if o.get("type") == "MARKET" and o.get("reduceOnly")
        ]
        self.assertEqual(reduce_market_closes, [])

    def test_sl_placement_fail_closed_uses_fail_closed_notification(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(binance_connector, "_place_sl_tp_order", return_value={"success": False, "error": "bad sl"}),
            patch.object(
                binance_connector,
                "close_position",
                return_value={"status": "closed", "symbol": "ETHUSDT", "position_side": "SHORT"},
            ),
            patch("telegram_client.notify_trade_error") as trade_error,
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_execution_fail_closed") as fail_closed,
            self.assertRaises(ValueError),
        ):
            binance_connector._execute_trade("SELL", "ETHUSDT", lot=0.5, sl_distance=20, rr=2.5)

        trade_error.assert_not_called()
        fail_closed.assert_called_once()

    def test_testnet_missing_stop_repairs_then_fails_closed(self):
        client = FakeClient()

        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", True),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", True),
            patch.object(
                binance_connector,
                "confirm_placed_protection",
                return_value=(False, {"symbol": "ETHUSDT", "has_sl": False, "has_tp": True}),
            ),
            patch.object(
                binance_connector,
                "_place_sl_tp_order",
                return_value={"success": False, "error": "shadow missing stop"},
            ),
            patch.object(
                binance_connector,
                "close_position",
                return_value={"status": "closed", "symbol": "ETHUSDT", "position_side": "SHORT"},
            ) as close_position,
            patch("telegram_client.notify_execution_fail_closed") as fail_closed,
            self.assertRaises(ValueError),
        ):
            binance_connector._execute_trade("SELL", "ETHUSDT", lot=0.5, sl_distance=20, rr=2.5)

        close_position.assert_called_once()
        fail_closed.assert_called_once()

    def test_hedge_mode_entry_payload(self):
        client = FakeClient()
        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 100}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "BINANCE_TESTNET", False),
            patch.object(binance_connector, "PROTECTION_TRUTH_REQUIRED", False),
            patch.object(binance_connector, "inspect_exchange_protection", return_value={"has_sl": True}),
            patch.object(binance_connector, "_place_sl_tp_order", return_value={"success": True, "algoId": "123"}),
            patch("telegram_client.notify_entry_protection_verifying"),
            patch("telegram_client.notify_protection_confirmed"),
        ):
            with patch.object(client, "futures_create_order", return_value={"orderId": 12345, "avgPrice": "2000.0"}) as mock_create:
                binance_connector._execute_trade("BUY", "ETHUSDT", lot=0.5, sl_distance=20, rr=2.5)
                mock_create.assert_called_once()
                kwargs = mock_create.call_args[1]
                self.assertEqual(kwargs.get("positionSide"), "LONG")
                self.assertNotIn("reduceOnly", kwargs)

    def test_full_sl_payload(self):
        client = FakeClient()
        with patch.object(client, "futures_create_order", return_value={"orderId": 999}) as mock_create:
            from binance_connector import _place_sl_tp_order
            _place_sl_tp_order(
                client=client,
                symbol="ETHUSDT",
                side="SELL",
                order_type="STOP_MARKET",
                stop_price=1980.0,
                position_side="LONG",
                close_position=True,
            )
            mock_create.assert_called_once()
            kwargs = mock_create.call_args[1]
            self.assertEqual(kwargs.get("positionSide"), "LONG")
            self.assertEqual(kwargs.get("closePosition"), "true")
            self.assertNotIn("quantity", kwargs)
            self.assertNotIn("reduceOnly", kwargs)

    def test_partial_tp_payload(self):
        client = FakeClient()
        with patch.object(client, "futures_create_order", return_value={"orderId": 999}) as mock_create:
            from binance_connector import _place_sl_tp_order
            _place_sl_tp_order(
                client=client,
                symbol="ETHUSDT",
                side="SELL",
                order_type="TAKE_PROFIT_MARKET",
                stop_price=2050.0,
                quantity=0.25,
                position_side="LONG",
                close_position=False,
            )
            mock_create.assert_called_once()
            kwargs = mock_create.call_args[1]
            self.assertEqual(kwargs.get("positionSide"), "LONG")
            self.assertEqual(kwargs.get("quantity"), "0.25")
            self.assertNotIn("closePosition", kwargs)
            self.assertNotIn("reduceOnly", kwargs)

    def test_halt_kill_switch_blocks_new_entries(self):
        import tempfile
        from webhook import app
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as halt_file:
            halt_file.write("operator\n")
            halt_path = halt_file.name
        try:
            with (
                patch("webhook.WEBHOOK_SECRET", "test_secret"),
                patch("webhook.BINANCE_TESTNET", False),
                patch("webhook.PAPER_MODE", False),
                patch("webhook.HALT_FILE", halt_path),
                patch("webhook.validate_signal_payload", return_value=(True, [])),
                patch("webhook._monitor_entry_gate_status", return_value={"allowed": True, "active_state": "active"}),
                patch("webhook._check_signal_age", return_value={"allowed": True}),
                patch("webhook._get_binance_client", return_value=MagicMock()),
                patch("webhook._get_cached_positions", return_value=([], True)),
                patch("webhook._check_entry_drift", return_value={"allowed": True}),
                patch(
                    "webhook.live_reconcile.reconcile_live_state",
                    return_value={"healthy": True, "critical_mismatches": [], "warnings": []},
                ),
                patch("webhook.plain_log") as mock_plain_log,
                patch("telegram_client.notify_rejected") as mock_notify,
            ):
                client = app.test_client()
                response = client.post("/webhook", json={
                    "secret": "test_secret",
                    "symbol": "LINKUSDT",
                    "signal": "BUY",
                    "entry": "15.5",
                    "source": "signal_generator",
                    "source_service": "signal_generator",
                    "strategy": "pullback",
                    "strategy_label": "1H_TREND_CONTINUATION",
                    "timeframe": "60",
                    "timestamp": 1779613507000,
                })
                self.assertEqual(response.status_code, 200)
                res_data = response.get_json()
                self.assertEqual(res_data["status"], "rejected")
                self.assertIn("halt", res_data["reason"].lower())

                halt_calls = [c for c in mock_plain_log.call_args_list if c.args[0] == "HALT_REJECT"]
                self.assertTrue(halt_calls)
        finally:
            import os
            os.unlink(halt_path)

    def test_tp1_and_tp2_payloads_are_hedge_mode_safe(self):
        # Assert TP1 & TP2 payloads are Hedge Mode safe during trade execution
        client = FakeClient()
        placed_orders = []
        def fake_create_order(**kwargs):
            placed_orders.append(kwargs)
            return {"orderId": len(placed_orders), "avgPrice": "100"}
        client.futures_create_order = fake_create_order
        
        with (
            patch.object(binance_connector, "_get_client", return_value=client),
            patch.object(binance_connector, "get_balance", return_value={"equity": 500}),
            patch.object(binance_connector, "_set_leverage"),
            patch.object(binance_connector, "inspect_exchange_protection", return_value={"has_sl": True, "has_tp": True}),
            patch.object(binance_connector, "has_exchange_protection", return_value=(True, {"has_sl": True, "has_tp": True})),
            patch.object(trade_db, "upsert_binance_order_state"),
        ):
            # Run trade execution
            binance_connector._execute_trade("BUY", "ETHUSDT", lot=1.0, sl_distance=50, rr=2.5)

        # 3 orders should be placed: 1 market entry, 1 stop loss, 2 take profits (TP1 and TP2)
        # Total = 4 orders
        self.assertEqual(len(placed_orders), 4)
        
        # Check TP1 and TP2 (which are TAKE_PROFIT_MARKET orders)
        tp_orders = [o for o in placed_orders if o.get("type") == "TAKE_PROFIT_MARKET"]
        self.assertEqual(len(tp_orders), 2)
        
        for tp in tp_orders:
            # opposite side to entry (BUY -> SELL)
            self.assertEqual(tp.get("side"), "SELL")
            # positionSide LONG
            self.assertEqual(tp.get("positionSide"), "LONG")
            # quantity used for partial exit
            self.assertIsNotNone(tp.get("quantity"))
            self.assertGreater(float(tp.get("quantity")), 0)
            # no reduceOnly
            self.assertNotIn("reduceOnly", tp)
            # no closePosition=true
            self.assertNotIn("closePosition", tp)

    def test_tp1_fill_reduces_remaining_position_size_and_pnl_recorded(self):
        # Test that TP1 fill reduces remaining quantity, and realized milestone PnL is recorded
        from binance_monitor import _reconcile_order_state
        import binance_monitor
        
        client = FakeClient()
        
        # Mock previous order state with TP1 details and original qty = 1.0, remaining = 1.0
        # raw_state_json has: tp1_price=105.0, tp1_qty=0.5, tp1_detail={"orderId": "123"}
        prev_raw_state = {
            "tp1_price": 105.0,
            "tp1_qty": 0.5,
            "tp1_detail": {"orderId": "123"},
            "tp2_price": 225.0,
            "tp2_qty": 0.5,
        }
        import json
        
        mock_prev_state = {
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "side": "BUY",
            "remaining_qty": 1.0,
            "entry_price": 100.0,
            "raw_state_json": json.dumps(prev_raw_state),
        }
        
        # Mock futures_get_all_orders returning a FILLED TP1 order
        client.futures_get_all_orders = lambda symbol, limit=20: [
            {
                "orderId": 123,
                "symbol": "ETHUSDT",
                "status": "FILLED",
                "type": "TAKE_PROFIT_MARKET",
                "avgPrice": "105.0",
                "executedQty": "0.5",
                "origQty": "0.5",
            }
        ]
        
        with (
            patch.object(trade_db, "get_binance_order_state", return_value=mock_prev_state),
            patch.object(trade_db, "upsert_binance_order_state") as mock_upsert,
            patch.object(trade_db, "log_milestone", return_value=True) as mock_log_ms,
            patch.object(trade_db, "log_exit") as mock_log_exit,
            patch.object(trade_db, "milestone_exists", return_value=False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log,
            patch.object(binance_monitor.telegram_client, "notify_milestone"),
        ):
            # Position volume is now 0.5 (TP1 filled!)
            position = {
                "symbol": "ETHUSDT",
                "tv_symbol": "ETHUSDT",
                "volume": 0.5,
                "openPrice": 100.0,
                "currentPrice": 105.0,
                "type": "BUY"
            }
            binance_monitor._position_state["ETHUSDT"] = {
                "trade_id": 999,
                "first_seen": 100,
                "original_qty": 1.0,
                "direction": "BUY"
            }
            
            _reconcile_order_state(position)
            
            # Verify MILESTONE_FILLED and MILESTONE_PNL_RECORDED were logged
            log_calls = [c.args[0] for c in mock_plain_log.call_args_list]
            self.assertIn("MILESTONE_FILLED", log_calls)
            self.assertIn("MILESTONE_PNL_RECORDED", log_calls)
            
            # Verify trade_db actions
            mock_log_ms.assert_called_once_with(999, "milestone_0", 105.0, 2.5) # Directional pnl: BUY 100 -> 105 with qty 0.5 = 2.5
            mock_log_exit.assert_called_once()
            
            # Verify remaining qty updated to 0.5 in DB
            self.assertEqual(mock_upsert.call_args.kwargs["remaining_qty"], 0.5)

    def test_missing_milestone_order_detected_and_warned(self):
        # Test that a missing expected milestone order is detected and logged as warning
        import binance_monitor
        from binance_monitor import _reconcile_order_state
        import json
        
        client = FakeClient()
        prev_raw_state = {
            "tp1_price": 105.0,
            "tp1_qty": 0.5,
            "tp1_detail": {"orderId": "123"},
            "tp2_price": 225.0,
            "tp2_qty": 0.5,
        }
        mock_prev_state = {
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "side": "BUY",
            "remaining_qty": 1.0,
            "entry_price": 100.0,
            "raw_state_json": json.dumps(prev_raw_state),
        }
        
        # Mock exchange open orders to NOT have the TP1 order
        client.futures_get_open_orders = lambda symbol: []
        client.futures_get_all_orders = lambda symbol, limit=20: []
        
        with (
            patch.object(trade_db, "get_binance_order_state", return_value=mock_prev_state),
            patch.object(trade_db, "upsert_binance_order_state"),
            patch.object(trade_db, "milestone_exists", return_value=False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log,
        ):
            position = {
                "symbol": "ETHUSDT",
                "tv_symbol": "ETHUSDT",
                "volume": 1.0,
                "openPrice": 100.0,
                "currentPrice": 102.0,
                "type": "BUY"
            }
            binance_monitor._position_state["ETHUSDT"] = {
                "trade_id": 999,
                "first_seen": 100,
                "original_qty": 1.0,
                "direction": "BUY"
            }
            
            _reconcile_order_state(position)
            
            # Verify MILESTONE_RECONCILED_WARNING is logged
            log_calls = [c.args[0] for c in mock_plain_log.call_args_list]
            self.assertIn("MILESTONE_RECONCILED_WARNING", log_calls)

    def test_duplicate_milestone_order_not_created(self):
        # Test that duplicate protective/milestone orders are not created when exchange is already protected
        import binance_monitor
        from binance_monitor import _repair_missing_protection_if_needed
        
        client = FakeClient()
        
        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "get_post_fill_protection_mode", return_value="repair"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_position_protection_anchors", return_value=(95.0, 110.0)),
            patch.object(binance_monitor, "has_exchange_protection", return_value=(True, {"has_sl": True, "has_tp": True})),
            patch.object(binance_monitor, "_place_sl_tp_order") as mock_place,
        ):
            position = {
                "symbol": "ETHUSDT",
                "tv_symbol": "ETHUSDT",
                "volume": 1.0,
                "type": "BUY"
            }
            
            res = _repair_missing_protection_if_needed(position)
            self.assertTrue(res)
            # Verify no order placement attempts were made! (No duplicates!)
            mock_place.assert_not_called()

    def test_hype_state_reconciliation_and_trailing(self):
        # HYPEUSDT LONG has STOP_MARKET SELL LONG closePosition=true and TAKE_PROFIT_MARKET SELL LONG qty=59.62
        import binance_monitor
        from binance_monitor import _update_sl_order, _reconcile_order_state
        import json
        
        client = FakeClient()
        # Mock open orders on exchange
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 1001,
                "symbol": "HYPEUSDT",
                "type": "STOP_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "true",
                "stopPrice": "2.1"
            },
            {
                "orderId": 1002,
                "symbol": "HYPEUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "false",
                "quantity": "59.62",
                "stopPrice": "2.8"
            }
        ]
        
        # 1. Test trailing SL replacement skip
        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log,
        ):
            ok = _update_sl_order(
                "HYPEUSDT", "HYPEUSDT", "BUY", 2.2, {"volume": 59.62, "currentPrice": 2.3}
            )
            self.assertFalse(ok)
            # Must log TRAIL_ACTIVE_STATIC_SL
            log_calls = [c.args[0] for c in mock_plain_log.call_args_list]
            self.assertIn("TRAIL_ACTIVE_STATIC_SL", log_calls)

        # 2. Test milestone reconciliation with unmapped TP order
        prev_raw_state = {
            "tp1_price": 2.7,
            "tp1_qty": 29.81,
            "tp2_price": 3.2,
            "tp2_qty": 29.81,
        }
        mock_prev_state = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "side": "BUY",
            "remaining_qty": 59.62,
            "entry_price": 2.5,
            "raw_state_json": json.dumps(prev_raw_state),
        }
        
        with (
            patch.object(trade_db, "get_binance_order_state", return_value=mock_prev_state),
            patch.object(trade_db, "upsert_binance_order_state"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log_reconcile,
        ):
            position = {
                "symbol": "HYPEUSDT",
                "tv_symbol": "HYPEUSDT",
                "volume": 59.62,
                "openPrice": 2.5,
                "currentPrice": 2.6,
                "type": "BUY"
            }
            binance_monitor._position_state["HYPEUSDT"] = {
                "trade_id": 999,
                "first_seen": 100,
                "original_qty": 59.62,
                "direction": "BUY"
            }
            
            _reconcile_order_state(position)
            
            # Verify MILESTONE_RECONCILED_UNMAPPED_TP is logged
            log_calls = [c.args[0] for c in mock_plain_log_reconcile.call_args_list]
            self.assertIn("MILESTONE_RECONCILED_UNMAPPED_TP", log_calls)
            
            # Verify tp_active is NOT false (tp1_active is True since unmapped TP exists and is mapped to missing TP)
            reconcile_details = [c.args[1] for c in mock_plain_log_reconcile.call_args_list if c.args[0] == "MILESTONE_RECONCILED"]
            self.assertTrue(reconcile_details)
            self.assertTrue(reconcile_details[0]["tp1_active"])

    def test_sol_state_reconciliation_and_trailing(self):
        # SOLUSDT SHORT has STOP_MARKET BUY SHORT closePosition=true and TAKE_PROFIT_MARKET BUY SHORT qty=20 + qty=20
        import binance_monitor
        from binance_monitor import _update_sl_order, _reconcile_order_state
        import json
        
        client = FakeClient()
        # Mock open orders on exchange
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 2001,
                "symbol": "SOLUSDT",
                "type": "STOP_MARKET",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": "true",
                "stopPrice": "155.0"
            },
            {
                "orderId": 2002,
                "symbol": "SOLUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": "false",
                "quantity": "20.0",
                "stopPrice": "145.0"
            },
            {
                "orderId": 2003,
                "symbol": "SOLUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": "false",
                "quantity": "20.0",
                "stopPrice": "135.0"
            }
        ]
        
        # 1. Test trailing SL replacement skip
        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log,
        ):
            ok = _update_sl_order(
                "SOLUSDT", "SOLUSDT", "SELL", 154.0, {"volume": -40.0, "currentPrice": 150.0}
            )
            self.assertFalse(ok)
            # Must log TRAIL_ACTIVE_STATIC_SL
            log_calls = [c.args[0] for c in mock_plain_log.call_args_list]
            self.assertIn("TRAIL_ACTIVE_STATIC_SL", log_calls)

        # 2. Test milestone reconciliation with unmapped TP orders
        prev_raw_state = {
            "tp1_price": 140.0,
            "tp1_qty": 20.0,
            "tp2_price": 130.0,
            "tp2_qty": 20.0,
        }
        mock_prev_state = {
            "symbol": "SOLUSDT",
            "tv_symbol": "SOLUSDT",
            "side": "SELL",
            "remaining_qty": 40.0,
            "entry_price": 150.0,
            "raw_state_json": json.dumps(prev_raw_state),
        }
        
        with (
            patch.object(trade_db, "get_binance_order_state", return_value=mock_prev_state),
            patch.object(trade_db, "upsert_binance_order_state"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log_reconcile,
        ):
            position = {
                "symbol": "SOLUSDT",
                "tv_symbol": "SOLUSDT",
                "volume": 40.0,
                "openPrice": 150.0,
                "currentPrice": 148.0,
                "type": "SELL"
            }
            binance_monitor._position_state["SOLUSDT"] = {
                "trade_id": 888,
                "first_seen": 100,
                "original_qty": 40.0,
                "direction": "SELL"
            }
            
            _reconcile_order_state(position)
            
            # Verify MILESTONE_RECONCILED_UNMAPPED_TP is logged (for both unmapped orders)
            unmapped_calls = [c for c in mock_plain_log_reconcile.call_args_list if c.args[0] == "MILESTONE_RECONCILED_UNMAPPED_TP"]
            self.assertEqual(len(unmapped_calls), 2)
            
            # Verify both tp1_active and tp2_active are True (not false!)
            reconcile_details = [c.args[1] for c in mock_plain_log_reconcile.call_args_list if c.args[0] == "MILESTONE_RECONCILED"]
            self.assertTrue(reconcile_details)
            self.assertTrue(reconcile_details[0]["tp1_active"])
            self.assertTrue(reconcile_details[0]["tp2_active"])

    def test_doctrine_static_sl_trail_active(self):
        # Given HYPE LONG with existing STOP_MARKET SELL LONG closePosition=true and active TP
        import binance_monitor
        from binance_monitor import _update_sl_order, _check_trailing_stop
        import time
        
        client = FakeClient()
        # Mock open orders on exchange
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 1001,
                "symbol": "HYPEUSDT",
                "type": "STOP_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "true",
                "stopPrice": "2.1"
            },
            {
                "orderId": 1002,
                "symbol": "HYPEUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "false",
                "quantity": "59.62",
                "stopPrice": "2.8"
            }
        ]
        
        # We mock futures_create_order to raise an error or track if it was called
        create_called = False
        def mock_create_order(**kwargs):
            nonlocal create_called
            create_called = True
            return {"orderId": 9999}
        client.futures_create_order = mock_create_order
        
        cancel_called = False
        def mock_cancel_order(symbol, orderId):
            nonlocal cancel_called
            cancel_called = True
            return {}
        client.futures_cancel_order = mock_cancel_order

        # Setup state to trail active reached
        position = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "volume": 59.62,
            "openPrice": 2.5,
            "currentPrice": 3.0,  # Price has reached trigger_r
            "profit": 29.81,
            "type": "BUY"
        }
        
        state = binance_monitor._get_state("HYPEUSDT")
        state["trailing_active"] = False
        state["current_sl"] = 2.1
        state["trade_id"] = 999
        
        # Mock position config in cc_state
        cc_state = binance_monitor._get_position_state("HYPEUSDT")
        cc_state["trail_mode"] = "fixed"
        cc_state["trail_param"] = 0.5
        cc_state["trail_trigger_r"] = 1.0
        cc_state["original_sl_distance"] = 0.4
        cc_state["original_sl"] = 2.1
        
        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log,
            patch.object(binance_monitor, "_send_telegram") as mock_send_telegram,
        ):
            # when trail_active is reached
            _check_trailing_stop(position)
            
            # then monitor logs TRAIL_ACTIVE_STATIC_SL and TRAIL_SKIPPED_STATIC_HARD_SL
            log_calls = [c.args[0] for c in mock_plain_log.call_args_list]
            self.assertIn("TRAIL_ACTIVE_STATIC_SL", log_calls)
            self.assertIn("TRAIL_SKIPPED_STATIC_HARD_SL", log_calls)
            
            # does not call futures_create_order
            self.assertFalse(create_called)
            
            # does not cancel the old SL
            self.assertFalse(cancel_called)
            
            # and does not send TRAILING STOP FAILED
            telegram_calls = [c.args[0] for c in mock_send_telegram.call_args_list]
            for call_text in telegram_calls:
                self.assertNotIn("TRAILING STOP FAILED", call_text)

    def test_unmapped_tp_debouncing(self):
        # Verify that multiple reconcile ticks only log the unmapped TP order once.
        import binance_monitor
        from binance_monitor import _reconcile_order_state
        import json
        
        client = FakeClient()
        # Mock one unmapped TP order on exchange
        client.futures_get_open_orders = lambda symbol: [
            {
                "orderId": 5001,
                "symbol": "HYPEUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": "false",
                "quantity": "29.81",
                "stopPrice": "4.5" # Far from expected TP1/TP2
            }
        ]
        
        prev_raw_state = {
            "tp1_price": 3.0,
            "tp1_qty": 29.81,
            "tp2_price": 3.2,
            "tp2_qty": 29.81,
        }
        mock_prev_state = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "side": "BUY",
            "remaining_qty": 59.62,
            "entry_price": 2.5,
            "raw_state_json": json.dumps(prev_raw_state),
        }
        
        with (
            patch.object(trade_db, "get_binance_order_state", return_value=mock_prev_state),
            patch.object(trade_db, "upsert_binance_order_state"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "plain_log") as mock_plain_log_reconcile,
        ):
            position = {
                "symbol": "HYPEUSDT",
                "tv_symbol": "HYPEUSDT",
                "volume": 59.62,
                "openPrice": 2.5,
                "currentPrice": 2.6,
                "type": "BUY"
            }
            binance_monitor._position_state["HYPEUSDT"] = {
                "trade_id": 999,
                "first_seen": 100,
                "original_qty": 59.62,
                "direction": "BUY"
            }
            
            # Tick 1: logs unmapped TP
            _reconcile_order_state(position)
            log_calls_1 = [c.args[0] for c in mock_plain_log_reconcile.call_args_list if c.args[0] == "MILESTONE_RECONCILED_UNMAPPED_TP"]
            self.assertEqual(len(log_calls_1), 1)
            
            # Reset mock log list
            mock_plain_log_reconcile.reset_mock()
            
            # Tick 2: does NOT log unmapped TP (debounced!)
            _reconcile_order_state(position)
            log_calls_2 = [c.args[0] for c in mock_plain_log_reconcile.call_args_list if c.args[0] == "MILESTONE_RECONCILED_UNMAPPED_TP"]
            self.assertEqual(len(log_calls_2), 0)


if __name__ == "__main__":
    unittest.main()
