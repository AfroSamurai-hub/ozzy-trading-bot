#!/usr/bin/env python3
"""Copy runtime SQLite databases into a dated non-overwriting backup folder."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
DBS = (
    BOT_DIR / "trades.db",
    BOT_DIR / "ozzy_memory.db",
)


def backup_runtime_dbs(now: datetime | None = None) -> list[Path]:
    """Back up existing runtime DBs and return copied paths."""
    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    target_dir = BOT_DIR / "backups" / stamp.strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for db_path in DBS:
        if not db_path.exists():
            continue
        dest = target_dir / f"{db_path.stem}_{stamp.strftime('%H%M%S')}{db_path.suffix}"
        if dest.exists():
            raise FileExistsError(f"backup already exists: {dest}")
        shutil.copy2(db_path, dest)
        copied.append(dest)
    return copied


def main() -> int:
    """Run the focused runtime DB backup command."""
    copied = backup_runtime_dbs()
    if not copied:
        print("No runtime DBs found to back up.")
        return 0
    print("Runtime DB backups:")
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
