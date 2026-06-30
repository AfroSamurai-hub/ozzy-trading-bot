import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import ozzy_context_observer as obs
import command_center
from command_center import (
    execute,
    CommandType,
    CommandResult,
    cmd_lm_close,
    cmd_lm_watch,
    cmd_lm_reject,
)
from telegram_client import notify_loss_minimization_candidate
from telegram_command_bot import parse_command


class Phase2TelegramApprovalTests(unittest.TestCase):
    def setUp(self):
        self.obs_dir = tempfile.TemporaryDirectory()
        self.lm_path = os.path.join(self.obs_dir.name, "loss_minimization_candidates.json")
        self.decision_log_path = os.path.join(self.obs_dir.name, "loss_minimization_decision_log.md")
        self.original_exists = os.path.exists

        # Patch OBSERVER_DIR and paths in observer and command_center
        self.patches = [
            patch.object(obs, "OBSERVER_DIR", self.obs_dir.name),
            patch("command_center.os.path.exists", side_effect=self.mock_exists),
        ]
        for p in self.patches:
            p.start()

        # Temporary SQLite trades database redirector
        self.temp_db_path = Path(self.obs_dir.name) / "temp_trades.db"
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    direction TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    qty REAL,
                    pnl REAL,
                    exit_reason TEXT,
                    execution_state TEXT,
                    timeframe TEXT,
                    ts TEXT,
                    risk_dollars REAL,
                    peak_pnl REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exits (
                    trade_id INTEGER,
                    price REAL,
                    qty_pct REAL,
                    ts TEXT,
                    pnl_contribution REAL,
                    exit_type TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS milestones (
                    trade_id INTEGER
                )
                """
            )
            conn.commit()

        self.original_connect = sqlite3.connect
        self.connect_patch = patch("sqlite3.connect", side_effect=self.mock_connect)
        self.connect_patch.start()

        # Mocking requests.post for Telegram notification inspections
        self.mock_post = patch("requests.post")
        self.mock_post_m = self.mock_post.start()
        self.mock_lm_open = patch("telegram_client._loss_min_candidate_trade_is_open", return_value=True)
        self.mock_lm_open_m = self.mock_lm_open.start()

        # Mocking Binance connector methods
        self.mock_get_positions = patch("command_center.get_open_positions")
        self.mock_close_pos = patch("command_center.close_position")
        self.mock_get_positions_m = self.mock_get_positions.start()
        self.mock_close_pos_m = self.mock_close_pos.start()

        # Patch the hardcoded paths inside command_center to our temp files
        self.cc_lm_path_patch = patch("command_center.os.path.join", side_effect=self.mock_join)
        self.cc_lm_path_patch.start()

    def tearDown(self):
        patch.stopall()
        self.obs_dir.cleanup()

    def mock_exists(self, path):
        # Redirect exists check for candidates JSON and decision log
        if "loss_minimization_candidates.json" in path:
            return self.original_exists(self.lm_path)
        if "loss_minimization_decision_log.md" in path:
            return self.original_exists(self.decision_log_path)
        return self.original_exists(path)

    def mock_join(self, *args):
        # Redirect os.path.join for observer config paths to temp dir
        if len(args) >= 2 and args[1] == "loss_minimization_candidates.json":
            return self.lm_path
        if len(args) >= 2 and args[1] == "loss_minimization_decision_log.md":
            return self.decision_log_path
        return os.path.join(*args)

    def mock_connect(self, database, *args, **kwargs):
        # Redirect all sqlite3.connect to our isolated test database
        return self.original_connect(self.temp_db_path, *args, **kwargs)

    def _add_test_trade(self, trade_id, symbol, side, qty=10.0, exit_price=None):
        with self.original_connect(self.temp_db_path) as conn:
            conn.execute(
                """
                INSERT INTO trades (id, symbol, direction, entry_price, exit_price, qty, execution_state, timeframe, ts, risk_dollars, peak_pnl)
                VALUES (?, ?, ?, 100.0, ?, ?, ?, '1h', '2026-05-30 12:00:00', 10.0, 5.0)
                """,
                (trade_id, symbol, side, exit_price, qty, "open" if exit_price is None else "closed")
            )
            conn.commit()

    def _write_test_candidates(self, candidates):
        with open(self.lm_path, "w") as f:
            json.dump(candidates, f, indent=2)

    def _read_candidates(self):
        if not os.path.exists(self.lm_path):
            return []
        with open(self.lm_path, "r") as f:
            return json.load(f)

    # ── Test 1: ROUNDTRIP_CANDIDATE sends Telegram alert ──
    def test_roundtrip_candidate_sends_telegram_alert(self):
        """1. ROUNDTRIP_CANDIDATE sends Telegram alert with inline buttons."""
        candidate = {
            "candidate_id": "TEST_ID_ROUNDTRIP",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 42,
            "symbol": "LINKUSDT",
            "side": "LONG",
            "grade": "A",
            "entry_price": 100.0,
            "current_price": 99.5,
            "current_pnl": -5.0,
            "peak_pnl": 35.0,
            "current_r": -0.05,
            "peak_r": 0.35,
            "giveback_pct": 114.3,
            "age_minutes": 25.5,
            "recommendation": "EXIT_REVIEW",
            "reason": "Winner round-tripped. OBSERVE ONLY — no auto-exit",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }

        # Mocking TELEGRAM_TOKEN and CHAT_ID
        with (
            patch("telegram_client.TELEGRAM_TOKEN", "12345"),
            patch("telegram_client.TELEGRAM_CHAT_ID", "67890"),
        ):
            notify_loss_minimization_candidate(candidate)

        # Verify that requests.post was called with HTML parse mode and reply_markup containing inline buttons
        self.mock_post_m.assert_called_once()
        args, kwargs = self.mock_post_m.call_args
        json_data = kwargs.get("json") or {}
        
        self.assertEqual(json_data.get("chat_id"), "67890")
        self.assertIn("parse_mode", json_data)
        self.assertEqual(json_data.get("parse_mode"), "HTML")
        
        # Verify header is correct
        text = json_data.get("text", "")
        self.assertIn("🔵 <b>TESTNET Loss Minimization Alert</b>", text)
        self.assertNotIn("🔴 <b>LIVE MICRO Loss Minimization Alert</b>", text)
        
        # Verify candidate_id and other fields are in the body
        self.assertIn("TEST_ID_ROUNDTRIP", text)
        self.assertIn("Status:", text)
        self.assertIn("Created At:", text)
        self.assertIn("Last Seen At:", text)
        
        # Verify reason text was replaced correctly
        self.assertIn("APPROVAL REQUIRED — no auto-exit unless Close Early is approved.", text)
        self.assertNotIn("OBSERVE ONLY — no auto-exit", text)
        
        # Verify inline keyboard reply_markup is correct
        reply_markup = json_data.get("reply_markup") or {}
        self.assertIn("inline_keyboard", reply_markup)
        buttons = reply_markup["inline_keyboard"][0]
        self.assertEqual(len(buttons), 3)
        self.assertEqual(buttons[0]["text"], "🛑 CLOSE EARLY")
        self.assertEqual(buttons[0]["callback_data"], "/lm_close TEST_ID_ROUNDTRIP")

    def test_live_micro_candidate_uses_live_micro_header(self):
        """1b. LIVE_MICRO candidate uses LIVE MICRO header."""
        candidate = {
            "candidate_id": "TEST_ID_MICRO",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "LIVE_MICRO",
            "trade_id": 43,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "grade": "B",
            "entry_price": 100.0,
            "current_price": 99.5,
            "current_pnl": -0.1,
            "peak_pnl": 0.5,
            "current_r": -0.05,
            "peak_r": 0.35,
            "giveback_pct": 114.3,
            "age_minutes": 25.5,
            "recommendation": "EXIT_REVIEW",
            "reason": "Winner round-tripped. OBSERVE ONLY — no auto-exit",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }

        with (
            patch("telegram_client.TELEGRAM_TOKEN", "12345"),
            patch("telegram_client.TELEGRAM_CHAT_ID", "67890"),
        ):
            notify_loss_minimization_candidate(candidate)

        self.mock_post_m.assert_called_once()
        args, kwargs = self.mock_post_m.call_args
        json_data = kwargs.get("json") or {}
        text = json_data.get("text", "")
        self.assertIn("🔴 <b>LIVE MICRO Loss Minimization Alert</b>", text)
        self.assertNotIn("🔵 <b>TESTNET Loss Minimization Alert</b>", text)

    def test_loss_min_candidate_suppressed_when_trade_not_open(self):
        candidate = {
            "candidate_id": "STANDARD_TESTNET_LINKUSDT_42_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 42,
            "symbol": "LINKUSDT",
            "side": "LONG",
            "status": "OPEN",
        }
        self.mock_lm_open_m.return_value = False
        with (
            patch("telegram_client.TELEGRAM_TOKEN", "12345"),
            patch("telegram_client.TELEGRAM_CHAT_ID", "67890"),
        ):
            notify_loss_minimization_candidate(candidate)
        self.mock_post_m.assert_not_called()

    # ── Test 2: CLOSE EARLY revalidates before closing ──
    def test_close_early_revalidates_and_closes_successfully(self):
        """2. CLOSE EARLY revalidates before closing and closes successfully if all pass."""
        self._add_test_trade(101, "BTCUSDT", "LONG", qty=2.5)
        
        candidates = [{
            "candidate_id": "TESTNET_BTCUSDT_101_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 101,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "grade": "A",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        # Mock active position on exchange matching exactly
        self.mock_get_positions_m.return_value = [{
            "symbol": "BTCUSDT",
            "type": "BUY",
            "volume": 2.5,
            "profit": -2.0,
            "currentPrice": 99.0,
        }]
        self.mock_close_pos_m.return_value = {"status": "closed"}

        res = execute("lm_close", candidate_id="TESTNET_BTCUSDT_101_ROUNDTRIP_CANDIDATE")
        self.assertTrue(res.success)
        self.assertIn("ROUNDTRIP early exit approved and executed", res.message)

        # Verify exchange position closed
        self.mock_close_pos_m.assert_called_once_with("BTCUSDT", position_side="LONG")

        # Verify DB trade marked closed
        with sqlite3.connect(self.temp_db_path) as conn:
            row = conn.execute("SELECT exit_price, exit_reason, execution_state FROM trades WHERE id=101").fetchone()
            self.assertEqual(row[0], 99.0)
            self.assertEqual(row[1], "roundtrip_early_exit_approved")
            self.assertEqual(row[2], "closed")

        # Verify candidate status marked APPROVED_CLOSED
        updated = self._read_candidates()
        self.assertEqual(updated[0]["status"], "APPROVED_CLOSED")
        self.assertIsNotNone(updated[0].get("resolved_at"))

    # ── Test 3: CLOSE EARLY closes using live remaining quantity, not original qty ──
    def test_close_early_uses_live_remaining_qty_never_original(self):
        """3. CLOSE EARLY closes using live remaining quantity, not original DB qty."""
        # DB trade qty is 10.0
        self._add_test_trade(102, "ETHUSDT", "LONG", qty=10.0)
        
        candidates = [{
            "candidate_id": "TESTNET_ETHUSDT_102_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 102,
            "symbol": "ETHUSDT",
            "side": "LONG",
            "grade": "B",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        # Exchange position has partially filled / remaining volume is only 4.0 units
        self.mock_get_positions_m.return_value = [{
            "symbol": "ETHUSDT",
            "type": "BUY",
            "volume": 4.0,
            "profit": -0.5,
            "currentPrice": 2500.0,
        }]
        self.mock_close_pos_m.return_value = {"status": "closed"}

        res = execute("lm_close", candidate_id="TESTNET_ETHUSDT_102_ROUNDTRIP_CANDIDATE")
        self.assertTrue(res.success)
        self.assertIn("Closed quantity: 4.0 units", res.message)

    # ── Test 4: CLOSE EARLY fails safely if candidate cleared ──
    def test_close_early_fails_safely_if_candidate_cleared(self):
        """4. CLOSE EARLY fails safely if candidate is CONDITION_CLEARED or not OPEN."""
        candidates = [{
            "candidate_id": "TESTNET_BTCUSDT_103_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 103,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "status": "CONDITION_CLEARED",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        res = execute("lm_close", candidate_id="TESTNET_BTCUSDT_103_ROUNDTRIP_CANDIDATE")
        self.assertFalse(res.success)
        self.assertIn("not OPEN", res.message)
        self.mock_close_pos_m.assert_not_called()

    def test_close_early_stale_missing_candidate_message(self):
        self._write_test_candidates([])
        res = execute("lm_close", candidate_id="STANDARD_TESTNET_LINKUSDT_99_ROUNDTRIP_CANDIDATE")
        self.assertFalse(res.success)
        self.assertIn("candidate expired/stale", res.message)
        self.assertEqual(res.details.get("reason"), "stale_missing")

    # ── Test 5: CLOSE EARLY fails safely if trade already closed ──
    def test_close_early_fails_safely_if_trade_already_closed(self):
        """5. CLOSE EARLY fails safely if parent trade is already closed in DB."""
        # parent trade already closed (exit_price=50000.0)
        self._add_test_trade(104, "BTCUSDT", "LONG", exit_price=50000.0)
        
        candidates = [{
            "candidate_id": "TESTNET_BTCUSDT_104_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 104,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        res = execute("lm_close", candidate_id="TESTNET_BTCUSDT_104_ROUNDTRIP_CANDIDATE")
        self.assertFalse(res.success)
        self.assertIn("Trade is already closed", res.message)
        self.mock_close_pos_m.assert_not_called()

    # ── Test 6: CLOSE EARLY fails safely on orphan/qty mismatch ──
    def test_close_early_fails_safely_on_orphan_side_mismatch(self):
        """6. CLOSE EARLY fails safely if there is a side mismatch or exchange position missing."""
        self._add_test_trade(105, "LINKUSDT", "LONG")
        
        candidates = [{
            "candidate_id": "TESTNET_LINKUSDT_105_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 105,
            "symbol": "LINKUSDT",
            "side": "LONG",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        # Exchange has SHORT position, but DB trade is LONG (side mismatch)
        self.mock_get_positions_m.return_value = [{
            "symbol": "LINKUSDT",
            "type": "SELL", # SHORT
            "volume": 10.0,
            "profit": -1.0,
            "currentPrice": 15.0,
        }]

        res = execute("lm_close", candidate_id="TESTNET_LINKUSDT_105_ROUNDTRIP_CANDIDATE")
        self.assertFalse(res.success)
        self.assertIn("Side mismatch", res.message)
        self.mock_close_pos_m.assert_not_called()

    # ── Test 7: WATCH suppresses duplicate alerts for 15 minutes ──
    def test_watch_suppresses_repeat_alerts_for_15_minutes(self):
        """7. WATCH suppresses repeat alerts for 15 minutes, then allows reopening."""
        candidates = [{
            "candidate_id": "TESTNET_LINKUSDT_106_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 106,
            "symbol": "LINKUSDT",
            "side": "LONG",
            "grade": "B",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        # Mark WATCHED
        res = execute("lm_watch", candidate_id="TESTNET_LINKUSDT_106_ROUNDTRIP_CANDIDATE")
        self.assertTrue(res.success)
        self.assertEqual(self._read_candidates()[0]["status"], "WATCHED")

        # Clear mock post count
        self.mock_post_m.reset_mock()

        # Run observer files writer (1m has passed - suppressed)
        trade = {
            "id": 106,
            "instance": "STANDARD_TESTNET",
            "symbol": "LINKUSDT",
            "side": "LONG",
            "setup_grade": "B",
            "loss_min_candidates": [{
                "candidate_id": "TESTNET_LINKUSDT_106_ROUNDTRIP_CANDIDATE",
                "candidate_type": "ROUNDTRIP_CANDIDATE",
                "instance": "STANDARD_TESTNET",
                "trade_id": 106,
                "symbol": "LINKUSDT",
                "side": "LONG",
                "grade": "B",
            }]
        }
        
        # 1. 1 minute passed: still suppressed
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir.name):
            obs._write_loss_minimization_files([trade])
        self.assertEqual(self._read_candidates()[0]["status"], "WATCHED")
        self.mock_post_m.assert_not_called()

        # 2. 16 minutes passed: no longer suppressed -> OPEN and alert sent!
        self.mock_post_m.reset_mock()
        older_time = (datetime.now() - timedelta(minutes=16)).isoformat()
        
        cands = self._read_candidates()
        cands[0]["watched_at"] = older_time
        self._write_test_candidates(cands)

        with patch.object(obs, "OBSERVER_DIR", self.obs_dir.name):
            obs._write_loss_minimization_files([trade])
        
        updated = self._read_candidates()
        self.assertEqual(updated[0]["status"], "OPEN")
        self.assertIsNotNone(updated[0].get("reopened_at"))
        self.mock_post_m.assert_called_once()

    # ── Test 8: REJECT suppresses future alerts for same candidate ──
    def test_reject_suppresses_future_alerts_unless_severity_worsens(self):
        """8. REJECT suppresses future alerts unless severity worsens."""
        candidates = [{
            "candidate_id": "TESTNET_LINKUSDT_107_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 107,
            "symbol": "LINKUSDT",
            "side": "LONG",
            "grade": "B",
            "current_r": -0.05,
            "current_pnl": -1.0,
            "recommendation": "PROTECT_REVIEW",
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
        }]
        self._write_test_candidates(candidates)

        # Mark REJECTED
        res = execute("lm_reject", candidate_id="TESTNET_LINKUSDT_107_ROUNDTRIP_CANDIDATE")
        self.assertTrue(res.success)
        self.assertEqual(self._read_candidates()[0]["status"], "REJECTED")

        # Clear mock post count
        self.mock_post_m.reset_mock()

        # Run observer files writer (same severity - suppressed)
        trade = {
            "id": 107,
            "instance": "STANDARD_TESTNET",
            "symbol": "LINKUSDT",
            "side": "LONG",
            "setup_grade": "B",
            "loss_min_candidates": [{
                "candidate_id": "TESTNET_LINKUSDT_107_ROUNDTRIP_CANDIDATE",
                "candidate_type": "ROUNDTRIP_CANDIDATE",
                "instance": "STANDARD_TESTNET",
                "trade_id": 107,
                "symbol": "LINKUSDT",
                "side": "LONG",
                "grade": "B",
                "current_r": -0.05,
                "current_pnl": -1.0,
                "recommendation": "PROTECT_REVIEW",
            }]
        }
        
        with patch.object(obs, "OBSERVER_DIR", self.obs_dir.name):
            obs._write_loss_minimization_files([trade])
        self.assertEqual(self._read_candidates()[0]["status"], "REJECTED")
        self.mock_post_m.assert_not_called()

        # Rerun observer files writer (severity worsens: recommendation transitions to EXIT_REVIEW)
        self.mock_post_m.reset_mock()
        trade_worsened = {
            "id": 107,
            "instance": "STANDARD_TESTNET",
            "symbol": "LINKUSDT",
            "side": "LONG",
            "setup_grade": "B",
            "loss_min_candidates": [{
                "candidate_id": "TESTNET_LINKUSDT_107_ROUNDTRIP_CANDIDATE",
                "candidate_type": "ROUNDTRIP_CANDIDATE",
                "instance": "STANDARD_TESTNET",
                "trade_id": 107,
                "symbol": "LINKUSDT",
                "side": "LONG",
                "grade": "B",
                "current_r": -0.22, # worsened!
                "current_pnl": -6.0,
                "recommendation": "EXIT_REVIEW", # worsened severity!
            }]
        }

        with patch.object(obs, "OBSERVER_DIR", self.obs_dir.name):
            obs._write_loss_minimization_files([trade_worsened])

        updated = self._read_candidates()
        self.assertEqual(updated[0]["status"], "OPEN")
        self.mock_post_m.assert_called_once()

    # ── Test 9: EARLY_INVALIDATION does not create close button ──
    def test_early_invalidation_does_not_create_close_button(self):
        """9. EARLY_INVALIDATION_CANDIDATE does not create close early button."""
        candidate = {
            "candidate_id": "TEST_ID_EI",
            "candidate_type": "EARLY_INVALIDATION_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 42,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "grade": "A",
            "recommendation": "EXIT_REVIEW",
            "status": "OPEN",
        }

        with (
            patch("telegram_client.TELEGRAM_TOKEN", "12345"),
            patch("telegram_client.TELEGRAM_CHAT_ID", "67890"),
        ):
            notify_loss_minimization_candidate(candidate)

        self.mock_post_m.assert_called_once()
        args, kwargs = self.mock_post_m.call_args
        json_data = kwargs.get("json") or {}
        
        # Verify reply_markup is NOT present in the payload (observe-only)
        self.assertNotIn("reply_markup", json_data)

    # ── Test 10: No auto-exit path exists ──
    def test_no_auto_exit_path_exists(self):
        """10. Verify no automatic close path exists in the observer."""
        # Read the file contents of ozzy_context_observer.py and assert no call to close_position
        with open("/home/rick/ozzy-bot/ozzy_context_observer.py", "r") as f:
            content = f.read()
            self.assertNotIn("close_position(", content)
            self.assertNotIn("close_position_qty(", content)

    # ── Test 11: Existing scratch approval still works ──
    def test_existing_scratch_approval_command_parsing(self):
        """11. Verify that slash command parsing for scratch exits still works perfectly."""
        cmd, kwargs = parse_command("/approve_scratch ALERT_XYZ")
        self.assertEqual(cmd, "approve_scratch")
        self.assertEqual(kwargs.get("alert_id"), "ALERT_XYZ")

        cmd, kwargs = parse_command("/reject_scratch ALERT_XYZ")
        self.assertEqual(cmd, "reject_scratch")
        self.assertEqual(kwargs.get("alert_id"), "ALERT_XYZ")

        cmd, kwargs = parse_command("/watch_scratch ALERT_XYZ")
        self.assertEqual(cmd, "watch_scratch")
        self.assertEqual(kwargs.get("alert_id"), "ALERT_XYZ")

    # ── Test 12: Stale alert revalidation handling ──
    def test_close_early_fails_on_stale_alert_if_no_longer_valid(self):
        """12. Stale alert handling: CLOSE EARLY fails safely on stale alert if candidate condition cleared."""
        self._add_test_trade(108, "BTCUSDT", "LONG")
        
        # Alert is 20 minutes old (stale), and candidate condition cleared (status CONDITION_CLEARED)
        candidates = [{
            "candidate_id": "TESTNET_BTCUSDT_108_ROUNDTRIP_CANDIDATE",
            "candidate_type": "ROUNDTRIP_CANDIDATE",
            "instance": "STANDARD_TESTNET",
            "trade_id": 108,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "status": "CONDITION_CLEARED",
            "created_at": (datetime.now() - timedelta(minutes=20)).isoformat(),
        }]
        self._write_test_candidates(candidates)

        res = execute("lm_close", candidate_id="TESTNET_BTCUSDT_108_ROUNDTRIP_CANDIDATE")
        self.assertFalse(res.success)
        self.assertIn("candidate stale/condition cleared", res.message)
        self.mock_close_pos_m.assert_not_called()

    def test_status_parse_with_suffix(self):
        """13. Verify `/status@JarvisBot` and `/status` commands parse correctly."""
        cmd, kwargs = parse_command("/status@JarvisBot")
        self.assertEqual(cmd, "status")
        self.assertEqual(kwargs, {})

        cmd, kwargs = parse_command("/status")
        self.assertEqual(cmd, "status")
        self.assertEqual(kwargs, {})

        cmd, kwargs = parse_command("/close@JarvisBot BTCUSDT")
        self.assertEqual(cmd, "close")
        self.assertEqual(kwargs.get("symbol"), "BTCUSDT")
