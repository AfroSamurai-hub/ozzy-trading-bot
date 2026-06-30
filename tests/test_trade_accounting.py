import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import binance_monitor
import trade_db


class TradeAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(trade_db, "DB_PATH", Path(self.tempdir.name) / "trades.db")
        self.journal_patch = patch.object(trade_db, "_journal_event")
        self.db_patch.start()
        self.journal_patch.start()

    def tearDown(self):
        self.journal_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_sell_close_reconstructs_negative_pnl_when_exit_above_entry(self):
        audit = trade_db.reconcile_trade_close_pnl(
            direction="SELL",
            entry_price=4523.96,
            exit_price=4528.7601,
            original_qty=10.035,
            realized_partial_pnl=20.24492971344,
            realized_partial_qty_pct=0.25,
            fallback_pnl=135.55415917344,
        )

        self.assertTrue(audit["mismatch"])
        self.assertLess(audit["pnl"], 0)
        self.assertAlmostEqual(audit["remaining_qty"], 7.52625)

    def test_buy_close_reconstructs_positive_pnl_when_exit_above_entry(self):
        audit = trade_db.reconcile_trade_close_pnl(
            direction="BUY",
            entry_price=100.0,
            exit_price=110.0,
            original_qty=2.0,
            realized_partial_pnl=5.0,
            realized_partial_qty_pct=0.25,
            fallback_pnl=20.0,
        )

        self.assertFalse(audit["mismatch"])
        self.assertAlmostEqual(audit["pnl"], 20.0)

    def test_realized_partial_fraction_excludes_fractional_terminal_slice(self):
        trade_id = trade_db.log_trade(
            None,
            "BNBUSDT",
            "SELL",
            entry_price=100.0,
            qty=100.0,
        )
        trade_db.log_exit(
            trade_id,
            "milestone_0",
            qty_pct=0.4375,
            notes="partial=true",
        )
        trade_db.log_exit(
            trade_id,
            "momentum_exit",
            qty_pct=0.5625,
            notes="terminal=true",
        )

        self.assertAlmostEqual(trade_db.get_realized_exit_qty_pct(trade_id), 0.4375)

    def test_exchange_fill_ledger_includes_actual_fills_and_commissions(self):
        fills = [
            {"side": "SELL", "price": "60044.20", "qty": "0.2400", "realizedPnl": "0", "commission": "5.76424320"},
            {"side": "BUY", "price": "59918.80", "qty": "0.0600", "realizedPnl": "7.52400000", "commission": "1.43805120"},
            {"side": "BUY", "price": "59919.10", "qty": "0.0450", "realizedPnl": "5.62950000", "commission": "1.07854380"},
            {"side": "BUY", "price": "59919.10", "qty": "0.0450", "realizedPnl": "5.62950000", "commission": "1.07854380"},
            {"side": "BUY", "price": "59919.10", "qty": "0.0900", "realizedPnl": "11.25900000", "commission": "2.15708760"},
        ]

        ledger = trade_db.reconcile_exchange_fill_ledger("SELL", fills, funding=0.0)

        self.assertTrue(ledger["complete"])
        self.assertAlmostEqual(ledger["entry_price"], 60044.20)
        self.assertAlmostEqual(ledger["exit_price"], 59919.025)
        self.assertAlmostEqual(ledger["gross_pnl"], 30.042)
        self.assertAlmostEqual(ledger["fees"], 11.51646960)
        self.assertAlmostEqual(ledger["net_pnl"], 18.52553040)

    def test_exchange_fill_cycle_stops_before_later_same_symbol_trade(self):
        fills = [
            {"time": 1000, "positionSide": "SHORT", "side": "SELL", "qty": "0.24"},
            {"time": 2000, "positionSide": "SHORT", "side": "BUY", "qty": "0.06"},
            {"time": 3000, "positionSide": "SHORT", "side": "BUY", "qty": "0.18"},
            {"time": 4000, "positionSide": "SHORT", "side": "SELL", "qty": "0.10"},
            {"time": 5000, "positionSide": "SHORT", "side": "BUY", "qty": "0.10"},
        ]

        cycle = binance_monitor._select_exchange_fill_cycle("SELL", fills)

        self.assertTrue(cycle["complete"])
        self.assertEqual([fill["time"] for fill in cycle["fills"]], [1000, 2000, 3000])
        self.assertEqual(cycle["terminal_time_ms"], 3000)

    def test_classifies_stale_short_math_as_dirty(self):
        trade_id = trade_db.log_trade(
            None,
            "XAUUSDT",
            "SELL",
            entry_price=4523.96,
            qty=10.035,
            risk_dollars=165.10,
        )
        trade_db.log_exit(
            trade_id,
            "milestone_0",
            price=4515.71,
            pnl_contribution=20.24492971344,
            qty_pct=0.25,
        )
        with trade_db._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_price = ?, pnl = ?, execution_state = ?
                WHERE id = ?
                """,
                (4528.7601, 135.55415917344, "closed", trade_id),
            )
            conn.commit()

        result = trade_db.classify_trade_accounting(trade_id)

        self.assertEqual(result["status"], "dirty")
        self.assertLess(result["reconstructed_pnl"], 0)
        with trade_db._connect() as conn:
            row = conn.execute("SELECT accounting_status FROM trades WHERE id = ?", (trade_id,)).fetchone()
        self.assertEqual(row["accounting_status"], "dirty")

    def test_corrected_rows_are_allowed_in_recent_stats_but_dirty_rows_are_excluded(self):
        dirty_id = trade_db.log_trade(
            None,
            "XAUUSDT",
            "SELL",
            entry_price=4523.96,
            qty=10.035,
            strategy="momentum",
            setup_grade="A",
            risk_dollars=100.0,
        )
        with trade_db._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_price = ?, pnl = ?, r_multiple = ?, execution_state = ?
                WHERE id = ?
                """,
                (4528.7601, 135.55, 1.35, "closed", dirty_id),
            )
            conn.commit()
        trade_db.classify_trade_accounting(dirty_id)

        corrected_id = trade_db.log_trade(
            None,
            "XAUUSDT",
            "SELL",
            entry_price=4495.16,
            qty=8.079,
            strategy="momentum",
            setup_grade="A",
            risk_dollars=143.48,
        )
        trade_db.close_trade(
            corrected_id,
            exit_price=4479.39999,
            pnl=127.33544079000025,
            exit_reason="opposite",
            accounting_status="corrected",
            accounting_notes="unit-test correction evidence",
        )

        stats = trade_db.get_recent_closed_trade_stats(symbol="XAUUSDT", strategy="momentum", setup_grade="A")

        self.assertEqual(stats["sample_size"], 1)
        self.assertAlmostEqual(stats["total_pnl"], 127.33544079000025)

    def test_fail_closed_rows_are_excluded_from_default_recent_stats(self):
        trade_id = trade_db.log_trade(
            None,
            "ETHUSDT",
            "BUY",
            entry_price=100.0,
            qty=1.0,
            strategy="momentum",
            setup_grade="A",
            risk_dollars=10.0,
        )
        trade_db.close_trade(trade_id, exit_price=100.0, pnl=0.0, exit_reason="execution_failed")

        stats = trade_db.get_recent_closed_trade_stats(symbol="ETHUSDT", strategy="momentum", setup_grade="A")

        self.assertEqual(stats["sample_size"], 0)


if __name__ == "__main__":
    unittest.main()
