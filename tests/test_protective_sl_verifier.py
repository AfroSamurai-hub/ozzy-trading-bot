import unittest
from datetime import datetime, timezone
from binance_connector import inspect_exchange_protection

class TestProtectiveSLVerifier(unittest.TestCase):
    def test_type_null_hype_long_sell_long_below_entry_classified_as_sl(self):
        algo_orders = [
            {
                "algoId": 1000000094564920,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "reduceOnly": True,
                "closePosition": False,
                "triggerPrice": "70.96700",
                "quantity": "126.14",
                "algoStatus": "NEW",
            }
        ]

        detail = inspect_exchange_protection(
            symbol="HYPEUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_sl=71.113,
            entry_price=72.952,
            current_price=72.888,
            remaining_exchange_qty=126.14,
        )

        self.assertTrue(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 1)
        self.assertEqual(detail["candidate_sl_orders"][0]["reason"], "inferred_sl_shape")
        self.assertAlmostEqual(detail["exchange_sl_trigger"], 70.967)

    def test_type_null_long_wrong_side_buy_is_ignored(self):
        algo_orders = [
            {
                "algoId": 1,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "BUY",
                "positionSide": "LONG",
                "reduceOnly": True,
                "triggerPrice": "70.96700",
                "quantity": "126.14",
                "algoStatus": "NEW",
            }
        ]

        detail = inspect_exchange_protection(
            symbol="HYPEUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_sl=70.967,
            entry_price=72.952,
            current_price=72.888,
            remaining_exchange_qty=126.14,
        )

        self.assertFalse(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 0)
        self.assertIn("wrong_close_side", detail["rejected_orders"][0]["reason"])

    def test_type_null_short_buy_short_above_entry_classified_as_sl(self):
        algo_orders = [
            {
                "algoId": 2,
                "type": None,
                "symbol": "ETHUSDT",
                "side": "BUY",
                "positionSide": "SHORT",
                "reduceOnly": True,
                "triggerPrice": "1907.03",
                "quantity": "1.33",
                "algoStatus": "NEW",
            }
        ]

        detail = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="BUY",
            expected_position_side="SHORT",
            expected_sl=1907.03,
            entry_price=1870.0,
            current_price=1868.0,
            remaining_exchange_qty=1.33,
        )

        self.assertTrue(detail["has_sl"])
        self.assertEqual(detail["candidate_sl_orders"][0]["reason"], "inferred_sl_shape")

    def test_type_null_tp_shape_classified_as_tp(self):
        algo_orders = [
            {
                "algoId": 3,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "reduceOnly": True,
                "triggerPrice": "78.04300",
                "quantity": "126.14",
                "algoStatus": "NEW",
            }
        ]

        detail = inspect_exchange_protection(
            symbol="HYPEUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_tp=78.043,
            entry_price=72.952,
            current_price=72.888,
            remaining_exchange_qty=126.14,
        )

        self.assertTrue(detail["has_tp"])
        self.assertEqual(detail["tp_order_count"], 1)
        self.assertEqual(detail["candidate_tp_orders"][0]["reason"], "inferred_tp_shape")

    def test_db_sl_mismatch_does_not_fail_when_type_null_exchange_sl_covers_remaining_qty(self):
        algo_orders = [
            {
                "algoId": 1000000094564920,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "reduceOnly": True,
                "triggerPrice": "70.96700",
                "quantity": "126.14",
                "algoStatus": "NEW",
            },
            {
                "algoId": 1000000094564925,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "reduceOnly": True,
                "triggerPrice": "78.04300",
                "quantity": "126.14",
                "algoStatus": "NEW",
            },
        ]

        detail = inspect_exchange_protection(
            symbol="HYPEUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_sl=71.113,
            expected_tp=78.043,
            entry_price=72.952,
            current_price=72.888,
            remaining_exchange_qty=126.14,
        )

        self.assertTrue(detail["has_sl"])
        self.assertTrue(detail["has_tp"])
        self.assertTrue(detail["protected"])
        self.assertAlmostEqual(detail["sl_price_delta"], 0.146)

    def test_type_null_wrong_position_side_is_ignored(self):
        algo_orders = [
            {
                "algoId": 4,
                "type": None,
                "symbol": "HYPEUSDT",
                "side": "SELL",
                "positionSide": "SHORT",
                "reduceOnly": True,
                "triggerPrice": "70.96700",
                "quantity": "126.14",
                "algoStatus": "NEW",
            }
        ]

        detail = inspect_exchange_protection(
            symbol="HYPEUSDT",
            open_orders=[],
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_sl=70.967,
            entry_price=72.952,
            current_price=72.888,
            remaining_exchange_qty=126.14,
        )

        self.assertFalse(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 0)
        self.assertIn("wrong_position_side", detail["rejected_orders"][0]["reason"])

    def test_close_position_stop_market_valid_sl_for_short(self):
        """
        STOP_MARKET order with closePosition=true, side=BUY, positionSide=SHORT counts as valid SL.
        """
        orders = []
        algo_orders = [
            {
                "algoId": 4000001449259272,
                "orderType": "STOP_MARKET",
                "symbol": "ETHUSDT",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": True,
                "triggerPrice": "2025.35",
                "quantity": "0.0",
                "algoStatus": "NEW"
            }
        ]
        
        detail = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="BUY",
            expected_position_side="SHORT",
            expected_sl=2025.017,  # stop price does not strictly match
            expected_sl_qty=0.2    # qty does not strictly match
        )
        
        self.assertTrue(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 1)

    def test_close_position_stop_market_valid_sl_for_long(self):
        """
        STOP_MARKET order with closePosition=true, side=SELL, positionSide=LONG counts as valid SL.
        """
        orders = [
            {
                "orderId": 4000001449259273,
                "type": "STOP_MARKET",
                "symbol": "ETHUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "closePosition": True,
                "stopPrice": "1980.5",
                "origQty": "0.0",
                "status": "NEW"
            }
        ]
        algo_orders = []
        
        detail = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="LONG",
            expected_sl=1985.0,
            expected_sl_qty=0.2
        )
        
        self.assertTrue(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 1)

    def test_tp_orders_not_mistaken_for_sl(self):
        """
        TAKE_PROFIT_MARKET orders are not mistaken for SL orders.
        """
        orders = []
        algo_orders = [
            {
                "algoId": 4000001449259312,
                "orderType": "TAKE_PROFIT_MARKET",
                "symbol": "ETHUSDT",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": False,
                "triggerPrice": "1987.64",
                "quantity": "0.1",
                "algoStatus": "NEW"
            }
        ]
        
        detail = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="BUY",
            expected_position_side="SHORT",
            expected_sl=2025.017,
            expected_sl_qty=0.2
        )
        
        self.assertFalse(detail["has_sl"])
        self.assertEqual(detail["sl_order_count"], 0)

    def test_missing_sl_returns_protected_false(self):
        """
        If SL is missing, protected=False is returned.
        """
        orders = []
        algo_orders = [
            {
                "algoId": 4000001449259312,
                "orderType": "TAKE_PROFIT_MARKET",
                "symbol": "ETHUSDT",
                "side": "BUY",
                "positionSide": "SHORT",
                "closePosition": False,
                "triggerPrice": "1987.64",
                "quantity": "0.1",
                "algoStatus": "NEW"
            }
        ]
        
        detail = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="BUY",
            expected_position_side="SHORT",
            expected_sl=2025.017,
            expected_sl_qty=0.2,
            expected_tp=1987.64
        )
        
        self.assertFalse(detail["has_sl"])
        self.assertTrue(detail["has_tp"])
        self.assertFalse(detail["protected"])

    def test_one_way_mode_position_side_null_handled_correctly(self):
        """
        In one-way mode, expected_position_side="BOTH", "NULL", "NONE", or "" matches order positionSide=BOTH, null, etc.
        """
        orders = [
            {
                "orderId": 4000001449259274,
                "type": "STOP_MARKET",
                "symbol": "ETHUSDT",
                "side": "SELL",
                "positionSide": "BOTH",
                "closePosition": True,
                "stopPrice": "1980.5",
                "origQty": "0.0",
                "status": "NEW"
            }
        ]
        algo_orders = []
        
        # Test case: expected is "BOTH"
        detail_both = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="BOTH",
            expected_sl=1980.5,
            expected_sl_qty=0.2
        )
        self.assertTrue(detail_both["has_sl"])
        
        # Test case: expected is "NONE"
        detail_none = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="NONE",
            expected_sl=1980.5,
            expected_sl_qty=0.2
        )
        self.assertTrue(detail_none["has_sl"])
        
        # Test case: expected is ""
        detail_empty = inspect_exchange_protection(
            symbol="ETHUSDT",
            open_orders=orders,
            algo_orders=algo_orders,
            expected_side="SELL",
            expected_position_side="",
            expected_sl=1980.5,
            expected_sl_qty=0.2
        )
        self.assertTrue(detail_empty["has_sl"])
