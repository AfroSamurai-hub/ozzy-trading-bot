import json
import os
import tempfile
import unittest

from movement_policy import build_movement_snapshot, record_signal_outcome


class MovementPolicyTests(unittest.TestCase):
    def test_normal_fast_volume_move_opens_sl_tolerance(self):
        asset = {
            "min_sl": 20,
            "default_offset": 100,
            "min_sl_tolerance_pct": 0.10,
            "normal_move_bonus_pct": 0.05,
            "fast_move_bonus_pct": 0.15,
            "volume_bonus_pct": 0.05,
            "strong_volume_ratio": 1.20,
            "max_min_sl_tolerance_pct": 0.30,
        }
        live = {"atr": 19.42141, "volume": 71452.9304, "volume_avg20": 22122.5613}

        snapshot = build_movement_snapshot("ETHUSD", asset, live, sl_distance=19.42141)

        self.assertEqual(snapshot["movement_class"], "normal")
        self.assertAlmostEqual(snapshot["tolerance_pct"], 0.20, places=4)
        self.assertAlmostEqual(snapshot["min_sl_buffer"], 16.0, places=4)
        self.assertTrue(snapshot["allowed_with_tolerance"])

    def test_quiet_move_stays_tight(self):
        asset = {
            "min_sl": 20,
            "default_offset": 100,
            "min_sl_tolerance_pct": 0.10,
            "normal_move_bonus_pct": 0.05,
            "fast_move_bonus_pct": 0.15,
            "volume_bonus_pct": 0.05,
            "strong_volume_ratio": 1.20,
            "max_min_sl_tolerance_pct": 0.30,
        }
        live = {"atr": 17.0, "volume": 1000, "volume_avg20": 2000}

        snapshot = build_movement_snapshot("ETHUSD", asset, live, sl_distance=17.0)

        self.assertEqual(snapshot["movement_class"], "quiet")
        self.assertAlmostEqual(snapshot["tolerance_pct"], 0.10, places=4)
        self.assertAlmostEqual(snapshot["min_sl_buffer"], 18.0, places=4)
        self.assertFalse(snapshot["allowed_with_tolerance"])

    def test_record_signal_outcome_tracks_symbol_stats(self):
        snapshot = {
            "movement_class": "normal",
            "movement_ratio": 0.97,
            "volume_ratio": 3.23,
            "allowed_with_tolerance": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            stats_path = os.path.join(tmp, "signal_stats.json")
            record_signal_outcome("ETHUSD", "approved", snapshot, stats_path=stats_path)
            record_signal_outcome("ETHUSD", "rejected", snapshot, reason="SL too tight", stats_path=stats_path)

            with open(stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        symbol = data["symbols"]["ETHUSD"]
        self.assertEqual(symbol["approved"], 1)
        self.assertEqual(symbol["rejected"], 1)
        self.assertEqual(symbol["movement_classes"]["normal"], 2)
        self.assertEqual(symbol["allowed_with_tolerance"], 2)
        self.assertEqual(symbol["reasons"]["SL too tight"], 1)


if __name__ == "__main__":
    unittest.main()
