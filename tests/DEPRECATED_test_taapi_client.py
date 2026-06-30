import unittest
from unittest.mock import patch

import taapi_client


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class TaapiForexBulkTests(unittest.TestCase):
    def test_forex_bulk_returns_dual_read_payload_from_single_request(self):
        payload = {
            "data": [
                {"id": "supertrend_bt1", "indicator": "supertrend", "result": {"value": 4754.1908, "valueAdvice": "long"}, "errors": []},
                {"id": "rsi_bt1", "indicator": "rsi", "result": {"value": 63.0874}, "errors": []},
                {"id": "ema_bt1", "indicator": "ema", "result": {"value": 4797.5609}, "errors": []},
                {"id": "atr_bt1", "indicator": "atr", "result": {"value": 36.99208}, "errors": []},
                {"id": "supertrend_bt0", "indicator": "supertrend", "result": {"value": 4754.1908, "valueAdvice": "short"}, "errors": []},
                {"id": "rsi_bt0", "indicator": "rsi", "result": {"value": 56.2370}, "errors": []},
                {"id": "ema_bt0", "indicator": "ema", "result": {"value": 4797.8658}, "errors": []},
                {"id": "atr_bt0", "indicator": "atr", "result": {"value": 36.37264}, "errors": []},
            ]
        }

        with patch("taapi_client.requests.post", return_value=_FakeResponse(payload)) as mock_post:
            data = taapi_client.get_bulk_indicators("XAUUSD")

        self.assertEqual(data["supertrend_direction"], "long")
        self.assertEqual(data["supertrend_direction_forming"], "short")
        self.assertEqual(data["confirmed"]["atr"], 36.99208)
        self.assertEqual(data["forming"]["atr"], 36.37264)
        self.assertEqual(data["backtrack_1"]["rsi"], 63.09)
        self.assertEqual(data["backtrack_0"]["rsi"], 56.24)
        self.assertEqual(data["volume"], 0.0)
        self.assertEqual(data["volume_avg20"], 0.0)

        mock_post.assert_called_once()
        sent_payload = mock_post.call_args.kwargs["json"]
        indicators = sent_payload["construct"]["indicators"]
        self.assertEqual(len(indicators), 8)
        self.assertEqual({item["id"] for item in indicators}, {
            "supertrend_bt1", "rsi_bt1", "ema_bt1", "atr_bt1",
            "supertrend_bt0", "rsi_bt0", "ema_bt0", "atr_bt0",
        })

    def test_forex_bulk_falls_back_to_twelvedata_on_provider_error(self):
        failing_payload = {
            "data": [
                {
                    "id": "forex_EUR/USD_4h",
                    "errors": ["An unknown error has occurred!"],
                    "error": {"error": "You've exceeded the maximum requests per minute"},
                }
            ]
        }
        fallback = {"symbol": "EURUSD", "source": "twelvedata", "supertrend_direction": None}

        with patch("taapi_client.requests.post", return_value=_FakeResponse(failing_payload)):
            with patch("twelvedata_client.get_bulk_indicators", return_value=fallback) as mock_twelve:
                data = taapi_client.get_bulk_indicators("EURUSD")

        self.assertEqual(data, fallback)
        mock_twelve.assert_called_once_with("EURUSD")


if __name__ == "__main__":
    unittest.main()
