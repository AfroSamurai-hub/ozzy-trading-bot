import json
import tempfile
import unittest
from unittest.mock import patch

from review_console import build_review_dashboard_context

try:
    import webhook
except ModuleNotFoundError:  # pragma: no cover - environment-specific dependency
    webhook = None


class ReviewConsoleTests(unittest.TestCase):
    def test_build_dashboard_context_summarizes_reviews_and_recent_events(self):
        reviews = {
            "reviews": [
                {
                    "id": "a1",
                    "ts": "2026-04-25T10:00:00+00:00",
                    "decision": "approved",
                    "symbol": "BTCUSD",
                    "signal": "BUY",
                    "entry": 94000.0,
                    "sl": 93000.0,
                    "tp": 96500.0,
                    "rr": 2.5,
                    "outcome": "win",
                    "outcome_status": "resolved",
                },
                {
                    "id": "r1",
                    "ts": "2026-04-25T11:00:00+00:00",
                    "decision": "rejected",
                    "symbol": "ETHUSD",
                    "signal": "SELL",
                    "entry": 1800.0,
                    "sl": 1820.0,
                    "tp": 1750.0,
                    "rr": 2.5,
                    "filter_name": "rsi_exhaustion",
                    "filter_reason": "RSI exhaustion — RSI 75 above 70 on BUY",
                    "outcome": "loss",
                    "outcome_status": "resolved",
                    "r_multiple": -1.0,
                },
                {
                    "id": "r2",
                    "ts": "2026-04-25T12:00:00+00:00",
                    "decision": "rejected",
                    "symbol": "ETHUSD",
                    "signal": "BUY",
                    "entry": 1810.0,
                    "sl": 1790.0,
                    "tp": 1860.0,
                    "rr": 2.5,
                    "filter_name": "volume_confirmation",
                    "filter_reason": "Low volume",
                    "outcome": None,
                    "outcome_status": "pending",
                    "r_multiple": None,
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviews_path = f"{tmp}/signal_reviews.json"
            log_path = f"{tmp}/trades.log"
            with open(reviews_path, "w", encoding="utf-8") as handle:
                json.dump(reviews, handle)
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write('{"ts":"2026-04-25 10:59:59","event":"SIGNAL_IN","symbol":"ETHUSD","signal":"SELL","entry":1800.0}\n')
                handle.write('{"ts":"2026-04-25 11:00:00","event":"REJECTED","symbol":"ETHUSD","signal":"SELL","reason":"RSI exhaustion"}\n')
                handle.write('{"ts":"2026-04-25 10:00:00","event":"APPROVED","symbol":"BTCUSD","signal":"BUY","entry":94000.0}\n')

            context = build_review_dashboard_context(reviews_path=reviews_path, log_path=log_path, min_signals=1)

        self.assertEqual(context["totals"]["reviews_total"], 3)
        self.assertEqual(context["totals"]["approved_total"], 1)
        self.assertEqual(context["totals"]["rejected_total"], 2)
        self.assertEqual(context["totals"]["resolved_total"], 2)
        self.assertEqual(context["totals"]["pending_total"], 1)
        self.assertEqual(context["latest_signals"][0]["id"], "r2")
        self.assertEqual(context["filters"][0]["filter_name"], "rsi_exhaustion")
        self.assertEqual(context["symbols"][0]["symbol"], "ETHUSD")
        self.assertEqual(context["recent_events"][0]["event"], "REJECTED")

    def test_build_dashboard_context_can_merge_multiple_log_sources(self):
        reviews = {"reviews": []}
        with tempfile.TemporaryDirectory() as tmp:
            reviews_path = f"{tmp}/signal_reviews.json"
            testnet_log = f"{tmp}/trades.log"
            live_micro_log = f"{tmp}/live_micro_trades.log"
            with open(reviews_path, "w", encoding="utf-8") as handle:
                json.dump(reviews, handle)
            with open(testnet_log, "w", encoding="utf-8") as handle:
                handle.write('{"ts":"2026-04-25 10:00:00","event":"APPROVED","symbol":"BTCUSD","signal":"BUY","entry":94000.0}\n')
            with open(live_micro_log, "w", encoding="utf-8") as handle:
                handle.write('{"ts":"2026-04-25 10:05:00","event":"REJECTED","symbol":"ETHUSD","signal":"SELL","reason":"low ADX"}\n')

            context = build_review_dashboard_context(
                reviews_path=reviews_path,
                log_path=testnet_log,
                min_signals=1,
                log_paths=[testnet_log, live_micro_log],
            )

        self.assertEqual([event["event"] for event in context["recent_events"]], ["REJECTED", "APPROVED"])

    @unittest.skipIf(webhook is None, "webhook dependency unavailable in this environment")
    def test_review_route_returns_html(self):
        fake_context = {
            "generated_at": "2026-04-25 15:00:00 UTC",
            "totals": {
                "reviews_total": 1,
                "approved_total": 1,
                "rejected_total": 0,
                "resolved_total": 1,
                "pending_total": 0,
                "unavailable_total": 0,
            },
            "latest_signals": [],
            "filters": [],
            "symbols": [],
            "recent_events": [],
        }
        with patch("webhook.build_review_dashboard_context", return_value=fake_context):
            client = webhook.app.test_client()
            response = client.get("/review")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Signal Review Console", body)
        self.assertIn("reviews_total", body)


if __name__ == "__main__":
    unittest.main()
