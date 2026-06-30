import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Allow importing from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trade_db
from scripts import shadow_monitor

class ShadowMonitorTests(unittest.TestCase):
    def setUp(self):
        # Redirect trade_db to a temporary database
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.db_patch.start()
        
        # Patch telegram_client exit notify to avoid network requests
        self.telegram_patch = patch("telegram_client.notify_shadow_exit")
        self.mock_notify = self.telegram_patch.start()
        
    def tearDown(self):
        self.telegram_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()
        
    @patch("scripts.shadow_monitor.fetch_batched_prices")
    @patch("time.sleep")
    def test_shadow_buy_tp_hit(self, mock_sleep, mock_fetch_prices):
        # 1. Log a Grade C shadow BUY trade
        trade_id = trade_db.log_trade(
            signal_id=None,
            symbol="SOLUSDT",
            direction="BUY",
            entry_price=80.0,
            qty=10.0,
            sl=75.0,
            tp=90.0,
            mode="paper",
            setup_grade="C",
            risk_dollars=5.0,
            execution_state="shadow"
        )
        
        # 2. Mock Binance prices to hit TP
        mock_fetch_prices.return_value = {"SOLUSDT": 91.0}
        
        # 3. time.sleep raises KeyboardInterrupt to exit the track_shadow_trades infinite loop
        mock_sleep.side_effect = KeyboardInterrupt()
        
        # Run loop
        with self.assertRaises(KeyboardInterrupt):
            shadow_monitor.track_shadow_trades()
            
        # 4. Check DB updates
        with trade_db._connect() as conn:
            trade = dict(conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone())
            
        self.assertEqual(trade["execution_state"], "shadow_closed")
        self.assertEqual(trade["exit_price"], 90.0) # Should exit at TP price
        self.assertEqual(trade["exit_reason"], "tp")
        
        # Verify Fee Reality Check Math:
        # entry size = 80 * 10 = 800
        # exit size = 90 * 10 = 900
        # gross pnl = (90 - 80) * 10 = 100
        # fee entry (0.05%) = 0.40
        # fee exit (0.05%) = 0.45
        # slippage (0.02%) = 0.16
        # deductions = 1.01
        # net pnl = 100 - 1.01 = 98.99
        self.assertAlmostEqual(trade["pnl"], 98.99, places=4)
        self.assertAlmostEqual(trade["gross_pnl"], 100.0, places=4)
        self.assertAlmostEqual(trade["fees"], 0.85, places=4)
        
        # Verify Telegram alert was triggered
        self.mock_notify.assert_called_once_with(
            symbol="SOLUSDT",
            direction="BUY",
            entry=80.0,
            exit_price=90.0,
            net_pnl=98.99,
            exit_reason="tp",
            setup_grade="C"
        )

    @patch("scripts.shadow_monitor.fetch_batched_prices")
    @patch("time.sleep")
    def test_shadow_sell_sl_hit(self, mock_sleep, mock_fetch_prices):
        # 1. Log a Grade C shadow SELL trade
        trade_id = trade_db.log_trade(
            signal_id=None,
            symbol="BTCUSDT",
            direction="SELL",
            entry_price=60000.0,
            qty=0.1,
            sl=61000.0,
            tp=58000.0,
            mode="paper",
            setup_grade="C",
            risk_dollars=10.0,
            execution_state="shadow"
        )
        
        # 2. Mock Binance prices to hit SL
        mock_fetch_prices.return_value = {"BTCUSDT": 61200.0}
        
        # 3. time.sleep raises KeyboardInterrupt to exit the track_shadow_trades infinite loop
        mock_sleep.side_effect = KeyboardInterrupt()
        
        # Run loop
        with self.assertRaises(KeyboardInterrupt):
            shadow_monitor.track_shadow_trades()
            
        # 4. Check DB updates
        with trade_db._connect() as conn:
            trade = dict(conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone())
            
        self.assertEqual(trade["execution_state"], "shadow_closed")
        self.assertEqual(trade["exit_price"], 61000.0) # Should exit at SL price
        self.assertEqual(trade["exit_reason"], "sl")
        
        # Verify Fee Reality Check Math:
        # entry size = 60000 * 0.1 = 6000
        # exit size = 61000 * 0.1 = 6100
        # gross pnl = (60000 - 61000) * 0.1 = -100
        # fee entry (0.05%) = 3.0
        # fee exit (0.05%) = 3.05
        # slippage (0.02%) = 1.20
        # deductions = 7.25
        # net pnl = -100 - 7.25 = -107.25
        self.assertAlmostEqual(trade["pnl"], -107.25, places=4)
        self.assertAlmostEqual(trade["gross_pnl"], -100.0, places=4)
        self.assertAlmostEqual(trade["fees"], 6.05, places=4)
        
        # Verify Telegram alert was triggered
        self.mock_notify.assert_called_once_with(
            symbol="BTCUSDT",
            direction="SELL",
            entry=60000.0,
            exit_price=61000.0,
            net_pnl=-107.25,
            exit_reason="sl",
            setup_grade="C"
        )

if __name__ == "__main__":
    unittest.main()
