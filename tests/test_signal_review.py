import tempfile
import unittest

from signal_review import append_review, load_reviews, summarize_filter_impacts


class SignalReviewTests(unittest.TestCase):
    def test_append_review_persists_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/reviews.json"
            append_review({"id": "r1", "decision": "rejected", "filter_name": "kill_zone", "symbol": "US500"}, path=path)
            data = load_reviews(path)
            self.assertEqual(len(data["reviews"]), 1)
            self.assertEqual(data["reviews"][0]["id"], "r1")

    def test_summary_flags_only_after_minimum_sample(self):
        reviews = []
        for i in range(20):
            reviews.append({
                "id": f"r{i}",
                "decision": "rejected",
                "filter_name": "kill_zone",
                "symbol": "US500",
                "outcome": "win" if i < 12 else "loss",
                "r_multiple": 2.0 if i < 12 else -1.0,
                "outcome_status": "resolved",
            })
        summary = summarize_filter_impacts(reviews, min_signals=20)
        kill_zone = summary["filters"]["kill_zone"]
        self.assertEqual(kill_zone["signals"], 20)
        self.assertEqual(kill_zone["blocked_winners"], 12)
        self.assertEqual(kill_zone["blocked_losers"], 8)
        self.assertTrue(kill_zone["flagged"])


if __name__ == "__main__":
    unittest.main()
