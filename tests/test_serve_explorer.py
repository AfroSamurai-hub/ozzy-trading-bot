import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.serve_explorer as serve_explorer


class ServeExplorerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "trades.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                pnl REAL,
                exit_reason TEXT,
                sl REAL,
                tp REAL,
                timeframe TEXT,
                execution_state TEXT,
                mode TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO trades (
                id, ts, symbol, direction, entry_price, exit_price, qty, pnl, exit_reason, sl, tp, timeframe, execution_state, mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "2026-06-27T09:00:00+00:00", "BTCUSDT", "BUY", 100.0, None, 2.0, None, None, 90.0, 120.0, "1h", "confirmed", "testnet"),
                (2, "2026-06-27T09:05:00+00:00", "ETHUSDT", "SELL", 200.0, None, 3.0, None, None, 210.0, 180.0, "1h", "confirmed", "live_micro"),
                (3, "2026-06-27T08:00:00+00:00", "SOLUSDT", "BUY", 50.0, 55.0, 1.0, 5.0, "tp", 45.0, 60.0, "1h", "closed", "live_micro"),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    @patch.object(serve_explorer, "fetch_binance_prices", return_value={"BTCUSDT": 105.0, "ETHUSDT": 190.0})
    def test_get_live_portfolio_filters_open_rows_by_mode(self, _mock_prices):
        testnet_rows = serve_explorer.get_live_portfolio(str(self.db), mode="testnet")
        live_micro_rows = serve_explorer.get_live_portfolio(str(self.db), mode="live_micro")

        self.assertEqual([row["symbol"] for row in testnet_rows], ["BTCUSDT"])
        self.assertEqual([row["symbol"] for row in live_micro_rows], ["ETHUSDT"])

    def test_get_recent_history_filters_closed_rows_by_mode(self):
        testnet_rows = serve_explorer.get_recent_history(str(self.db), mode="testnet")
        live_micro_rows = serve_explorer.get_recent_history(str(self.db), mode="live_micro")

        self.assertEqual(testnet_rows, [])
        self.assertEqual([row["symbol"] for row in live_micro_rows], ["SOLUSDT"])


if __name__ == "__main__":
    unittest.main()
