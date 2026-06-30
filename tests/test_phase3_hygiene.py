import unittest
from unittest.mock import patch

import command_center
import webhook


class FakePurgeClient:
    def __init__(self):
        self.cancelled_normal = []
        self.cancelled_algo = []

    def futures_position_information(self):
        return [{"symbol": "BTCUSDT", "positionAmt": "0.01"}]

    def futures_get_open_orders(self, symbol):
        if symbol == "ETHUSDT":
            return [
                {"symbol": symbol, "orderId": 10, "type": "STOP_MARKET", "reduceOnly": True},
                {"symbol": symbol, "orderId": 11, "type": "LIMIT", "reduceOnly": False},
            ]
        if symbol == "BTCUSDT":
            return [{"symbol": symbol, "orderId": 20, "type": "STOP_MARKET", "reduceOnly": True}]
        return []

    def futures_get_open_algo_orders(self, symbol):
        if symbol == "ETHUSDT":
            return [{"symbol": symbol, "algoId": 30, "orderType": "TAKE_PROFIT_MARKET", "reduceOnly": "true"}]
        if symbol == "BTCUSDT":
            return [{"symbol": symbol, "algoId": 40, "orderType": "STOP_MARKET", "reduceOnly": "true"}]
        return []

    def futures_cancel_order(self, symbol, orderId):
        self.cancelled_normal.append((symbol, orderId))
        return {"status": "SUCCESS"}

    def futures_cancel_algo_order(self, symbol, algoId):
        self.cancelled_algo.append((symbol, algoId))
        return {"status": "SUCCESS"}


class FakeStatusClient:
    def futures_get_open_orders(self, symbol):
        return []

    def futures_get_open_algo_orders(self, symbol):
        return [
            {
                "symbol": symbol,
                "algoId": 101,
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "triggerPrice": "76993.20",
                "reduceOnly": True,
            },
            {
                "symbol": symbol,
                "algoId": 102,
                "orderType": "TAKE_PROFIT_MARKET",
                "algoStatus": "NEW",
                "triggerPrice": "78287.40",
                "reduceOnly": True,
            },
        ]


class Phase3HygieneTests(unittest.TestCase):
    def test_status_guard_allows_localhost_without_token(self):
        with webhook.app.test_request_context("/status", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            self.assertTrue(webhook._status_endpoint_authorized())

    def test_status_guard_blocks_remote_without_token(self):
        with webhook.app.test_request_context("/status", environ_base={"REMOTE_ADDR": "203.0.113.10"}):
            with patch.object(webhook, "HERMES_STATUS_KEY", ""):
                self.assertFalse(webhook._status_endpoint_authorized())

    def test_status_guard_blocks_proxied_localhost_without_token(self):
        with webhook.app.test_request_context(
            "/status",
            headers={"X-Forwarded-For": "203.0.113.10"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            with patch.object(webhook, "HERMES_STATUS_KEY", ""):
                self.assertFalse(webhook._status_endpoint_authorized())

    def test_status_guard_allows_remote_with_matching_token(self):
        with webhook.app.test_request_context(
            "/status",
            headers={"X-Hermes-Status-Key": "secret"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        ):
            with patch.object(webhook, "HERMES_STATUS_KEY", "secret"):
                self.assertTrue(webhook._status_endpoint_authorized())

    def test_purge_stale_stops_cancels_only_orphaned_reduce_only_protection(self):
        client = FakePurgeClient()
        with (
            patch.object(command_center, "PAPER_MODE", False),
            patch.object(command_center, "_get_client", return_value=client),
            patch.object(command_center, "ASSETS", {"ETHUSDT": {}, "BTCUSDT": {}}),
        ):
            result = command_center.cmd_purge_stale_stops()

        self.assertTrue(result.success)
        self.assertEqual(client.cancelled_normal, [("ETHUSDT", 10)])
        self.assertEqual(client.cancelled_algo, [("ETHUSDT", 30)])
        self.assertEqual(result.details["active_position_symbols"], ["BTCUSDT"])

    def test_status_sl_tp_reads_algo_protection_orders(self):
        client = FakeStatusClient()
        with (
            patch.object(command_center, "PAPER_MODE", False),
            patch.object(command_center, "_get_client", return_value=client),
        ):
            sl_price, tp_price = command_center._get_sl_tp_from_orders("BTCUSDT")

        self.assertEqual(sl_price, 76993.20)
        self.assertEqual(tp_price, 78287.40)


if __name__ == "__main__":
    unittest.main()
