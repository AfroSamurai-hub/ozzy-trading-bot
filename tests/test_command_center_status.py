import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

import command_center
import trade_db
from command_center import cmd_status

class TestCommandCenterStatus(unittest.TestCase):
    def test_legacy_instance_labels_use_unified_trade_db(self):
        with patch.object(trade_db, "DB_PATH", Path("/tmp/unified-trades.db")):
            self.assertEqual(
                command_center._command_db_path_for_instance("STANDARD_TESTNET"),
                "/tmp/unified-trades.db",
            )
            self.assertEqual(
                command_center._command_db_path_for_instance("LIVE_MICRO"),
                "/tmp/unified-trades.db",
            )

    @patch('command_center.get_open_positions')
    @patch('command_center.get_balance')
    @patch('command_center._get_sl_tp_from_orders')
    @patch('command_center._count_recent_errors_24h')
    @patch('sqlite3.connect')
    def test_cmd_status_formatting_and_math(self, mock_db_connect, mock_recent_errs, mock_sl_tp, mock_balance, mock_open_pos):
        # 1. Setup open positions
        mock_open_pos.return_value = [
            {
                "symbol": "SOLUSDT",
                "tv_symbol": "SOLUSDT",
                "type": "SELL",
                "openPrice": 82.47,
                "currentPrice": 82.33,
                "volume": 40.0,
                "profit": 5.60,
                "stopLoss": None,
                "takeProfit": None
            },
            {
                "symbol": "ETHUSDT",
                "tv_symbol": "ETHUSDT",
                "type": "BUY",
                "openPrice": 3000.0,
                "currentPrice": 3000.0,
                "volume": 0.0,  # Should be filtered out because volume is 0!
                "profit": 0.0,
                "stopLoss": None,
                "takeProfit": None
            }
        ]

        # 2. Setup balance
        mock_balance.return_value = {
            "equity": 15000.25,
            "balance": 14994.65
        }

        # 3. Setup mock SL/TP
        mock_sl_tp.return_value = (83.767, 81.822)

        # 4. Setup mock errors
        mock_recent_errs.return_value = {
            "-2015": 1,
            "-4061": 2,
            "-4130": 3,
            "ReadTimeout": 4,
            "TRAILING STOP FAILED": 5
        }

        # 5. Setup mock sqlite trades
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"id": 172, "symbol": "HYPEUSDT", "direction": "BUY", "pnl": 361.66},
            {"id": 175, "symbol": "LINKUSDT", "direction": "SELL", "pnl": -27.77}
        ]

        # 6. Execute cmd_status under various patching conditions
        with patch('command_center.PAPER_MODE', False), \
             patch('command_center.MAX_POSITIONS', 5), \
             patch.dict('os.environ', {'HERMES_LIVE_MICRO_NO_NEW_ENTRIES': 'True'}):
            
            res = cmd_status()

        self.assertTrue(res.success)
        msg = res.message

        # Assert headers
        self.assertIn("HERMES COMMAND CENTER", msg)
        self.assertIn("Mode: <code>TESTNET</code>", msg)
        
        # Assert account fields
        self.assertIn("Equity: $15000.25", msg)
        self.assertIn("Balance: $14994.65", msg)
        self.assertIn("Positions: 1 / 5", msg)  # Only 1 position because ETHUSDT volume was 0!

        # Assert PnL summary
        self.assertIn("Today Realized PnL: <b>$+333.89</b>", msg)  # 361.66 - 27.77
        self.assertIn("Open Unrealized PnL: <b>$+5.60</b>", msg)
        self.assertIn("Today Net PnL: <b>$+339.49</b>", msg)
        self.assertIn("Closed Trades Today: 2", msg)
        self.assertIn("Best Closed Trade: HYPEUSDT (BUY) <b>$+361.66</b>", msg)

        # Assert open positions protection details
        self.assertIn("SOLUSDT SELL", msg)
        self.assertIn("Entry: 82.47 | Current: 82.33", msg)
        self.assertIn("PnL: $+5.60", msg)
        self.assertIn("SL: 83.77 | TP: 81.82", msg)
        self.assertIn("Protection: <code>PROTECTED</code>", msg)

        # Assert Risk/health
        self.assertIn("Live new entries lock status:", msg)
        self.assertIn("-2015 (Invalid credentials): 1", msg)
        self.assertIn("-4061 (Invalid position side): 2", msg)
        self.assertIn("-4130 (Duplicate close position): 3", msg)
        self.assertIn("ReadTimeout (Network issue): 4", msg)
        self.assertIn("TRAILING STOP FAILED: 5", msg)

    @patch('command_center.build_command_center_status')
    @patch('command_center.plain_log')
    def test_cmd_status_fallback_on_exception(self, mock_plain_log, mock_build_status):
        # Setup the rich status builder to raise an exception
        mock_build_status.side_effect = ValueError("Mock database connection failed")

        res = cmd_status()

        # Assertions
        self.assertFalse(res.success)
        self.assertIn("STATUS_RICH_FALLBACK", res.message)
        self.assertIn("Mock database connection failed", res.message)
        mock_plain_log.assert_any_call("STATUS_RICH_FALLBACK", {"error": "Mock database connection failed"})


if __name__ == "__main__":
    unittest.main()
