import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow importing from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trade_db
from scripts import optimize_parameters

class OptimizeParametersTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.db_patch.start()
        
    def tearDown(self):
        self.db_patch.stop()
        self.tempdir.cleanup()
        
    def _insert_trade(self, symbol: str, direction: str, entry: float, exit: float, pnl: float, state: str, days_offset: int = 0):
        # We write direct SQLite insert to precisely control timestamps if needed
        # Or we can log and close using trade_db helper.
        # Direct SQL is faster and cleaner for setting custom states and dates.
        import sqlite3
        from datetime import datetime, timedelta, UTC
        ts = (datetime.now(UTC) - timedelta(days=days_offset)).strftime("%Y-%m-%d %H:%M:%S")
        
        with trade_db._connect() as conn:
            conn.execute(
                """
                INSERT INTO trades (ts, symbol, direction, entry_price, exit_price, pnl, qty, execution_state, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, symbol, direction, entry, exit, pnl, 1.0, state, "paper")
            )
            conn.commit()

    @patch("sys.argv")
    def test_insufficient_shadow_data(self, mock_argv):
        # Insert 1 live trade, 1 shadow trade
        self._insert_trade("SOLUSDT", "BUY", 80.0, 90.0, 10.0, "closed")
        self._insert_trade("ETHUSDT", "BUY", 2000.0, 2010.0, 10.0, "shadow_closed")
        
        mock_argv.__getitem__.side_effect = lambda x: str(self.db_path) if x == 1 else "optimize_parameters.py"
        mock_argv.__len__.return_value = 2
        
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            optimize_parameters.main()
        finally:
            sys.stdout = sys.__stdout__
            
        output = captured_output.getvalue()
        self.assertIn("INSUFFICIENT SHADOW DATA", output)

    @patch("sys.argv")
    def test_opportunity_detected_loose_gating(self, mock_argv):
        # Insert live trades (stable)
        self._insert_trade("SOLUSDT", "BUY", 80.0, 81.0, 1.0, "closed")
        
        # Insert 3 profitable shadow trades: win rate = 100%, profit factor >= 1.4
        self._insert_trade("ETHUSDT", "BUY", 2000.0, 2050.0, 50.0, "shadow_closed")
        self._insert_trade("LINKUSDT", "BUY", 15.0, 18.0, 3.0, "shadow_closed")
        self._insert_trade("XAUUSDT", "BUY", 2300.0, 2350.0, 50.0, "shadow_closed")
        
        mock_argv.__getitem__.side_effect = lambda x: str(self.db_path) if x == 1 else "optimize_parameters.py"
        mock_argv.__len__.return_value = 2
        
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            optimize_parameters.main()
        finally:
            sys.stdout = sys.__stdout__
            
        output = captured_output.getvalue()
        self.assertIn("OPPORTUNITY DETECTED — Loose Gating Rules!", output)
        self.assertIn("SETUP_GRADE_C_LIVE", output)

    @patch("sys.argv")
    def test_risk_filters_validated(self, mock_argv):
        # Profitable live trades (win rate >= 50%)
        self._insert_trade("SOLUSDT", "BUY", 80.0, 90.0, 10.0, "closed")
        self._insert_trade("BTCUSDT", "BUY", 60000.0, 61000.0, 1000.0, "closed")
        
        # Losing shadow trades: win rate = 0% (< 40%)
        self._insert_trade("ETHUSDT", "BUY", 2000.0, 1950.0, -50.0, "shadow_closed")
        self._insert_trade("LINKUSDT", "BUY", 15.0, 12.0, -3.0, "shadow_closed")
        self._insert_trade("XAUUSDT", "BUY", 2300.0, 2250.0, -50.0, "shadow_closed")
        
        mock_argv.__getitem__.side_effect = lambda x: str(self.db_path) if x == 1 else "optimize_parameters.py"
        mock_argv.__len__.return_value = 2
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            optimize_parameters.main()
        finally:
            sys.stdout = sys.__stdout__
            
        output = captured_output.getvalue()
        self.assertIn("RISK FILTERS VALIDATED — Maintain strict rules!", output)

    @patch("sys.argv")
    def test_warning_high_chop(self, mock_argv):
        # Losing live trades (win rate < 45%)
        self._insert_trade("SOLUSDT", "BUY", 80.0, 75.0, -5.0, "closed")
        self._insert_trade("BTCUSDT", "BUY", 60000.0, 59000.0, -1000.0, "closed")
        
        # Losing shadow trades (win rate < 45%)
        self._insert_trade("ETHUSDT", "BUY", 2000.0, 1950.0, -50.0, "shadow_closed")
        self._insert_trade("LINKUSDT", "BUY", 15.0, 12.0, -3.0, "shadow_closed")
        self._insert_trade("XAUUSDT", "BUY", 2300.0, 2250.0, -50.0, "shadow_closed")
        
        mock_argv.__getitem__.side_effect = lambda x: str(self.db_path) if x == 1 else "optimize_parameters.py"
        mock_argv.__len__.return_value = 2
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            optimize_parameters.main()
        finally:
            sys.stdout = sys.__stdout__
            
        output = captured_output.getvalue()
        self.assertIn("WARNING — High Chop / Correlation Drawdown Regime!", output)
        self.assertIn("adx_threshold", output)

if __name__ == "__main__":
    unittest.main()
