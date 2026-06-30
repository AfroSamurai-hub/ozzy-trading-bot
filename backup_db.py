#!/usr/bin/env python3
"""
HERMES — Daily SQLite backup.

Usage (cron):
    0 0 * * * cd /home/rick/ozzy-bot && ./venv/bin/python backup_db.py
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("trades.db")
BACKUP_DIR = Path(__file__).with_name("backups")


def main() -> int:
    if not DB_PATH.exists():
        print(f"No DB found at {DB_PATH}")
        return 1

    BACKUP_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / f"trades_{today}.db"

    shutil.copy2(DB_PATH, backup_path)
    print(f"Backed up to {backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
