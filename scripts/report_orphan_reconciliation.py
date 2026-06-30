#!/usr/bin/env python3
"""Generate a read-only orphan reconciliation report from DB and observer state."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTNET_DB = ROOT / "trades.db"
DEFAULT_LIVE_DB = ROOT / "trades.db"
DEFAULT_OBSERVER_DIR = ROOT / "observer"


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except Exception:
        return fallback


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _recent_trade_rows(db_path: Path, symbol: str, limit: int = 5) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with _connect_readonly(db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, direction, entry_price, exit_price, qty, pnl,
                       exit_reason, execution_state, source, strategy_label
                FROM trades
                WHERE UPPER(symbol) = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (symbol.upper(), limit),
            ).fetchall()
    except Exception:
        return []
    return [dict(row) for row in rows]


def _recommendation(orphan: dict, related_rows: list[dict]) -> str:
    qty = abs(float(orphan.get("qty") or orphan.get("volume") or orphan.get("positionAmt") or 0.0))
    if qty <= 0:
        return "IGNORE_DUST"
    for row in related_rows:
        if row.get("exit_price") is None and str(row.get("execution_state") or "").lower() not in {
            "closed",
            "execution_failed",
            "fail_closed",
        }:
            return "ADOPT_CANDIDATE_NEEDS_APPROVAL"
    if related_rows:
        return "MANUAL_CLOSE_RECOMMENDED"
    return "UNKNOWN_NEEDS_REVIEW"


def _orphan_summary(orphan: dict, mode: str, db_path: Path) -> dict:
    symbol = str(orphan.get("symbol") or "").upper()
    related = _recent_trade_rows(db_path, symbol)
    return {
        "mode": mode,
        "symbol": symbol,
        "side": orphan.get("side") or orphan.get("type") or orphan.get("positionSide"),
        "position_side": orphan.get("positionSide") or orphan.get("side"),
        "qty": orphan.get("qty") or orphan.get("volume") or orphan.get("positionAmt"),
        "entry_price": orphan.get("entry_price") or orphan.get("openPrice") or orphan.get("entryPrice"),
        "mark_price": orphan.get("mark_price") or orphan.get("currentPrice") or orphan.get("markPrice"),
        "unrealized_pnl": orphan.get("unrealized_pnl") or orphan.get("profit") or orphan.get("unRealizedProfit"),
        "related_trade_ids": ",".join(str(row.get("id")) for row in related if row.get("id") is not None),
        "recommendation": _recommendation(orphan, related),
        "management_allowed": False,
    }


def build_report(
    *,
    testnet_db: Path = DEFAULT_TESTNET_DB,
    live_db: Path = DEFAULT_LIVE_DB,
    observer_dir: Path = DEFAULT_OBSERVER_DIR,
    report_date: date | None = None,
) -> dict:
    report_date = report_date or datetime.now(UTC).date()
    raw_orphans = _read_json(observer_dir / "orphan_positions.json", [])
    if isinstance(raw_orphans, dict):
        raw_orphans = raw_orphans.get("orphan_positions") or raw_orphans.get("positions") or []
    if not isinstance(raw_orphans, list):
        raw_orphans = []

    rows = []
    for orphan in raw_orphans:
        if not isinstance(orphan, dict):
            continue
        mode = str(orphan.get("mode") or orphan.get("execution_mode") or "STANDARD_TESTNET").upper()
        db_path = live_db if mode in {"LIVE", "LIVE_MICRO"} else testnet_db
        rows.append(_orphan_summary(orphan, mode, db_path))

    return {
        "date": report_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": rows,
        "observer_path": str(observer_dir / "orphan_positions.json"),
    }


def _markdown_table(rows: list[dict]) -> str:
    columns = [
        "mode",
        "symbol",
        "side",
        "qty",
        "entry_price",
        "mark_price",
        "unrealized_pnl",
        "related_trade_ids",
        "recommendation",
        "management_allowed",
    ]
    if not rows:
        return "_No orphan positions found._\n"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict) -> str:
    return "\n".join(
        [
            f"# Orphan Reconciliation Report {report['date']}",
            "",
            f"Generated: `{report['generated_at']}`",
            f"Observer source: `{report['observer_path']}`",
            "",
            _markdown_table(report["rows"]),
            "",
            "All rows are read-only recommendations. Orphans are never safe for automatic management.",
            "",
        ]
    )


def write_outputs(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["date"].replace("-", "")
    md_path = output_dir / f"orphan_reconciliation_report_{stamp}.md"
    csv_path = output_dir / f"orphan_reconciliation_report_{stamp}.csv"
    md_path.write_text(render_markdown(report))
    with csv_path.open("w", newline="") as fh:
        fieldnames = [
            "mode",
            "symbol",
            "side",
            "position_side",
            "qty",
            "entry_price",
            "mark_price",
            "unrealized_pnl",
            "related_trade_ids",
            "recommendation",
            "management_allowed",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow(row)
    return md_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--testnet-db", type=Path, default=DEFAULT_TESTNET_DB)
    parser.add_argument("--live-db", type=Path, default=DEFAULT_LIVE_DB)
    parser.add_argument("--observer-dir", type=Path, default=DEFAULT_OBSERVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    report = build_report(testnet_db=args.testnet_db, live_db=args.live_db, observer_dir=args.observer_dir)
    md_path, csv_path = write_outputs(report, args.output_dir)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
