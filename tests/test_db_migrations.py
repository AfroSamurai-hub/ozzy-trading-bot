import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trade_db


class TestDBMigrations(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.journal_patch = patch.object(trade_db, "_journal_event")
        self.db_patch.start()
        self.journal_patch.start()

    def tearDown(self):
        self.journal_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def _get_columns(self, conn, table):
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

    def test_columns_added_on_fresh_database(self):
        with trade_db._connect() as conn:
            for table in ("signals", "trades", "exits", "milestones"):
                cols = self._get_columns(conn, table)
                self.assertIn("lane", cols, f"{table} missing lane")
                self.assertIn("mode", cols, f"{table} missing mode")

    def test_system_events_table_created(self):
        with trade_db._connect() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            self.assertIn("system_events", tables)

    def test_log_system_event_inserts_row(self):
        trade_db.log_system_event(
            event_type="test_event",
            payload={"foo": "bar"},
            source="test",
        )
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT event_type, payload, source FROM system_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "test_event")
        self.assertIn("bar", row[1])
        self.assertEqual(row[2], "test")

    def test_migration_is_idempotent(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(trade_db._INIT_SQL)
            trade_db.migrate_unified_columns(conn)
            trade_db.create_system_events_table(conn)
            conn.commit()
            # Second run must not raise
            trade_db.migrate_unified_columns(conn)
            trade_db.create_system_events_table(conn)
            conn.commit()


if __name__ == "__main__":
    unittest.main()
