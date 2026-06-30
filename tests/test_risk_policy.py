import unittest
from unittest.mock import patch

import risk_policy


class RiskPolicyTests(unittest.TestCase):
    def test_micro_bootstrap_full_grade_uses_five_dollar_risk(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_RISK_USD", 5.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
        ):
            decision = risk_policy.resolve_trade_risk(34.40, 0.02, 0.02)

        self.assertTrue(decision.bootstrap_active)
        self.assertEqual(decision.mode, "micro_bootstrap")
        self.assertAlmostEqual(decision.risk_dollars, 5.0)
        self.assertAlmostEqual(decision.effective_risk_pct, 5.0 / 34.40)

    def test_micro_bootstrap_preserves_b_grade_reduction(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_RISK_USD", 5.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
        ):
            decision = risk_policy.resolve_trade_risk(34.40, 0.02, 0.01)

        self.assertAlmostEqual(decision.risk_dollars, 2.5)
        self.assertAlmostEqual(decision.adjusted_multiplier, 0.5)

    def test_micro_bootstrap_caps_upside_multiplier_at_target_risk(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_RISK_USD", 5.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
        ):
            decision = risk_policy.resolve_trade_risk(34.40, 0.02, 0.035)

        self.assertAlmostEqual(decision.risk_dollars, 5.0)
        self.assertAlmostEqual(decision.adjusted_multiplier, 1.75)

    def test_percentage_mode_above_bootstrap_ceiling(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_RISK_USD", 5.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
        ):
            decision = risk_policy.resolve_trade_risk(500.0, 0.02, 0.02)

        self.assertFalse(decision.bootstrap_active)
        self.assertEqual(decision.mode, "percentage")
        self.assertAlmostEqual(decision.risk_dollars, 10.0)
        self.assertAlmostEqual(decision.effective_risk_pct, 0.02)

    def test_effective_max_positions_is_one_during_bootstrap(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 1),
        ):
            self.assertEqual(risk_policy.effective_max_positions(3, 34.40), 1)
            self.assertEqual(risk_policy.effective_max_positions(3, 500.0), 3)

    def test_effective_max_positions_honors_bootstrap_cap_override(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MAX_POSITIONS", 2),
        ):
            self.assertEqual(risk_policy.effective_max_positions(3, 34.40), 2)
            self.assertEqual(risk_policy.effective_max_positions(1, 34.40), 1)

    def test_bootstrap_risk_reports_high_risk_target_loss_and_buffers(self):
        with (
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", True),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_RISK_USD", 5.0),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0),
            patch.object(risk_policy, "LIVE_RISK_ESTIMATED_FEE_USD", 0.15),
            patch.object(risk_policy, "LIVE_RISK_SLIPPAGE_BUFFER_USD", 0.35),
        ):
            decision = risk_policy.resolve_trade_risk(33.95, 0.02, 0.02)

        self.assertAlmostEqual(decision.target_loss_at_sl_usd, 5.0)
        self.assertAlmostEqual(decision.effective_risk_pct, 5.0 / 33.95)
        self.assertAlmostEqual(decision.effective_risk_usd, 5.5)
        self.assertIn("HIGH-RISK BOOTSTRAP", decision.warning)

    def test_bootstrap_daily_stop_blocks_on_dollar_not_strategy_full_loss(self):
        with (
            patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 5.5),
            patch.object(risk_policy, "LIVE_MAX_DAILY_FULL_LOSSES", 1),
        ):
            dollar_stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 5.6, "daily_strategy_full_losses": 0},
                target_loss_at_sl_usd=5.0,
            )
            full_loss_stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 0.1, "daily_strategy_full_losses": 1},
                target_loss_at_sl_usd=5.0,
            )

        self.assertTrue(dollar_stop["live_trading_blocked_for_day"])
        self.assertIn("Daily loss", dollar_stop["reason"])
        self.assertFalse(full_loss_stop["live_trading_blocked_for_day"])
        self.assertIsNone(full_loss_stop["reason"])

    def test_bootstrap_daily_stop_uses_equity_percentage_when_no_explicit_cap(self):
        with (
            patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 0.0),
            patch.object(risk_policy, "DAILY_LOSS_PCT", 0.02),
        ):
            stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 250.0},
                target_loss_at_sl_usd=5.0,
                equity=10000.0,
            )
        self.assertTrue(stop["live_trading_blocked_for_day"])
        self.assertAlmostEqual(stop["live_max_daily_loss_usd"], 200.0)
        self.assertIn("Daily loss $250.00 reached cap $200.00", stop["reason"])

    def test_safety_incident_is_visible_without_hard_pause(self):
        visible = risk_policy.bootstrap_daily_stop(
            {"daily_realized_loss_usd": 0.1, "daily_safety_incidents": 1},
            target_loss_at_sl_usd=5.0,
        )
        rearmed = risk_policy.bootstrap_daily_stop(
            {
                "daily_realized_loss_usd": 0.1,
                "daily_safety_incidents": 1,
                "rearm_open_authorizations": 1,
            },
            target_loss_at_sl_usd=5.0,
        )
        allowed, reason = risk_policy.rearm_authorization_check(
            {"healthy": True, "positions": []},
            visible,
            {"daily_safety_incidents": 1},
        )

        self.assertFalse(visible["live_paused_for_safety"])
        self.assertFalse(visible["live_blocked_for_day"])
        self.assertTrue(visible["safety_incident_risk_adjust_active"])
        self.assertAlmostEqual(visible["safety_incident_risk_multiplier"], 0.5)
        self.assertTrue(allowed, reason)
        self.assertFalse(rearmed["live_paused_for_safety"])
        self.assertTrue(rearmed["rearm_available"])

    def test_rearm_uses_reduced_risk_multiplier(self):
        with patch.object(risk_policy, "REARM_RISK_MULTIPLIER", 0.5):
            adjusted, multiplier = risk_policy.apply_rearm_risk_multiplier(0.02, {"rearm_available": True})

        self.assertEqual(multiplier, 0.5)
        self.assertAlmostEqual(adjusted, 0.01)

    def test_second_safety_incident_after_rearm_is_not_daily_hard_block(self):
        stop = risk_policy.bootstrap_daily_stop(
            {
                "daily_realized_loss_usd": 0.2,
                "daily_safety_incidents": 2,
                "daily_safety_incidents_after_rearm": 1,
                "rearm_used_count": 1,
            },
            target_loss_at_sl_usd=5.0,
        )

        self.assertFalse(stop["live_blocked_for_day"])
        self.assertIsNone(stop["reason"])

    def test_dollar_limit_blocks_even_with_rearm_authorization(self):
        with patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 5.5):
            stop = risk_policy.bootstrap_daily_stop(
                {
                    "daily_realized_loss_usd": 5.6,
                    "daily_safety_incidents": 1,
                    "rearm_open_authorizations": 1,
                },
                target_loss_at_sl_usd=5.0,
            )

        self.assertTrue(stop["live_blocked_for_day"])
        self.assertFalse(stop["rearm_available"])

    def test_bootstrap_daily_stop_blocks_when_next_trade_exceeds_remaining_budget(self):
        with (
            patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 5.5),
            patch.object(risk_policy, "MICRO_BOOTSTRAP_MODE", False),
        ):
            stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 3.62},
                target_loss_at_sl_usd=5.0,
                effective_risk_usd=5.5,
            )

        self.assertTrue(stop["live_trading_blocked_for_day"])
        self.assertIn("Remaining daily loss budget", stop["reason"])
        self.assertAlmostEqual(stop["remaining_daily_loss_budget_usd"], 1.88)

    def test_bootstrap_daily_stop_blocks_on_realized_loss_cap(self):
        with patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 11.0):
            stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 11.50},
                target_loss_at_sl_usd=5.0,
                effective_risk_usd=5.5,
            )
        self.assertTrue(stop["live_trading_blocked_for_day"])
        self.assertIn("Daily loss", stop["reason"])

    def test_bootstrap_daily_stop_blocks_on_consecutive_losses_cap(self):
        with (
            patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 15.0),
            patch.object(risk_policy, "CONSECUTIVE_LOSS_HALT", 2),
        ):
            stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 1.0, "daily_consecutive_losses": 2},
                target_loss_at_sl_usd=5.0,
                effective_risk_usd=5.5,
            )
        self.assertTrue(stop["live_trading_blocked_for_day"])
        self.assertIn("Consecutive losses", stop["reason"])

    def test_bootstrap_daily_stop_blocks_on_trades_count_cap(self):
        with (
            patch.object(risk_policy, "LIVE_MAX_DAILY_LOSS_USD", 15.0),
            patch.object(risk_policy, "MAX_TRADES_PER_DAY", 3),
        ):
            stop = risk_policy.bootstrap_daily_stop(
                {"daily_realized_loss_usd": 1.0, "daily_trades_count": 3},
                target_loss_at_sl_usd=5.0,
                effective_risk_usd=5.5,
            )
        self.assertTrue(stop["live_trading_blocked_for_day"])
        self.assertIn("Daily trades count", stop["reason"])


if __name__ == "__main__":
    unittest.main()
