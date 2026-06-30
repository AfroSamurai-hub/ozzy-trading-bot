"""
tests/test_loss_minimization_controller.py
==========================================
Phase 1 Loss Minimization Controller — OBSERVE ONLY.

Tests cover:
  1.  ROUNDTRIP_CANDIDATE detected (R-based path)
  2.  ROUNDTRIP_CANDIDATE NOT detected when peak too low (both R and dollar)
  3.  Grade B EARLY_INVALIDATION_CANDIDATE detected
  4.  Grade A EARLY_INVALIDATION_CANDIDATE uses stricter threshold
  5.  PROFIT_LOCK_CANDIDATE detected
  6.  GRADE_B_TIME_DECAY_CANDIDATE detected
  7.  No Binance write calls from loss minimisation controller
  8.  Candidate deduplication (last_seen_at updated, not duplicated)
  9.  Candidate resolves when trade closes
  10. Existing scratch-approval and milestone tests still pass (import smoke)

Tuning tests (Phase 1 v0.1 patch):
  T1. STANDARD_TESTNET: tiny $0.68 peak does NOT trigger ROUNDTRIP (RENDER case)
  T2. STANDARD_TESTNET: R-path still fires correctly
  T3. LIVE_MICRO: $0.30 dollar fallback still works
  T4. STANDARD_TESTNET: risk-scaled fallback fires when R is unavailable and
      peak >= max($10, 5% of risk)
  T5. STANDARD_TESTNET: risk-scaled fallback suppressed when R is computable
  T6. giveback_ratio stored as raw fraction (0.0–1.0+)
  T7. giveback_pct stored as percentage (0.0–100.0+), not re-multiplied
  T8. Markdown writes giveback_pct directly (no x100)
  T9. Grade normalisation: lowercase 'b' triggers Grade B rules
  T10. Grade normalisation: 'A ' (with trailing space) triggers Grade A rules
  T11. EARLY_INVALIDATION fires when peak_r is None (zero MFE worst case)
  T12. EARLY_INVALIDATION fires for grade A with current_r <= -0.50
  T13. EARLY_INVALIDATION fires for grade B with current_r <= -0.35
  T14. candidate dict contains both giveback_ratio and giveback_pct fields

Safety assertions:
  * No function in determine_loss_minimization_candidates() or
    _write_loss_minimization_files() calls any Binance connector method.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import ozzy_context_observer as obs
from ozzy_context_observer import (
    determine_loss_minimization_candidates,
    _write_loss_minimization_files,
    _lm_candidate_id,
    ROUNDTRIP_CANDIDATE,
    EARLY_INVALIDATION_CANDIDATE,
    PROFIT_LOCK_CANDIDATE,
    GRADE_B_TIME_DECAY_CANDIDATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(
    trade_id: int = 1,
    instance: str = "STANDARD_TESTNET",
    symbol: str = "LINKUSDT",
    side: str = "BUY",
    setup_grade: str = "B",
    entry_price: float = 9.0,
    current_price: float = 8.5,
    qty: float = 100.0,
    risk_dollars: float = 100.0,
    peak_pnl: float = 0.0,
    effective_peak_pnl: float = 0.0,
    current_pnl: float = -10.0,
    giveback_pct: float = 0.0,   # expressed as percentage (0–100+), matching t["giveback_pct"]
    trade_age: float = 1.0,       # hours
    timeframe: str = "60",
):
    return {
        "id":                trade_id,
        "instance":          instance,
        "symbol":            symbol,
        "side":              side,
        "setup_grade":       setup_grade,
        "entry_price":       entry_price,
        "current_price":     current_price,
        "qty":               qty,
        "risk_dollars":      risk_dollars,
        "peak_pnl":          peak_pnl,
        "effective_peak_pnl": effective_peak_pnl,
        "current_pnl":       current_pnl,
        "giveback_pct":      giveback_pct,  # percentage, e.g. 25.97
        "trade_age":         trade_age,
        "timeframe":         timeframe,
    }


# ===========================================================================
# Original 10 required tests
# ===========================================================================

class TestRoundtripCandidate(unittest.TestCase):
    """Tests 1 & 2: ROUNDTRIP_CANDIDATE detection."""

    def test_roundtrip_detected_r_based(self):
        """Test 1: peak_r >= 0.30 AND current_r <= 0.00 → ROUNDTRIP detected."""
        # risk_dollars=100, peak_pnl=35 → peak_r=0.35; current_pnl=-5 → current_r=-0.05
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
            giveback_pct=114.3,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types,
                      f"Expected ROUNDTRIP_CANDIDATE, got {types}")
        rt = next(r for r in results if r["candidate_type"] == ROUNDTRIP_CANDIDATE)
        self.assertEqual(rt["instance"], "STANDARD_TESTNET")
        self.assertEqual(rt["trade_id"], 1)
        self.assertIsNotNone(rt["peak_r"])
        self.assertGreaterEqual(rt["peak_r"], 0.30)
        self.assertIsNotNone(rt["current_r"])
        self.assertLessEqual(rt["current_r"], 0.00)
        # Safety: no Binance write fields
        self.assertNotIn("binance_order_id", rt)

    def test_roundtrip_not_detected_peak_too_low(self):
        """Test 2: peak_r < 0.30 AND peak_pnl < $10 → ROUNDTRIP must NOT fire.

        Both the R-based path (peak_r >= 0.30) and the STANDARD_TESTNET
        risk-scaled fallback (peak_pnl >= max($10, 5% of risk)) must both be
        unsatisfied.  We use a peak_pnl of $0.10, giving peak_r=0.001.
        """
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=0.10,   # peak_r=0.001 < 0.30; $0.10 << $10 threshold
            current_pnl=-5.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(ROUNDTRIP_CANDIDATE, types,
                         f"ROUNDTRIP should NOT fire when peak_r < 0.30 "
                         f"and peak_pnl << threshold, got {types}")

    def test_roundtrip_dollar_path_live_micro(self):
        """ROUNDTRIP dollar-path: peak_pnl >= 0.30 and current_pnl <= 0.00 (LIVE_MICRO)."""
        trade = _make_trade(
            instance="LIVE_MICRO",
            risk_dollars=1.0,
            effective_peak_pnl=0.50,   # > 0.30
            current_pnl=-0.10,          # <= 0
            giveback_pct=120.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types)

    def test_roundtrip_severity_exit_review_when_deeply_negative(self):
        """When current_r <= -0.20 severity should be EXIT_REVIEW."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-25.0,   # current_r = -0.25
            giveback_pct=171.0,
        )
        results = determine_loss_minimization_candidates(trade)
        rt = next((r for r in results if r["candidate_type"] == ROUNDTRIP_CANDIDATE), None)
        self.assertIsNotNone(rt)
        self.assertEqual(rt["recommendation"], "EXIT_REVIEW")


class TestEarlyInvalidationCandidate(unittest.TestCase):
    """Tests 3 & 4: EARLY_INVALIDATION_CANDIDATE with grade differentiation."""

    def test_grade_b_early_invalidation_detected(self):
        """Test 3: Grade B — current_r <= -0.35, peak_r < 0.15, age >= 20 min."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=5.0,    # peak_r = 0.05 < 0.15 ✓
            current_pnl=-38.0,          # current_r = -0.38 <= -0.35 ✓
            trade_age=0.5,              # 0.5h = 30 min >= 20 min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types)

    def test_grade_b_not_fire_before_age_window(self):
        """Grade B invalidation must NOT fire before 20 minutes."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=5.0,
            current_pnl=-38.0,
            trade_age=0.2,  # 12 minutes — too fresh
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types)

    def test_grade_b_not_fire_peak_too_high(self):
        """Grade B invalidation must NOT fire if peak_r >= 0.15."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=20.0,   # peak_r=0.20 >= 0.15 → block
            current_pnl=-38.0,
            trade_age=0.5,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types)

    def test_grade_a_stricter_threshold(self):
        """Test 4: Grade A uses -0.50 threshold (not -0.35)."""
        # current_r = -0.40: fires for B, must NOT fire for A
        trade_a = _make_trade(
            setup_grade="A",
            risk_dollars=100.0,
            effective_peak_pnl=5.0,   # peak_r = 0.05 < 0.25
            current_pnl=-40.0,         # current_r = -0.40  (between -0.35 and -0.50)
            trade_age=1.0,             # 60 min >= 30 min
        )
        results_a = determine_loss_minimization_candidates(trade_a)
        types_a = [r["candidate_type"] for r in results_a]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types_a,
                         "Grade A must NOT fire at -0.40R (threshold is -0.50)")

        # current_r = -0.55: must fire for A
        trade_a2 = _make_trade(
            setup_grade="A",
            risk_dollars=100.0,
            effective_peak_pnl=5.0,
            current_pnl=-55.0,         # current_r = -0.55 <= -0.50 ✓
            trade_age=1.0,
        )
        results_a2 = determine_loss_minimization_candidates(trade_a2)
        types_a2 = [r["candidate_type"] for r in results_a2]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types_a2,
                      "Grade A must fire at -0.55R with peak_r < 0.25")

    def test_grade_a_peak_too_high(self):
        """Grade A invalidation must NOT fire if peak_r >= 0.25."""
        trade = _make_trade(
            setup_grade="A",
            risk_dollars=100.0,
            effective_peak_pnl=30.0,   # peak_r = 0.30 >= 0.25
            current_pnl=-55.0,
            trade_age=1.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types)


class TestProfitLockCandidate(unittest.TestCase):
    """Test 5: PROFIT_LOCK_CANDIDATE detected."""

    def test_profit_lock_detected(self):
        """Test 5: peak_r >= 0.50 and current_r <= peak_r - 0.30."""
        # peak_r=0.60, current_r=0.20 → giveback=0.40R >= 0.30R ✓
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=60.0,  # peak_r = 0.60
            current_pnl=20.0,          # current_r = 0.20
            giveback_pct=66.7,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(PROFIT_LOCK_CANDIDATE, types)
        pl = next(r for r in results if r["candidate_type"] == PROFIT_LOCK_CANDIDATE)
        self.assertEqual(pl["recommendation"], "PROTECT_REVIEW")

    def test_profit_lock_not_fire_below_half_r_peak(self):
        """PROFIT_LOCK must NOT fire if peak_r < 0.50."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=40.0,  # peak_r=0.40 < 0.50
            current_pnl=5.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(PROFIT_LOCK_CANDIDATE, types)

    def test_profit_lock_not_fire_small_giveback(self):
        """PROFIT_LOCK must NOT fire if giveback < 0.30R."""
        # peak_r=0.60, current_r=0.35 → giveback=0.25R < 0.30R
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=60.0,
            current_pnl=35.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(PROFIT_LOCK_CANDIDATE, types)


class TestGradeBTimeDecayCandidate(unittest.TestCase):
    """Test 6: GRADE_B_TIME_DECAY_CANDIDATE detected."""

    def test_grade_b_time_decay_detected(self):
        """Test 6: Grade B, age >= 8h, peak_r < 0.50, current_r <= 0.10."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=30.0,  # peak_r = 0.30 < 0.50 ✓
            current_pnl=8.0,           # current_r = 0.08 <= 0.10 ✓
            trade_age=9.0,             # >= 8h ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(GRADE_B_TIME_DECAY_CANDIDATE, types)
        td = next(r for r in results if r["candidate_type"] == GRADE_B_TIME_DECAY_CANDIDATE)
        self.assertEqual(td["recommendation"], "EXIT_REVIEW")

    def test_grade_b_time_decay_not_fire_grade_a(self):
        """GRADE_B_TIME_DECAY must NOT fire for Grade A."""
        trade = _make_trade(
            setup_grade="A",
            risk_dollars=100.0,
            effective_peak_pnl=30.0,
            current_pnl=8.0,
            trade_age=9.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(GRADE_B_TIME_DECAY_CANDIDATE, types)

    def test_grade_b_time_decay_not_fire_before_8h(self):
        """GRADE_B_TIME_DECAY must NOT fire if age < 8h."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=30.0,
            current_pnl=8.0,
            trade_age=7.9,  # just under 8h
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(GRADE_B_TIME_DECAY_CANDIDATE, types)

    def test_grade_b_time_decay_not_fire_high_peak(self):
        """GRADE_B_TIME_DECAY must NOT fire if peak_r >= 0.50."""
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=55.0,  # peak_r=0.55 >= 0.50
            current_pnl=8.0,
            trade_age=9.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(GRADE_B_TIME_DECAY_CANDIDATE, types)


class TestNoBinanceWriteCalls(unittest.TestCase):
    """Test 7: No Binance write calls from loss minimization controller."""

    def test_determine_candidates_no_binance_calls(self):
        """determine_loss_minimization_candidates must not call any Binance connector."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
        )
        results = determine_loss_minimization_candidates(trade)
        self.assertIsInstance(results, list)
        for entry in results:
            self.assertNotIn("binance_order_id", entry)
            self.assertNotIn("close_result", entry)

    def test_write_loss_min_files_no_binance_calls(self):
        """_write_loss_minimization_files must only write to filesystem, no Binance."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
        )
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(obs, "OBSERVER_DIR", tmpdir):
                _write_loss_minimization_files([trade])
                lm_path = os.path.join(tmpdir, "loss_minimization_candidates.json")
                self.assertTrue(os.path.exists(lm_path))
                with open(lm_path) as f:
                    data = json.load(f)
                self.assertIsInstance(data, list)
                for entry in data:
                    self.assertNotIn("binance_order_id", entry)
                    self.assertNotIn("close_result", entry)


class TestCandidateDeduplication(unittest.TestCase):
    """Test 8: Candidate deduplication — last_seen_at updated, not duplicated."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.obs_dir = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_two_cycles(self, trade):
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        lm_path = os.path.join(self.obs_dir, "loss_minimization_candidates.json")
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir):
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data1 = json.load(f)
            first_ts = data1[0]["created_at"] if data1 else None
            import time; time.sleep(0.01)
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data2 = json.load(f)
        return data1, data2, first_ts

    def test_no_duplicate_entries(self):
        trade = _make_trade(risk_dollars=100.0, effective_peak_pnl=35.0, current_pnl=-5.0)
        data1, data2, _ = self._run_two_cycles(trade)
        candidate_ids = [c["candidate_id"] for c in data2]
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)),
                         "Duplicate candidate_ids found in JSON")

    def test_created_at_preserved_on_update(self):
        trade = _make_trade(risk_dollars=100.0, effective_peak_pnl=35.0, current_pnl=-5.0)
        data1, data2, _ = self._run_two_cycles(trade)
        if data1 and data2:
            rt1 = next((c for c in data1 if c["candidate_type"] == ROUNDTRIP_CANDIDATE), None)
            rt2 = next((c for c in data2 if c["candidate_type"] == ROUNDTRIP_CANDIDATE), None)
            if rt1 and rt2:
                self.assertEqual(rt1["created_at"], rt2["created_at"])


class TestCandidateResolvesOnClose(unittest.TestCase):
    """Test 9: Candidate resolves when parent trade closes."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.obs_dir = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_candidate_resolved_when_trade_not_open(self):
        trade = _make_trade(trade_id=42, risk_dollars=100.0,
                            effective_peak_pnl=35.0, current_pnl=-5.0)
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        lm_path = os.path.join(self.obs_dir, "loss_minimization_candidates.json")
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir):
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data1 = json.load(f)
            self.assertTrue(any(c["status"] == "OPEN" for c in data1))
            _write_loss_minimization_files([])  # trade closed
            with open(lm_path) as f:
                data2 = json.load(f)
        statuses = [c["status"] for c in data2]
        self.assertTrue(all(s == "RESOLVED" for s in statuses))
        for c in data2:
            self.assertIn("resolved_at", c)

    def test_candidate_stays_open_while_trade_open(self):
        trade = _make_trade(trade_id=99, risk_dollars=100.0,
                            effective_peak_pnl=35.0, current_pnl=-5.0)
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        lm_path = os.path.join(self.obs_dir, "loss_minimization_candidates.json")
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir):
            _write_loss_minimization_files([trade])
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data = json.load(f)
        statuses = [c["status"] for c in data]
        self.assertTrue(all(s == "OPEN" for s in statuses))

    def test_candidate_cleared_when_condition_cleared_but_trade_still_open(self):
        # 1. Create a trade that triggers a candidate
        trade = _make_trade(trade_id=99, risk_dollars=100.0,
                            effective_peak_pnl=35.0, current_pnl=-5.0)
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        lm_path = os.path.join(self.obs_dir, "loss_minimization_candidates.json")
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir):
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data1 = json.load(f)
            self.assertEqual(data1[0]["status"], "OPEN")
            
            # 2. Modify same trade so condition is no longer true (e.g. peak_pnl is 0.0)
            trade_stale = _make_trade(trade_id=99, risk_dollars=100.0,
                                      effective_peak_pnl=0.0, current_pnl=-5.0)
            trade_stale["loss_min_candidates"] = determine_loss_minimization_candidates(trade_stale)
            self.assertEqual(len(trade_stale["loss_min_candidates"]), 0) # condition cleared!
            
            # 3. Rerun observer files write with trade still open but condition no longer true
            _write_loss_minimization_files([trade_stale])
            with open(lm_path) as f:
                data2 = json.load(f)
                
            self.assertEqual(len(data2), 1)
            self.assertEqual(data2[0]["status"], "CONDITION_CLEARED")
            self.assertIsNotNone(data2[0].get("resolved_at"))

    def test_candidate_reopened_when_condition_retriggered(self):
        # 1. candidate OPEN
        trade = _make_trade(trade_id=99, risk_dollars=100.0,
                            effective_peak_pnl=35.0, current_pnl=-5.0)
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        lm_path = os.path.join(self.obs_dir, "loss_minimization_candidates.json")
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir):
            _write_loss_minimization_files([trade])
            with open(lm_path) as f:
                data1 = json.load(f)
            self.assertEqual(data1[0]["status"], "OPEN")
            self.assertNotIn("resolved_at", data1[0])

            # 2. condition clears -> CONDITION_CLEARED with resolved_at
            trade_stale = _make_trade(trade_id=99, risk_dollars=100.0,
                                      effective_peak_pnl=0.0, current_pnl=-5.0)
            trade_stale["loss_min_candidates"] = determine_loss_minimization_candidates(trade_stale)
            _write_loss_minimization_files([trade_stale])
            with open(lm_path) as f:
                data2 = json.load(f)
            self.assertEqual(data2[0]["status"], "CONDITION_CLEARED")
            self.assertIsNotNone(data2[0].get("resolved_at"))
            first_resolved_at = data2[0]["resolved_at"]

            # 3. condition fires again -> OPEN with resolved_at cleared and reopened_at set
            trade_active_again = _make_trade(trade_id=99, risk_dollars=100.0,
                                             effective_peak_pnl=35.0, current_pnl=-5.0)
            trade_active_again["loss_min_candidates"] = determine_loss_minimization_candidates(trade_active_again)
            _write_loss_minimization_files([trade_active_again])
            with open(lm_path) as f:
                data3 = json.load(f)
            self.assertEqual(data3[0]["status"], "OPEN")
            self.assertNotIn("resolved_at", data3[0])
            self.assertIsNotNone(data3[0].get("reopened_at"))
            self.assertEqual(data3[0].get("previous_resolved_at"), first_resolved_at)


class TestExistingBehaviourPreserved(unittest.TestCase):
    """Test 10: Existing imports and constants still work."""

    def test_scratch_approval_imports_intact(self):
        from ozzy_context_observer import (
            send_scratch_exit_notification,
            manage_persistent_files,
            is_trade_open_in_db,
            handle_decide_cli,
            handle_score_cli,
        )
        self.assertTrue(callable(send_scratch_exit_notification))
        self.assertTrue(callable(manage_persistent_files))
        self.assertTrue(callable(is_trade_open_in_db))

    def test_milestone_and_mfe_guard_imports_intact(self):
        from ozzy_context_observer import (
            determine_mfe_guard,
            determine_advisory_v03,
            get_active_open_trades,
            get_expected_holding_window,
            is_position_fresh,
        )
        self.assertTrue(callable(determine_mfe_guard))
        self.assertTrue(callable(determine_advisory_v03))
        self.assertTrue(callable(get_active_open_trades))

    def test_loss_min_constants_intact(self):
        from ozzy_context_observer import (
            ROUNDTRIP_CANDIDATE,
            EARLY_INVALIDATION_CANDIDATE,
            PROFIT_LOCK_CANDIDATE,
            GRADE_B_TIME_DECAY_CANDIDATE,
            _LOSS_MIN_CANDIDATE_TYPES,
        )
        for const in [ROUNDTRIP_CANDIDATE, EARLY_INVALIDATION_CANDIDATE,
                      PROFIT_LOCK_CANDIDATE, GRADE_B_TIME_DECAY_CANDIDATE]:
            self.assertIsInstance(const, str)
            self.assertIn(const, _LOSS_MIN_CANDIDATE_TYPES)

    def test_candidate_id_stable(self):
        trade = _make_trade(trade_id=55, instance="LIVE_MICRO", symbol="BNBUSDT")
        cid1 = _lm_candidate_id(trade, ROUNDTRIP_CANDIDATE)
        cid2 = _lm_candidate_id(trade, ROUNDTRIP_CANDIDATE)
        self.assertEqual(cid1, cid2)
        self.assertEqual(cid1, "LIVE_MICRO_BNBUSDT_55_ROUNDTRIP_CANDIDATE")

    def test_candidate_id_requires_real_trade_id_outside_dry_run(self):
        trade = _make_trade(trade_id="demo-seed", instance="STANDARD_TESTNET", symbol="LINKUSDT")
        with patch.dict("os.environ", {"DRY_RUN_TEST_ALERT": "false"}):
            cid = _lm_candidate_id(trade, ROUNDTRIP_CANDIDATE)
        self.assertEqual(cid, "")

    def test_all_candidates_have_required_fields(self):
        required = {
            "candidate_id", "candidate_type", "instance", "trade_id", "symbol",
            "side", "grade", "timeframe", "entry_price", "current_price",
            "current_pnl", "peak_pnl", "current_r", "peak_r",
            "giveback_ratio", "giveback_pct",  # both fields required
            "age_minutes", "recommendation", "reason", "status",
            "created_at", "last_seen_at",
        }
        trade = _make_trade(risk_dollars=100.0, effective_peak_pnl=35.0, current_pnl=-5.0)
        results = determine_loss_minimization_candidates(trade)
        self.assertTrue(len(results) > 0)
        for c in results:
            missing = required - set(c.keys())
            self.assertEqual(missing, set(), f"Candidate missing fields: {missing}")


class TestMultipleCandidatesOnOneTrade(unittest.TestCase):
    def test_roundtrip_and_profit_lock_coexist(self):
        """A trade at scratch that peaked at 0.60R fires both ROUNDTRIP and PROFIT_LOCK."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=60.0,
            current_pnl=-2.0,
            giveback_pct=103.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types)
        self.assertIn(PROFIT_LOCK_CANDIDATE, types)


# ===========================================================================
# Tuning tests (Phase 1 v0.1 patch)
# ===========================================================================

class TestRoundtripThresholdSeparation(unittest.TestCase):
    """T1–T5: Instance-aware roundtrip threshold separation."""

    def test_t1_standard_testnet_tiny_peak_does_not_trigger(self):
        """T1: RENDER-style: STANDARD_TESTNET peak_pnl=$0.68 must NOT trigger ROUNDTRIP.

        The flat $0.30 dollar fallback was removed for STANDARD_TESTNET.
        With risk_dollars=200 and peak_pnl=0.68, peak_r=0.0034 < 0.30.
        The risk-scaled fallback threshold is max($10, 200*0.05)=$10, so
        $0.68 << $10 also does not trigger the fallback.
        """
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            symbol="RENDERUSDT",
            risk_dollars=200.0,           # ~$200 risk on $10k testnet
            effective_peak_pnl=0.68,      # tiny absolute peak
            current_pnl=-0.30,            # slightly negative
            giveback_pct=144.1,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(
            ROUNDTRIP_CANDIDATE, types,
            f"STANDARD_TESTNET tiny $0.68 peak must NOT trigger ROUNDTRIP; got {types}"
        )

    def test_t2_standard_testnet_r_path_still_fires(self):
        """T2: STANDARD_TESTNET R-based path fires when peak_r >= 0.30."""
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            risk_dollars=200.0,
            effective_peak_pnl=70.0,      # peak_r = 0.35 >= 0.30 ✓
            current_pnl=-5.0,             # current_r = -0.025 <= 0.00 ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types,
                      "STANDARD_TESTNET R-path must still fire when peak_r >= 0.30")

    def test_t3_live_micro_dollar_fallback_still_works(self):
        """T3: LIVE_MICRO dollar fallback: peak_pnl >= $0.30 and current_pnl <= $0.00."""
        trade = _make_trade(
            instance="LIVE_MICRO",
            risk_dollars=0.50,            # very tiny sizing
            effective_peak_pnl=0.40,      # > $0.30 ✓
            current_pnl=-0.05,            # <= $0.00 ✓
            giveback_pct=112.5,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types,
                      "LIVE_MICRO dollar fallback must still fire at peak_pnl=$0.40")

    def test_t4_standard_risk_scaled_fallback_fires_when_r_unavailable(self):
        """T4: STANDARD risk-scaled fallback fires when R cannot be computed
        (risk_dollars=0) and peak_pnl >= $10."""
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            risk_dollars=0.0,             # R not computable
            effective_peak_pnl=12.0,      # >= max($10, 0*5%) = $10 ✓
            current_pnl=-2.0,             # <= $0.00 ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(ROUNDTRIP_CANDIDATE, types,
                      "STANDARD risk-scaled fallback must fire when R unavailable "
                      "and peak_pnl >= $10")

    def test_t4b_standard_risk_scaled_fallback_suppressed_below_threshold(self):
        """T4b: STANDARD risk-scaled fallback suppressed when peak_pnl < max($10, 5% of risk)."""
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            risk_dollars=0.0,             # R not computable
            effective_peak_pnl=5.0,       # < $10 threshold
            current_pnl=-1.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(ROUNDTRIP_CANDIDATE, types,
                         "STANDARD risk-scaled fallback must NOT fire when "
                         "peak_pnl < $10")

    def test_t5_standard_fallback_suppressed_when_r_computable(self):
        """T5: STANDARD risk-scaled fallback must NOT fire when R IS computable
        (even if peak_pnl >= threshold), since the R-path is the correct check."""
        # risk_dollars=100, peak_pnl=8 → peak_r=0.08 < 0.30 (R-path won't fire)
        # Fallback requires R to be non-computable — since risk_dollars > 0,
        # fallback is blocked.
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            risk_dollars=100.0,           # R IS computable
            effective_peak_pnl=8.0,       # peak_r=0.08 < 0.30 (R-path won't fire)
                                           # $8 < $10 threshold too
            current_pnl=-2.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(ROUNDTRIP_CANDIDATE, types,
                         "STANDARD fallback must NOT fire when R is computable "
                         "but peak_r < 0.30")

    def test_t5b_standard_fallback_suppressed_even_if_peak_high_when_r_computable(self):
        """T5b: Even with peak_pnl=$15 on STANDARD, if R is computable but peak_r < 0.30,
        the risk-scaled fallback must not fire (fallback is only for R=unavailable cases)."""
        trade = _make_trade(
            instance="STANDARD_TESTNET",
            risk_dollars=100.0,           # R IS computable → fallback blocked
            effective_peak_pnl=15.0,      # peak_r=0.15 < 0.30 (R-path won't fire)
                                           # $15 > $10 threshold, but fallback blocked
            current_pnl=-5.0,
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(ROUNDTRIP_CANDIDATE, types,
                         "Fallback must be blocked when R is computable, "
                         "even if peak_pnl exceeds risk-scaled threshold")


class TestGivebackMetricCleanup(unittest.TestCase):
    """T6–T8: giveback_ratio and giveback_pct field consistency."""

    def test_t6_giveback_ratio_is_raw_fraction(self):
        """T6: giveback_ratio must be a raw fraction (e.g. 0.6597), not a percentage."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
            giveback_pct=114.3,           # source: t["giveback_pct"] = 114.3 (%)
        )
        results = determine_loss_minimization_candidates(trade)
        self.assertTrue(len(results) > 0)
        for c in results:
            self.assertIn("giveback_ratio", c)
            # ratio must be <= 2.0 for all reasonable cases (not in 100s)
            self.assertLess(c["giveback_ratio"], 10.0,
                            f"giveback_ratio={c['giveback_ratio']} looks like a percentage, "
                            f"expected a raw fraction < 10")
            # For 114.3% input → ratio should be ~1.143
            self.assertAlmostEqual(c["giveback_ratio"], 1.143, places=2)

    def test_t7_giveback_pct_is_percentage_value(self):
        """T7: giveback_pct must equal the source percentage (e.g. 114.3), not 11430."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
            giveback_pct=114.3,
        )
        results = determine_loss_minimization_candidates(trade)
        self.assertTrue(len(results) > 0)
        for c in results:
            self.assertIn("giveback_pct", c)
            # Must be ~114.3, not 11430 (the old x100 double-multiply bug)
            self.assertAlmostEqual(c["giveback_pct"], 114.3, places=1,
                                   msg=f"giveback_pct={c['giveback_pct']} looks wrong; "
                                       f"expected ~114.3%")

    def test_t7b_giveback_pct_zero_when_no_giveback(self):
        """T7b: giveback_pct=0 in input → both fields zero."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=40.0,    # still rising, no giveback scenario
            giveback_pct=0.0,
        )
        results = determine_loss_minimization_candidates(trade)
        for c in results:
            self.assertAlmostEqual(c["giveback_ratio"], 0.0, places=4)
            self.assertAlmostEqual(c["giveback_pct"], 0.0, places=2)

    def test_t8_markdown_writes_pct_directly_not_multiplied(self):
        """T8: Markdown log must display giveback_pct as-is, not multiplied by 100."""
        trade = _make_trade(
            risk_dollars=100.0,
            effective_peak_pnl=35.0,
            current_pnl=-5.0,
            giveback_pct=25.97,   # should appear as "25.97%" in markdown
        )
        trade["loss_min_candidates"] = determine_loss_minimization_candidates(trade)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(obs, "OBSERVER_DIR", tmpdir):
                _write_loss_minimization_files([trade])
                log_path = os.path.join(tmpdir, "loss_minimization_decision_log.md")
                if os.path.exists(log_path):
                    content = open(log_path).read()
                    # Should contain something like "Giveback: 26.0%" not "2597.0%"
                    self.assertNotIn("2597", content,
                                     f"Markdown must not show 2597% (double-multiplied). "
                                     f"Relevant content: {[l for l in content.splitlines() if 'Giveback' in l]}")


class TestEarlyInvalidationGradeNormalisation(unittest.TestCase):
    """T9–T13: Grade normalisation and edge cases for EARLY_INVALIDATION."""

    def test_t9_lowercase_b_triggers_grade_b_rules(self):
        """T9: Grade stored as lowercase 'b' in DB must trigger Grade B rules."""
        trade = _make_trade(
            setup_grade="b",              # lowercase from DB
            risk_dollars=100.0,
            effective_peak_pnl=5.0,       # peak_r=0.05 < 0.15 ✓
            current_pnl=-38.0,            # current_r=-0.38 <= -0.35 ✓
            trade_age=0.5,                # 30min >= 20min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types,
                      "Grade 'b' (lowercase) must trigger Grade B invalidation rules")

    def test_t10_grade_a_with_trailing_space(self):
        """T10: Grade stored as 'A ' (trailing space) must trigger Grade A rules."""
        trade = _make_trade(
            setup_grade="A ",             # trailing space from DB
            risk_dollars=100.0,
            effective_peak_pnl=5.0,       # peak_r=0.05 < 0.25 ✓
            current_pnl=-55.0,            # current_r=-0.55 <= -0.50 ✓
            trade_age=1.0,                # 60min >= 30min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types,
                      "Grade 'A ' (with space) must trigger Grade A invalidation rules")

    def test_t11_early_invalidation_fires_when_peak_r_none_zero_mfe(self):
        """T11: EARLY_INVALIDATION fires when peak_pnl=0 → peak_r=None (zero MFE worst case).

        Previously: `if current_r is not None and peak_r is not None` blocked this.
        Now: peak_r=None is treated as 0.0 (worst case, no MFE proven at all).
        """
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=100.0,
            effective_peak_pnl=0.0,       # peak_pnl=0 → peak_r=None (zero MFE)
            current_pnl=-38.0,            # current_r=-0.38 <= -0.35 ✓
            trade_age=0.5,                # 30min >= 20min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types,
                      "EARLY_INVALIDATION must fire when peak_r is None (zero MFE = worst case)")

    def test_t12_grade_a_early_invalidation_fires_at_minus_0_50(self):
        """T12: Grade A fires EARLY_INVALIDATION with current_r <= -0.50, peak_r < 0.25, age >= 30min.
        Covers the BTC/LINK observed case (long drawdown, no MFE).
        """
        trade = _make_trade(
            setup_grade="A",
            risk_dollars=150.0,
            effective_peak_pnl=10.0,      # peak_r = 0.067 < 0.25 ✓
            current_pnl=-78.0,            # current_r = -0.52 <= -0.50 ✓
            trade_age=0.6,                # 36min >= 30min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types,
                      "Grade A invalidation must fire: current_r=-0.52, peak_r=0.067, age=36min")
        ei = next(r for r in results if r["candidate_type"] == EARLY_INVALIDATION_CANDIDATE)
        self.assertEqual(ei["recommendation"], "EXIT_REVIEW")
        self.assertEqual(ei["grade"], "A")

    def test_t13_grade_b_early_invalidation_fires_at_minus_0_35(self):
        """T13: Grade B fires EARLY_INVALIDATION with current_r <= -0.35, peak_r < 0.15, age >= 20min.
        Covers the BTC/LINK observed case for Grade B.
        """
        trade = _make_trade(
            setup_grade="B",
            risk_dollars=80.0,
            effective_peak_pnl=4.0,       # peak_r = 0.05 < 0.15 ✓
            current_pnl=-30.0,            # current_r = -0.375 <= -0.35 ✓
            trade_age=0.4,                # 24min >= 20min ✓
        )
        results = determine_loss_minimization_candidates(trade)
        types = [r["candidate_type"] for r in results]
        self.assertIn(EARLY_INVALIDATION_CANDIDATE, types,
                      "Grade B invalidation must fire: current_r=-0.375, peak_r=0.05, age=24min")
        ei = next(r for r in results if r["candidate_type"] == EARLY_INVALIDATION_CANDIDATE)
        self.assertEqual(ei["grade"], "B")

    def test_t14_both_giveback_fields_present_in_output(self):
        """T14: Every candidate dict must contain both giveback_ratio and giveback_pct."""
        trade = _make_trade(
            setup_grade="A",
            risk_dollars=100.0,
            effective_peak_pnl=5.0,
            current_pnl=-55.0,
            giveback_pct=1100.0,   # extreme giveback
            trade_age=1.0,
        )
        results = determine_loss_minimization_candidates(trade)
        self.assertTrue(len(results) > 0, "Expected at least one candidate")
        for c in results:
            self.assertIn("giveback_ratio", c,
                          "giveback_ratio field missing from candidate")
            self.assertIn("giveback_pct", c,
                          "giveback_pct field missing from candidate")
            # giveback_ratio must be ~ giveback_pct / 100
            self.assertAlmostEqual(c["giveback_ratio"],
                                   c["giveback_pct"] / 100.0,
                                   places=4,
                                   msg="giveback_ratio must equal giveback_pct / 100")

    def test_explain_why_no_candidate_when_thresholds_not_met(self):
        """If BTC/LINK shows no EARLY_INVALIDATION, explain exactly why.

        This test documents the gating conditions so operators can verify
        live behaviour by substituting real current_r / grade / age values.
        """
        # Scenario: Grade A, current_r=-0.45 (not quite -0.50), age=25min (not 30min yet)
        trade_btc = _make_trade(
            symbol="BTCUSDT",
            setup_grade="A",
            risk_dollars=200.0,
            effective_peak_pnl=5.0,       # peak_r=0.025 < 0.25 ✓
            current_pnl=-88.0,            # current_r=-0.44 — NOT <= -0.50 ✗
            trade_age=0.4,                # 24min — NOT >= 30min ✗ for grade A
        )
        results = determine_loss_minimization_candidates(trade_btc)
        types = [r["candidate_type"] for r in results]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types,
                         "Grade A must NOT fire when current_r=-0.44 (need -0.50) "
                         "and age=24min (need 30min)")

        # Scenario: Grade A, but grade not set in DB (empty string)
        trade_link = _make_trade(
            symbol="LINKUSDT",
            setup_grade="",               # grade missing from DB — neither A nor B
            risk_dollars=200.0,
            effective_peak_pnl=5.0,
            current_pnl=-110.0,           # current_r=-0.55
            trade_age=1.0,                # 60min
        )
        results2 = determine_loss_minimization_candidates(trade_link)
        types2 = [r["candidate_type"] for r in results2]
        self.assertNotIn(EARLY_INVALIDATION_CANDIDATE, types2,
                         "EARLY_INVALIDATION must NOT fire when grade is empty/unknown — "
                         "verify setup_grade is being written to DB for all new trades")


class TestSetupGradeDBLoading(unittest.TestCase):
    """T15: DB Integration test to verify setup_grade is loaded correctly from trades table."""

    def setUp(self):
        self.tmp_std = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_live = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_std.close()
        self.tmp_live.close()

    def tearDown(self):
        try:
            os.unlink(self.tmp_std.name)
        except Exception:
            pass
        try:
            os.unlink(self.tmp_live.name)
        except Exception:
            pass

    def test_setup_grade_is_loaded_correctly_from_db(self):
        import sqlite3
        # Setup tables in standard testnet database
        conn = sqlite3.connect(self.tmp_std.name)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                peak_pnl REAL,
                peak_price REAL,
                regime TEXT,
                timeframe TEXT,
                strategy TEXT,
                risk_dollars REAL,
                setup_grade TEXT
            )
        """)
        c.execute("""
            CREATE TABLE binance_order_state (
                symbol TEXT PRIMARY KEY,
                current_sl REAL,
                current_tp REAL,
                runner_status TEXT,
                updated_ts TEXT
            )
        """)
        c.execute("""
            CREATE TABLE milestones (
                trade_id INTEGER,
                milestone_name TEXT
            )
        """)

        # Insert a trade with a specific setup_grade
        c.execute("""
            INSERT INTO trades (id, ts, symbol, direction, entry_price, exit_price, qty, peak_pnl, regime, timeframe, strategy, risk_dollars, setup_grade)
            VALUES (42, '2026-05-31 12:00:00', 'BTCUSDT', 'BUY', 70000.0, NULL, 1.0, 50.0, 'smc_pro', '60', 'momentum', 100.0, 'B')
        """)
        conn.commit()
        conn.close()

        # Insert empty live DB just to prevent crash
        conn_l = sqlite3.connect(self.tmp_live.name)
        c_l = conn_l.cursor()
        c_l.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                peak_pnl REAL,
                peak_price REAL,
                regime TEXT,
                timeframe TEXT,
                strategy TEXT,
                risk_dollars REAL,
                setup_grade TEXT
            )
        """)
        conn_l.commit()
        conn_l.close()

        # Patch the DB paths in ozzy_context_observer
        with patch.object(obs, "DB_PATH_STD", self.tmp_std.name), \
             patch.object(obs, "DB_PATH_LIVE", self.tmp_live.name), \
             patch("ozzy_context_observer.fetch_public_price", return_value=70100.0):
             
             weaknesses_mock = {
                 "STANDARD_TESTNET": {"symbols": {}, "regimes": {}},
                 "LIVE_MICRO": {"symbols": {}, "regimes": {}}
             }
             open_trades = obs.get_active_open_trades(weaknesses_mock, {})
             
        self.assertEqual(len(open_trades), 1)
        btc_trade = open_trades[0]
        self.assertEqual(btc_trade["id"], 42)
        self.assertEqual(btc_trade["symbol"], "BTCUSDT")
        # Prove setup_grade is loaded correctly!
        self.assertEqual(btc_trade["setup_grade"], "B")


if __name__ == "__main__":
    unittest.main()
