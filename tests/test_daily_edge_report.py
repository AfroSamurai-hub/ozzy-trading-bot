import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts import report_daily_edge


class DailyEdgeReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "trades.db"
        self._create_db()

    def tearDown(self):
        self.tmp.cleanup()

    def _create_db(self):
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL,
                source TEXT,
                timeframe TEXT,
                lane TEXT,
                strategy_label TEXT,
                entry_setup_label TEXT
            );
            CREATE TABLE trade_gates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                trade_id INTEGER,
                ts TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                filter_json TEXT,
                lane TEXT,
                mode TEXT
            );
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                pnl REAL,
                gross_pnl REAL,
                exit_reason TEXT,
                strategy TEXT,
                timeframe TEXT,
                r_multiple REAL,
                duration_min INTEGER,
                risk_dollars REAL,
                peak_pnl REAL,
                strategy_label TEXT,
                lane TEXT,
                execution_state TEXT DEFAULT 'closed',
                mode TEXT DEFAULT 'testnet'
            );
            """
        )
        rows = [
            ("2026-06-23T08:00:00+00:00", "BTCUSDT", "SELL", "signal_generator", "1h", "1H_TREND"),
            ("2026-06-23T09:00:00+00:00", "XAUUSDT", "SELL", "signal_generator", "1h", "1H_TREND"),
            ("2026-06-23T10:00:00+00:00", "SOLUSDT", "SELL", "signal_generator", "1h", "1H_TREND"),
            ("2026-06-23T11:00:00+00:00", "LINKUSDT", "BUY", "15m_reversion", "15m", "15M_MEAN_REVERSION"),
        ]
        conn.executemany(
            """
            INSERT INTO signals (ts, symbol, direction, source, timeframe, lane)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.executemany(
            """
            INSERT INTO trade_gates (signal_id, ts, gate_name, decision, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, "2026-06-23T08:00:01+00:00", "final_approval", "passed", None),
                (2, "2026-06-23T09:00:01+00:00", "local_regime_filter_adx_low", "rejected", "ADX 17 < 25"),
                (3, "2026-06-23T10:00:01+00:00", "max_positions", "rejected", "Max concurrent positions"),
                (4, "2026-06-23T11:00:01+00:00", "max_positions", "rejected", "Max concurrent positions"),
                (4, "2026-06-23T11:01:01+00:00", "max_positions", "rejected", "Max concurrent positions"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO trades (
                signal_id, ts, symbol, direction, exit_price, pnl, exit_reason,
                strategy, timeframe, r_multiple, duration_min, risk_dollars, peak_pnl,
                strategy_label, lane
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "2026-06-23T08:00:02+00:00",
                    "BTCUSDT",
                    "SELL",
                    100.0,
                    -10.0,
                    "sl",
                    "momentum",
                    "1h",
                    -0.5,
                    60,
                    20.0,
                    0.0,
                    "1H_TREND_CONTINUATION",
                    "1H_TREND",
                )
            ],
        )
        conn.commit()
        conn.close()

    def test_report_surfaces_throughput_and_quality_bottlenecks(self):
        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(report["summary"]["signals"], 4)
        self.assertEqual(report["summary"]["trades_opened"], 1)
        self.assertEqual(report["gates"]["rejected_count"], 4)
        self.assertEqual(report["gates"]["top_rejected_gates"][0]["gate_name"], "max_positions")
        self.assertEqual(report["position_pressure"]["state"], "historical_cap_pressure")
        self.assertEqual(report["position_pressure"]["max_position_blocks"], 3)
        self.assertEqual(report["cap_occupancy"]["max_position_blocks"], 3)
        blocked = {item["symbol"]: item["blocked_count"] for item in report["cap_occupancy"]["blocked_symbols"]}
        self.assertEqual(blocked["LINKUSDT"], 2)
        self.assertEqual(blocked["SOLUSDT"], 1)
        self.assertEqual(len(report["trade_quality"]["no_peak_losers"]), 1)
        findings = {item["finding"] for item in report["recommendations"]}
        self.assertIn("max_positions was a historical bottleneck", findings)
        self.assertIn("Some losers never went green", findings)

    def test_report_marks_cap_currently_full_when_open_positions_reach_cap(self):
        conn = sqlite3.connect(self.db)
        conn.executemany(
            """
            INSERT INTO trades (
                signal_id, ts, symbol, direction, exit_price, pnl, exit_reason,
                strategy, timeframe, r_multiple, risk_dollars, peak_pnl,
                strategy_label, lane
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (2, "2026-06-23T09:00:02+00:00", "XAUUSDT", "SELL", None, None, None, "momentum", "1h", None, 10.0, 5.0, "1H_TREND", "1H_TREND"),
                (3, "2026-06-23T10:00:02+00:00", "SOLUSDT", "SELL", None, None, None, "momentum", "1h", None, 10.0, 2.0, "1H_TREND", "1H_TREND"),
                (4, "2026-06-23T11:00:02+00:00", "LINKUSDT", "BUY", None, None, None, "mean_reversion", "15m", None, 10.0, 0.0, "15M_MR", "15M_MEAN_REVERSION"),
            ],
        )
        conn.commit()
        conn.close()

        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(report["position_pressure"]["state"], "currently_at_cap")
        self.assertEqual(report["position_pressure"]["open_positions"], 3)
        self.assertEqual(report["position_pressure"]["cap_utilization_pct"], 100.0)
        self.assertEqual(report["cap_occupancy"]["top_occupiers"][0]["blocked_count"], 3)
        self.assertIn("pnl", report["cap_occupancy"]["top_occupiers"][0])
        self.assertIn("duration_min", report["cap_occupancy"]["top_occupiers"][0])
        findings = {item["finding"] for item in report["recommendations"]}
        self.assertIn("position cap is currently full", findings)

    def test_markdown_contains_actionable_sections(self):
        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )
        markdown = report_daily_edge.render_markdown(report)

        self.assertIn("OzzyBot Daily Edge Report", markdown)
        self.assertIn("Top Rejection Gates", markdown)
        self.assertIn("Trade Quality Flags", markdown)
        self.assertIn("Position Pressure", markdown)
        self.assertIn("Cap Occupancy Attribution", markdown)
        self.assertIn("Recommendations", markdown)
        self.assertIn("Scope: unified system view across STANDARD_TESTNET and LIVE_MICRO", markdown)

    def test_report_exposes_data_sources(self):
        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[self.root / "trades.log", self.root / "live_micro" / "trades_live.log"],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(report["sources"]["database"], str(self.db))
        self.assertEqual(report["sources"]["scope"], "unified system view across STANDARD_TESTNET and LIVE_MICRO")
        self.assertEqual(report["sources"]["logs"], [str(self.root / "trades.log"), str(self.root / "live_micro" / "trades_live.log")])

    def test_report_keeps_shadow_closed_pnl_out_of_executed_summary(self):
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            INSERT INTO trades (
                ts, symbol, direction, exit_price, pnl, exit_reason,
                r_multiple, execution_state, mode, lane
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-23T09:30:00+00:00",
                "ETHUSDT",
                "SELL",
                2100.0,
                -100.0,
                "sl",
                -1.0,
                "shadow_closed",
                "paper",
                "1H_TREND",
            ),
        )
        conn.commit()
        conn.close()

        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(report["summary"]["closed"], 1)
        self.assertEqual(report["summary"]["total_pnl"], -10.0)
        self.assertEqual(report["shadow_summary"]["closed"], 1)
        self.assertEqual(report["shadow_summary"]["total_pnl"], -100.0)

    def test_report_window_accepts_sqlite_space_timestamp_format(self):
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            INSERT INTO trades (ts, symbol, direction, exit_price, pnl, execution_state, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-22 13:00:00", "ETHUSDT", "SELL", 2000.0, 5.0, "closed", "testnet"),
        )
        conn.commit()
        conn.close()

        report = report_daily_edge.build_report(
            db_path=self.db,
            log_paths=[],
            hours=24,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(report["summary"]["closed"], 2)
        self.assertEqual(report["summary"]["total_pnl"], -5.0)


if __name__ == "__main__":
    unittest.main()
