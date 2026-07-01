import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.openclaw_breakout_executor as obe
from core.openclaw_breakout_executor import (
    attach_derivatives_context,
    build_breakout_payload,
    evaluate_blueprint_trigger,
    load_active_blueprints,
)


def _concurrent_state_writer(state_path: str, scan_lock_path: str, prefix: str, count: int) -> None:
    path = Path(state_path)
    for index in range(count):
        with obe.exclusive_file_lock(Path(scan_lock_path), timeout=10):
            state = obe.load_state(path)
            state.setdefault("fired", {})[f"{prefix}-{index}"] = {
                "fired_at": obe.utc_now().isoformat()
            }
            obe.save_state(state, path)
        time.sleep(0.001)


def _concurrent_shadow_logger(path: str, prefix: str, count: int) -> None:
    original_save = obe.save_shadow_opportunities

    def delayed_save(rows, path):
        time.sleep(0.02)
        original_save(rows, path)

    with mock.patch.object(obe, "save_shadow_opportunities", side_effect=delayed_save):
        for index in range(count):
            symbol = f"{prefix}{index}USDT"
            obe.log_shadow_opportunity(
                {"symbol": symbol, "side": "BUY", "entry_price": 100.0, "stop_loss": 99.0},
                {"symbol": symbol, "assigned_setup_type": "BREAKOUT", "status": "SHADOW", "would_fire": True},
                {"close": 100.0, "atr": 1.0},
                path=Path(path),
            )
            time.sleep(0.001)


class OpenClawBreakoutExecutorTests(unittest.TestCase):
    def _neutral_1h_context(self):
        return {"rsi": 55.0, "ema_distance_pct": 2.0, "close": 102.0, "ema200": 100.0, "interval": "1h"}

    def test_load_active_blueprints_ignores_meta_and_non_armed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "active_orders.json"
            path.write_text(json.dumps({
                "_openclaw_meta": {"note": "not a blueprint"},
                "SOLUSDT": {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 69.5, "status": "ARMED"},
                "HYPEUSDT": {"symbol": "HYPEUSDT", "side": "SELL", "entry_price": 50.0, "status": "FIRED"},
            }))

            rows = load_active_blueprints(path)

        self.assertEqual([row["symbol"] for row in rows], ["SOLUSDT"])
        self.assertEqual(rows[0]["side"], "BUY")

    def test_corrupt_execution_state_is_backed_up_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openclaw_breakout_state.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                obe.load_state(path)

            self.assertEqual(len(list(Path(tmp).glob("*.corrupt"))), 1)
            self.assertTrue(path.exists())
            with self.assertRaises(RuntimeError):
                obe.load_state(path)

    def test_invalid_execution_state_shape_is_backed_up_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openclaw_breakout_state.json"
            path.write_text(json.dumps({"fired": ["not-a-map"]}), encoding="utf-8")

            with self.assertRaises(RuntimeError):
                obe.load_state(path)

            self.assertEqual(len(list(Path(tmp).glob("*.corrupt"))), 1)

    def test_scan_fails_closed_without_posting_when_execution_state_is_corrupt(self):
        with mock.patch.object(
            obe,
            "load_state",
            side_effect=obe.StateCorruptionError("corrupt state"),
        ), mock.patch.object(obe, "post_webhook") as post_webhook:
            result = obe.scan_once()

        self.assertEqual(result["status"], "STATE_CORRUPT")
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["fired"], 0)
        post_webhook.assert_not_called()

    def test_cooldown_fails_closed_when_fired_timestamp_is_invalid(self):
        blueprint = {"symbol": "BTCUSDT", "side": "BUY", "entry_price": 50000.0}
        state = {"fired": {obe._breakout_key(blueprint): {"fired_at": "invalid"}}}

        self.assertTrue(obe._cooldown_active(blueprint, state))

    def test_cross_process_scan_lock_preserves_all_cooldown_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            lock_path = Path(tmp) / "scan.lock"
            obe.save_state({"fired": {}, "last_scan": None, "last_results": []}, state_path)
            process_context = multiprocessing.get_context("spawn")
            workers = [
                process_context.Process(
                    target=_concurrent_state_writer,
                    args=(str(state_path), str(lock_path), prefix, 20),
                )
                for prefix in ("execution", "shadow")
            ]

            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=15)

            self.assertEqual([worker.exitcode for worker in workers], [0, 0])
            self.assertEqual(len(obe.load_state(state_path)["fired"]), 40)

    def test_all_json_state_saves_use_atomic_writer(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(obe, "_atomic_write_json") as atomic_write:
            root = Path(tmp)
            obe.save_state({"fired": {}}, root / "execution.json")
            obe.save_opportunity_state({"breakouts": {}}, root / "opportunity.json")
            obe.save_shadow_opportunities([], root / "shadow.json")

        self.assertEqual(atomic_write.call_count, 3)

    def test_corrupt_observation_state_is_backed_up_before_safe_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            opportunity = root / "opportunity.json"
            shadow = root / "shadow.json"
            opportunity.write_text("{broken", encoding="utf-8")
            shadow.write_text("[broken", encoding="utf-8")

            self.assertEqual(obe.load_opportunity_state(opportunity)["breakouts"], {})
            self.assertEqual(obe.load_shadow_opportunities(shadow), [])

            self.assertEqual(len(list(root.glob("opportunity.json.*.corrupt"))), 1)
            self.assertEqual(len(list(root.glob("shadow.json.*.corrupt"))), 1)

    def test_concurrent_shadow_loggers_preserve_every_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadow.json"
            process_context = multiprocessing.get_context("spawn")
            workers = [
                process_context.Process(target=_concurrent_shadow_logger, args=(str(path), prefix, 20))
                for prefix in ("A", "B")
            ]

            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=15)

            self.assertEqual([worker.exitcode for worker in workers], [0, 0])
            self.assertEqual(len(obe.load_shadow_opportunities(path)), 40)

    def test_buy_blueprint_passes_only_after_trigger_with_impulse_confirmation(self):
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 69.5, "status": "ARMED"}
        indicators = {
            "close": 69.58,
            "open": 69.2,
            "high": 69.8,
            "low": 69.1,
            "volume_ratio": 1.25,
            "atr": 0.4,
            "top_wick_pct": 0.05,
            "bottom_wick_pct": 0.15,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["signal"], "BUY")
        self.assertEqual(verdict["reason"], "breakout_confirmed")

    def test_buy_blueprint_rejects_before_trigger(self):
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 69.5, "status": "ARMED"}
        indicators = {
            "close": 69.49,
            "open": 69.2,
            "high": 69.6,
            "low": 69.1,
            "volume_ratio": 1.25,
            "atr": 0.4,
            "top_wick_pct": 0.05,
            "bottom_wick_pct": 0.15,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertIn("close_not_beyond_trigger", verdict["reasons"])

    def test_buy_blueprint_rejects_weak_post_loss_momentum_candle(self):
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 100.0, "status": "ARMED"}
        indicators = {
            "close": 100.22,
            "open": 100.0,
            "high": 100.3,
            "low": 99.9,
            "volume_ratio": 0.70,
            "atr": 1.0,
            "top_wick_pct": 0.49,
            "bottom_wick_pct": 0.10,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertIn("volume_expansion_missing", verdict["reasons"])
        self.assertIn("displacement_body_too_small", verdict["reasons"])

    def test_buy_blueprint_rejects_late_chase_far_beyond_trigger(self):
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 100.0, "status": "ARMED"}
        indicators = {
            "close": 101.0,
            "open": 100.2,
            "high": 101.2,
            "low": 100.1,
            "volume_ratio": 1.5,
            "atr": 1.0,
            "top_wick_pct": 0.05,
            "bottom_wick_pct": 0.15,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertIn("chasing_avoided_price_too_far_above_trigger", verdict["reasons"])

    def test_sell_blueprint_rejects_late_chase_far_below_trigger(self):
        blueprint = {"symbol": "SOLUSDT", "side": "SELL", "entry_price": 100.0, "status": "ARMED"}
        indicators = {
            "close": 99.0,
            "open": 99.8,
            "high": 99.9,
            "low": 98.8,
            "volume_ratio": 1.5,
            "atr": 1.0,
            "top_wick_pct": 0.15,
            "bottom_wick_pct": 0.05,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertIn("chasing_avoided_price_too_far_below_trigger", verdict["reasons"])

    def test_render_b_mixed_regression_rejected_by_tier_quality(self):
        blueprint = {
            "symbol": "RENDERUSDT",
            "side": "BUY",
            "entry_price": 1.862,
            "status": "ARMED",
            "openclaw_lane_tier": "B",
            "entry_setup_label": "OPENCLAW_BREAKOUT_B_MIXED",
        }
        indicators = {
            "close": 1.862,
            "open": 1.857,
            "high": 1.862,
            "low": 1.8435,
            "volume_ratio": 1.164,
            "atr": 0.0185,
            "top_wick_pct": 0.0,
            "bottom_wick_pct": 0.73,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["lane_tier"], "B")
        self.assertIn("volume_expansion_missing", verdict["reasons"])
        self.assertIn("displacement_body_too_small", verdict["reasons"])

    def test_hype_regression_rejected_by_low_quality_and_1h_anti_chase(self):
        blueprint = {
            "symbol": "HYPEUSDT",
            "side": "BUY",
            "entry_price": 68.486,
            "status": "ARMED",
            "openclaw_lane_tier": "A",
            "entry_setup_label": "OPENCLAW_BREAKOUT_A_ALIGNED",
        }
        indicators = {
            "close": 68.536,
            "open": 68.12,
            "high": 68.6,
            "low": 67.9,
            "volume_ratio": 0.696,
            "atr": 1.3867,
            "top_wick_pct": 0.09,
            "bottom_wick_pct": 0.31,
        }
        hot_context = {"rsi": 76.22, "ema_distance_pct": 13.008, "close": 68.37, "ema200": 60.5, "interval": "1h"}

        verdict = evaluate_blueprint_trigger(blueprint, indicators, hot_context)

        self.assertFalse(verdict["passed"])
        self.assertIn("volume_expansion_missing", verdict["reasons"])
        self.assertIn("displacement_body_too_small", verdict["reasons"])
        self.assertIn("overextended_1h_rsi_ema_chase", verdict["reasons"])


    def test_non_breakout_setup_is_observe_only_and_cannot_fire(self):
        blueprint = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 100.0,
            "status": "ARMED",
            "assigned_setup_type": "PULLBACK",
            "secondary_setup_type": "RETEST",
        }
        indicators = {
            "close": 100.1,
            "open": 99.5,
            "high": 100.2,
            "low": 99.4,
            "volume_ratio": 2.0,
            "atr": 1.0,
            "top_wick_pct": 0.05,
            "bottom_wick_pct": 0.15,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["reason"], "setup_not_enabled_for_breakout_executor")
        self.assertIn("setup_not_enabled_for_breakout_executor", verdict["reasons"])
        self.assertEqual(verdict["assigned_setup_type"], "PULLBACK")

    def test_shadow_only_setup_is_terminal_observation_only(self):
        blueprint = {
            "symbol": "ZECUSDT",
            "side": "BUY",
            "entry_price": 100.0,
            "status": "ARMED",
            "assigned_setup_type": "SHADOW_ONLY",
            "secondary_setup_type": "BREAKOUT",
        }
        indicators = {
            "close": 100.1,
            "open": 99.5,
            "high": 100.2,
            "low": 99.4,
            "volume_ratio": 2.0,
            "atr": 1.0,
            "top_wick_pct": 0.05,
            "bottom_wick_pct": 0.15,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["reason"], "bench_watch_observation_only")
        self.assertEqual(verdict["assigned_setup_type"], "SHADOW_ONLY")

    def test_payload_targets_breakout_retest_lane_and_testnet_source(self):
        os.environ["WEBHOOK_SECRET"] = "secret-for-test"
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 69.5, "stop_loss": 68.5}
        indicators = {"close": 69.7, "atr": 0.4}

        payload = build_breakout_payload(blueprint, indicators)

        self.assertEqual(payload["symbol"], "SOLUSDT")
        self.assertEqual(payload["signal"], "BUY")
        self.assertEqual(payload["strategy"], "breakout")
        self.assertEqual(payload["strategy_label"], "BREAKOUT_RETEST")
        self.assertEqual(payload["entry_setup_label"], "OPENCLAW_BREAKOUT")
        self.assertEqual(payload["source_service"], "openclaw_breakout_executor")
        self.assertEqual(payload["execution_mode"], "TESTNET")
        self.assertEqual(payload["webhook_port"], 5001)

    def test_payload_preserves_daily_profile_labels_from_blueprint(self):
        blueprint = {
            "symbol": "RENDERUSDT",
            "side": "BUY",
            "entry_price": 2.5,
            "stop_loss": 2.4,
            "entry_setup_label": "OPENCLAW_BREAKOUT_B_MIXED",
            "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT_MIXED",
        }
        indicators = {"close": 2.52, "atr": 0.04}

        payload = build_breakout_payload(blueprint, indicators)

        self.assertEqual(payload["entry_setup_label"], "OPENCLAW_BREAKOUT_B_MIXED")
        self.assertEqual(payload["regime_label"], "OPENCLAW_4H_MACRO_BREAKOUT_MIXED")

    def test_derivatives_context_is_attached_as_advisory_only(self):
        verdict = {"symbol": "SOLUSDT", "signal": "BUY", "passed": True, "reasons": []}

        enriched = attach_derivatives_context(
            verdict,
            lambda symbol, direction: {
                "status": "ok",
                "symbol": symbol,
                "direction": direction,
                "verdict": "supportive",
                "score": 3,
                "reasons": ["oi_confirms_new_longs"],
                "metrics": {"open_interest_delta_pct": 2.5},
            },
        )

        self.assertTrue(enriched["passed"])
        self.assertNotIn("oi_confirms_new_longs", enriched["reasons"])
        self.assertEqual(enriched["derivatives_context"]["verdict"], "supportive")
        self.assertEqual(enriched["derivatives_context"]["score"], 3)


class OpenClawShadowExecutorTests(unittest.TestCase):
    """Shadow-mode evaluation paths for BREAKOUT, RETEST, PULLBACK and CONTINUATION."""

    def setUp(self):
        self._orig_shadow_mode = obe.SHADOW_MODE
        self._orig_state_path = obe.OPPORTUNITY_STATE_PATH
        self._orig_shadow_path = obe.SHADOW_OPPORTUNITIES_PATH
        self._tmp = Path(tempfile.mkdtemp())
        obe.OPPORTUNITY_STATE_PATH = self._tmp / "openclaw_opportunity_state.json"
        obe.SHADOW_OPPORTUNITIES_PATH = self._tmp / "openclaw_shadow_opportunities.json"
        obe.SHADOW_MODE = True

    def tearDown(self):
        obe.SHADOW_MODE = self._orig_shadow_mode
        obe.OPPORTUNITY_STATE_PATH = self._orig_state_path
        obe.SHADOW_OPPORTUNITIES_PATH = self._orig_shadow_path

    def _neutral_1h_context(self):
        return {"rsi": 55.0, "ema_distance_pct": 2.0, "close": 102.0, "ema200": 100.0, "interval": "1h"}

    def test_shadow_breakout_uses_relaxed_thresholds_and_does_not_execute(self):
        blueprint = {"symbol": "SOLUSDT", "side": "BUY", "entry_price": 100.0, "status": "ARMED"}
        indicators = {
            "close": 100.22,
            "open": 100.0,
            "high": 100.3,
            "low": 99.9,
            "volume_ratio": 0.70,
            "atr": 1.0,
            "top_wick_pct": 0.10,
            "bottom_wick_pct": 0.10,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, self._neutral_1h_context())

        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["would_fire"])
        self.assertFalse(verdict["execution_enabled"])
        self.assertEqual(verdict["status"], "SHADOW_WOULD_FIRE")
        self.assertEqual(verdict["assigned_setup_type"], "BREAKOUT")
        obe.log_shadow_opportunity(blueprint, verdict, indicators, path=obe.SHADOW_OPPORTUNITIES_PATH)
        rows = obe.load_shadow_opportunities(obe.SHADOW_OPPORTUNITIES_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["setup"], "BREAKOUT")
        self.assertEqual(rows[0]["would_fire"], True)

    def test_shadow_retest_would_fire_with_fresh_breakout_and_rejection(self):
        blueprint = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 65000.0,
            "status": "ARMED",
            "assigned_setup_type": "RETEST",
        }
        obe.record_breakout_memory(blueprint, {"close": 65050.0})
        indicators = {
            "close": 65020.0,
            "open": 64980.0,
            "high": 65050.0,
            "low": 64990.0,
            "atr": 120.0,
            "bottom_wick_pct": 0.50,
            "top_wick_pct": 0.10,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators)

        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["would_fire"])
        self.assertFalse(verdict["execution_enabled"])
        self.assertEqual(verdict["status"], "SHADOW_WOULD_FIRE")
        self.assertEqual(verdict["reason"], "OPENCLAW_RETEST_CONFIRMED")
        obe.log_shadow_opportunity(blueprint, verdict, indicators, path=obe.SHADOW_OPPORTUNITIES_PATH)
        rows = obe.load_shadow_opportunities(obe.SHADOW_OPPORTUNITIES_PATH)
        self.assertEqual(rows[-1]["setup"], "RETEST")

    def test_shadow_pullback_would_fire_on_1h_ema_reclaim(self):
        blueprint = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 64850.0,
            "status": "ARMED",
            "assigned_setup_type": "PULLBACK",
        }
        indicators = {
            "close": 64880.0,
            "open": 64850.0,
            "high": 64900.0,
            "low": 64820.0,
            "rsi": 40.0,
            "bottom_wick_pct": 0.50,
            "top_wick_pct": 0.10,
            "ema200_1h": 64850.0,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators)

        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["would_fire"])
        self.assertFalse(verdict["execution_enabled"])
        self.assertEqual(verdict["status"], "SHADOW_WOULD_FIRE")
        self.assertEqual(verdict["reason"], "OPENCLAW_PULLBACK_VALUE_RECLAIM")

    def test_shadow_continuation_would_fire_on_minor_range_break(self):
        blueprint = {
            "symbol": "NEARUSDT",
            "side": "BUY",
            "entry_price": 5.0,
            "status": "ARMED",
            "assigned_setup_type": "CONTINUATION",
        }
        recent_candles = [
            {"open": 4.5, "high": 4.9, "low": 4.4, "close": 4.8, "volume": 1000.0}
            for _ in range(40)
        ]
        indicators = {
            "close": 4.95,
            "open": 4.85,
            "high": 5.0,
            "low": 4.8,
            "volume_ratio": 0.80,
        }

        verdict = evaluate_blueprint_trigger(blueprint, indicators, recent_candles=recent_candles)

        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["would_fire"])
        self.assertFalse(verdict["execution_enabled"])
        self.assertEqual(verdict["status"], "SHADOW_WOULD_FIRE")
        self.assertEqual(verdict["reason"], "OPENCLAW_CONTINUATION_FLAG_BREAK")

    def test_retest_memory_state_shape_and_expiry(self):
        blueprint = {"symbol": "SOLUSDT", "side": "SELL", "entry_price": 70.0}
        now = obe.utc_now()
        obe.record_breakout_memory(blueprint, {"close": 69.5}, now=now)
        state = obe.load_opportunity_state()
        key = obe._breakout_memory_key("SOLUSDT", "SELL", 70.0)
        self.assertIn(key, state["breakouts"])
        stored = state["breakouts"][key]
        self.assertEqual(stored["symbol"], "SOLUSDT")
        self.assertEqual(stored["side"], "SELL")
        self.assertEqual(stored["expiry_candles"], 48)
        self.assertTrue(obe.prior_breakout_fresh(blueprint, state, now=now + timedelta(hours=1))[0])
        self.assertFalse(obe.prior_breakout_fresh(blueprint, state, now=now + timedelta(hours=13))[0])


if __name__ == "__main__":
    unittest.main()
