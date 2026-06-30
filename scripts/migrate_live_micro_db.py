#!/usr/bin/env python3
"""Migrate live_micro SQLite DB rows into the main trades DB.

Each migrated row is tagged with mode='live_micro' and lane='live_micro' so
historical live_micro records remain distinguishable after the two databases are
unified.

The script is idempotent: on a second run it deletes previously migrated
live_micro rows and re-inserts them, so running it twice does not duplicate data.

Usage:
    python scripts/migrate_live_micro_db.py
    python scripts/migrate_live_micro_db.py --dry-run
    python scripts/migrate_live_micro_db.py --src path/to/trades_live.db --dst path/to/trades.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

DEFAULT_SRC = Path(__file__).resolve().parent.parent / "live_micro" / "trades_live.db"
DEFAULT_DST = Path(__file__).resolve().parent.parent / "trades.db"

# Tables to migrate.  The canonical DB schema uses the singular
# ``binance_order_state``; the unified-core plan refers to it as
# ``binance_order_states``.
TABLES = [
    "signals",
    "trades",
    "trade_gates",
    "exits",
    "milestones",
    "live_bootstrap_events",
    "market_regime_log",
    "binance_order_state",
]

MODE_VALUE = "live_micro"
LANE_VALUE = "live_micro"


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    """Return True if ``table`` exists in the connected database."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Return True if ``column`` exists on ``table``."""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def get_columns(cursor: sqlite3.Cursor, table: str) -> list[str]:
    """Return column names for ``table``."""
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def ensure_columns(cursor: sqlite3.Cursor, table: str) -> None:
    """Add ``lane`` and ``mode`` columns to ``table`` if they are missing."""
    if not column_exists(cursor, table, "lane"):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN lane TEXT")
        print(f"  Added column lane to {table}")
    if not column_exists(cursor, table, "mode"):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN mode TEXT")
        print(f"  Added column mode to {table}")


def build_insert_cols(copy_cols: list[str]) -> list[str]:
    """Return column list for INSERT, ensuring mode and lane are present."""
    insert_cols = list(copy_cols)
    if "mode" not in insert_cols:
        insert_cols.append("mode")
    if "lane" not in insert_cols:
        insert_cols.append("lane")
    return insert_cols


def build_insert_values(
    src_row: tuple[Any, ...],
    copy_cols: list[str],
) -> list[Any]:
    """Build the value list for an INSERT, forcing mode/lane to live_micro.

    ``src_row`` contains the source values corresponding to ``copy_cols``
    (the id column is already stripped).
    """
    values = list(src_row)

    if "mode" in copy_cols:
        values[copy_cols.index("mode")] = MODE_VALUE
    else:
        values.append(MODE_VALUE)

    if "lane" in copy_cols:
        values[copy_cols.index("lane")] = LANE_VALUE
    else:
        values.append(LANE_VALUE)

    return values


def migrate_signals(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
) -> tuple[int, dict[int, int]]:
    """Migrate the ``signals`` table and return (count, {src_id: dst_id})."""
    table = "signals"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0, {}

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT id, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    id_map: dict[int, int] = {}
    inserted = 0
    for row in rows:
        src_id = row[0]
        values = build_insert_values(row[1:], copy_cols)
        dst_cur.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        id_map[src_id] = dst_cur.lastrowid
        inserted += 1

    print(
        f"  {table}: preserved existing rows, inserted {inserted} rows"
    )
    return inserted, id_map


def migrate_trades(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
    signal_id_map: dict[int, int],
) -> tuple[int, dict[int, int]]:
    """Migrate the ``trades`` table and return (count, {src_id: dst_id})."""
    table = "trades"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0, {}

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT id, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    id_map: dict[int, int] = {}
    inserted = 0
    reused = 0
    for row in rows:
        src_id = row[0]
        values = build_insert_values(row[1:], copy_cols)

        src_payload = dict(zip(copy_cols, row[1:]))
        existing_id = None
        match_cols = [c for c in ("symbol", "direction", "ts", "entry_price", "qty") if c in copy_cols]
        if match_cols:
            where = " AND ".join([f"{col} IS ?" for col in match_cols] + ["mode IS ?"])
            params = [src_payload.get(col) for col in match_cols] + [MODE_VALUE]
            existing = dst_cur.execute(f"SELECT id FROM {table} WHERE {where} LIMIT 1", params).fetchone()
            if existing:
                existing_id = int(existing[0])

        if "signal_id" in copy_cols:
            idx = copy_cols.index("signal_id")
            old_signal_id = values[idx]
            if old_signal_id is not None and old_signal_id in signal_id_map:
                values[idx] = signal_id_map[old_signal_id]
            else:
                values[idx] = None

        if existing_id is not None:
            id_map[src_id] = existing_id
            reused += 1
            continue

        dst_cur.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)
        id_map[src_id] = dst_cur.lastrowid
        inserted += 1

    print(
        f"  {table}: preserved existing rows, reused {reused}, inserted {inserted} rows"
    )
    return inserted, id_map


def migrate_child_table(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
    table: str,
    trade_id_map: dict[int, int],
) -> int:
    """Migrate a child table whose FK to ``trades`` is named ``trade_id``."""
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT id, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    inserted = 0
    reused = 0
    for row in rows:
        values = build_insert_values(row[1:], copy_cols)
        src_payload = dict(zip(copy_cols, row[1:]))

        if "trade_id" in copy_cols:
            idx = copy_cols.index("trade_id")
            old_trade_id = values[idx]
            if old_trade_id is not None and old_trade_id in trade_id_map:
                values[idx] = trade_id_map[old_trade_id]
            else:
                values[idx] = None

        match_cols = [c for c in ("trade_id", "ts", "exit_type", "milestone", "gate_name", "decision") if c in insert_cols]
        existing = None
        if match_cols:
            value_by_col = dict(zip(insert_cols, values))
            for col in copy_cols:
                if col not in value_by_col:
                    value_by_col[col] = src_payload.get(col)
            where = " AND ".join([f"{col} IS ?" for col in match_cols] + ["mode IS ?"])
            params = [value_by_col.get(col) for col in match_cols] + [MODE_VALUE]
            existing = dst_cur.execute(f"SELECT id FROM {table} WHERE {where} LIMIT 1", params).fetchone()
        if existing:
            reused += 1
            continue

        dst_cur.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        inserted += 1

    print(
        f"  {table}: preserved existing rows, reused {reused}, inserted {inserted} rows"
    )
    return inserted


def migrate_market_regime_log(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
) -> int:
    """Migrate the ``market_regime_log`` table."""
    table = "market_regime_log"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    for row in rows:
        values = build_insert_values(row, copy_cols)
        dst_cur.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )

    print(f"  {table}: preserved existing rows, inserted {len(rows)} rows")
    return len(rows)


def migrate_trade_gates(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
    signal_id_map: dict[int, int],
    trade_id_map: dict[int, int],
) -> int:
    """Migrate ``trade_gates`` while remapping signal_id and trade_id."""
    table = "trade_gates"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT id, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    inserted = 0
    reused = 0
    for row in rows:
        values = build_insert_values(row[1:], copy_cols)
        value_by_col = dict(zip(insert_cols, values))

        if "signal_id" in copy_cols:
            idx = copy_cols.index("signal_id")
            old_signal_id = values[idx]
            values[idx] = signal_id_map.get(old_signal_id) if old_signal_id is not None else None

        if "trade_id" in copy_cols:
            idx = copy_cols.index("trade_id")
            old_trade_id = values[idx]
            values[idx] = trade_id_map.get(old_trade_id) if old_trade_id is not None else None
        value_by_col = dict(zip(insert_cols, values))

        match_cols = [c for c in ("signal_id", "trade_id", "ts", "gate_name", "decision") if c in insert_cols]
        if match_cols:
            where = " AND ".join([f"{col} IS ?" for col in match_cols] + ["mode IS ?"])
            params = [value_by_col.get(col) for col in match_cols] + [MODE_VALUE]
            existing = dst_cur.execute(f"SELECT id FROM {table} WHERE {where} LIMIT 1", params).fetchone()
            if existing:
                reused += 1
                continue

        dst_cur.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        inserted += 1

    print(
        f"  {table}: preserved existing rows, reused {reused}, inserted {inserted} rows"
    )
    return inserted


def migrate_live_bootstrap_events(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
    trade_id_map: dict[int, int],
) -> int:
    """Migrate bootstrap events while remapping trade_id when present."""
    table = "live_bootstrap_events"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "id"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT id, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    inserted = 0
    for row in rows:
        values = build_insert_values(row[1:], copy_cols)

        if "trade_id" in copy_cols:
            idx = copy_cols.index("trade_id")
            old_trade_id = values[idx]
            values[idx] = trade_id_map.get(old_trade_id) if old_trade_id is not None else None

        try:
            dst_cur.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                values,
            )
            inserted += 1
        except sqlite3.IntegrityError:
            dst_cur.execute(
                f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                values,
            )
            inserted += 1

    print(
        f"  {table}: preserved existing rows, inserted/replaced {inserted} rows"
    )
    return inserted


def migrate_binance_order_state(
    src_cur: sqlite3.Cursor,
    dst_cur: sqlite3.Cursor,
) -> int:
    """Migrate ``binance_order_state`` by replacing matching symbols.

    The table is keyed by ``symbol``.  During final unification, the source
    live_micro DB is the active runtime state, so stale destination rows for the
    same symbols must be replaced rather than preserved.
    """
    table = "binance_order_state"
    if not table_exists(src_cur, table) or not table_exists(dst_cur, table):
        print(f"  Skipping {table}: missing in source or destination")
        return 0

    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    copy_cols = [c for c in src_cols if c in dst_cols and c != "symbol"]
    insert_cols = build_insert_cols(copy_cols)

    placeholders = ",".join(["?"] * len(insert_cols))
    col_names = ",".join(insert_cols)

    src_cur.execute(f"SELECT symbol, {','.join(copy_cols)} FROM {table}")
    rows = src_cur.fetchall()

    inserted = 0
    replaced = 0
    for row in rows:
        symbol = row[0]
        values = build_insert_values(row[1:], copy_cols)
        dst_cur.execute(f"DELETE FROM {table} WHERE symbol = ?", (symbol,))
        replaced += dst_cur.rowcount
        dst_cur.execute(
            f"INSERT INTO {table} (symbol,{col_names}) "
            f"VALUES (?,{placeholders})",
            [symbol] + values,
        )
        inserted += 1

    print(
        f"  {table}: replaced {replaced} destination rows, inserted {inserted} rows"
    )
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge live_micro rows into the main trades database."
    )
    parser.add_argument(
        "--src",
        default=str(DEFAULT_SRC),
        help="Source live_micro database path",
    )
    parser.add_argument(
        "--dst",
        default=str(DEFAULT_DST),
        help="Destination main database path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the migration but roll back all changes",
    )
    args = parser.parse_args()

    src_path = Path(args.src)
    dst_path = Path(args.dst)

    if not src_path.exists():
        print(f"Source DB {src_path} does not exist; nothing to migrate.")
        return 0

    if not dst_path.exists():
        print(f"Destination DB {dst_path} does not exist; aborting.")
        return 1

    print(f"Migrating {src_path} -> {dst_path}")
    if args.dry_run:
        print("DRY RUN: changes will be rolled back")

    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))

    src_cur = src.cursor()
    dst_cur = dst.cursor()

    # Foreign keys can get in the way while we delete and re-insert rows in
    # dependency order.  The script maintains referential integrity itself.
    dst_cur.execute("PRAGMA foreign_keys = OFF")

    try:
        print("Ensuring lane and mode columns exist...")
        for table in TABLES:
            if table_exists(dst_cur, table):
                ensure_columns(dst_cur, table)
            else:
                print(f"  Table {table} missing in destination; skipping column adds")

        print("Migrating tables...")
        counts: dict[str, int] = {}

        signal_count, signal_id_map = migrate_signals(src_cur, dst_cur)
        counts["signals"] = signal_count

        trade_count, trade_id_map = migrate_trades(src_cur, dst_cur, signal_id_map)
        counts["trades"] = trade_count

        counts["trade_gates"] = migrate_trade_gates(src_cur, dst_cur, signal_id_map, trade_id_map)
        counts["exits"] = migrate_child_table(src_cur, dst_cur, "exits", trade_id_map)
        counts["milestones"] = migrate_child_table(
            src_cur, dst_cur, "milestones", trade_id_map
        )
        counts["live_bootstrap_events"] = migrate_live_bootstrap_events(src_cur, dst_cur, trade_id_map)
        counts["market_regime_log"] = migrate_market_regime_log(src_cur, dst_cur)
        counts["binance_order_state"] = migrate_binance_order_state(src_cur, dst_cur)

        if args.dry_run:
            print("DRY RUN: rolling back changes")
            dst.rollback()
        else:
            dst.commit()
            print("Committed migration")

        print("\nMigration summary:")
        for table in TABLES:
            print(f"  {table}: {counts.get(table, 0)} rows")

        return 0
    except Exception as exc:
        print(f"Migration failed: {exc}")
        dst.rollback()
        return 1
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
