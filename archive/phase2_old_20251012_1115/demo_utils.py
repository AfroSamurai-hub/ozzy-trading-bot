"""
Shared helpers for the Ozzy demo trading environment.

Provides a canonical way to resolve the demo database path and to
initialize the SQLite schema used across the demo tooling.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DEFAULT_STARTING_BALANCE = 10_000.0
DEFAULT_DB_FILENAME = "demo_trades.db"


def get_demo_db_path() -> str:
    """Resolve the demo database path with environment override support."""
    env_path = os.getenv("OZZY_DEMO_DB_PATH")
    if env_path:
        return os.path.abspath(os.path.expanduser(env_path))

    project_root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(project_root, DEFAULT_DB_FILENAME)


def initialize_demo_database(
    db_path: Optional[str] = None,
    *,
    overwrite: bool = False,
    starting_balance: float = DEFAULT_STARTING_BALANCE,
) -> str:
    """Create the demo database (optionally overwriting existing data)."""
    path = os.path.abspath(db_path or get_demo_db_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if overwrite and os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_config (
            id INTEGER PRIMARY KEY,
            starting_capital REAL NOT NULL,
            current_balance REAL NOT NULL,
            start_date TEXT NOT NULL,
            total_trades INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity REAL NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            pnl REAL,
            pnl_percentage REAL,
            status TEXT DEFAULT 'open',
            confidence REAL,
            rsi REAL,
            ma_signal TEXT,
            balance_after REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            starting_balance REAL NOT NULL,
            ending_balance REAL NOT NULL,
            trades_count INTEGER NOT NULL,
            winning_trades INTEGER NOT NULL,
            losing_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            daily_pnl REAL NOT NULL,
            daily_pnl_percent REAL NOT NULL,
            best_trade REAL,
            worst_trade REAL,
            max_balance REAL,
            min_balance REAL,
            drawdown_percent REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("SELECT COUNT(*) FROM demo_config")
    has_config = cursor.fetchone()[0] or 0
    if has_config == 0:
        cursor.execute(
            """
            INSERT INTO demo_config (
                starting_capital, current_balance, start_date, total_trades, total_pnl
            ) VALUES (?, ?, ?, 0, 0.0)
            """,
            (
                starting_balance,
                starting_balance,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    conn.commit()
    conn.close()
    return path


def ensure_demo_database(db_path: Optional[str] = None) -> str:
    """Guarantee that the demo database exists and return its path."""
    path = os.path.abspath(db_path or get_demo_db_path())
    if not os.path.exists(path):
        initialize_demo_database(path)
    return path
