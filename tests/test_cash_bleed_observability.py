import csv
import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import export_obsidian_journal
from scripts import report_orphan_reconciliation
from scripts.report_cash_bleed import build_report, write_outputs
import status_summary
from product_lifecycle import classify_lifecycle_items
from status_summary import build_danger_board


def _init_trade_db(path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                ts TEXT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                pnl REAL,
                gross_pnl REAL,
                fees REAL DEFAULT 0,
                funding REAL DEFAULT 0,
                exit_reason TEXT,
                regime TEXT,
                strategy TEXT,
                timeframe TEXT,
                r_multiple REAL,
                duration_min INTEGER,
                mode TEXT,
                setup_grade TEXT,
                risk_dollars REAL,
                reward_dollars REAL,
                rr REAL,
                sl REAL,
                tp REAL,
                atr REAL,
                volume_ratio REAL,
                context_json TEXT,
                source TEXT,
                strategy_label TEXT,
                entry_setup_label TEXT,
                regime_label TEXT,
                source_service TEXT,
                webhook_port INTEGER,
                execution_mode TEXT,
                execution_state TEXT DEFAULT 'confirmed',
                accounting_status TEXT DEFAULT 'clean',
                accounting_notes TEXT,
                accounting_checked_at TEXT,
                peak_pnl REAL DEFAULT 0,
                peak_price REAL
            )
            """
        )
        for row in rows:
            columns = list(row)
            placeholders = ",".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO trades ({','.join(columns)}) VALUES ({placeholders})",
                [row[column] for column in columns],
            )
        conn.commit()
    finally:
        conn.close()


class CashBleedObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.testnet_db = self.root / "trades.db"
        self.live_db = self.root / "trades_live.db"
        self.observer = self.root / "observer"
        self.observer.mkdir()
        base = {
            "ts": (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "direction": "BUY",
            "entry_price": 100.0,
            "exit_price": 99.0,
            "qty": 1.0,
            "mode": "testnet",
            "risk_dollars": 100.0,
            "strategy_label": "1H_TREND_CONTINUATION",
            "strategy": "momentum",
            "timeframe": "60",
            "setup_grade": "A",
            "duration_min": 60,
            "execution_state": "confirmed",
        }
        _init_trade_db(
            self.testnet_db,
            [
                {
                    **base,
                    "id": 1,
                    "symbol": "HYPEUSDT",
                    "pnl": -50.0,
                    "gross_pnl": -49.0,
                    "exit_reason": "momentum_exit",
                    "peak_pnl": 40.0,
                },
                {
                    **base,
                    "id": 2,
                    "symbol": "ETHUSDT",
                    "pnl": 120.0,
                    "gross_pnl": 121.0,
                    "exit_reason": "trail",
                    "peak_pnl": 150.0,
                },
                {
                    **base,
                    "id": 3,
                    "symbol": "LINKUSDT",
                    "pnl": -20.0,
                    "gross_pnl": -20.0,
                    "exit_reason": "sl",
                    "setup_grade": "B",
                    "peak_pnl": 0.0,
                },
            ],
        )
        _init_trade_db(self.live_db, [])
        (self.observer / "loss_minimization_candidates.json").write_text(
            json.dumps(
                [
                    {
                        "trade_id": 1,
                        "id": "candidate-1",
                        "status": "RESOLVED",
                        "created_at": "2026-06-01T12:15:00+00:00",
                    }
                ]
            )
        )
        (self.observer / "action_queue.json").write_text("[]")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cash_bleed_report_writes_markdown_and_csv(self):
        report = build_report(testnet_db=self.testnet_db, live_db=self.live_db, observer_dir=self.observer)
        md_path, csv_path = write_outputs(report, self.root / "reports")

        self.assertTrue(md_path.exists())
        self.assertTrue(csv_path.exists())
        self.assertIn("MOMENTUM_EXIT Losses", md_path.read_text())
        with csv_path.open() as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(any(row["table"] == "pnl_by_exit_reason" for row in rows))

    def test_momentum_exit_appears_as_negative_bucket(self):
        report = build_report(testnet_db=self.testnet_db, live_db=self.live_db, observer_dir=self.observer)
        section = next(
            section
            for dataset in report["datasets"]
            for section in dataset["sections"]
            if any(row["bucket"] == "momentum_exit" for row in section["pnl_by_exit_reason"])
        )
        bucket = next(row for row in section["pnl_by_exit_reason"] if row["bucket"] == "momentum_exit")
        self.assertLess(bucket["pnl"], 0)
        self.assertEqual(section["momentum_exit_losses"][0]["symbol"], "HYPEUSDT")

    def test_cash_bleed_report_splits_rows_by_mode_and_ignores_paper(self):
        mixed_db = self.root / "mixed.db"
        recent = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        _init_trade_db(
            mixed_db,
            [
                {
                    "id": 1,
                    "ts": recent,
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "entry_price": 100.0,
                    "exit_price": 99.0,
                    "qty": 1.0,
                    "pnl": -1.0,
                    "gross_pnl": -1.0,
                    "exit_reason": "sl",
                    "mode": "testnet",
                    "strategy_label": "1H_TREND_CONTINUATION",
                    "execution_state": "closed",
                    "peak_pnl": 10.0,
                },
                {
                    "id": 2,
                    "ts": recent,
                    "symbol": "ETHUSDT",
                    "direction": "SELL",
                    "entry_price": 2000.0,
                    "exit_price": 1980.0,
                    "qty": 1.0,
                    "pnl": 20.0,
                    "gross_pnl": 20.0,
                    "exit_reason": "tp",
                    "mode": "live_micro",
                    "strategy_label": "BREAKOUT_RETEST",
                    "execution_state": "closed",
                    "peak_pnl": 25.0,
                },
                {
                    "id": 3,
                    "ts": recent,
                    "symbol": "SOLUSDT",
                    "direction": "BUY",
                    "entry_price": 50.0,
                    "exit_price": 51.0,
                    "qty": 1.0,
                    "pnl": 1.0,
                    "gross_pnl": 1.0,
                    "exit_reason": "tp",
                    "mode": "paper",
                    "strategy_label": "PAPER_ONLY",
                    "execution_state": "closed",
                    "peak_pnl": 2.0,
                },
            ],
        )

        report = build_report(testnet_db=mixed_db, live_db=mixed_db, observer_dir=self.observer)
        dataset_counts = {dataset["mode"]: dataset["sections"][0]["closed_count"] for dataset in report["datasets"]}

        self.assertEqual(dataset_counts["STANDARD_TESTNET"], 1)
        self.assertEqual(dataset_counts["LIVE_MICRO"], 1)
        self.assertNotIn("PAPER_ONLY", json.dumps(report))

    def test_danger_board_limits_max_five_rows_and_live_alert_only(self):
        positions = [
            {"symbol": f"SYM{i}USDT", "type": "BUY", "openPrice": 100.0, "currentPrice": 96.0, "profit": -4.0}
            for i in range(7)
        ]
        trade_rows = {
            f"SYM{i}USDT": {
                "symbol": f"SYM{i}USDT",
                "direction": "BUY",
                "ts": "2026-06-01 12:00:00",
                "sl": 90.0,
                "risk_dollars": 10.0,
                "peak_pnl": 4.0,
                "strategy_label": "1H_TREND_CONTINUATION",
            }
            for i in range(7)
        }
        rows = build_danger_board(mode="LIVE", positions=positions, trade_rows=trade_rows, limit=5)

        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["live_behavior"] == "alert_only" for row in rows))
        self.assertTrue(all(row["action_label"] in {"HOLD", "PROTECT", "REDUCE_RISK", "EXIT_REQUIRED"} for row in rows))

    def test_grade_b_no_progress_near_threshold_does_not_show_plain_hold(self):
        rows = build_danger_board(
            mode="LIVE",
            positions=[{"symbol": "LINKUSDT", "type": "BUY", "openPrice": 100.0, "currentPrice": 96.8, "profit": -3.2}],
            trade_rows={
                "LINKUSDT": {
                    "symbol": "LINKUSDT",
                    "direction": "BUY",
                    "ts": "2026-06-01 12:00:00",
                    "sl": 90.0,
                    "risk_dollars": 10.0,
                    "peak_pnl": 1.0,
                    "setup_grade": "B",
                    "strategy_label": "1H_TREND_CONTINUATION",
                }
            },
            limit=5,
        )

        self.assertEqual(rows[0]["failure_label"], "GRADE_B_NO_PROGRESS")
        self.assertIn(rows[0]["action_label"], {"PROTECT", "REDUCE_RISK"})
        self.assertEqual(rows[0]["live_behavior"], "alert_only")

    def test_testnet_grade_b_no_progress_breached_threshold_exit_required(self):
        rows = build_danger_board(
            mode="TESTNET",
            positions=[{"symbol": "LINKUSDT", "type": "BUY", "openPrice": 100.0, "currentPrice": 96.0, "profit": -4.0}],
            trade_rows={
                "LINKUSDT": {
                    "symbol": "LINKUSDT",
                    "direction": "BUY",
                    "ts": "2026-06-01 12:00:00",
                    "sl": 90.0,
                    "risk_dollars": 10.0,
                    "peak_pnl": 1.0,
                    "setup_grade": "B",
                    "strategy_label": "1H_TREND_CONTINUATION",
                }
            },
            limit=5,
        )

        self.assertEqual(rows[0]["failure_label"], "GRADE_B_NO_PROGRESS")
        self.assertEqual(rows[0]["action_label"], "EXIT_REQUIRED")

    def test_protection_risk_requires_reconcile_not_hold(self):
        rows = build_danger_board(
            mode="TESTNET",
            positions=[{"symbol": "BNBUSDT", "type": "SELL", "openPrice": 590.0, "currentPrice": 570.0, "profit": 80.0}],
            trade_rows={},
            reconciliation={"healthy": False, "critical_mismatches": [{"symbol": "BNBUSDT"}]},
            limit=5,
        )

        self.assertEqual(rows[0]["failure_label"], "PROTECTION_RISK")
        self.assertEqual(rows[0]["action_label"], "RECONCILE_REQUIRED")

    def test_recent_auto_protect_actions_filters_by_mode(self):
        observer_dir = self.root / "observer"
        observer_dir.mkdir(exist_ok=True)
        (observer_dir / "auto_protect_actions.json").write_text(
            json.dumps(
                [
                    {"action_id": "live-1", "mode": "LIVE", "created_at": "2026-06-01T12:00:00+00:00"},
                    {"action_id": "testnet-1", "mode": "TESTNET", "created_at": "2026-06-01T13:00:00+00:00"},
                ]
            )
        )
        with patch.object(status_summary, "ROOT", self.root):
            rows = status_summary.recent_auto_protect_actions(mode="TESTNET")

        self.assertEqual([row["action_id"] for row in rows], ["testnet-1"])

    def test_recent_auto_protect_actions_normalizes_unified_mode_synonyms(self):
        observer_dir = self.root / "observer"
        observer_dir.mkdir(exist_ok=True)
        (observer_dir / "auto_protect_actions.json").write_text(
            json.dumps(
                [
                    {"action_id": "live-micro-1", "mode": "LIVE_MICRO", "created_at": "2026-06-01T12:00:00+00:00"},
                    {"action_id": "standard-testnet-1", "mode": "STANDARD_TESTNET", "created_at": "2026-06-01T13:00:00+00:00"},
                ]
            )
        )
        with patch.object(status_summary, "ROOT", self.root):
            live_rows = status_summary.recent_auto_protect_actions(mode="LIVE")
            testnet_rows = status_summary.recent_auto_protect_actions(mode="TESTNET")

        self.assertEqual([row["action_id"] for row in live_rows], ["live-micro-1"])
        self.assertEqual([row["action_id"] for row in testnet_rows], ["standard-testnet-1"])

    def test_lifecycle_classifier_identifies_orphan_and_db_ghost(self):
        rows = classify_lifecycle_items(
            mode="TESTNET",
            positions=[{"symbol": "BNBUSDT", "type": "SELL", "volume": 4.04}],
            trade_rows={"SOLUSDT": {"id": 100075, "symbol": "SOLUSDT", "direction": "BUY", "qty": 53.4}},
            reconciliation={"healthy": False},
        )
        by_symbol = {row["symbol"]: row for row in rows}

        self.assertEqual(by_symbol["BNBUSDT"]["state"], "ORPHAN_EXCHANGE_POSITION")
        self.assertFalse(by_symbol["BNBUSDT"]["monitor_action_allowed"])
        self.assertEqual(by_symbol["SOLUSDT"]["state"], "DB_GHOST_TRADE")

    def test_product_sync_health_exposes_operator_action_required(self):
        health = status_summary.build_product_sync_health(
            binance_testnet=True,
            positions=[{"symbol": "BNBUSDT", "type": "SELL", "volume": 4.04}],
            trade_rows={},
            reconciliation={"healthy": False},
            no_new_entries_flag=False,
        )

        self.assertEqual(health["status"], "attention_required")
        self.assertEqual(health["operator_action_required"][0]["state"], "ORPHAN_EXCHANGE_POSITION")

    def test_context_observer_writes_product_state_with_orphans(self):
        import ozzy_context_observer

        (self.observer / "orphan_positions.json").write_text(
            json.dumps([{"symbol": "BNBUSDT", "side": "SHORT", "qty": 4.04}])
        )
        (self.observer / "loss_minimization_candidates.json").write_text("[]")
        with (
            patch.object(ozzy_context_observer, "OBSERVER_DIR", str(self.observer)),
            patch.object(ozzy_context_observer, "_refresh_orphan_positions", return_value=None),
        ):
            ozzy_context_observer.manage_persistent_files([], [])

        product_state = json.loads((self.observer / "product_state_context.json").read_text())
        self.assertEqual(product_state["orphan_position_count"], 1)
        self.assertEqual(product_state["operator_action_required"][0]["state"], "ORPHAN_EXCHANGE_POSITION")

    def test_orphan_reconciliation_report_is_read_only_and_blocks_management(self):
        (self.observer / "orphan_positions.json").write_text(
            json.dumps([{"symbol": "BNBUSDT", "side": "SHORT", "qty": 4.04, "entry_price": 646.2}])
        )
        report = report_orphan_reconciliation.build_report(
            testnet_db=self.testnet_db,
            live_db=self.live_db,
            observer_dir=self.observer,
        )
        md_path, csv_path = report_orphan_reconciliation.write_outputs(report, self.root / "reports")

        self.assertTrue(md_path.exists())
        self.assertTrue(csv_path.exists())
        self.assertEqual(report["rows"][0]["symbol"], "BNBUSDT")
        self.assertFalse(report["rows"][0]["management_allowed"])
        self.assertIn(report["rows"][0]["recommendation"], {"UNKNOWN_NEEDS_REVIEW", "MANUAL_CLOSE_RECOMMENDED"})

    def test_obsidian_export_writes_matching_cash_bleed_report(self):
        obsidian_root = self.root / "OzzyBot_Obsidian"
        obsidian_root.mkdir()
        report_dir = self.root / "reports"
        with (
            patch.object(export_obsidian_journal, "build_report") as build,
            patch.object(export_obsidian_journal, "render_markdown", wraps=export_obsidian_journal.render_markdown),
        ):
            report = build_report(testnet_db=self.testnet_db, live_db=self.live_db, observer_dir=self.observer)
            build.return_value = report
            note_path = export_obsidian_journal.export_cash_bleed_snapshot(obsidian_root, report_dir)

        self.assertTrue(note_path.exists())
        self.assertTrue((report_dir / f"cash_bleed_report_{report['date'].replace('-', '')}.md").exists())
        self.assertTrue((report_dir / f"cash_bleed_report_{report['date'].replace('-', '')}.csv").exists())

    def test_obsidian_exporter_noops_if_path_missing(self):
        missing_preferred = self.root / "missing-preferred"
        missing_fallback = self.root / "missing-fallback"
        with patch.object(export_obsidian_journal, "plain_log") as log:
            root = export_obsidian_journal.resolve_export_root(missing_preferred, missing_fallback)

        self.assertIsNone(root)
        log.assert_called_once()
        self.assertEqual(log.call_args.args[0], "OBSIDIAN_EXPORT_SKIPPED")

    def test_obsidian_exporter_noops_when_disabled(self):
        existing = self.root / "existing"
        existing.mkdir()
        with patch.dict("os.environ", {"HERMES_OBSIDIAN_EXPORT_DISABLED": "true"}), patch.object(
            export_obsidian_journal, "plain_log"
        ) as log:
            root = export_obsidian_journal.resolve_export_root(existing, existing)

        self.assertIsNone(root)
        self.assertEqual(log.call_args.args[0], "OBSIDIAN_EXPORT_SKIPPED")

    def test_observability_modules_do_not_import_order_connector(self):
        import scripts.report_cash_bleed as report_cash_bleed

        self.assertFalse(hasattr(report_cash_bleed, "binance_connector"))
        self.assertFalse(hasattr(export_obsidian_journal, "binance_connector"))


if __name__ == "__main__":
    unittest.main()
