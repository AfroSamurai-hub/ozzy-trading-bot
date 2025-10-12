"""
Simple SQLite helper for Ozzy Simple to store signals, trades, and positions.
This is intentionally minimal and synchronous; it's sufficient for single-process
use and for migrating from CSV to SQLite.
"""
import sqlite3
import threading
from typing import Optional

DB_PATH = 'ozzy_simple.db'

_schema_initialized = False
_schema_lock = threading.Lock()


def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    global _schema_initialized
    with _schema_lock:
        if _schema_initialized:
            return
        conn = _get_conn()
        c = conn.cursor()
        # Signals table: many rows, store technical features and raw json
        c.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                signal TEXT,
                confidence REAL,
                quality TEXT,
                rsi REAL,
                ema_short REAL,
                ema_long REAL,
                volume_ratio REAL,
                momentum REAL,
                hour INTEGER,
                day_of_week INTEGER,
                atr_pct REAL,
                stddev_returns_pct REAL,
                reason TEXT
            )
        ''')

        # Trades table: completed trades with realized pnl
        c.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_timestamp TEXT,
                exit_timestamp TEXT,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                position_size REAL,
                position_value REAL,
                pnl REAL,
                duration_seconds INTEGER,
                quality TEXT,
                confidence REAL,
                entry_reason TEXT,
                exit_reason TEXT
            )
        ''')

        # Positions snapshot for quick monitoring
        c.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                side TEXT,
                qty REAL,
                entry_price REAL,
                unrealized_pnl REAL
            )
        ''')

        conn.commit()
        conn.close()
        _schema_initialized = True


def insert_signal(signal_row: dict):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO signals (
            timestamp, symbol, signal, confidence, quality,
            rsi, ema_short, ema_long, volume_ratio, momentum,
            hour, day_of_week, atr_pct, stddev_returns_pct, reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        signal_row.get('timestamp'),
        signal_row.get('symbol'),
        signal_row.get('signal'),
        signal_row.get('confidence'),
        signal_row.get('quality'),
        signal_row.get('rsi'),
        signal_row.get('ema_short'),
        signal_row.get('ema_long'),
        signal_row.get('volume_ratio'),
        signal_row.get('momentum'),
        signal_row.get('hour'),
        signal_row.get('day_of_week'),
        signal_row.get('atr_pct'),
        signal_row.get('stddev_returns_pct'),
        signal_row.get('reason')
    ))
    conn.commit()
    conn.close()


def insert_trade(trade_row: dict):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (
            entry_timestamp, exit_timestamp, symbol, side,
            entry_price, exit_price, position_size, position_value,
            pnl, duration_seconds, quality, confidence,
            entry_reason, exit_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        trade_row.get('entry_timestamp'),
        trade_row.get('exit_timestamp'),
        trade_row.get('symbol'),
        trade_row.get('side'),
        trade_row.get('entry_price'),
        trade_row.get('exit_price'),
        trade_row.get('position_size'),
        trade_row.get('position_value'),
        trade_row.get('pnl'),
        trade_row.get('duration_seconds'),
        trade_row.get('quality'),
        trade_row.get('confidence'),
        trade_row.get('entry_reason'),
        trade_row.get('exit_reason')
    ))
    conn.commit()
    conn.close()


def insert_position_snapshot(snapshot_row: dict):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO positions (timestamp, symbol, side, qty, entry_price, unrealized_pnl)
        VALUES (?,?,?,?,?,?)
    ''', (
        snapshot_row.get('timestamp'),
        snapshot_row.get('symbol'),
        snapshot_row.get('side'),
        snapshot_row.get('qty'),
        snapshot_row.get('entry_price'),
        snapshot_row.get('unrealized_pnl')
    ))
    conn.commit()
    conn.close()


def create_tables():
    """Backward compatible alias to initialize DB schema."""
    init_db()


def log_signal(signal_row: dict):
    """High-level alias used by main.py to log signals."""
    try:
        insert_signal(signal_row)
    except Exception:
        # bubble up? keep best-effort behavior
        raise


def log_trade_open(trade_row: dict) -> int:
    """Insert an 'open' trade record and return its id.

    We'll insert a row with exit_timestamp NULL; caller should call log_trade_close with id when closed.
    """
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (
            entry_timestamp, exit_timestamp, symbol, side,
            entry_price, exit_price, position_size, position_value,
            pnl, duration_seconds, quality, confidence,
            entry_reason, exit_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        trade_row.get('entry_timestamp'),
        None,
        trade_row.get('symbol'),
        trade_row.get('side'),
        trade_row.get('entry_price'),
        None,
        trade_row.get('position_size'),
        trade_row.get('position_value'),
        None,
        None,
        trade_row.get('quality'),
        trade_row.get('confidence'),
        trade_row.get('entry_reason'),
        None
    ))
    conn.commit()
    rowid = c.lastrowid
    conn.close()
    return rowid


def log_trade_close(trade_id: int, exit_timestamp: str, exit_price: float, pnl: float, exit_reason: str):
    conn = _get_conn()
    c = conn.cursor()
    c.execute('''
        UPDATE trades SET exit_timestamp = ?, exit_price = ?, pnl = ?, exit_reason = ?
        WHERE id = ?
    ''', (exit_timestamp, exit_price, pnl, exit_reason, trade_id))
    conn.commit()
    conn.close()
