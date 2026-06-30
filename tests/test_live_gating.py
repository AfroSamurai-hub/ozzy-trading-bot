import unittest
from unittest.mock import patch

import live_gating


class LiveGatingTests(unittest.TestCase):
    def test_grade_health_watches_weak_lane_below_strategy_sample_floor(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "GRADE_HEALTH_MIN_TRADES", 3),
            patch.object(live_gating, "GRADE_HEALTH_RED_MAX_AVG_PNL", -10.0),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
        ):
            stats.return_value = {
                "sample_size": 3,
                "wins": 0,
                "losses": 3,
                "win_rate": 0.0,
                "total_pnl": -90.0,
                "avg_pnl": -30.0,
            }
            decision = live_gating.evaluate_grade_health("A")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.gate_name, "grade_health")
        self.assertEqual(decision.details["lane_state"], "red")
        self.assertEqual(decision.verdict, "watch")
        self.assertIn("red lane", decision.reason)

    def test_grade_health_allows_yellow_lane_to_avoid_starvation(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "GRADE_HEALTH_MIN_TRADES", 3),
            patch.object(live_gating, "GRADE_HEALTH_MIN_AVG_PNL", 0.0),
            patch.object(live_gating, "GRADE_HEALTH_RED_MAX_AVG_PNL", -10.0),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
        ):
            stats.return_value = {
                "sample_size": 3,
                "wins": 1,
                "losses": 2,
                "win_rate": 1 / 3,
                "total_pnl": -15.0,
                "avg_pnl": -5.0,
            }
            decision = live_gating.evaluate_grade_health("B")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.details["lane_state"], "yellow")
        self.assertIn("allowed at controlled risk", decision.reason)

    def test_grade_a_with_six_weak_samples_is_reduced_not_rejected(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "GRADE_HEALTH_MIN_TRADES", 3),
            patch.object(live_gating, "GRADE_HEALTH_RED_MAX_AVG_PNL", -10.0),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
            patch.object(live_gating, "LIVE_GATE_REDUCED_RISK_MULTIPLIER", 0.5),
        ):
            stats.return_value = {
                "sample_size": 6,
                "wins": 0,
                "losses": 6,
                "win_rate": 0.0,
                "total_pnl": -240.0,
                "avg_pnl": -40.0,
            }
            decision = live_gating.evaluate_grade_health("A")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.verdict, "allow_reduced")
        self.assertEqual(decision.risk_multiplier, 0.5)

    def test_grade_health_allows_insufficient_sample(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "GRADE_HEALTH_MIN_TRADES", 5),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
        ):
            stats.return_value = {"sample_size": 2, "avg_pnl": -100.0}
            decision = live_gating.evaluate_grade_health("A")

        self.assertTrue(decision.allowed)
        self.assertIn("insufficient", decision.reason)

    def test_symbol_heat_reduces_weak_lane_before_mature_block(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "SYMBOL_HEAT_MIN_TRADES", 3),
            patch.object(live_gating, "SYMBOL_HEAT_RED_MAX_AVG_PNL", -10.0),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
        ):
            stats.return_value = {
                "sample_size": 6,
                "wins": 0,
                "losses": 3,
                "win_rate": 0.0,
                "total_pnl": -45.0,
                "avg_pnl": -15.0,
            }
            with patch.object(live_gating, "LIVE_GATE_REDUCED_RISK_MULTIPLIER", 0.5):
                decision = live_gating.evaluate_symbol_heat("SOLUSDT", "SELL", "B")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.gate_name, "symbol_heat")
        self.assertEqual(decision.details["lane_state"], "red")
        self.assertEqual(decision.verdict, "allow_reduced")
        self.assertEqual(decision.risk_multiplier, 0.5)
        self.assertIn("SOLUSDT SELL grade B red lane", decision.reason)

    def test_symbol_heat_mature_weak_lane_stays_advisory(self):
        with (
            patch.object(live_gating, "DATA_DRIVEN_LIVE_GATING", True),
            patch.object(live_gating, "SYMBOL_HEAT_MIN_TRADES", 3),
            patch.object(live_gating, "SYMBOL_HEAT_RED_MAX_AVG_PNL", -10.0),
            patch.object(live_gating, "DATA_GATING_DB", ""),
            patch.object(live_gating.trade_db, "get_recent_closed_trade_stats") as stats,
        ):
            stats.return_value = {
                "sample_size": 20,
                "wins": 1,
                "losses": 19,
                "win_rate": 0.05,
                "total_pnl": -400.0,
                "avg_pnl": -20.0,
            }
            decision = live_gating.evaluate_symbol_heat("ETHUSDT", "SELL", "A")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.verdict, "allow_reduced")

    def test_evaluate_live_setup_includes_live_opportunity_state(self):
        with (
            patch.object(live_gating, "evaluate_grade_health") as grade_health,
            patch.object(live_gating, "evaluate_symbol_heat") as symbol_heat,
            patch.object(live_gating.trade_db, "get_latest_trade_age_hours", return_value=25.0),
        ):
            grade_health.return_value = live_gating.GateDecision(True, "ok", "grade_health", {"lane_state": "green"})
            symbol_heat.return_value = live_gating.GateDecision(True, "ok", "symbol_heat", {"lane_state": "yellow"})
            decision = live_gating.evaluate_live_setup("ETHUSDT", "SELL", "B")

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.details["live_opportunity"]["active"])
        self.assertEqual(decision.details["symbol_heat"]["lane_state"], "yellow")

    def test_live_gate_has_no_protection_entry_veto(self):
        self.assertFalse(hasattr(live_gating, "protection_truth_for_positions"))

if __name__ == "__main__":
    unittest.main()
