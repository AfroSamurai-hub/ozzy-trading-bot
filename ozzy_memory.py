"""SQLite decision memory for setup outcomes and append-only trade events."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config import BINANCE_TESTNET, OZZY_MEMORY_DB
from historical_ohlc import fetch_candles

DB_PATH = Path(OZZY_MEMORY_DB)
WINDOWS = {"1h": 1, "4h": 4, "8h": 8, "24h": 24}
_SCHEMA_VERSION = "2026-05-21-phase1"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setup_events (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    instance_mode TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    timeframe TEXT,
    grade TEXT,
    decision TEXT NOT NULL,
    reason TEXT,
    reason_json TEXT,
    indicators_json TEXT,
    proposed_entry REAL,
    proposed_sl REAL,
    proposed_tp REAL,
    rr REAL,
    risk_usd REAL,
    source_trade_id TEXT,
    live_gating_verdict TEXT,
    risk_multiplier REAL
);
CREATE INDEX IF NOT EXISTS idx_memory_events_symbol_ts ON setup_events(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_events_decision ON setup_events(decision, instance_mode);

CREATE TABLE IF NOT EXISTS setup_outcomes (
    outcome_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES setup_events(event_id),
    window TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    mfe_r REAL,
    mae_r REAL,
    final_r REAL,
    hit_0_5r INTEGER,
    hit_1r INTEGER,
    hit_2r INTEGER,
    hit_sl INTEGER,
    hit_tp INTEGER,
    reversed INTEGER,
    time_to_mfe_minutes REAL,
    time_to_mae_minutes REAL,
    entry_quality TEXT,
    exit_quality TEXT,
    protection_quality TEXT,
    notes TEXT,
    UNIQUE(event_id, window)
);
CREATE INDEX IF NOT EXISTS idx_memory_outcomes_event ON setup_outcomes(event_id, window);

CREATE TABLE IF NOT EXISTS memory_verdicts (
    verdict_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    symbol TEXT,
    direction TEXT,
    grade TEXT,
    verdict TEXT NOT NULL,
    sample_count INTEGER,
    avg_mfe_r REAL,
    avg_mae_r REAL,
    avg_final_r REAL,
    reason TEXT NOT NULL,
    action_taken TEXT,
    safety_issue INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trade_journal_events (
    journal_event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    trade_id TEXT,
    symbol TEXT,
    event_type TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    exchange_payload_hash TEXT,
    raw_payload_json TEXT,
    actor TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_journal_trade ON trade_journal_events(trade_id, created_at);
"""


def instance_mode() -> str:
    """Return the process mode used on memory rows."""
    if BINANCE_TESTNET:
        return "TESTNET"
    return "LIVE_MICRO"


@contextmanager
def _connect(path: Path | None = None):
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (_SCHEMA_VERSION, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


def ensure_schema(path: Path | None = None) -> None:
    """Create the memory DB and idempotent Phase 1 tables."""
    with _connect(path):
        pass


def _json(value) -> str | None:
    return json.dumps(value, default=str, sort_keys=True) if value is not None else None


def record_setup_event(  # noqa: PLR0913
    *,
    symbol: str,
    direction: str,
    decision: str,
    event_id: str | None = None,
    timeframe: str | None = None,
    grade: str | None = None,
    reason: str | None = None,
    reason_json=None,
    indicators=None,
    proposed_entry: float | None = None,
    proposed_sl: float | None = None,
    proposed_tp: float | None = None,
    rr: float | None = None,
    risk_usd: float | None = None,
    source_trade_id: str | int | None = None,
    live_gating_verdict: str | None = None,
    risk_multiplier: float | None = None,
    process_mode: str | None = None,
    created_at: str | None = None,
) -> str:
    """Insert one setup decision and keep duplicate event ids idempotent."""
    eid = event_id or str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO setup_events (
                event_id, created_at, instance_mode, symbol, direction, timeframe, grade,
                decision, reason, reason_json, indicators_json, proposed_entry, proposed_sl,
                proposed_tp, rr, risk_usd, source_trade_id, live_gating_verdict, risk_multiplier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                created_at or datetime.now(UTC).isoformat(),
                process_mode or instance_mode(),
                symbol,
                direction,
                timeframe,
                grade,
                decision,
                reason,
                _json(reason_json),
                _json(indicators),
                proposed_entry,
                proposed_sl,
                proposed_tp,
                rr,
                risk_usd,
                str(source_trade_id) if source_trade_id is not None else None,
                live_gating_verdict,
                risk_multiplier,
            ),
        )
        conn.commit()
    return eid


def record_trade_journal_event(  # noqa: PLR0913
    *,
    event_type: str,
    trade_id: str | int | None = None,
    symbol: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    raw_payload=None,
    actor: str = "bot",
) -> str:
    """Append an immutable trade timeline event."""
    event_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO trade_journal_events (
                journal_event_id, created_at, trade_id, symbol, event_type, previous_state,
                new_state, raw_payload_json, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                datetime.now(UTC).isoformat(),
                str(trade_id) if trade_id is not None else None,
                symbol,
                event_type,
                previous_state,
                new_state,
                _json(raw_payload),
                actor,
            ),
        )
        conn.commit()
    return event_id


def _candle_time_minutes(start: datetime, raw_ts: str) -> float:
    candle_ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    if candle_ts.tzinfo is None:
        candle_ts = candle_ts.replace(tzinfo=UTC)
    return (candle_ts.astimezone(UTC) - start).total_seconds() / 60


def compute_r_outcome(  # noqa: PLR0913
    direction: str,
    entry: float,
    sl: float,
    tp: float | None,
    candles: Iterable[dict],
    entry_ts: str | None = None,
) -> dict | None:
    """Compute R-based price excursion only when an entry/SL anchor exists."""
    risk = abs(float(entry) - float(sl))
    if risk <= 0:
        return None
    start = datetime.fromisoformat(entry_ts.replace("Z", "+00:00")) if entry_ts else datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    direction_u = direction.upper()
    favorable = []
    adverse = []
    finals = []
    timed_favorable = []
    timed_adverse = []
    hit_sl = False
    hit_tp = False
    for candle in candles:
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        if direction_u in {"BUY", "LONG"}:
            fav_r = (high - entry) / risk
            adv_r = (low - entry) / risk
            final_r = (close - entry) / risk
            hit_sl = hit_sl or low <= sl
            hit_tp = hit_tp or (tp is not None and high >= tp)
        else:
            fav_r = (entry - low) / risk
            adv_r = (entry - high) / risk
            final_r = (entry - close) / risk
            hit_sl = hit_sl or high >= sl
            hit_tp = hit_tp or (tp is not None and low <= tp)
        mins = _candle_time_minutes(start, candle["ts"]) if candle.get("ts") else None
        favorable.append(fav_r)
        adverse.append(adv_r)
        finals.append(final_r)
        timed_favorable.append((fav_r, mins))
        timed_adverse.append((adv_r, mins))
    if not finals:
        return None
    mfe_r, mfe_mins = max(timed_favorable, key=lambda item: item[0])
    mae_r, mae_mins = min(timed_adverse, key=lambda item: item[0])
    final_r = finals[-1]
    entry_quality = "good" if mfe_r >= 1.0 else "bad" if mfe_r < 0.25 and mae_r <= -0.5 else "neutral"
    exit_quality = "needs_review" if mfe_r >= 1.0 and final_r <= 0 else "neutral"
    return {
        "mfe_r": round(mfe_r, 6),
        "mae_r": round(mae_r, 6),
        "final_r": round(final_r, 6),
        "hit_0_5r": int(mfe_r >= 0.5),
        "hit_1r": int(mfe_r >= 1.0),
        "hit_2r": int(mfe_r >= 2.0),
        "hit_sl": int(hit_sl),
        "hit_tp": int(hit_tp),
        "reversed": int(mfe_r >= 0.5 and final_r <= 0),
        "time_to_mfe_minutes": mfe_mins,
        "time_to_mae_minutes": mae_mins,
        "entry_quality": entry_quality,
        "exit_quality": exit_quality,
        "protection_quality": "unknown",
    }


def save_outcome(event_id: str, window: str, outcome: dict, notes: str | None = None) -> None:
    """Store one computed outcome window idempotently."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO setup_outcomes (
                outcome_id, event_id, window, measured_at, mfe_r, mae_r, final_r, hit_0_5r,
                hit_1r, hit_2r, hit_sl, hit_tp, reversed, time_to_mfe_minutes,
                time_to_mae_minutes, entry_quality, exit_quality, protection_quality, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{event_id}:{window}",
                event_id,
                window,
                datetime.now(UTC).isoformat(),
                outcome.get("mfe_r"),
                outcome.get("mae_r"),
                outcome.get("final_r"),
                outcome.get("hit_0_5r"),
                outcome.get("hit_1r"),
                outcome.get("hit_2r"),
                outcome.get("hit_sl"),
                outcome.get("hit_tp"),
                outcome.get("reversed"),
                outcome.get("time_to_mfe_minutes"),
                outcome.get("time_to_mae_minutes"),
                outcome.get("entry_quality"),
                outcome.get("exit_quality"),
                outcome.get("protection_quality"),
                notes,
            ),
        )
        conn.commit()


def label_pending_outcomes(now: datetime | None = None) -> dict:
    """Backfill due R outcome windows for events with a valid entry and SL."""
    now_utc = now or datetime.now(UTC)
    updated = 0
    unavailable = 0
    with _connect() as conn:
        events = conn.execute(
            """
            SELECT e.*
            FROM setup_events e
            WHERE e.proposed_entry IS NOT NULL AND e.proposed_sl IS NOT NULL
            ORDER BY e.created_at
            """
        ).fetchall()
        existing = {
            (row["event_id"], row["window"])
            for row in conn.execute("SELECT event_id, window FROM setup_outcomes").fetchall()
        }
    for event in events:
        created = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        for window, hours in WINDOWS.items():
            if (event["event_id"], window) in existing or now_utc < created + timedelta(hours=hours):
                continue
            candles, meta = fetch_candles(
                event["symbol"],
                event["created_at"],
                (created + timedelta(hours=hours)).isoformat(),
            )
            outcome = compute_r_outcome(
                event["direction"],
                event["proposed_entry"],
                event["proposed_sl"],
                event["proposed_tp"],
                candles,
                event["created_at"],
            )
            if not meta.get("reliable") or outcome is None:
                unavailable += 1
                continue
            save_outcome(event["event_id"], window, outcome, notes=f"provider={meta.get('provider')}")
            updated += 1
    return {"updated": updated, "unavailable": unavailable}


def record_memory_verdict(  # noqa: PLR0913
    *,
    symbol: str | None,
    direction: str | None,
    grade: str | None,
    sample_count: int,
    avg_mfe_r: float | None,
    avg_mae_r: float | None,
    avg_final_r: float | None,
    safety_issue: bool = False,
) -> dict:
    """Persist a non-oracular verdict that reduces before it blocks."""
    if safety_issue:
        verdict, action, reason = "watch", "safety_observation", "safety issue is reported to execution safety"
    elif sample_count < 5:
        verdict, action, reason = "watch", "collect_more_samples", f"only {sample_count} clean samples"
    elif sample_count < 20:
        verdict, action, reason = "allow_reduced", "reduced_risk", f"{sample_count} samples: reduce before block"
    elif avg_final_r is not None and avg_final_r < -0.5 and (avg_mfe_r or 0) < 0.5:
        verdict, action, reason = "allow_reduced", "reduced_risk", "mature weak R lane remains advisory"
    else:
        verdict, action, reason = "allow", "normal_risk", "mature lane not severely weak"
    payload = {
        "verdict_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "symbol": symbol,
        "direction": direction,
        "grade": grade,
        "verdict": verdict,
        "sample_count": int(sample_count),
        "avg_mfe_r": avg_mfe_r,
        "avg_mae_r": avg_mae_r,
        "avg_final_r": avg_final_r,
        "reason": reason,
        "action_taken": action,
        "safety_issue": int(safety_issue),
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO memory_verdicts (
                verdict_id, created_at, symbol, direction, grade, verdict, sample_count,
                avg_mfe_r, avg_mae_r, avg_final_r, reason, action_taken, safety_issue
            ) VALUES (:verdict_id, :created_at, :symbol, :direction, :grade, :verdict,
                      :sample_count, :avg_mfe_r, :avg_mae_r, :avg_final_r, :reason,
                      :action_taken, :safety_issue)
            """,
            payload,
        )
        conn.commit()
    return payload
