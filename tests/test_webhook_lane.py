import time
import unittest
from unittest.mock import patch

import webhook


class TestWebhookLane(unittest.TestCase):
    def setUp(self):
        self.client = webhook.app.test_client()

    @patch("webhook._base_record_signal_review", return_value=None)
    @patch("webhook._monitor_entry_gate_status", return_value={"allowed": True})
    def test_unknown_lane_rejected(self, mock_monitor, mock_review):
        resp = self.client.post(
            "/webhook",
            json={
                "secret": webhook.WEBHOOK_SECRET,
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "entry": 100.0,
                "timestamp": int(time.time()),
                "version": "2.2.2",
                "regime": "smc_pro",
                "structure": "bullish_bos",
                "bias": "bullish",
                "source_service": "unknown_source",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertIn("unknown or disabled lane", body.get("reason", "").lower())

    @patch("webhook._base_record_signal_review", return_value=None)
    @patch("webhook._monitor_entry_gate_status", return_value={"allowed": True})
    def test_known_lane_accepted(self, mock_monitor, mock_review):
        resp = self.client.post(
            "/webhook",
            json={
                "secret": webhook.WEBHOOK_SECRET,
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "entry": 100.0,
                "timestamp": int(time.time()),
                "version": "2.2.2",
                "regime": "smc_pro",
                "structure": "bullish_bos",
                "bias": "bullish",
                "source_service": "signal_generator",
            },
        )
        # The signal may be rejected for other reasons (balance, monitor, etc.),
        # but it must NOT be rejected for lane reasons.
        body = resp.get_json()
        self.assertNotIn("unknown or disabled lane", body.get("reason", "").lower())
        self.assertNotIn("not in lane", body.get("reason", "").lower())


if __name__ == "__main__":
    unittest.main()
