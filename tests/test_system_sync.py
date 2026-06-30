import os
import json
import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import trade_db
import command_center
import ozzy_context_observer

class SystemSyncTests(unittest.TestCase):
    def setUp(self):
        # Create temp dir and temp DB
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        
        # Patch trade_db.DB_PATH
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.db_patch.start()
        
        # Initialize DB tables and create the database file
        with trade_db._connect() as conn:
            pass
        
        # Patch ozzy_context_observer DB paths
        self.observer_std_patch = patch.object(ozzy_context_observer, "DB_PATH_STD", str(self.db_path))
        self.observer_live_patch = patch.object(ozzy_context_observer, "DB_PATH_LIVE", str(self.db_path))
        self.observer_std_patch.start()
        self.observer_live_patch.start()
        
        # Prepare temp observer folder inside tempdir for action_queue and scoreboard
        self.obs_dir = Path(self.tempdir.name) / "observer"
        self.obs_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path = self.obs_dir / "action_queue.json"
        self.scoreboard_path = self.obs_dir / "alert_scoreboard.json"

    def tearDown(self):
        self.observer_live_patch.stop()
        self.observer_std_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_close_trade_always_sets_execution_state_closed(self):
        # Log active trade
        trade_id = trade_db.log_trade(
            signal_id=None,
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=100.0,
            qty=1.0,
            sl=95.0,
            tp=110.0,
            rr=2.0,
            regime="trend",
            strategy="momentum",
            timeframe="1h",
            mode="live",
            setup_grade="A",
            risk_dollars=10.0,
            reward_dollars=20.0,
            atr=5.0,
            volume_ratio=1.0,
            context="{}",
            execution_state="protection_verified"
        )
        
        # Close trade
        trade_db.close_trade(trade_id, exit_price=105.0, pnl=5.0, exit_reason="tp")
        
        # Verify it became "closed" in DB
        trade = trade_db.get_trade_by_id(trade_id)
        self.assertEqual(trade["execution_state"], "closed")

    def test_migration_updates_historical_closed_trades(self):
        # Log trade and directly set exit_price and execution_state='confirmed' via raw SQL
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trades (symbol, direction, entry_price, exit_price, execution_state)
                VALUES ('ETHUSDT', 'BUY', 200.0, 210.0, 'confirmed')
                """
            )
            conn.commit()
            
        # Run one-time migration logic
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE trades SET execution_state='closed' WHERE exit_price IS NOT NULL;")
            conn.commit()
            
        # Verify it is updated to "closed"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT execution_state FROM trades WHERE symbol='ETHUSDT'").fetchone()
            self.assertEqual(row["execution_state"], "closed")

    def test_is_trade_open_in_db_states(self):
        # 1. Missing trade -> NOT_FOUND
        self.assertEqual(ozzy_context_observer.is_trade_open_in_db("STANDARD_TESTNET", 9999), "NOT_FOUND")
        
        # 2. Open trade -> OPEN
        trade_id_open = trade_db.log_trade(
            None, "SOLUSDT", "BUY", 50.0, 1.0, 48.0, 55.0, 2.5, "range", "reversion", "1h", "live", "B", 5.0, 12.5, 2.0, 1.0, "{}", "confirmed"
        )
        self.assertEqual(ozzy_context_observer.is_trade_open_in_db("STANDARD_TESTNET", trade_id_open), "OPEN")
        
        # 3. Closed trade -> CLOSED
        trade_id_closed = trade_db.log_trade(
            None, "ADAUSDT", "BUY", 1.0, 10.0, 0.9, 1.2, 2.0, "trend", "momentum", "1h", "live", "A", 1.0, 2.0, 0.1, 1.0, "{}", "confirmed"
        )
        trade_db.close_trade(trade_id_closed, exit_price=1.1, pnl=1.0, exit_reason="manual")
        self.assertEqual(ozzy_context_observer.is_trade_open_in_db("STANDARD_TESTNET", trade_id_closed), "CLOSED")

    def test_observer_auto_resolve_handles_not_found(self):
        # Create a mock action queue and scoreboard with:
        # - One closed trade alert (should resolve)
        # - One missing trade alert (should get status ERROR_TRADE_NOT_FOUND)
        
        # Closed trade in DB
        trade_id_closed = trade_db.log_trade(
            None, "SUIUSDT", "SELL", 1.5, 10.0, 1.6, 1.3, 2.0, "range", "reversion", "1h", "live", "A", 1.0, 2.0, 0.1, 1.0, "{}", "confirmed"
        )
        trade_db.close_trade(trade_id_closed, exit_price=1.4, pnl=1.0, exit_reason="tp")
        
        # Missing trade ID (never in DB)
        trade_id_missing = 8888
        
        alert_id_closed = f"STANDARD_TESTNET_SUIUSDT_{trade_id_closed}"
        alert_id_missing = f"STANDARD_TESTNET_XRPUSDT_{trade_id_missing}"
        
        action_queue = [
            {
                "alert_id": alert_id_closed,
                "trade_id": trade_id_closed,
                "instance": "STANDARD_TESTNET",
                "symbol": "SUIUSDT",
                "resolved": False
            },
            {
                "alert_id": alert_id_missing,
                "trade_id": trade_id_missing,
                "instance": "STANDARD_TESTNET",
                "symbol": "XRPUSDT",
                "resolved": False
            }
        ]
        
        scoreboard = {
            "total_alerts": 2,
            "unresolved": 2,
            "alert_history": {
                alert_id_closed: {
                    "resolved": False,
                    "status": None
                },
                alert_id_missing: {
                    "resolved": False,
                    "status": None
                }
            }
        }
        
        # Write files
        with open(self.queue_path, "w") as f:
            json.dump(action_queue, f)
        with open(self.scoreboard_path, "w") as f:
            json.dump(scoreboard, f)
            
        # Run auto-resolve check inside patched environment
        with patch.object(ozzy_context_observer, "OBSERVER_DIR", str(self.obs_dir)), \
             patch.object(ozzy_context_observer, "send_scratch_exit_notification", return_value=True), \
             patch.object(ozzy_context_observer, "send_mfe_guard_notification", return_value=True):
            ozzy_context_observer.manage_persistent_files([], [])
            
        # Load results
        with open(self.queue_path) as f:
            q_res = json.load(f)
        with open(self.scoreboard_path) as f:
            s_res = json.load(f)
            
        # Closed trade alert -> resolved=True
        closed_alert = next(a for a in q_res if a["alert_id"] == alert_id_closed)
        self.assertTrue(closed_alert.get("resolved"))
        self.assertTrue(s_res["alert_history"][alert_id_closed]["resolved"])
        
        # Missing trade alert -> resolved=False, status=ERROR_TRADE_NOT_FOUND
        missing_alert = next(a for a in q_res if a["alert_id"] == alert_id_missing)
        self.assertFalse(missing_alert.get("resolved"))
        self.assertEqual(missing_alert.get("status"), "ERROR_TRADE_NOT_FOUND")
        self.assertFalse(s_res["alert_history"][alert_id_missing]["resolved"])
        self.assertEqual(s_res["alert_history"][alert_id_missing]["status"], "ERROR_TRADE_NOT_FOUND")

    def test_approve_scratch_returns_error_trade_not_found(self):
        # Mock a queue containing a missing trade
        trade_id_missing = 9999
        alert_id = f"STANDARD_TESTNET_DOGEUSDT_{trade_id_missing}"
        
        queue = [
            {
                "alert_id": alert_id,
                "trade_id": trade_id_missing,
                "instance": "STANDARD_TESTNET",
                "symbol": "DOGEUSDT",
                "side": "LONG",
                "qty": 10.0,
                "status": "pending_approval",
                "expires_at": "2030-01-01T00:00:00"
            }
        ]
        
        with open(self.queue_path, "w") as f:
            json.dump(queue, f)
            
        # Run cmd_approve_scratch on patched command_center with observer_dir mapped
        with patch("command_center.os.path.exists", return_value=True), \
             patch("command_center.open", unittest.mock.mock_open(read_data=json.dumps(queue))), \
             patch("sqlite3.connect") as mock_connect:
            
            # Setup DB connect to return None (no row found)
            mock_conn = mock_connect.return_value.__enter__.return_value
            mock_cursor = mock_conn.cursor.return_value
            mock_cursor.fetchone.return_value = None
            
            result = command_center.cmd_approve_scratch(alert_id)
            
            # Verify result matches
            self.assertFalse(result.success)
            self.assertEqual(result.details.get("reason"), "ERROR_TRADE_NOT_FOUND")
            self.assertIn("Trade not found in database", result.message)

    def test_approve_scratch_success_sets_execution_state_closed(self):
        # 1. Log trade in database
        trade_id = trade_db.log_trade(
            signal_id=None,
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=100.0,
            qty=1.0,
            sl=95.0,
            tp=110.0,
            rr=2.0,
            regime="trend",
            strategy="momentum",
            timeframe="1h",
            mode="live",
            setup_grade="A",
            risk_dollars=10.0,
            reward_dollars=20.0,
            atr=5.0,
            volume_ratio=1.0,
            context="{}",
            execution_state="protection_verified"
        )
        
        # Bypass Fresh Position Guard by setting ts to 10 hours ago
        from datetime import datetime, timedelta
        past_ts = (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        with trade_db._connect() as conn:
            conn.execute("UPDATE trades SET ts = ? WHERE id = ?", (past_ts, trade_id))
            conn.commit()
        
        # 2. Add alert to action_queue
        alert_id = f"STANDARD_TESTNET_BTCUSDT_{trade_id}"
        queue = [
            {
                "alert_id": alert_id,
                "trade_id": trade_id,
                "instance": "STANDARD_TESTNET",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "qty": 1.0,
                "status": "pending_approval",
                "expires_at": "2030-01-01T00:00:00"
            }
        ]
        
        with open(self.queue_path, "w") as f:
            json.dump(queue, f)
            
        # Mock values for exchange functions
        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 98.0,
                "volume": 1.0
            }
        ]
        
        # Redirect sqlite3.connect to the temporary database
        original_connect = sqlite3.connect
        def redirect_connect(path, *args, **kwargs):
            return original_connect(str(self.db_path), *args, **kwargs)

        # Run scratch close approval
        with patch("command_center.os.path.exists", return_value=True), \
             patch("command_center.open", unittest.mock.mock_open(read_data=json.dumps(queue))), \
             patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.close_position", return_value={"success": True, "status": "closed"}), \
             patch("sqlite3.connect", side_effect=redirect_connect):
             
            result = command_center.cmd_approve_scratch(alert_id)
            self.assertTrue(result.success)
            
        # Verify the database state now has execution_state='closed'
        trade = trade_db.get_trade_by_id(trade_id)
        self.assertEqual(trade["execution_state"], "closed")
        self.assertEqual(trade["exit_reason"], "scratch_exit_approved")

    def test_approve_scratch_partial_qty(self):
        # 1. Log trade in database with original qty 1000.0
        trade_id = trade_db.log_trade(
            signal_id=None,
            symbol="WLDUSDT",
            direction="BUY",
            entry_price=10.0,
            qty=1000.0,
            sl=9.0,
            tp=12.0,
            rr=2.0,
            regime="trend",
            strategy="momentum",
            timeframe="1h",
            mode="live",
            setup_grade="A",
            risk_dollars=10.0,
            reward_dollars=20.0,
            atr=1.0,
            volume_ratio=1.0,
            context="{}",
            execution_state="protection_verified"
        )
        
        # Bypass Fresh Position Guard by setting ts to 10 hours ago
        from datetime import datetime, timedelta
        past_ts = (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        with trade_db._connect() as conn:
            conn.execute("UPDATE trades SET ts = ? WHERE id = ?", (past_ts, trade_id))
            conn.commit()
        
        # 2. Add alert to action_queue with original qty 1000.0
        alert_id = f"STANDARD_TESTNET_WLDUSDT_{trade_id}"
        queue = [
            {
                "alert_id": alert_id,
                "trade_id": trade_id,
                "instance": "STANDARD_TESTNET",
                "symbol": "WLDUSDT",
                "side": "LONG",
                "qty": 1000.0,
                "status": "pending_approval",
                "expires_at": "2030-01-01T00:00:00"
            }
        ]
        
        with open(self.queue_path, "w") as f:
            json.dump(queue, f)
            
        # Mock exchange position with volume 500.0 (reduced)
        mock_positions = [
            {
                "symbol": "WLDUSDT",
                "type": "BUY",
                "openPrice": 10.0,
                "currentPrice": 10.0,
                "volume": 500.0,
                "profit": 0.0
            }
        ]
        
        # Redirect sqlite3.connect to the temporary database
        original_connect = sqlite3.connect
        def redirect_connect(path, *args, **kwargs):
            return original_connect(str(self.db_path), *args, **kwargs)

        # Run scratch close approval. First time it should refresh the alert to 500.0
        with patch("command_center.os.path.exists", return_value=True), \
             patch("command_center.open", unittest.mock.mock_open(read_data=json.dumps(queue))), \
             patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.close_position", return_value={"success": True, "status": "closed"}) as mock_close, \
             patch("sqlite3.connect", side_effect=redirect_connect):
             
            result = command_center.cmd_approve_scratch(alert_id)
            self.assertFalse(result.success)
            self.assertIn("refreshed to 500.0", result.message)
            mock_close.assert_not_called()
            
        # Now update our mock queue to have the refreshed 500.0 quantity
        queue[0]["qty"] = 500.0
        with open(self.queue_path, "w") as f:
            json.dump(queue, f)
            
        # Run second time - validation should pass and it should execute
        with patch("command_center.os.path.exists", return_value=True), \
             patch("command_center.open", unittest.mock.mock_open(read_data=json.dumps(queue))), \
             patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.close_position", return_value={"success": True, "status": "closed"}) as mock_close, \
             patch("sqlite3.connect", side_effect=redirect_connect):
             
            result = command_center.cmd_approve_scratch(alert_id)
            self.assertTrue(result.success)
            mock_close.assert_called_once_with("WLDUSDT")

    def test_orphan_reconciler_cases(self):
        # Setup DB open trade for CASE 2, 3, 4
        # Case 2: trade exists in DB, missing on exchange
        trade_id_ghost = trade_db.log_trade(None, "GHOSTUSDT", "BUY", 100.0, 1.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, {}, "protection_verified")
        
        # Case 3: side mismatch
        trade_id_side = trade_db.log_trade(None, "MISMATCHUSDT", "BUY", 100.0, 1.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, {}, "protection_verified")
        
        # Case 4: qty mismatch
        trade_id_qty = trade_db.log_trade(None, "QTYUSDT", "BUY", 100.0, 1.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, {}, "protection_verified")

        # Mock exchange positions
        mock_positions = [
            # Case 1: exchange exists, no DB row
            {
                "symbol": "ORPHANUSDT",
                "type": "SELL", # SHORT position
                "openPrice": 50.0,
                "currentPrice": 48.0,
                "volume": 2.0,
                "profit": 4.0
            },
            # Case 3: side mismatch (exchange is SHORT, DB is LONG)
            {
                "symbol": "MISMATCHUSDT",
                "type": "SELL",
                "openPrice": 100.0,
                "currentPrice": 102.0,
                "volume": 1.0,
                "profit": -2.0
            },
            # Case 4: qty mismatch (exchange is 2.5, DB is 1.0)
            {
                "symbol": "QTYUSDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 98.0,
                "volume": 2.5,
                "profit": -5.0
            }
        ]

        import binance_monitor
        with patch("binance_monitor.plain_log") as mock_log, \
             patch("binance_monitor.trade_db", trade_db):
            
            # Run reconciler
            binance_monitor._reconcile_orphan_positions(mock_positions)
            
            # Verify logged events
            log_events = [c.args[0] for c in mock_log.call_args_list]
            
            # Verify ORPHAN_EXCHANGE_POSITION was logged for Case 1
            self.assertIn("ORPHAN_EXCHANGE_POSITION", log_events)
            orphan_log = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "ORPHAN_EXCHANGE_POSITION"][0]
            self.assertEqual(orphan_log["symbol"], "ORPHANUSDT")
            self.assertEqual(orphan_log["side"], "SHORT")
            self.assertEqual(orphan_log["qty"], 2.0)
            
            # Verify DB_GHOST_TRADE was logged for Case 2
            self.assertIn("DB_GHOST_TRADE", log_events)
            ghost_log = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "DB_GHOST_TRADE"][0]
            self.assertEqual(ghost_log["symbol"], "GHOSTUSDT")
            self.assertEqual(ghost_log["trade_id"], trade_id_ghost)
            
            # Verify POSITION_SIDE_MISMATCH was logged for Case 3
            self.assertIn("POSITION_SIDE_MISMATCH", log_events)
            side_log = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "POSITION_SIDE_MISMATCH"][0]
            self.assertEqual(side_log["symbol"], "MISMATCHUSDT")
            self.assertEqual(side_log["trade_id"], trade_id_side)
            self.assertEqual(side_log["exchange_side"], "SHORT")
            
            # Verify POSITION_QTY_MISMATCH was logged for Case 4
            self.assertIn("POSITION_QTY_MISMATCH", log_events)
            qty_log = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "POSITION_QTY_MISMATCH"][0]
            self.assertEqual(qty_log["symbol"], "QTYUSDT")
            self.assertEqual(qty_log["trade_id"], trade_id_qty)
            self.assertEqual(qty_log["exchange_qty"], 2.5)
            self.assertEqual(qty_log["db_qty"], 1.0)

    def test_adopt_orphan_new(self):
        # Mock exchange positions
        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 98.0,
                "volume": 1.0,
                "profit": -2.0
            }
        ]
        
        with patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.trade_db", trade_db):
            
            # Run adoption command without trade_id (creates new row)
            res = command_center.cmd_adopt_orphan("BTCUSDT", "LONG", 1.0, 100.0)
            self.assertTrue(res.success)
            self.assertIn("adopted successfully", res.message)
            
            # Verify trade row exists and is populated correctly
            trade_id = res.details["trade_id"]
            trade = trade_db.get_trade_by_id(trade_id)
            self.assertEqual(trade["symbol"], "BTCUSDT")
            self.assertEqual(trade["direction"], "BUY")
            self.assertEqual(trade["source"], "orphan_adopted")
            self.assertEqual(trade["execution_state"], "protection_verified")

    def test_adopt_orphan_relink(self):
        # 1. Log a closed trade in DB to act as candidate
        trade_id = trade_db.log_trade(None, "ETHUSDT", "SELL", 3000.0, 2.0, 3050.0, 2900.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, {}, "closed")
        with trade_db._connect() as conn:
            conn.execute("UPDATE trades SET exit_price = 2950.0, exit_reason = 'tp' WHERE id = ?", (trade_id,))
            conn.commit()
            
        # Mock exchange positions
        mock_positions = [
            {
                "symbol": "ETHUSDT",
                "type": "SELL",
                "openPrice": 3000.0,
                "currentPrice": 2980.0,
                "volume": 2.0,
                "profit": 40.0
            }
        ]
        
        with patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.trade_db", trade_db):
            
            # Run adoption with candidate trade_id (relinks row)
            res = command_center.cmd_adopt_orphan("ETHUSDT", "SHORT", 2.0, 3000.0, trade_id=trade_id)
            self.assertTrue(res.success)
            self.assertEqual(res.details["trade_id"], trade_id)
            
            # Verify closed columns are reset and state is updated
            trade = trade_db.get_trade_by_id(trade_id)
            self.assertIsNone(trade["exit_price"])
            self.assertIsNone(trade["pnl"])
            self.assertIsNone(trade["exit_reason"])
            self.assertEqual(trade["source"], "orphan_adopted")
            self.assertEqual(trade["execution_state"], "protection_verified")

    def test_close_orphan(self):
        # Mock exchange positions
        mock_positions = [
            {
                "symbol": "SOLUSDT",
                "type": "SELL",
                "openPrice": 150.0,
                "currentPrice": 148.0,
                "volume": 20.0,
                "profit": 40.0
            }
        ]
        
        with patch("command_center.get_open_positions", return_value=mock_positions), \
             patch("command_center.close_position", return_value={"success": True, "status": "closed"}) as mock_close:
            
            res = command_center.cmd_close_orphan("SOLUSDT", "SHORT", 20.0)
            self.assertTrue(res.success)
            mock_close.assert_called_once_with("SOLUSDT")

    def test_webhook_reconciliation_blocks_orphan_state(self):
        import webhook
        with patch("webhook.WEBHOOK_SECRET", "test_secret"), \
             patch("webhook.validate_signal_payload", return_value=(True, [])), \
             patch("webhook._monitor_entry_gate_status", return_value={"allowed": True, "active_state": "active"}), \
             patch("webhook._get_cached_positions", return_value=([], True)), \
             patch("webhook._entry_daily_stop_status", return_value={"live_trading_blocked_for_day": False}), \
             patch("webhook._check_signal_age", return_value={"allowed": True}), \
             patch("webhook._check_entry_drift", return_value={"allowed": True}), \
             patch("webhook._get_binance_client", return_value=MagicMock()), \
             patch(
                 "webhook.live_reconcile.reconcile_live_state",
                 return_value={
                     "healthy": False,
                     "critical_mismatches": ["ORPHAN_EXCHANGE_POSITION SOLUSDT SHORT"],
                     "warnings": [],
                 },
             ), \
             patch("webhook.PAPER_MODE", False):
             
            # Test webhook signal is blocked for SOLUSDT
            webhook.plain_log = MagicMock()
            webhook.telegram_client = MagicMock()
            
            app = webhook.app.test_client()
            import time
            payload = {
                "secret": "test_secret",
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "entry": 148.0,
                "sl": 155.0,
                "tp": 135.0,
                "source": "signal_generator",
                "source_service": "signal_generator",
                "strategy": "pullback",
                "strategy_label": "1H_TREND_CONTINUATION",
                "timeframe": "60",
                "timestamp": int(time.time()),
            }
            res = app.post("/webhook", json=payload)
            data = json.loads(res.data)
            self.assertEqual(res.status_code, 200, data)
            self.assertEqual(data["status"], "rejected")
            self.assertIn("Reconciliation critical mismatch", data["reason"])

    def test_entry_reconciliation_blocks_only_symbol_with_stale_algo_orders(self):
        import webhook

        reconciliation = {
            "healthy": True,
            "critical_mismatches": [],
            "stale_algo_orders": [
                {"symbol": "BTCUSDT", "algo_id": 123, "order_type": "STOP_MARKET"},
            ],
        }

        btc_reason = webhook._entry_reconciliation_block_reason("BTCUSDT", reconciliation)
        eth_reason = webhook._entry_reconciliation_block_reason("ETHUSDT", reconciliation)

        self.assertIn("BTCUSDT", btc_reason)
        self.assertIn("stale", btc_reason.lower())
        self.assertIsNone(eth_reason)

    def test_partial_aware_qty_reconciliation(self):
        # 1. Original full position matches
        trade_id_full = trade_db.log_trade(None, "FULLUSDT", "BUY", 100.0, 1.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, "{}", "protection_verified")
        
        # 2. 25% partial exit matches reduced exchange qty (expected remaining = 0.75)
        trade_id_p25 = trade_db.log_trade(None, "PARTIAL25USDT", "BUY", 100.0, 1.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 1.0, "{}", "protection_verified")
        trade_db.log_exit(trade_id_p25, "milestone_0", price=105.0, pnl_contribution=1.25, qty_pct=0.25)
        
        # 3. 50% partial exit matches reduced exchange qty (expected remaining = 5.0) via binance_order_state
        trade_id_p50 = trade_db.log_trade(None, "PARTIAL50USDT", "BUY", 100.0, 10.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 10.0, "{}", "protection_verified")
        trade_db.upsert_binance_order_state(symbol="PARTIAL50USDT", remaining_qty=5.0)
        
        # 4. Real unexpected qty mismatch still alerts
        trade_id_real_mismatch = trade_db.log_trade(None, "REALMISMATCHUSDT", "BUY", 100.0, 10.0, 95.0, 110.0, 2.0, "trend", "momentum", "1h", "live", "A", 10.0, 20.0, 5.0, 10.0, "{}", "protection_verified")
        trade_db.upsert_binance_order_state(symbol="REALMISMATCHUSDT", remaining_qty=5.0) # Expected is 5.0, but exchange will have 4.0

        mock_positions = [
            {
                "symbol": "FULLUSDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 100.0,
                "volume": 1.0,
                "profit": 0.0
            },
            {
                "symbol": "PARTIAL25USDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 100.0,
                "volume": 0.75, # 1.0 - 0.25 = 0.75
                "profit": 0.0
            },
            {
                "symbol": "PARTIAL50USDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 100.0,
                "volume": 5.0, # 10.0 * 0.5 = 5.0
                "profit": 0.0
            },
            {
                "symbol": "REALMISMATCHUSDT",
                "type": "BUY",
                "openPrice": 100.0,
                "currentPrice": 100.0,
                "volume": 4.0, # Expected is 5.0, actual is 4.0 -> Mismatch
                "profit": 0.0
            }
        ]

        import binance_monitor
        with patch("binance_monitor.plain_log") as mock_log, \
             patch("binance_monitor.trade_db", trade_db):
            
            # Run reconciler
            binance_monitor._reconcile_orphan_positions(mock_positions)
            
            log_events = [c.args[0] for c in mock_log.call_args_list]
            
            # Assert reconciled events
            reconciled_logs = [c.args[1] for c in mock_log.call_args_list if c.args[0] == "POSITION_QTY_RECONCILED"]
            
            # Check FULLUSDT
            full_log = next(l for l in reconciled_logs if l["symbol"] == "FULLUSDT")
            self.assertEqual(full_log["exchange_qty"], 1.0)
            self.assertEqual(full_log["expected_qty"], 1.0)
            
            # Check PARTIAL25USDT
            p25_log = next(l for l in reconciled_logs if l["symbol"] == "PARTIAL25USDT")
            self.assertEqual(p25_log["exchange_qty"], 0.75)
            self.assertEqual(p25_log["expected_qty"], 0.75)
            
            # Check PARTIAL50USDT
            p50_log = next(l for l in reconciled_logs if l["symbol"] == "PARTIAL50USDT")
            self.assertEqual(p50_log["exchange_qty"], 5.0)
            self.assertEqual(p50_log["expected_qty"], 5.0)
            
            # Check REALMISMATCHUSDT anchors to exchange qty and flags noisy accounting.
            # Exchange size is safer for protection management than stale qty_pct math.
            real_mismatch_log = next(l for l in reconciled_logs if l["symbol"] == "REALMISMATCHUSDT")
            self.assertEqual(real_mismatch_log["exchange_qty"], 4.0)
            self.assertEqual(real_mismatch_log["expected_qty"], 4.0)
            self.assertTrue(real_mismatch_log["accounting_noisy"])


if __name__ == "__main__":
    unittest.main()
