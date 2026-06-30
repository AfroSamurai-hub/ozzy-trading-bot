#!/usr/bin/env python3
"""OzzyBot launch-readiness evidence report."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_PATH = ROOT / "trades.db"
LOG_PATH = ROOT / "trades.log"
PROTECTIVE_EXITS = {"time_reduce", "time_exit", "momentum_exit", "profit_protect"}
ERROR_MARKERS = (
    "_ERROR",
    "PROTECTIVE_CLOSE_FAILED",
    "BINANCE_PARTIAL_CLOSE_ERROR",
)


def rows(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a SQLite query and return rows."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


def scalar(sql: str, params: tuple = ()):
    """Return the first column of the first row for a query."""
    result = rows(sql, params)
    return result[0][0] if result else None


def clean_filter() -> str:
    """Return the SQL predicate for non-migrated, non-ghost trades."""
    return (
        "COALESCE(source, 'live') != 'migrated' "
        "AND COALESCE(mode, 'live') != 'ghost' "
        "AND COALESCE(accounting_status, 'clean') IN ('clean', 'corrected')"
    )


def recent_errors(limit: int = 12) -> list[dict]:
    """Return recent structured error events from trades.log."""
    if not LOG_PATH.exists():
        return []
    events = []
    with LOG_PATH.open("rb") as handle:
        for raw in handle:
            try:
                line = raw.decode("utf-8", errors="ignore").strip("\x00\n ")
                if not line:
                    continue
                event = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            name = str(event.get("event", ""))
            if event.get("reason") == "unit_test" or (event.get("result") or {}).get("error") == "boom":
                continue
            if any(marker in name for marker in ERROR_MARKERS):
                events.append(event)
    return events[-limit:]


def binance_unrealized() -> tuple[float | None, list[dict]]:
    """Return current Binance unrealized PnL if private API access is available."""
    try:
        from binance_connector import get_open_positions  # noqa: PLC0415

        positions = get_open_positions()
    except Exception:
        return None, []
    total = 0.0
    simplified = []
    for pos in positions:
        pnl = float(pos.get("profit", 0) or 0)
        total += pnl
        simplified.append({
            "symbol": pos.get("tv_symbol", pos.get("symbol")),
            "side": pos.get("type"),
            "entry": pos.get("openPrice"),
            "current": pos.get("currentPrice"),
            "pnl": round(pnl, 2),
        })
    return total, simplified


def print_table(title: str, data: list[sqlite3.Row], columns: list[str]) -> None:
    """Print a small Markdown table."""
    print(f"\n## {title}")
    if not data:
        print("None")
        return
    print(" | ".join(columns))
    print(" | ".join("---" for _ in columns))
    for row in data:
        print(" | ".join(str(row[col]) if row[col] is not None else "" for col in columns))


def main() -> None:
    """Build and print the launch readiness report."""
    clean = clean_filter()
    closed_pnl = scalar(f"SELECT ROUND(SUM(COALESCE(pnl, 0)), 2) FROM trades WHERE {clean} AND exit_price IS NOT NULL")
    open_trades = rows(
        f"""
        SELECT id, symbol, direction, setup_grade, entry_price, qty, ts
        FROM trades
        WHERE {clean} AND exit_price IS NULL
        ORDER BY id
        """
    )
    streak = scalar("SELECT ROUND(SUM(COALESCE(pnl, 0)), 2) FROM trades WHERE id IN (36, 37)")
    post_streak = rows(
        """
        SELECT id, symbol, setup_grade, ROUND(COALESCE(pnl, 0), 2) AS pnl, exit_reason
        FROM trades
        WHERE id >= 39 AND exit_price IS NOT NULL
        ORDER BY id
        """
    )
    grade_perf = rows(
        f"""
        SELECT COALESCE(setup_grade, 'missing') AS grade,
               COUNT(*) AS trades,
               ROUND(SUM(COALESCE(pnl, 0)), 2) AS pnl,
               ROUND(AVG(COALESCE(pnl, 0)), 2) AS avg_pnl
        FROM trades
        WHERE {clean}
        GROUP BY COALESCE(setup_grade, 'missing')
        ORDER BY grade
        """
    )
    exits_by_reason = rows(
        """
        SELECT exit_type, COUNT(*) AS count
        FROM exits
        GROUP BY exit_type
        ORDER BY count DESC, exit_type
        """
    )
    protective = rows(
        f"""
        SELECT exit_type, COUNT(*) AS count
        FROM exits
        WHERE exit_type IN ({','.join('?' for _ in PROTECTIVE_EXITS)})
        GROUP BY exit_type
        ORDER BY exit_type
        """,
        tuple(sorted(PROTECTIVE_EXITS)),
    )
    unrealized, live_positions = binance_unrealized()

    print("# OzzyBot Launch Readiness Report")
    print(f"\nDB: {DB_PATH}")
    print(f"Clean closed PnL: ${closed_pnl or 0}")
    print(f"Verified trades #36 + #37 streak: ${streak or 0}")
    if unrealized is None:
        print("Unrealized PnL: unavailable (Binance query failed or credentials unavailable)")
    else:
        print(f"Unrealized PnL from Binance open positions: ${round(unrealized, 2)}")

    print_table(
        "Open Clean Trades",
        open_trades,
        ["id", "symbol", "direction", "setup_grade", "entry_price", "qty", "ts"],
    )
    print_table("A/B Grade Performance", grade_perf, ["grade", "trades", "pnl", "avg_pnl"])
    print_table("Exits By Reason", exits_by_reason, ["exit_type", "count"])
    print_table("Protective Exits Actually Logged", protective, ["exit_type", "count"])
    print_table(
        "Later Drawdown Context After #36/#37",
        post_streak,
        ["id", "symbol", "setup_grade", "pnl", "exit_reason"],
    )

    print("\n## Live Open Positions")
    if live_positions:
        for pos in live_positions:
            print(f"- {pos['symbol']} {pos['side']} entry={pos['entry']} current={pos['current']} pnl=${pos['pnl']}")
    else:
        print("None reported by Binance query")

    print("\n## Recent Error Events")
    errors = recent_errors()
    if not errors:
        print("None")
    for event in errors:
        print(json.dumps(event, sort_keys=True))


if __name__ == "__main__":
    main()
