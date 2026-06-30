import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import ozzy_memory


class OzzyMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ozzy_memory.db"
        self.path_patch = patch.object(ozzy_memory, "DB_PATH", self.db_path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tempdir.cleanup()

    def test_schema_is_idempotent_and_pragmas_are_enabled(self):
        ozzy_memory.ensure_schema()
        ozzy_memory.ensure_schema()

        with closing(sqlite3.connect(self.db_path)) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            migration_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        with ozzy_memory._connect() as conn:
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(migration_count, 1)

    def test_setup_event_insert_is_duplicate_safe_and_keeps_mode(self):
        for _ in range(2):
            ozzy_memory.record_setup_event(
                event_id="event-1",
                symbol="ETHUSDT",
                direction="SELL",
                decision="approved",
                process_mode="LIVE_MICRO",
                indicators={"volume": 1.2},
            )

        with ozzy_memory._connect() as conn:
            rows = conn.execute("SELECT instance_mode, decision FROM setup_events").fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["instance_mode"], "LIVE_MICRO")
        self.assertEqual(rows[0]["decision"], "approved")

    def test_r_outcome_preserves_good_entry_after_opposite_like_reversal(self):
        outcome = ozzy_memory.compute_r_outcome(
            "BUY",
            entry=100.0,
            sl=90.0,
            tp=125.0,
            candles=[
                {"high": 112.0, "low": 99.0, "close": 111.0},
                {"high": 111.0, "low": 98.0, "close": 99.0},
            ],
        )

        self.assertEqual(outcome["hit_1r"], 1)
        self.assertEqual(outcome["entry_quality"], "good")
        self.assertEqual(outcome["exit_quality"], "needs_review")
        self.assertEqual(outcome["reversed"], 1)

    def test_r_outcome_missing_stop_anchor_does_not_fabricate_r(self):
        outcome = ozzy_memory.compute_r_outcome(
            "SELL",
            entry=100.0,
            sl=100.0,
            tp=90.0,
            candles=[{"high": 101.0, "low": 97.0, "close": 98.0}],
        )

        self.assertIsNone(outcome)

    def test_memory_verdict_is_advisory_even_for_weak_or_safety_lanes(self):
        reduced = ozzy_memory.record_memory_verdict(
            symbol="LINKUSDT",
            direction="SELL",
            grade="B",
            sample_count=6,
            avg_mfe_r=0.7,
            avg_mae_r=-0.4,
            avg_final_r=-0.2,
        )
        safety = ozzy_memory.record_memory_verdict(
            symbol="ETHUSDT",
            direction="SELL",
            grade="A",
            sample_count=1,
            avg_mfe_r=None,
            avg_mae_r=None,
            avg_final_r=None,
            safety_issue=True,
        )

        self.assertEqual(reduced["verdict"], "allow_reduced")
        self.assertEqual(safety["verdict"], "watch")

    def test_trade_journal_is_append_only(self):
        first = ozzy_memory.record_trade_journal_event(event_type="trade_opened", trade_id=7, symbol="ETHUSDT")
        second = ozzy_memory.record_trade_journal_event(event_type="trade_closed", trade_id=7, symbol="ETHUSDT")

        with ozzy_memory._connect() as conn:
            rows = conn.execute(
                "SELECT journal_event_id, event_type FROM trade_journal_events WHERE trade_id = '7' ORDER BY created_at"
            ).fetchall()

        self.assertEqual({first, second}, {row["journal_event_id"] for row in rows})
        self.assertEqual([row["event_type"] for row in rows], ["trade_opened", "trade_closed"])


if __name__ == "__main__":
    unittest.main()
