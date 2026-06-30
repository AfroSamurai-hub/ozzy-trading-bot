# ============================================
# HERMES — SQLite trade journal & analytics
# ============================================
# Replaces signal_reviews.json and orphaned binance_journal.py functions.
# Written alongside trades.log on every entry/exit/gate decision.

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if os.environ.get("HERMES_TRADE_DB"):
    DB_PATH = Path(os.environ["HERMES_TRADE_DB"])
elif os.environ.get("TRADE_DB_TEST_MODE"):
    DB_PATH = Path(__file__).with_name("trades_test.db")
else:
    DB_PATH = Path(__file__).with_name("trades.db")
logger = logging.getLogger(__name__)

CLEAN_ACCOUNTING_STATUSES = ("clean", "corrected")


def _runtime_is_live_micro() -> bool:
    """Return whether the current process is the live-micro runtime."""
    instance = os.environ.get("HERMES_INSTANCE_NAME", "")
    port = os.environ.get("HERMES_PORT", "")
    return instance.strip().upper().replace("_", " ") == "LIVE MICRO" or port == "5001"


def calculate_directional_pnl(direction: str, entry_price: float, exit_price: float, qty: float) -> float:
    """Return raw directional PnL before fees/funding for one position slice."""
    side = str(direction or "").upper()
    entry = float(entry_price or 0)
    exit_ = float(exit_price or 0)
    quantity = abs(float(qty or 0))
    if entry <= 0 or exit_ <= 0 or quantity <= 0:
        return 0.0
    if side == "SELL":
        return (entry - exit_) * quantity
    return (exit_ - entry) * quantity


def reconcile_exchange_fill_ledger(direction: str, fills: list[dict], funding: float = 0.0) -> dict:
    """Build authoritative trade accounting from exchange fills.

    Entry/exit prices are quantity-weighted. Binance ``realizedPnl`` is the
    gross result, commissions are positive costs, and funding is signed income.
    """
    entry_side = "SELL" if str(direction or "").upper() == "SELL" else "BUY"
    exit_side = "BUY" if entry_side == "SELL" else "SELL"
    entry_qty = entry_notional = 0.0
    exit_qty = exit_notional = 0.0
    gross_pnl = fees = 0.0

    for fill in fills or []:
        side = str(fill.get("side") or "").upper()
        qty = abs(float(fill.get("qty") or 0.0))
        price = float(fill.get("price") or 0.0)
        if qty <= 0 or price <= 0 or side not in {entry_side, exit_side}:
            continue
        fees += abs(float(fill.get("commission") or 0.0))
        if side == entry_side:
            entry_qty += qty
            entry_notional += qty * price
        else:
            exit_qty += qty
            exit_notional += qty * price
            gross_pnl += float(fill.get("realizedPnl") or 0.0)

    tolerance = max(1e-9, entry_qty * 1e-6)
    complete = entry_qty > 0 and exit_qty > 0 and abs(entry_qty - exit_qty) <= tolerance
    signed_funding = float(funding or 0.0)
    return {
        "complete": complete,
        "entry_qty": entry_qty,
        "exit_qty": exit_qty,
        "entry_price": entry_notional / entry_qty if entry_qty else None,
        "exit_price": exit_notional / exit_qty if exit_qty else None,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "funding": signed_funding,
        "net_pnl": gross_pnl - fees + signed_funding,
    }


def reconcile_trade_close_pnl(
    *,
    direction: str,
    entry_price: float,
    exit_price: float,
    original_qty: float,
    realized_partial_pnl: float = 0.0,
    realized_partial_qty_pct: float = 0.0,
    fallback_pnl: float | None = None,
) -> dict:
    """Reconcile final close PnL from immutable trade math.

    Binance position snapshots can disappear before the monitor sees the final
    realized PnL. This helper rebuilds the close from entry/exit/side and any
    partial exits already logged so closed rows remain internally consistent.
    """
    partial_pct = min(max(float(realized_partial_qty_pct or 0.0), 0.0), 1.0)
    remaining_qty = abs(float(original_qty or 0.0)) * max(0.0, 1.0 - partial_pct)
    final_slice_pnl = calculate_directional_pnl(direction, entry_price, exit_price, remaining_qty)
    reconstructed = float(realized_partial_pnl or 0.0) + final_slice_pnl
    fallback = float(fallback_pnl) if fallback_pnl is not None else None
    mismatch = False
    if fallback is not None:
        tolerance = max(1.0, abs(reconstructed) * 0.25)
        mismatch = abs(fallback - reconstructed) > tolerance
    return {
        "pnl": reconstructed,
        "final_slice_pnl": final_slice_pnl,
        "remaining_qty": remaining_qty,
        "realized_partial_pnl": float(realized_partial_pnl or 0.0),
        "realized_partial_qty_pct": partial_pct,
        "fallback_pnl": fallback,
        "mismatch": mismatch,
    }


def _journal_event(**kwargs) -> None:
    """Append Ozzy Memory journal rows without letting analytics break trading."""
    try:
        from ozzy_memory import record_trade_journal_event

        record_trade_journal_event(**kwargs)
    except Exception as e:
        logger.debug("memory journal append failed: %s", e)


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------
_INIT_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    symbol      TEXT NOT NULL,
    direction   TEXT NOT NULL,          -- BUY | SELL
    entry_price REAL,
    bias        TEXT,
    structure   TEXT,
    regime      TEXT DEFAULT 'unknown',
    version     TEXT,
    source      TEXT,
    timeframe   TEXT,
    pine_ts     INTEGER,
    volume_ratio REAL,                  -- volume / 20-period avg at signal time
    strategy_label TEXT,
    entry_setup_label TEXT,
    regime_label TEXT,
    source_service TEXT,
    webhook_port INTEGER,
    execution_mode TEXT,
    lane        TEXT DEFAULT 'UNKNOWN',
    mode        TEXT DEFAULT 'testnet'  -- testnet | live
);

CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     INTEGER REFERENCES signals(id),
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    symbol        TEXT NOT NULL,
    direction     TEXT NOT NULL,
    entry_price   REAL,
    exit_price    REAL,
    qty           REAL,
    pnl           REAL,
    gross_pnl     REAL,
    fees          REAL DEFAULT 0,
    funding       REAL DEFAULT 0,
    exit_reason   TEXT,                 -- tp | sl | breakeven | trail | opposite | manual | expiry
    regime        TEXT,
    strategy      TEXT,
    timeframe     TEXT,
    r_multiple    REAL,
    duration_min  INTEGER,
    lane          TEXT DEFAULT 'UNKNOWN',
    mode          TEXT DEFAULT 'testnet',
    setup_grade   TEXT,
    risk_dollars  REAL,
    reward_dollars REAL,
    rr            REAL,
    sl            REAL,
    tp            REAL,
    atr           REAL,                 -- ATR at signal time (price units)
    volume_ratio  REAL,                 -- volume / 20-period avg at signal time
    context_json  TEXT,                 -- fear_greed, funding_rate, multiplier, reasoning
    source        TEXT DEFAULT 'live',   -- live | paper | migrated
    strategy_label TEXT,
    entry_setup_label TEXT,
    regime_label TEXT,
    source_service TEXT,
    webhook_port INTEGER,
    execution_mode TEXT,
    execution_state TEXT DEFAULT 'confirmed',
    accounting_status TEXT DEFAULT 'clean', -- clean | corrected | dirty | unchecked
    accounting_notes  TEXT,
    accounting_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS trade_gates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER REFERENCES signals(id),
    trade_id    INTEGER REFERENCES trades(id),
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    gate_name   TEXT NOT NULL,
    decision    TEXT NOT NULL,          -- passed | rejected
    reason      TEXT,
    filter_json TEXT
);

CREATE TABLE IF NOT EXISTS exits (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id         INTEGER REFERENCES trades(id),
    ts               TEXT NOT NULL DEFAULT (datetime('now')),
    exit_type        TEXT NOT NULL,     -- tp | sl | breakeven | trail | partial | opposite | manual | expiry
    price            REAL,
    pnl_contribution REAL,
    qty_pct          REAL,              -- 0.25, 0.5, 1.0, …
    notes            TEXT,
    lane             TEXT DEFAULT 'UNKNOWN',
    mode             TEXT DEFAULT 'testnet'
);

CREATE TABLE IF NOT EXISTS market_regime_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    symbol       TEXT NOT NULL,
    regime       TEXT,
    indicators_json TEXT
);

CREATE TABLE IF NOT EXISTS milestones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER NOT NULL,
    milestone   TEXT NOT NULL,           -- '1R_breakeven', '1.5R_trail_active', '2R_trail_update', '2.5R_tp'
    price       REAL,
    pnl         REAL,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    lane        TEXT DEFAULT 'UNKNOWN',
    mode        TEXT DEFAULT 'testnet',
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    UNIQUE(trade_id, milestone)
);
CREATE INDEX IF NOT EXISTS idx_milestones_trade ON milestones(trade_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_ts       ON signals(ts);
CREATE INDEX IF NOT EXISTS idx_signals_symbol   ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_ts        ON trades(ts);
CREATE INDEX IF NOT EXISTS idx_gates_signal     ON trade_gates(signal_id);
CREATE INDEX IF NOT EXISTS idx_gates_trade      ON trade_gates(trade_id);
CREATE INDEX IF NOT EXISTS idx_exits_trade      ON exits(trade_id);
CREATE INDEX IF NOT EXISTS idx_regime_symbol_ts ON market_regime_log(symbol, ts);

CREATE TABLE IF NOT EXISTS gate_thresholds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    gate_name   TEXT NOT NULL,
    threshold   REAL,
    win_rate    REAL,
    sample_size INTEGER,
    params_json TEXT,
    updated_ts  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_gate_thresholds_symbol_gate ON gate_thresholds(symbol, gate_name);

CREATE TABLE IF NOT EXISTS binance_order_state (
    symbol                    TEXT PRIMARY KEY,
    tv_symbol                 TEXT,
    side                      TEXT,
    entry_order_id            TEXT,
    sl_order_id               TEXT,
    tp_order_id               TEXT,
    original_qty              REAL,
    remaining_qty             REAL,
    entry_price               REAL,
    original_sl               REAL,
    current_sl                REAL,
    current_tp                REAL,
    original_sl_distance      REAL,
    realized_partial_exits_json TEXT,
    runner_status             TEXT,
    raw_state_json            TEXT,
    updated_ts                TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS live_bootstrap_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    day_utc     TEXT NOT NULL DEFAULT (date('now')),
    event_type  TEXT NOT NULL,
    event_key   TEXT,
    trade_id    INTEGER REFERENCES trades(id),
    reason      TEXT,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_live_bootstrap_events_day_type ON live_bootstrap_events(day_utc, event_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_live_bootstrap_event_key ON live_bootstrap_events(day_utc, event_type, event_key);
"""


def migrate_unified_columns(conn: sqlite3.Connection) -> None:
    """Ensure lane/mode columns exist on unified-core tables. Idempotent."""
    for table in ("signals", "trades", "exits", "milestones"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "lane" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN lane TEXT DEFAULT 'UNKNOWN'")
        if "mode" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN mode TEXT DEFAULT 'testnet'")


def create_system_events_table(conn: sqlite3.Connection) -> None:
    """Create the unified system_events table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            payload TEXT,
            source TEXT
        )
    """)


def log_system_event(
    event_type: str,
    payload: dict | None = None,
    source: str = "system",
) -> None:
    """Insert a row into system_events."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO system_events (event_type, payload, source) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload, default=str) if payload else None, source),
        )
        conn.commit()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_INIT_SQL)
    migrate_unified_columns(conn)
    create_system_events_table(conn)
    # Migrate existing DBs: add atr column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
    signal_cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    if "sl" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN sl REAL")
    if "tp" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN tp REAL")
    if "atr" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN atr REAL")
    if "source" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'live'")
    if "volume_ratio" not in cols:
        conn.execute("ALTER TABLE signals ADD COLUMN volume_ratio REAL")
        conn.execute("ALTER TABLE trades ADD COLUMN volume_ratio REAL")
    if "peak_pnl" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN peak_pnl REAL DEFAULT 0")
    if "peak_price" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN peak_price REAL")
    if "execution_state" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN execution_state TEXT DEFAULT 'confirmed'")
    if "accounting_status" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN accounting_status TEXT DEFAULT 'clean'")
    if "accounting_notes" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN accounting_notes TEXT")
    if "accounting_checked_at" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN accounting_checked_at TEXT")
    label_cols = {
        "strategy_label": "TEXT",
        "entry_setup_label": "TEXT",
        "regime_label": "TEXT",
        "source_service": "TEXT",
        "webhook_port": "INTEGER",
        "execution_mode": "TEXT",
    }
    for col, col_type in label_cols.items():
        if col not in signal_cols:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {col_type}")
        if col not in cols:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
    if "lane" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN lane TEXT")
    conn.execute(
        """
        UPDATE trades
        SET strategy_label = CASE
            WHEN NULLIF(TRIM(strategy_label), '') IS NOT NULL THEN strategy_label
            WHEN LOWER(COALESCE(strategy, '')) = 'mean_reversion'
                 AND LOWER(COALESCE(timeframe, '')) IN ('15', '15m') THEN '15M_MEAN_REVERSION'
            WHEN LOWER(COALESCE(strategy, '')) IN ('trend_continuation', 'momentum', 'pullback', 'supertrend')
                 AND LOWER(COALESCE(timeframe, '')) IN ('60', '1h') THEN '1H_TREND_CONTINUATION'
            ELSE strategy_label
        END
        """
    )
    conn.execute(
        """
        UPDATE signals
        SET strategy_label = (
            SELECT trades.strategy_label
            FROM trades
            WHERE trades.signal_id = signals.id
              AND NULLIF(TRIM(trades.strategy_label), '') IS NOT NULL
            ORDER BY trades.id DESC
            LIMIT 1
        )
        WHERE NULLIF(TRIM(strategy_label), '') IS NULL
          AND EXISTS (
              SELECT 1
              FROM trades
              WHERE trades.signal_id = signals.id
                AND NULLIF(TRIM(trades.strategy_label), '') IS NOT NULL
          )
        """
    )
    # Ensure gate_thresholds table exists (added v2026-05-13)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "gate_thresholds" not in tables:
        conn.executescript("""
            CREATE TABLE gate_thresholds (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                gate_name   TEXT NOT NULL,
                threshold   REAL,
                win_rate    REAL,
                sample_size INTEGER,
                params_json TEXT,
                updated_ts  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX idx_gate_thresholds_symbol_gate ON gate_thresholds(symbol, gate_name);
        """)
    if "binance_order_state" not in tables:
        conn.executescript("""
            CREATE TABLE binance_order_state (
                symbol                    TEXT PRIMARY KEY,
                tv_symbol                 TEXT,
                side                      TEXT,
                entry_order_id            TEXT,
                sl_order_id               TEXT,
                tp_order_id               TEXT,
                original_qty              REAL,
                remaining_qty             REAL,
                entry_price               REAL,
                original_sl               REAL,
                current_sl                REAL,
                current_tp                REAL,
                original_sl_distance      REAL,
                realized_partial_exits_json TEXT,
                runner_status             TEXT,
                raw_state_json            TEXT,
                updated_ts                TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    if "live_bootstrap_events" not in tables:
        conn.executescript("""
            CREATE TABLE live_bootstrap_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL DEFAULT (datetime('now')),
                day_utc     TEXT NOT NULL DEFAULT (date('now')),
                event_type  TEXT NOT NULL,
                event_key   TEXT,
                trade_id    INTEGER REFERENCES trades(id),
                reason      TEXT,
                payload_json TEXT
            );
            CREATE INDEX idx_live_bootstrap_events_day_type ON live_bootstrap_events(day_utc, event_type);
            CREATE UNIQUE INDEX idx_live_bootstrap_event_key
                ON live_bootstrap_events(day_utc, event_type, event_key);
        """)
    conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_schema(conn)
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------
# Write helpers
# ------------------------------------------------------------------
def log_signal(
    symbol: str,
    direction: str,
    entry_price: float | None = None,
    bias: str | None = None,
    structure: str | None = None,
    regime: str | None = None,
    version: str | None = None,
    source: str | None = None,
    timeframe: str | None = None,
    pine_ts: int | None = None,
    volume_ratio: float | None = None,
    strategy_label: str | None = None,
    entry_setup_label: str | None = None,
    regime_label: str | None = None,
    source_service: str | None = None,
    webhook_port: int | None = None,
    execution_mode: str | None = None,
    mode: str = "live",
) -> int:
    """Log an incoming signal; return the signal row id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO signals
                (symbol, direction, entry_price, bias, structure, regime,
                 version, source, timeframe, pine_ts, volume_ratio,
                 strategy_label, entry_setup_label, regime_label, source_service, webhook_port, execution_mode,
                 mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                direction,
                entry_price,
                bias,
                structure,
                regime,
                version,
                source,
                timeframe,
                pine_ts,
                volume_ratio,
                strategy_label,
                entry_setup_label,
                regime_label,
                source_service,
                webhook_port,
                execution_mode,
                mode,
            ),
        )
        conn.commit()
        return cur.lastrowid


def log_gate_decision(
    signal_id: int | None,
    gate_name: str,
    decision: str,          # passed | rejected
    reason: str | None = None,
    filter_json: dict | None = None,
    trade_id: int | None = None,
) -> None:
    """Log a single gate decision. Called from webhook.py after every gate."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO trade_gates (signal_id, trade_id, gate_name, decision, reason, filter_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                trade_id,
                gate_name,
                decision,
                reason,
                json.dumps(filter_json, default=str) if filter_json else None,
            ),
        )
        conn.commit()


def log_trade(
    signal_id: int | None,
    symbol: str,
    direction: str,
    entry_price: float | None = None,
    qty: float | None = None,
    sl: float | None = None,
    tp: float | None = None,
    rr: float | None = None,
    regime: str | None = None,
    strategy: str | None = None,
    timeframe: str | None = None,
    mode: str = "live",
    setup_grade: str | None = None,
    risk_dollars: float | None = None,
    reward_dollars: float | None = None,
    atr: float | None = None,
    volume_ratio: float | None = None,
    context: dict | None = None,
    strategy_label: str | None = None,
    entry_setup_label: str | None = None,
    regime_label: str | None = None,
    source_service: str | None = None,
    webhook_port: int | None = None,
    execution_mode: str | None = None,
    lane: str | None = None,
    execution_state: str = "confirmed",
) -> int:
    """Log an approved trade at entry time; return the trade row id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
                (signal_id, symbol, direction, entry_price, qty,
                 regime, strategy, timeframe, mode, setup_grade,
                 risk_dollars, reward_dollars, rr, sl, tp, atr, volume_ratio, context_json, source,
                 strategy_label, entry_setup_label, regime_label, source_service, webhook_port, execution_mode,
                 lane, execution_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                symbol,
                direction,
                entry_price,
                qty,
                regime,
                strategy,
                timeframe,
                mode,
                setup_grade,
                risk_dollars,
                reward_dollars,
                rr,
                sl,
                tp,
                atr,
                volume_ratio,
                json.dumps(context, default=str) if context else None,
                "live",
                strategy_label,
                entry_setup_label,
                regime_label,
                source_service,
                webhook_port,
                execution_mode,
                lane,
                execution_state,
            ),
        )
        conn.commit()
        trade_id = cur.lastrowid
    _journal_event(
        event_type="trade_opened",
        trade_id=trade_id,
        symbol=symbol,
        previous_state=None,
        new_state=execution_state,
        raw_payload={"direction": direction, "setup_grade": setup_grade, "risk_dollars": risk_dollars},
        actor="webhook",
    )
    return trade_id


def close_trade(
    trade_id: int,
    exit_price: float,
    pnl: float,
    gross_pnl: float | None = None,
    fees: float = 0,
    funding: float = 0,
    exit_reason: str = "unknown",
    r_multiple: float | None = None,
    duration_min: int | None = None,
    accounting_status: str | None = None,
    accounting_notes: str | None = None,
) -> None:
    """Back-fill a trade when it closes in binance_monitor.py."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT symbol, direction, setup_grade, strategy, timeframe, exit_price, exit_reason, risk_dollars FROM trades WHERE id = ?",
            (trade_id,),
        ).fetchone()
        if not existing or existing["exit_price"] is not None:
            return
        if r_multiple is None and existing["risk_dollars"] and float(existing["risk_dollars"]) > 0:
            r_multiple = pnl / float(existing["risk_dollars"])
        final_accounting_status = accounting_status or "clean"
        conn.execute(
            """
            UPDATE trades
            SET exit_price   = ?,
                pnl          = ?,
                gross_pnl    = ?,
                fees         = ?,
                funding      = ?,
                exit_reason  = ?,
                r_multiple   = ?,
                duration_min = ?
                , execution_state = ?,
                accounting_status = ?,
                accounting_notes = ?,
                accounting_checked_at = ?
            WHERE id = ?
            """,
            (
                exit_price,
                pnl,
                gross_pnl,
                fees,
                funding,
                exit_reason,
                r_multiple,
                duration_min,
                "closed",
                final_accounting_status,
                accounting_notes,
                datetime.now(UTC).isoformat(),
                trade_id,
            ),
        )
        conn.commit()

    # Same-symbol loss cooldown tracking
    if pnl < 0:
        try:
            import loss_cooldowns
            loss_cooldowns.register_cooldown(
                trade_id=trade_id,
                symbol=existing["symbol"],
                direction=existing["direction"],
                setup_grade=existing["setup_grade"] or "A",
                strategy=existing["strategy"] or "unknown",
                timeframe=existing["timeframe"] or "1h",
                pnl=pnl,
                is_live_micro=_runtime_is_live_micro()
            )
        except Exception as ex:
            logger.error(f"Error registering loss cooldown for trade {trade_id}: {ex}")

    _journal_event(
        event_type="trade_closed",
        trade_id=trade_id,
        symbol=existing["symbol"],
        previous_state="open",
        new_state=exit_reason,
        raw_payload={"exit_price": exit_price, "pnl": pnl, "r_multiple": r_multiple},
        actor="monitor",
    )


def log_exit(
    trade_id: int,
    exit_type: str,
    price: float | None = None,
    pnl_contribution: float | None = None,
    qty_pct: float | None = None,
    notes: str | None = None,
) -> None:
    """Record a partial or full exit event (tiered exits, trailing stop, etc.)."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO exits (trade_id, exit_type, price, pnl_contribution, qty_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (trade_id, exit_type, price, pnl_contribution, qty_pct, notes),
        )
        conn.commit()
    _journal_event(
        event_type=f"exit_{exit_type}",
        trade_id=trade_id,
        previous_state=None,
        new_state=exit_type,
        raw_payload={"price": price, "pnl_contribution": pnl_contribution, "qty_pct": qty_pct, "notes": notes},
        actor="monitor",
    )


def log_milestone(
    trade_id: int,
    milestone: str,
    price: float | None = None,
    pnl: float | None = None,
) -> bool:
    """Log a milestone hit for a trade. Returns True if newly inserted."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO milestones (trade_id, milestone, price, pnl)
                VALUES (?, ?, ?, ?)
                """,
                (trade_id, milestone, price, pnl),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("log_milestone failed: %s", e)
        return False


def milestone_exists(trade_id: int, milestone: str) -> bool:
    """Check if a milestone has already been logged for a trade."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM milestones WHERE trade_id = ? AND milestone = ?",
                (trade_id, milestone),
            ).fetchone()
            return row is not None
    except Exception as e:
        logger.error("milestone_exists failed: %s", e)
        return False


def update_trade_qty(trade_id: int, qty: float) -> None:
    """Update the executed quantity on a trade after broker fill."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE trades SET qty = ? WHERE id = ?",
                (qty, trade_id),
            )
            conn.commit()
    except Exception as e:
        logger.error("update_trade_qty failed: %s", e)


def update_trade_risk(trade_id: int, risk_dollars: float, reward_dollars: float | None = None) -> None:
    """Update actual risk/reward when executable broker size changes."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET risk_dollars = ?,
                    reward_dollars = COALESCE(?, reward_dollars)
                WHERE id = ?
                """,
                (risk_dollars, reward_dollars, trade_id),
            )
            conn.commit()
    except Exception as e:
        logger.error("update_trade_risk failed: %s", e)


def update_trade_fill(trade_id: int, entry_price: float | None, qty: float | None) -> None:
    """Persist actual broker fill details after a planned trade reaches the exchange."""
    valid_entry_price = entry_price if entry_price is not None and float(entry_price) > 0 else None
    with _connect() as conn:
        conn.execute(
            """
            UPDATE trades
            SET entry_price = COALESCE(?, entry_price),
                qty = COALESCE(?, qty)
            WHERE id = ?
            """,
            (valid_entry_price, qty, trade_id),
        )
        conn.commit()


def update_execution_state(trade_id: int, state: str, actor: str = "bot", payload: dict | None = None) -> bool:
    """Move a trade execution state and append a journal event."""
    with _connect() as conn:
        row = conn.execute("SELECT symbol, execution_state FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            return False
        previous = row["execution_state"]
        conn.execute("UPDATE trades SET execution_state = ? WHERE id = ?", (state, trade_id))
        conn.commit()
    _journal_event(
        event_type="execution_state",
        trade_id=trade_id,
        symbol=row["symbol"],
        previous_state=previous,
        new_state=state,
        raw_payload=payload,
        actor=actor,
    )
    return True


def confirm_trade(trade_id: int, actor: str = "webhook") -> bool:
    """Confirm an open trade only when an SL anchor exists."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT symbol, execution_state, sl, exit_price FROM trades WHERE id = ?",
            (trade_id,),
        ).fetchone()
    if not row or row["exit_price"] is not None or row["sl"] is None:
        return False
    return update_execution_state(
        trade_id,
        "confirmed",
        actor=actor,
        payload={"sl": row["sl"]},
    )


def update_trade_peak(trade_id: int, peak_pnl: float, peak_price: float) -> None:
    """Update the peak PnL and peak price for a trade."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET peak_pnl = MAX(COALESCE(peak_pnl, 0), ?),
                    peak_price = CASE WHEN COALESCE(peak_pnl, 0) < ? THEN ? ELSE peak_price END
                WHERE id = ?
                """,
                (peak_pnl, peak_pnl, peak_price, trade_id),
            )
            conn.commit()
    except Exception as e:
        logger.error("update_trade_peak failed: %s", e)


def get_milestones_for_trade(trade_id: int) -> list[sqlite3.Row]:
    """Return all milestones for a trade, ordered by time."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM milestones WHERE trade_id = ? ORDER BY ts",
            (trade_id,),
        ).fetchall()


def get_exits_for_trade(trade_id: int) -> list[sqlite3.Row]:
    """Return all exit events for a trade, ordered by time."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM exits WHERE trade_id = ? ORDER BY ts",
            (trade_id,),
        ).fetchall()


def get_realized_exit_pnl(trade_id: int) -> float:
    """Return PnL already realized by exit rows before the final close."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(pnl_contribution), 0) AS pnl
            FROM exits
            WHERE trade_id = ?
              AND pnl_contribution IS NOT NULL
            """,
            (trade_id,),
        ).fetchone()
    return float(row["pnl"] or 0) if row else 0.0


def get_realized_exit_qty_pct(trade_id: int) -> float:
    """Return the original-position fraction already closed by partial exits."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_pct), 0) AS qty_pct
            FROM exits
            WHERE trade_id = ?
              AND qty_pct IS NOT NULL
              AND COALESCE(qty_pct, 0) < 1.0
              AND COALESCE(notes, '') NOT LIKE '%terminal=true%'
            """,
            (trade_id,),
        ).fetchone()
    return float(row["qty_pct"] or 0) if row else 0.0


def update_trade_accounting_status(trade_id: int, status: str, notes: str | None = None) -> bool:
    """Persist the data-quality classification for a trade row."""
    status = str(status or "unchecked").lower()
    if status not in {"clean", "corrected", "dirty", "unchecked"}:
        raise ValueError(f"Unsupported accounting status: {status}")
    with _connect() as conn:
        row = conn.execute("SELECT symbol, accounting_status FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            return False
        previous = row["accounting_status"]
        conn.execute(
            """
            UPDATE trades
            SET accounting_status = ?,
                accounting_notes = ?,
                accounting_checked_at = ?
            WHERE id = ?
            """,
            (status, notes, datetime.now(UTC).isoformat(), trade_id),
        )
        conn.commit()
    _journal_event(
        event_type="accounting_status",
        trade_id=trade_id,
        symbol=row["symbol"],
        previous_state=previous,
        new_state=status,
        raw_payload={"notes": notes},
        actor="truth_layer",
    )
    return True


def classify_trade_accounting(
    trade_id: int,
    *,
    known_corrected: bool = False,
    persist: bool = True,
) -> dict:
    """Classify one closed trade as clean, corrected, dirty, or unchecked.

    ``dirty`` means stored PnL conflicts with immutable directional math.
    ``corrected`` means the stored row is mathematically consistent now, but
    there is evidence it was repaired by the accounting reconciliation layer.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not row:
        return {"trade_id": trade_id, "status": "unchecked", "notes": "trade not found"}
    if row["exit_price"] is None or row["pnl"] is None:
        result = {"trade_id": trade_id, "status": "unchecked", "notes": "trade is not closed"}
        if persist:
            update_trade_accounting_status(trade_id, "unchecked", result["notes"])
        return result
    if row["entry_price"] in (None, 0) or row["qty"] in (None, 0):
        result = {"trade_id": trade_id, "status": "dirty", "notes": "missing entry or quantity anchor"}
        if persist:
            update_trade_accounting_status(trade_id, "dirty", result["notes"])
        return result

    partial_pnl = get_realized_exit_pnl(trade_id)
    partial_qty_pct = get_realized_exit_qty_pct(trade_id)
    audit = reconcile_trade_close_pnl(
        direction=row["direction"],
        entry_price=row["entry_price"],
        exit_price=row["exit_price"],
        original_qty=row["qty"],
        realized_partial_pnl=partial_pnl,
        realized_partial_qty_pct=partial_qty_pct,
        fallback_pnl=row["pnl"],
    )
    stored_pnl = float(row["pnl"])
    reconstructed_pnl = float(audit["pnl"])
    # Directional sign check: a profitable BUY must have exit > entry;
    # a profitable SELL must have exit < entry.  If the sign is impossible,
    # the stored row is definitely dirty.
    entry = float(row["entry_price"] or 0)
    exit_ = float(row["exit_price"] or 0)
    side = str(row["direction"] or "").upper()
    sign_impossible = False
    if entry > 0 and exit_ > 0:
        if side == "BUY":
            sign_impossible = (exit_ > entry and stored_pnl < 0) or (exit_ < entry and stored_pnl > 0)
        elif side == "SELL":
            sign_impossible = (exit_ < entry and stored_pnl < 0) or (exit_ > entry and stored_pnl > 0)

    if audit["mismatch"] and sign_impossible:
        status = "dirty"
        notes = (
            f"stored pnl {stored_pnl:.8f} has impossible sign for {side} "
            f"entry={entry:.8f} exit={exit_:.8f}; reconstructed {reconstructed_pnl:.8f}"
        )
    elif audit["mismatch"]:
        # Reconstruction differs but the sign is plausible.  The stored PnL may
        # include contract-size multipliers, leverage, partial-exit rounding, or
        # fees/funding that the simple directional math does not capture.  Mark
        # as unchecked rather than falsely dirty.
        status = "unchecked"
        notes = (
            f"stored pnl {stored_pnl:.8f} differs from reconstructed "
            f"{reconstructed_pnl:.8f}; manual/contract review required"
        )
    elif known_corrected or row["accounting_status"] == "corrected":
        status = "corrected"
        notes = "stored pnl reconciles after accounting correction"
    else:
        status = "clean"
        notes = "stored pnl reconciles with directional math"
    result = {
        "trade_id": trade_id,
        "symbol": row["symbol"],
        "status": status,
        "notes": notes,
        "stored_pnl": row["pnl"],
        "reconstructed_pnl": audit["pnl"],
        "remaining_qty": audit["remaining_qty"],
        "realized_partial_pnl": audit["realized_partial_pnl"],
        "realized_partial_qty_pct": audit["realized_partial_qty_pct"],
    }
    if persist:
        update_trade_accounting_status(trade_id, status, notes)
    return result


def classify_closed_trade_accounting(
    *,
    corrected_trade_ids: set[int] | None = None,
    limit: int | None = None,
) -> dict:
    """Classify closed rows and return a status summary."""
    corrected_trade_ids = corrected_trade_ids or set()
    sql = """
        SELECT id
        FROM trades
        WHERE exit_price IS NOT NULL
          AND pnl IS NOT NULL
          AND COALESCE(source, 'live') != 'migrated'
        ORDER BY id DESC
    """
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    summary = {"clean": 0, "corrected": 0, "dirty": 0, "unchecked": 0, "classified": 0, "dirty_trade_ids": []}
    for row in rows:
        result = classify_trade_accounting(
            int(row["id"]),
            known_corrected=int(row["id"]) in corrected_trade_ids,
            persist=True,
        )
        status = result["status"]
        summary[status] = summary.get(status, 0) + 1
        summary["classified"] += 1
        if status == "dirty":
            summary["dirty_trade_ids"].append(int(row["id"]))
    return summary


def audit_closed_trade_math(limit: int = 100) -> list[dict]:
    """Return closed trades whose stored PnL conflicts with entry/exit math."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM trades
            WHERE exit_price IS NOT NULL
              AND entry_price IS NOT NULL
              AND qty IS NOT NULL
              AND pnl IS NOT NULL
              AND COALESCE(execution_state, '') = 'closed'
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    mismatches: list[dict] = []
    for row in rows:
        partial_pnl = get_realized_exit_pnl(row["id"])
        partial_qty_pct = get_realized_exit_qty_pct(row["id"])
        audit = reconcile_trade_close_pnl(
            direction=row["direction"],
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            original_qty=row["qty"],
            realized_partial_pnl=partial_pnl,
            realized_partial_qty_pct=partial_qty_pct,
            fallback_pnl=row["pnl"],
        )
        if audit["mismatch"]:
            mismatches.append(
                {
                    "trade_id": row["id"],
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "entry_price": row["entry_price"],
                    "exit_price": row["exit_price"],
                    "qty": row["qty"],
                    "stored_pnl": row["pnl"],
                    "reconciled_pnl": audit["pnl"],
                    "remaining_qty": audit["remaining_qty"],
                    "realized_partial_pnl": audit["realized_partial_pnl"],
                    "realized_partial_qty_pct": audit["realized_partial_qty_pct"],
                }
            )
    return mismatches


def _accounting_status_clause() -> str:
    return "COALESCE(accounting_status, 'clean') IN ('clean', 'corrected')"


def log_market_regime(symbol: str, regime: str | None = None, indicators: dict | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO market_regime_log (symbol, regime, indicators_json)
            VALUES (?, ?, ?)
            """,
            (symbol, regime, json.dumps(indicators, default=str) if indicators else None),
        )
        conn.commit()


# ------------------------------------------------------------------
# Read helpers
# ------------------------------------------------------------------
def get_open_trades(symbol: str | None = None) -> list[sqlite3.Row]:
    """Return trades that have not been closed yet (exit_price IS NULL)."""
    with _connect() as conn:
        sql = "SELECT * FROM trades WHERE exit_price IS NULL AND execution_state != 'shadow'"
        params = ()
        if symbol:
            sql += " AND symbol = ?"
            params = (symbol,)
        sql += " ORDER BY ts DESC"
        return conn.execute(sql, params).fetchall()


def count_trades_opened_today_sast() -> int:
    """Count non-migrated trade rows opened on the current SAST calendar day."""
    sast = ZoneInfo("Africa/Johannesburg")
    now_sast = datetime.now(sast)
    start_sast = datetime(now_sast.year, now_sast.month, now_sast.day, tzinfo=sast)
    end_sast = start_sast + timedelta(days=1)
    start_utc = start_sast.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    end_utc = end_sast.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS trade_count
            FROM trades
            WHERE datetime(ts) >= datetime(?)
              AND datetime(ts) < datetime(?)
              AND COALESCE(source, 'live') != 'migrated'
            """,
            (start_utc, end_utc),
        ).fetchone()
    return int(row["trade_count"] if row else 0)


def get_recent_closed_trade_stats(
    *,
    setup_grade: str | None = None,
    symbol: str | None = None,
    direction: str | None = None,
    strategy: str | None = None,
    execution_state: str | None = None,
    include_shadow: bool = True,
    include_dirty: bool = False,
    limit: int = 20,
) -> dict:
    """Return aggregate stats over recent clean closed trades."""
    clauses = [
        "pnl IS NOT NULL",
        "exit_price IS NOT NULL",
        "COALESCE(source, 'live') != 'migrated'",
    ]
    params: list = []
    if setup_grade:
        clauses.append("setup_grade = ?")
        params.append(setup_grade)
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    if strategy:
        clauses.append("strategy = ?")
        params.append(strategy)
    if execution_state:
        clauses.append("execution_state = ?")
        params.append(execution_state)
    elif not include_shadow:
        clauses.append("COALESCE(execution_state, 'confirmed') != 'shadow'")
    else:
        clauses.append("COALESCE(execution_state, 'closed') NOT IN ('shadow', 'fail_closed') AND COALESCE(exit_reason, '') NOT IN ('execution_failed', 'protection_truth_failed')")
    if not include_dirty:
        clauses.append(_accounting_status_clause())
    params.append(int(limit))

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT pnl, risk_dollars, r_multiple
            FROM trades
            WHERE {" AND ".join(clauses)}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    pnls = [float(r["pnl"]) for r in rows if r["pnl"] is not None]
    r_values = []
    for row in rows:
        if row["r_multiple"] is not None:
            r_values.append(float(row["r_multiple"]))
        elif row["pnl"] is not None and row["risk_dollars"] not in (None, 0):
            risk = abs(float(row["risk_dollars"]))
            if risk > 0:
                r_values.append(float(row["pnl"]) / risk)
    wins = sum(1 for pnl in pnls if pnl > 0)
    losses = sum(1 for pnl in pnls if pnl < 0)
    total_pnl = sum(pnls)
    sample_size = len(pnls)
    total_r = sum(r_values)
    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / sample_size if sample_size else None,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / sample_size if sample_size else None,
        "total_r": total_r,
        "avg_r": total_r / len(r_values) if r_values else None,
        "r_sample_size": len(r_values),
    }


def record_live_bootstrap_event(
    event_type: str,
    *,
    reason: str | None = None,
    trade_id: int | None = None,
    payload: dict | None = None,
    event_key: str | None = None,
    day_utc: str | None = None,
) -> bool:
    """Append an audited LIVE bootstrap operator or safety transition."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO live_bootstrap_events
                (day_utc, event_type, event_key, trade_id, reason, payload_json)
            VALUES (COALESCE(?, date('now')), ?, ?, ?, ?, ?)
            """,
            (
                day_utc,
                event_type,
                event_key,
                trade_id,
                reason,
                json.dumps(payload, default=str) if payload else None,
            ),
        )
        conn.commit()
        inserted = bool(cur.rowcount)
    if inserted:
        _journal_event(
            event_type=f"live_bootstrap_{event_type}",
            trade_id=trade_id,
            previous_state=None,
            new_state=event_type,
            raw_payload={"reason": reason, **(payload or {})},
            actor="operator" if event_type == "rearm_authorized" else "risk_policy",
        )
    return inserted


def authorize_live_rearm(reason: str, payload: dict | None = None, day_utc: str | None = None) -> bool:
    """Persist an explicit one-shot operator LIVE re-arm authorization."""
    return record_live_bootstrap_event(
        "rearm_authorized",
        reason=reason,
        payload=payload,
        event_key=f"operator_rearm:{day_utc or datetime.now(UTC).date().isoformat()}",
        day_utc=day_utc,
    )


def consume_live_rearm(trade_id: int, payload: dict | None = None, day_utc: str | None = None) -> bool:
    """Consume the armed reduced-risk next LIVE trade once."""
    return record_live_bootstrap_event(
        "rearm_consumed",
        reason="reduced-risk LIVE trade accepted after safety re-arm",
        trade_id=trade_id,
        payload=payload,
        event_key=f"trade:{trade_id}",
        day_utc=day_utc,
    )


def get_live_daily_loss_state(target_loss_at_sl_usd: float, day_utc: str | None = None) -> dict:
    """Return realized loss plus split LIVE bootstrap strategy/safety counters."""
    default_full_loss_floor = max(0.0, float(target_loss_at_sl_usd or 0.0) * 0.95)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, ts, pnl, exit_reason, risk_dollars, sl, execution_state
            FROM trades
            WHERE exit_price IS NOT NULL
              AND pnl IS NOT NULL
              AND mode = 'live'
              AND COALESCE(source, 'live') != 'migrated'
              AND date(ts) = COALESCE(?, date('now'))
            """,
            (day_utc,),
        ).fetchall()
        events = conn.execute(
            """
            SELECT ts, event_type, reason, trade_id
            FROM live_bootstrap_events
            WHERE day_utc = COALESCE(?, date('now'))
            ORDER BY datetime(ts), id
            """,
            (day_utc,),
        ).fetchall()

    realized_loss = sum(abs(float(row["pnl"])) for row in rows if float(row["pnl"]) < 0)
    safety_exit_reasons = {"missing_sl", "protection_truth_failed", "execution_failed"}
    strategy_full_losses = 0
    safety_incidents = []
    for row in rows:
        pnl = float(row["pnl"])
        exit_reason = str(row["exit_reason"] or "")
        if exit_reason in safety_exit_reasons or str(row["execution_state"] or "") == "fail_closed":
            safety_incidents.append({"ts": row["ts"], "reason": exit_reason or "fail_closed", "trade_id": row["id"]})
            continue
        risk_anchor = max(0.0, float(row["risk_dollars"] or 0.0))
        full_loss_floor = (risk_anchor or default_full_loss_floor) * 0.95
        confirmed_protected = row["sl"] is not None and exit_reason not in safety_exit_reasons
        if confirmed_protected and (
            exit_reason == "sl" or (full_loss_floor > 0 and pnl <= -full_loss_floor)
        ):
            strategy_full_losses += 1

    # Calculate consecutive losses (oldest to newest)
    sorted_rows = sorted(rows, key=lambda r: r["ts"] or "")
    consecutive_losses = 0
    for r in sorted_rows:
        pnl = float(r["pnl"] or 0.0)
        if pnl < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0

    event_safety_incidents = [
        {"ts": event["ts"], "reason": event["reason"] or event["event_type"], "trade_id": event["trade_id"]}
        for event in events
        if event["event_type"] == "safety_incident"
    ]
    safety_incidents.extend(event_safety_incidents)
    rearm_authorizations = [event for event in events if event["event_type"] == "rearm_authorized"]
    rearm_consumptions = [event for event in events if event["event_type"] == "rearm_consumed"]
    latest_rearm_ts = rearm_authorizations[-1]["ts"] if rearm_authorizations else None
    latest_consumed_ts = rearm_consumptions[-1]["ts"] if rearm_consumptions else None
    consumed_trade_ids = {event["trade_id"] for event in rearm_consumptions if event["trade_id"] is not None}
    safety_after_rearm = [
        incident
        for incident in safety_incidents
        if latest_consumed_ts is not None
        and (
            incident.get("trade_id") in consumed_trade_ids
            or str(incident["ts"]) > str(latest_consumed_ts)
        )
    ]
    open_rearm_authorizations = max(0, len(rearm_authorizations) - len(rearm_consumptions))
    return {
        "daily_realized_loss_usd": realized_loss,
        "daily_strategy_full_losses": strategy_full_losses,
        "daily_safety_incidents": len(safety_incidents),
        "daily_safety_incident_details": safety_incidents,
        "daily_safety_incidents_after_rearm": len(safety_after_rearm),
        "rearm_authorized_count": len(rearm_authorizations),
        "rearm_open_authorizations": open_rearm_authorizations,
        "rearm_used_count": len(rearm_consumptions),
        "latest_rearm_ts": latest_rearm_ts,
        "latest_rearm_consumed_ts": latest_consumed_ts,
        "closed_live_trades": len(rows),
        "day_utc": day_utc,
        "daily_consecutive_losses": consecutive_losses,
        "daily_trades_count": len(rows),
    }


def get_latest_trade_age_hours() -> float | None:
    """Return hours since the latest non-migrated trade row, or None if no trades exist."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT ts
            FROM trades
            WHERE COALESCE(source, 'live') != 'migrated'
            ORDER BY datetime(ts) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row or not row["ts"]:
        return None

    ts_raw = str(row["ts"])
    try:
        trade_ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        trade_ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
    if trade_ts.tzinfo is None:
        trade_ts = trade_ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - trade_ts.astimezone(UTC)).total_seconds() / 3600


def get_trade_by_id(trade_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return row


def upsert_binance_order_state(
    symbol: str,
    tv_symbol: str | None = None,
    side: str | None = None,
    entry_order_id: str | None = None,
    sl_order_id: str | None = None,
    tp_order_id: str | None = None,
    original_qty: float | None = None,
    remaining_qty: float | None = None,
    entry_price: float | None = None,
    original_sl: float | None = None,
    current_sl: float | None = None,
    current_tp: float | None = None,
    original_sl_distance: float | None = None,
    realized_partial_exits: list | None = None,
    runner_status: str | None = None,
    raw_state: dict | None = None,
) -> None:
    """Persist Binance protective order state for monitor restart reconciliation."""
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM binance_order_state WHERE symbol = ?", (symbol,)).fetchone()
        payload = {
            "symbol": symbol,
            "tv_symbol": tv_symbol,
            "side": side,
            "entry_order_id": entry_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "original_qty": original_qty,
            "remaining_qty": remaining_qty,
            "entry_price": entry_price,
            "original_sl": original_sl,
            "current_sl": current_sl,
            "current_tp": current_tp,
            "original_sl_distance": original_sl_distance,
            "realized_partial_exits_json": json.dumps(realized_partial_exits or [], default=str)
            if realized_partial_exits is not None
            else None,
            "runner_status": runner_status,
            "raw_state_json": json.dumps(raw_state or {}, default=str) if raw_state is not None else None,
        }
        if existing:
            merged = {k: payload[k] if payload[k] is not None else existing[k] for k in payload}
            conn.execute(
                """
                UPDATE binance_order_state
                SET tv_symbol = ?, side = ?, entry_order_id = ?, sl_order_id = ?, tp_order_id = ?,
                    original_qty = ?, remaining_qty = ?, entry_price = ?, original_sl = ?,
                    current_sl = ?, current_tp = ?, original_sl_distance = ?,
                    realized_partial_exits_json = ?, runner_status = ?, raw_state_json = ?,
                    updated_ts = datetime('now')
                WHERE symbol = ?
                """,
                (
                    merged["tv_symbol"],
                    merged["side"],
                    merged["entry_order_id"],
                    merged["sl_order_id"],
                    merged["tp_order_id"],
                    merged["original_qty"],
                    merged["remaining_qty"],
                    merged["entry_price"],
                    merged["original_sl"],
                    merged["current_sl"],
                    merged["current_tp"],
                    merged["original_sl_distance"],
                    merged["realized_partial_exits_json"],
                    merged["runner_status"],
                    merged["raw_state_json"],
                    symbol,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO binance_order_state (
                    symbol, tv_symbol, side, entry_order_id, sl_order_id, tp_order_id,
                    original_qty, remaining_qty, entry_price, original_sl, current_sl,
                    current_tp, original_sl_distance, realized_partial_exits_json,
                    runner_status, raw_state_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["symbol"],
                    payload["tv_symbol"],
                    payload["side"],
                    payload["entry_order_id"],
                    payload["sl_order_id"],
                    payload["tp_order_id"],
                    payload["original_qty"],
                    payload["remaining_qty"],
                    payload["entry_price"],
                    payload["original_sl"],
                    payload["current_sl"],
                    payload["current_tp"],
                    payload["original_sl_distance"],
                    payload["realized_partial_exits_json"],
                    payload["runner_status"],
                    payload["raw_state_json"],
                ),
            )
        conn.commit()


def get_binance_order_state(symbol: str) -> sqlite3.Row | None:
    """Return persisted Binance order state for a symbol."""
    with _connect() as conn:
        return conn.execute("SELECT * FROM binance_order_state WHERE symbol = ?", (symbol,)).fetchone()


def get_binance_order_states() -> list[sqlite3.Row]:
    """Return all persisted Binance order-state rows."""
    with _connect() as conn:
        return conn.execute("SELECT * FROM binance_order_state ORDER BY updated_ts DESC").fetchall()


def delete_binance_order_state(symbol: str) -> None:
    """Remove Binance order state for a closed position (cleanup)."""
    with _connect() as conn:
        conn.execute("DELETE FROM binance_order_state WHERE symbol = ?", (symbol,))
        conn.commit()


def get_signal_gates(signal_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM trade_gates WHERE signal_id = ? ORDER BY id",
            (signal_id,),
        ).fetchall()


def get_latest_signal(symbol: str, direction: str | None = None, within_sec: int = 300) -> sqlite3.Row | None:
    """Get the most recent signal for a symbol (optionally direction) within a time window."""
    cutoff = (datetime.now(UTC) - timedelta(seconds=within_sec)).isoformat()
    with _connect() as conn:
        sql = "SELECT * FROM signals WHERE symbol = ? AND ts > ?"
        params: tuple = (symbol, cutoff)
        if direction:
            sql += " AND direction = ?"
            params += (direction,)
        sql += " ORDER BY ts DESC LIMIT 1"
        return conn.execute(sql, params).fetchone()


# ------------------------------------------------------------------
# Weekly report
# ------------------------------------------------------------------
def weekly_report(week_start_iso: str | None = None) -> dict:
    """
    Generate weekly analytics.
    week_start_iso: ISO date string e.g. '2026-05-04'. Defaults to current week (Mon).
    Returns dict with:
      - best_pf_symbol
      - exit_method_ranking
      - false_negative_gates
    """
    if week_start_iso is None:
        today = datetime.now(UTC).date()
        monday = today - timedelta(days=today.weekday())
        week_start_iso = monday.isoformat()

    week_end_iso = (datetime.fromisoformat(week_start_iso) + timedelta(days=7)).isoformat()

    with _connect() as conn:
        # 1. Best PF by symbol (only closed trades)
        rows = conn.execute(
            """
            SELECT symbol,
                   COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses
            FROM trades
            WHERE ts >= ? AND ts < ? AND exit_price IS NOT NULL
              AND source != 'migrated'
              AND COALESCE(accounting_status, 'clean') IN ('clean', 'corrected')
              AND COALESCE(execution_state, 'closed') NOT IN ('shadow', 'fail_closed') AND COALESCE(exit_reason, '') NOT IN ('execution_failed', 'protection_truth_failed')
            GROUP BY symbol
            HAVING wins + losses > 0
            """,
            (week_start_iso, week_end_iso),
        ).fetchall()

        best_pf = {"symbol": None, "pf": 0.0, "wins": 0, "losses": 0}
        for r in rows:
            wins, losses = r["wins"], r["losses"]
            pf = wins / losses if losses else float("inf")
            if pf > best_pf["pf"]:
                best_pf = {"symbol": r["symbol"], "pf": round(pf, 2), "wins": wins, "losses": losses}

        # 2. Exit method profit capture ranking
        exit_rows = conn.execute(
            """
            SELECT exit_reason,
                   COUNT(*) as count,
                   SUM(pnl) as total_pnl,
                   AVG(pnl) as avg_pnl,
                   AVG(r_multiple) as avg_r
            FROM trades
            WHERE ts >= ? AND ts < ? AND exit_price IS NOT NULL
              AND source != 'migrated'
              AND COALESCE(accounting_status, 'clean') IN ('clean', 'corrected')
              AND COALESCE(execution_state, 'closed') NOT IN ('shadow', 'fail_closed') AND COALESCE(exit_reason, '') NOT IN ('execution_failed', 'protection_truth_failed')
            GROUP BY exit_reason
            """,
            (week_start_iso, week_end_iso),
        ).fetchall()

        exit_ranking = []
        for r in exit_rows:
            exit_ranking.append({
                "reason": r["exit_reason"] or "unknown",
                "count": r["count"],
                "total_pnl": round(r["total_pnl"] or 0, 2),
                "avg_pnl": round(r["avg_pnl"] or 0, 2),
                "avg_r": round(r["avg_r"] or 0, 2),
            })
        exit_ranking.sort(key=lambda x: x["total_pnl"], reverse=True)

        # 3. False negative gates (rejected signals where price later went to TP)
        fn_rows = conn.execute(
            """
            SELECT g.gate_name,
                   COUNT(DISTINCT g.signal_id) as rejected_count,
                   s.symbol,
                   s.entry_price,
                   s.direction
            FROM trade_gates g
            JOIN signals s ON s.id = g.signal_id
            WHERE g.decision = 'rejected'
              AND g.ts >= ? AND g.ts < ?
              AND EXISTS (
                  SELECT 1 FROM trades t
                  WHERE t.symbol = s.symbol
                    AND t.direction = s.direction
                    AND t.signal_id > s.id
                    AND t.pnl > 0
                    AND t.source != 'migrated'
              )
            GROUP BY g.gate_name
            """,
            (week_start_iso, week_end_iso),
        ).fetchall()

        false_negatives = []
        for r in fn_rows:
            false_negatives.append({
                "gate_name": r["gate_name"],
                "rejected_count": r["rejected_count"],
            })
        false_negatives.sort(key=lambda x: x["rejected_count"], reverse=True)

    return {
        "week": week_start_iso,
        "best_pf_symbol": best_pf,
        "exit_method_ranking": exit_ranking,
        "false_negative_gates": false_negatives,
    }


def get_false_negative_gates(days: int = 7) -> list[dict]:
    """Standalone helper: gates that rejected signals where a later same-direction trade was profitable."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT g.gate_name,
                   COUNT(DISTINCT g.signal_id) as rejected_count
            FROM trade_gates g
            JOIN signals s ON s.id = g.signal_id
            WHERE g.decision = 'rejected'
              AND g.ts > ?
              AND EXISTS (
                  SELECT 1 FROM trades t
                  WHERE t.symbol = s.symbol
                    AND t.direction = s.direction
                    AND t.signal_id > s.id
                    AND t.pnl > 0
                    AND t.source != 'migrated'
              )
            GROUP BY g.gate_name
            ORDER BY rejected_count DESC
            """,
            (cutoff,),
        ).fetchall()
        return [{"gate_name": r["gate_name"], "rejected_count": r["rejected_count"]} for r in rows]


# ------------------------------------------------------------------
# Milestone config (stored in gate_thresholds)
# ------------------------------------------------------------------
def get_milestone_config(symbol: str) -> list[dict]:
    """Return milestone config for a symbol. Per-symbol overrides merge with DEFAULT fallbacks.
    Each dict: {'gate_name': 'milestone_1', 'threshold': 1.5, 'close_pct': 0.50}
    """
    with _connect() as conn:
        # Fetch per-symbol overrides
        sym_rows = conn.execute(
            """
            SELECT gate_name, threshold, params_json
            FROM gate_thresholds
            WHERE symbol = ? AND gate_name LIKE 'milestone_%'
            """,
            (symbol,),
        ).fetchall()
        # Fetch defaults
        def_rows = conn.execute(
            """
            SELECT gate_name, threshold, params_json
            FROM gate_thresholds
            WHERE symbol = 'DEFAULT' AND gate_name LIKE 'milestone_%'
            """,
        ).fetchall()

    # Merge: per-symbol wins, missing gates fall back to DEFAULT
    merged = {}
    for r in def_rows:
        params = json.loads(r["params_json"]) if r["params_json"] else {}
        merged[r["gate_name"]] = {
            "gate_name": r["gate_name"],
            "threshold": r["threshold"],
            "close_pct": params.get("close_pct", 0.50),
        }
    for r in sym_rows:
        params = json.loads(r["params_json"]) if r["params_json"] else {}
        merged[r["gate_name"]] = {
            "gate_name": r["gate_name"],
            "threshold": r["threshold"],
            "close_pct": params.get("close_pct", 0.50),
        }

    return sorted(merged.values(), key=lambda x: x["threshold"])


def seed_milestone_thresholds() -> None:
    """Insert or refresh lane-aware milestone configs for monitor-managed exits."""
    from config import EXIT_MILESTONE_PROFILES, SYMBOL_EXIT_PROFILE, get_exit_milestones_for_symbol

    rows = [
        (
            "DEFAULT",
            milestone["gate_name"],
            float(milestone["threshold"]),
            json.dumps({"close_pct": float(milestone["close_pct"])}),
        )
        for milestone in EXIT_MILESTONE_PROFILES["macro"]
    ]
    for symbol in sorted(SYMBOL_EXIT_PROFILE):
        rows.extend(
            (
                symbol,
                milestone["gate_name"],
                float(milestone["threshold"]),
                json.dumps({"close_pct": float(milestone["close_pct"])}),
            )
            for milestone in get_exit_milestones_for_symbol(symbol)
        )

    with _connect() as conn:
        symbols = sorted({"DEFAULT", *SYMBOL_EXIT_PROFILE.keys()})
        placeholders = ",".join("?" for _ in symbols)
        conn.execute(
            f"DELETE FROM gate_thresholds WHERE symbol IN ({placeholders}) AND gate_name LIKE 'milestone_%'",
            symbols,
        )
        for symbol, gate_name, threshold, params_json in rows:
            conn.execute(
                """
                INSERT INTO gate_thresholds (symbol, gate_name, threshold, params_json, updated_ts)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(symbol, gate_name) DO UPDATE SET
                    threshold = excluded.threshold,
                    params_json = excluded.params_json,
                    updated_ts = datetime('now')
                """,
                (symbol, gate_name, threshold, params_json),
            )
        conn.commit()


def get_recent_choch_alert(symbol: str, minutes: int = 30) -> list[sqlite3.Row]:
    """Return recent choch_reversal gate decisions for a symbol."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM trade_gates
            WHERE gate_name = 'choch_reversal'
              AND ts > ?
              AND EXISTS (
                  SELECT 1 FROM trades t
                  WHERE t.id = trade_gates.trade_id
                    AND t.symbol = ?
                    AND t.exit_price IS NULL
              )
            ORDER BY ts DESC
            LIMIT 1
            """,
            (cutoff, symbol),
        ).fetchall()


# ------------------------------------------------------------------
# CLI / cron entrypoint
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    report = weekly_report(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(report, indent=2, default=str))
