import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ozzybot_doctor import (
    CORE_UNITS,
    assess_openclaw_breakout_state,
    classify_binance_validation_output,
    classify_product_sync_health,
    default_status_url,
    summarize_lane_performance,
)


class OzzyBotDoctorWatchdogTests(unittest.TestCase):
    def test_openclaw_breakout_state_is_critical_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openclaw_breakout_state.json"
            path.write_text(json.dumps({"last_scan": "2026-06-01T00:00:00+00:00", "last_results": []}))
            old = time.time() - 3600
            os.utime(path, (old, old))

            result = assess_openclaw_breakout_state(path, max_age_seconds=600)

        self.assertEqual(result["status"], "CRITICAL")
        self.assertIn("stale", result["reason"])

    def test_product_sync_health_critical_on_orphan_or_missing_protection(self):
        status = {
            "product_sync_health": {
                "protection_truth": {"healthy": False, "critical_mismatches": 1},
                "operator_action_required": ["ORPHAN_EXCHANGE_POSITION"],
            }
        }

        result = classify_product_sync_health(status)

        self.assertEqual(result["status"], "CRITICAL")
        self.assertTrue(result["pause_entries_recommended"])

    def test_product_sync_health_degraded_on_reconciliation_timeout_without_mismatch(self):
        status = {
            "product_sync_health": {
                "status": "degraded",
                "issues": ["exchange_reconciliation_unavailable"],
                "protection_truth": {
                    "healthy": None,
                    "critical_mismatches": 0,
                    "data_unavailable": True,
                    "reconciliation_refresh_error": "Binance API timeout",
                },
                "operator_action_required": [],
            },
            "reconciliation": {
                "data_unavailable": True,
                "reconciliation_refresh_error": "Binance API timeout",
            },
        }

        result = classify_product_sync_health(status)

        self.assertEqual(result["status"], "DEGRADED")
        self.assertFalse(result["pause_entries_recommended"])

    def test_binance_validation_timeout_is_degraded_not_critical(self):
        result = classify_binance_validation_output("ERROR|0|USDT|Binance API timeout")

        self.assertEqual(result["status"], "DEGRADED")

    def test_binance_validation_auth_failure_remains_critical(self):
        result = classify_binance_validation_output("FAIL|0|USDT|invalid api key")

        self.assertEqual(result["status"], "CRITICAL")

    def test_default_status_url_targets_live_micro(self):
        self.assertEqual(default_status_url(), "http://127.0.0.1:5001/status")

    def test_core_runtime_units_are_required(self):
        required_by_unit = {unit: required for unit, _desc, required in CORE_UNITS}

        self.assertTrue(required_by_unit["ozzybot-webhook.service"])
        self.assertTrue(required_by_unit["ozzybot-monitor.service"])
        self.assertTrue(required_by_unit["ozzybot-telegram-cmd.service"])

    def test_lane_performance_groups_june_trades_by_strategy_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "trades.db"
            conn = sqlite3.connect(db)
            conn.execute(
                """
                CREATE TABLE trades (
                    ts TEXT,
                    strategy_label TEXT,
                    entry_setup_label TEXT,
                    exit_price REAL,
                    exit_reason TEXT,
                    pnl REAL,
                    r_multiple REAL
                )
                """
            )
            conn.executemany(
                "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("2026-06-10 01:00:00", "BREAKOUT_RETEST", "OPENCLAW_BREAKOUT", 1.0, "tp", 50.0, 2.5),
                    ("2026-06-10 02:00:00", "BREAKOUT_RETEST", "OPENCLAW_BREAKOUT", 1.0, "sl", -20.0, -1.0),
                    ("2026-06-10 03:00:00", "1H_TREND_CONTINUATION", "MOMENTUM_B", 1.0, "sl", -10.0, -1.0),
                    ("2026-05-10 03:00:00", "OLD", "OLD", 1.0, "tp", 999.0, 9.0),
                ],
            )
            conn.commit(); conn.close()

            rows = summarize_lane_performance(db, since="2026-06-01")
            archived_rows = summarize_lane_performance(db, since="2026-06-01", include_archived=True)

        by_label = {row["strategy_label"]: row for row in rows}
        archived_by_label = {row["strategy_label"]: row for row in archived_rows}
        self.assertEqual(by_label["BREAKOUT_RETEST"]["trades"], 2)
        self.assertEqual(by_label["BREAKOUT_RETEST"]["wins"], 1)
        self.assertEqual(by_label["BREAKOUT_RETEST"]["sum_r"], 1.5)
        self.assertNotIn("1H_TREND_CONTINUATION", by_label)
        self.assertEqual(archived_by_label["1H_TREND_CONTINUATION"]["trades"], 1)
        self.assertNotIn("OLD", by_label)


if __name__ == "__main__":
    unittest.main()
