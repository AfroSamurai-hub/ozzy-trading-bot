import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import backup_runtime_dbs


class RuntimeDbBackupTests(unittest.TestCase):
    def test_backup_runtime_dbs_uses_dated_timestamped_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot_dir = Path(tmp)
            trade_db = bot_dir / "trades.db"
            live_db = bot_dir / "live_micro" / "trades_live.db"
            memory_db = bot_dir / "ozzy_memory.db"
            live_db.parent.mkdir()
            for path in (trade_db, live_db, memory_db):
                path.write_text(path.name)

            with (
                patch.object(backup_runtime_dbs, "BOT_DIR", bot_dir),
                patch.object(backup_runtime_dbs, "DBS", (trade_db, live_db, memory_db)),
            ):
                copied = backup_runtime_dbs.backup_runtime_dbs(datetime(2026, 5, 21, 19, 5, 6, tzinfo=UTC))

            self.assertEqual(len(copied), 3)
            self.assertTrue(all(path.parent == bot_dir / "backups" / "2026-05-21" for path in copied))
            self.assertEqual({path.name for path in copied}, {
                "trades_190506.db",
                "trades_live_190506.db",
                "ozzy_memory_190506.db",
            })


if __name__ == "__main__":
    unittest.main()
