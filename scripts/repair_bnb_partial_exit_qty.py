#!/usr/bin/env python3
"""Repair the two proven BNBUSDT partial-exit fractions for trade 100373."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

import trade_db
from binance_connector import _get_client

TRADE_ID = 100373
ORIGINAL_QTY = 18.13
EXPECTED = {
    1027: {
        "exit_type": "milestone_0",
        "fill_id": 143517400,
        "order_id": 1775544504,
        "qty": 4.53,
        "time": 1782792512398,
    },
    1028: {
        "exit_type": "regime_aware_chop_profit_taken",
        "fill_id": 143517525,
        "order_id": 1775555147,
        "qty": 3.40,
        "time": 1782792554141,
    },
}


def assert_flat_exchange(client) -> None:
    """Refuse repair unless positions and both order classes are empty."""
    positions = client.futures_position_information()
    nonflat = [row for row in positions or [] if abs(float(row.get("positionAmt") or 0.0)) > 0]
    normal_orders = client.futures_get_open_orders()
    try:
        algo_orders = client.futures_get_open_algo_orders()
    except Exception as exc:
        raise RuntimeError(f"cannot verify exchange algo-order state: {exc}") from exc
    if nonflat or normal_orders or algo_orders:
        raise RuntimeError("exchange is not flat or still has open orders")


def validate_exchange_evidence(fills: list[dict]) -> dict[int, dict]:
    """Return the exact exit-to-fill mapping or reject ambiguity."""
    mapping = {}
    for exit_id, expected in EXPECTED.items():
        candidates = []
        for row in fills or []:
            if str(row.get("side") or "").upper() != "BUY":
                continue
            if str(row.get("positionSide") or "").upper() != "SHORT":
                continue
            if abs(float(row.get("qty") or 0.0) - expected["qty"]) > 1e-12:
                continue
            if abs(int(row.get("time") or 0) - expected["time"]) > 10_000:
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(
                f"ambiguous exchange evidence for exit {exit_id}: {len(candidates)} candidates"
            )
        row = candidates[0]
        if int(row.get("id")) != expected["fill_id"] or int(row.get("orderId")) != expected["order_id"]:
            raise RuntimeError(f"exchange identifiers changed for exit {exit_id}")
        mapping[exit_id] = row
    return mapping


def sqlite_online_backup(db_path: Path, now: datetime) -> Path:
    """Create a transactionally consistent, non-overwriting SQLite backup."""
    backup_dir = db_path.parent / "backups" / now.astimezone(UTC).strftime("%Y-%m-%d")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / (
        f"{db_path.stem}_pre_partial_exit_repair_{now.astimezone(UTC).strftime('%H%M%S')}.db"
    )
    if backup_path.exists():
        raise FileExistsError(backup_path)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


def validate_db_state(db_path: Path) -> None:
    """Require the exact trade and pre-repair rows before mutation."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trade = conn.execute(
            "SELECT id, symbol, direction, qty FROM trades WHERE id = ?",
            (TRADE_ID,),
        ).fetchone()
        if (
            not trade
            or trade["symbol"] != "BNBUSDT"
            or trade["direction"] != "SELL"
            or abs(float(trade["qty"]) - ORIGINAL_QTY) > 1e-12
        ):
            raise RuntimeError("trade 100373 identity does not match repair contract")
        rows = conn.execute(
            "SELECT * FROM exits WHERE id IN (1027, 1028) ORDER BY id"
        ).fetchall()
        if len(rows) != 2:
            raise RuntimeError("target exit rows are missing")
        for row in rows:
            expected = EXPECTED[row["id"]]
            if (
                row["trade_id"] != TRADE_ID
                or row["exit_type"] != expected["exit_type"]
                or abs(float(row["qty_pct"]) - 0.25) > 1e-12
            ):
                raise RuntimeError(f"exit {row['id']} no longer matches pre-repair state")


def apply_repair(db_path: Path, fills: list[dict], now: datetime | None = None) -> Path:
    """Back up and compare-and-set the two approved fractions."""
    validate_exchange_evidence(fills)
    validate_db_state(db_path)
    stamp = now or datetime.now(UTC)
    backup_path = sqlite_online_backup(db_path, stamp)
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for exit_id, expected in EXPECTED.items():
            cursor = conn.execute(
                """
                UPDATE exits
                SET qty_pct = ?
                WHERE id = ? AND trade_id = ? AND abs(qty_pct - 0.25) <= 1e-12
                """,
                (expected["qty"] / ORIGINAL_QTY, exit_id, TRADE_ID),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"compare-and-set failed for exit {exit_id}")
        conn.commit()
    return backup_path


def fetch_repair_fills(client) -> list[dict]:
    return client.futures_account_trades(
        symbol="BNBUSDT",
        startTime=1782791900000,
        endTime=1782792700000,
        limit=100,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair BNB trade 100373 partial-exit fractions")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply after exact evidence and flat-state checks",
    )
    parser.add_argument("--db", type=Path, default=Path(trade_db.DB_PATH))
    args = parser.parse_args(argv)

    client = _get_client()
    fills = fetch_repair_fills(client)
    mapping = validate_exchange_evidence(fills)
    validate_db_state(args.db)
    for exit_id in sorted(EXPECTED):
        row = mapping[exit_id]
        expected = EXPECTED[exit_id]
        print(
            f"exit={exit_id} fill_id={row['id']} order_id={row['orderId']} "
            f"qty={expected['qty']} qty_pct={expected['qty'] / ORIGINAL_QTY:.12f}"
        )
    if not args.apply:
        print("DRY RUN: database unchanged")
        return 0

    assert_flat_exchange(client)
    backup_path = apply_repair(args.db, fills)
    print(f"backup={backup_path}")
    print("updated_exit_ids=1027,1028")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
