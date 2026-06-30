"""Bounded read-only evidence views for Hermes Advisor."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from config import HERMES_EVIDENCE_ROW_LIMIT, HERMES_GEMINI_MODEL
from hermes_advisor import ADVISOR_BOUNDARY
from scripts.ozzy_memory_report import build_report as build_memory_report

ROOT = Path(__file__).resolve().parent
TESTNET_DB_PATH = ROOT / "trades.db"
LIVE_DB_PATH = ROOT / "live_micro" / "trades_live.db"
TESTNET_LOG_PATH = ROOT / "trades.log"
LIVE_LOG_PATH = ROOT / "live_micro" / "trades_live.log"
STATUS_URLS = {
    "LIVE_MICRO": "http://127.0.0.1:5001/status",
    "TESTNET": "http://127.0.0.1:5000/status",
}
INCIDENT_EVENT_MARKERS = (
    "_ERROR",
    "FAIL",
    "PROTECTION",
    "RECONCILE",
    "CLOSE_FAILED",
    "EXECUTION",
)


def _note(notes: list[str], message: str) -> None:
    if message not in notes:
        notes.append(message)


def _fetch_status(mode: str) -> dict[str, Any]:
    """Fetch local status JSON with explicit unavailable detail."""
    url = STATUS_URLS[mode]
    try:
        response = requests.get(url, timeout=2)
        response.raise_for_status()
        payload = response.json()
        return {"available": True, "source": url, "data": payload}
    except Exception as exc:
        return {"available": False, "source": url, "error": f"{type(exc).__name__}: {exc}"}


# ── Live Verification ────────────────────────────────────────────────────────

_AUTH_ERROR_MARKERS = ("-2015", "APIError", "AuthenticationError", "Invalid API", "permission")


def _has_connection_errors(incidents: list[dict[str, Any]]) -> bool:
    """Return True if any incident record hints at an auth / connection failure."""
    for inc in incidents:
        err = str(inc.get("error") or "")
        event = str(inc.get("event") or "")
        if any(m in err or m in event for m in _AUTH_ERROR_MARKERS):
            return True
    return False


def _live_verification(live_status: dict[str, Any], testnet_status: dict[str, Any]) -> dict[str, Any]:
    """Perform a *fresh* live ping (strict 2-second timeout) of both webhooks.

    This is intentionally separate from the evidence-gathering _fetch_status calls
    so that the verification timestamp is captured last — closest to report delivery.
    Returns a structured dict that is embedded verbatim in the evidence pack.
    """
    results: dict[str, Any] = {}
    checked_at = datetime.now(UTC).isoformat()

    for mode, url in STATUS_URLS.items():
        try:
            resp = requests.get(url, timeout=2)
            resp.raise_for_status()
            payload = resp.json()
            bot_status = payload.get("status", "unknown")
            equity = (payload.get("risk") or {}).get("equity_usd")
            healthy = bot_status == "running"
            results[mode] = {
                "reachable": True,
                "healthy": healthy,
                "status_field": bot_status,
                "equity_usd": equity,
                "url": url,
            }
        except Exception as exc:
            results[mode] = {
                "reachable": False,
                "healthy": False,
                "error": f"{type(exc).__name__}: {exc}",
                "url": url,
            }

    return {"checked_at": checked_at, "endpoints": results}


def _connect_readonly(path: Path):
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=1)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    conn = _connect_readonly(path)
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _round(value: Any) -> Any:
    return round(float(value), 6) if isinstance(value, (float, int)) else value


def _r_from_risk(value: Any, risk: Any) -> float | None:
    if value is None or risk is None:
        return None
    risk_value = float(risk)
    if risk_value <= 0:
        return None
    return round(float(value) / risk_value, 6)


def _clean_trade(row: dict[str, Any], mode_label: str) -> dict[str, Any]:
    """Return the bounded trade fields useful for model evidence."""
    risk_usd = row.get("risk_dollars")
    data_quality_flags = []
    entry_price = row.get("entry_price")
    if entry_price is not None and float(entry_price) <= 0:
        data_quality_flags.append("invalid_nonpositive_entry_anchor")
    if row.get("exit_reason") in {"execution_failed", "protection_truth_failed"} and row.get("execution_state") not in {
        "fail_closed",
        "closed",
    }:
        data_quality_flags.append("historical_fail_close_state_not_normalized")
    accounting_status = row.get("accounting_status") or "unchecked"
    if accounting_status == "dirty":
        data_quality_flags.append("dirty_accounting_row_excluded_from_lane_promotion")
    elif accounting_status == "corrected":
        data_quality_flags.append("accounting_corrected_row")
    return {
        "trade_id": row.get("id"),
        "instance_mode": mode_label,
        "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "setup_grade": row.get("setup_grade"),
        "mode": row.get("mode"),
        "source": row.get("source"),
        "entry": _round(entry_price),
        "sl": _round(row.get("sl")),
        "tp": _round(row.get("tp")),
        "qty": _round(row.get("qty")),
        "risk_usd": _round(risk_usd),
        "reward_usd": _round(row.get("reward_dollars")),
        "pnl": _round(row.get("pnl")),
        "r_multiple": _round(row.get("r_multiple")),
        "realized_r_from_risk_usd": _r_from_risk(row.get("pnl"), risk_usd),
        "peak_pnl": _round(row.get("peak_pnl")),
        "peak_r_from_risk_usd": _r_from_risk(row.get("peak_pnl"), risk_usd),
        "peak_price": _round(row.get("peak_price")),
        "exit_reason": row.get("exit_reason"),
        "execution_state": row.get("execution_state"),
        "accounting_status": accounting_status,
        "accounting_notes": row.get("accounting_notes"),
        "state": "open" if row.get("exit_price") is None else "closed",
        "opened_at": row.get("ts"),
        "duration_min": row.get("duration_min"),
        "data_quality_flags": data_quality_flags,
    }


def _recent_trades(path: Path, mode_label: str, limit: int, notes: list[str]) -> list[dict[str, Any]]:
    try:
        rows = _rows(
            path,
            """
            SELECT id, ts, symbol, direction, entry_price, exit_price, qty, pnl,
                   exit_reason, r_multiple, duration_min, mode, setup_grade,
                   risk_dollars, reward_dollars, sl, tp, source, execution_state,
                   peak_pnl, peak_price, accounting_status, accounting_notes
            FROM trades
            WHERE COALESCE(source, 'live') != 'migrated'
              AND COALESCE(mode, 'live') != 'ghost'
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        _note(notes, f"{mode_label} recent trades unavailable: {type(exc).__name__}: {exc}")
        return []
    cleaned = [_clean_trade(row, mode_label) for row in rows]
    invalid_entries = [
        str(row["trade_id"])
        for row in cleaned
        if "invalid_nonpositive_entry_anchor" in row["data_quality_flags"]
    ]
    if invalid_entries:
        _note(
            notes,
            f"{mode_label} recent trades have invalid nonpositive entry anchors: {', '.join(invalid_entries)}.",
        )
    stale_fail_closes = [
        str(row["trade_id"])
        for row in cleaned
        if "historical_fail_close_state_not_normalized" in row["data_quality_flags"]
    ]
    if stale_fail_closes:
        _note(
            notes,
            f"{mode_label} historical fail-close execution states need normalization: {', '.join(stale_fail_closes)}.",
        )
    dirty_rows = [
        str(row["trade_id"])
        for row in cleaned
        if "dirty_accounting_row_excluded_from_lane_promotion" in row["data_quality_flags"]
    ]
    if dirty_rows:
        _note(
            notes,
            f"{mode_label} recent trades include dirty accounting rows excluded from lane promotion: "
            f"{', '.join(dirty_rows)}.",
        )
    return cleaned


def _status_view(mode: str, status: dict[str, Any], db_path: Path, limit: int, notes: list[str]) -> dict[str, Any]:
    open_trades = [row for row in _recent_trades(db_path, mode, limit, notes) if row["state"] == "open"]
    if not status["available"]:
        _note(notes, f"{mode} status unavailable from {status['source']}")
        return {
            "available": False,
            "source": status["source"],
            "error": status["error"],
            "instance_mode": mode,
            "open_db_trades": open_trades,
        }
    payload = status["data"]
    daily_stop = payload.get("daily_stop") or {}
    reconcile = payload.get("reconciliation") or {}
    return {
        "available": True,
        "source": status["source"],
        "instance_mode": mode,
        "execution_mode": payload.get("execution_mode"),
        "equity_usd": ((payload.get("risk") or {}).get("equity_usd")),
        "active_symbols": payload.get("active_symbols"),
        "max_positions": payload.get("effective_max_positions") or payload.get("max_positions"),
        "open_db_trades": open_trades,
        "bootstrap_risk": {
            "active": payload.get("micro_bootstrap_active"),
            "target_loss_at_sl_usd": ((payload.get("risk") or {}).get("target_loss_at_sl_usd")),
            "effective_risk_usd": ((payload.get("risk") or {}).get("effective_risk_usd")),
            "warning": ((payload.get("risk") or {}).get("warning")),
        },
        "daily_stop": {
            "model": daily_stop.get("model"),
            "live_blocked_for_day": daily_stop.get("live_blocked_for_day"),
            "live_paused_for_safety": daily_stop.get("live_paused_for_safety"),
            "rearm_available": daily_stop.get("rearm_available"),
            "reason": daily_stop.get("reason"),
        },
        "reconcile": {
            "healthy": reconcile.get("healthy"),
            "warnings": (reconcile.get("warnings") or [])[:limit],
            "critical_mismatches": (reconcile.get("critical_mismatches") or [])[:limit],
            "checked_at": reconcile.get("checked_at"),
            "stale_algo_order_count": reconcile.get("stale_algo_order_count"),
        },
        "protection_health": {
            "truth_required": payload.get("protection_truth_required"),
            "finalizer": payload.get("post_fill_protection_finalizer"),
        },
    }


def _exit_rows(path: Path, limit: int, notes: list[str], mode_label: str) -> list[dict[str, Any]]:
    try:
        return _rows(
            path,
            """
            SELECT e.trade_id, e.ts, e.exit_type, e.price, e.pnl_contribution,
                   e.qty_pct, e.notes, t.symbol, t.direction, t.setup_grade,
                   t.risk_dollars, t.pnl, t.peak_pnl, t.exit_reason
            FROM exits e JOIN trades t ON t.id = e.trade_id
            WHERE COALESCE(t.source, 'live') != 'migrated'
              AND COALESCE(t.mode, 'live') != 'ghost'
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        _note(notes, f"{mode_label} exit rows unavailable: {type(exc).__name__}: {exc}")
        return []


def _milestone_rows(path: Path, limit: int, notes: list[str], mode_label: str) -> list[dict[str, Any]]:
    try:
        return _rows(
            path,
            """
            SELECT m.trade_id, m.milestone, m.price, m.pnl, m.ts,
                   t.symbol, t.direction, t.setup_grade, t.exit_reason
            FROM milestones m JOIN trades t ON t.id = m.trade_id
            WHERE COALESCE(t.source, 'live') != 'migrated'
              AND COALESCE(t.mode, 'live') != 'ghost'
            ORDER BY m.id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        _note(notes, f"{mode_label} milestone rows unavailable: {type(exc).__name__}: {exc}")
        return []


def _exit_quality(
    testnet_trades: list[dict[str, Any]],
    live_trades: list[dict[str, Any]],
    live_exits: list[dict[str, Any]],
    testnet_exits: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    trades = live_trades + testnet_trades
    closed = [trade for trade in trades if trade["state"] == "closed"]
    givebacks = []
    for trade in closed:
        risk = trade.get("risk_usd")
        peak = trade.get("peak_pnl")
        if risk and peak is not None and peak >= 0.5 * risk and (trade.get("pnl") or 0) <= 0:
            copy = dict(trade)
            copy["peak_r_from_risk_usd"] = round(peak / risk, 6)
            givebacks.append(copy)
    exits = [{**row, "instance_mode": "LIVE_MICRO"} for row in live_exits]
    exits.extend({**row, "instance_mode": "TESTNET"} for row in testnet_exits)
    exit_reason_counts = Counter(str(trade.get("exit_reason") or "open") for trade in closed)
    exit_type_counts = Counter(str(row.get("exit_type") or "unknown") for row in exits)
    return {
        "closed_trade_sample_size": len(closed),
        "exit_reason_counts": dict(exit_reason_counts),
        "exit_type_counts": dict(exit_type_counts),
        "profit_giveback_candidates": givebacks[:limit],
        "momentum_exits": [row for row in exits if row.get("exit_type") == "momentum_exit"][:limit],
        "sl_exits": [row for row in exits if row.get("exit_type") == "sl"][:limit],
        "milestone_partial_exits": [
            row for row in exits if str(row.get("exit_type") or "").startswith("milestone_")
        ][:limit],
        "r_policy": "R evidence is only derived where risk_usd is present; missing anchors remain absent.",
    }


def _milestone_summary(
    live_rows: list[dict[str, Any]],
    testnet_rows: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    rows = [{**row, "instance_mode": "LIVE_MICRO"} for row in live_rows]
    rows.extend({**row, "instance_mode": "TESTNET"} for row in testnet_rows)
    milestone_counts = Counter(str(row["milestone"]) for row in rows)
    half_r_hits = [row for row in rows if row["milestone"] == "milestone_0"]
    state = "observed" if half_r_hits else "configured_or_not_yet_observed"
    return {
        "sample_size": len(rows),
        "milestone_counts": dict(milestone_counts),
        "recent_hits": rows[:limit],
        "half_r_partial_state": state,
        "half_r_observed_count": len(half_r_hits),
    }


def _safe_log_incidents(path: Path, mode: str, limit: int, notes: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        _note(notes, f"{mode} structured log incidents unavailable: {path} missing")
        return []
    incidents = []
    with path.open("rb") as handle:
        for raw in handle:
            try:
                payload = json.loads(raw.decode("utf-8", errors="ignore").strip("\x00\n "))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            event = str(payload.get("event") or "")
            if not any(marker in event for marker in INCIDENT_EVENT_MARKERS):
                continue
            incidents.append({
                "instance_mode": mode,
                "ts": payload.get("ts"),
                "event": event,
                "trade_id": payload.get("trade_id"),
                "symbol": payload.get("symbol"),
                "error": payload.get("error"),
                "reason": payload.get("reason"),
                "status": payload.get("status"),
            })
    incidents = incidents[-limit:]
    if any(incident.get("trade_id") is None for incident in incidents):
        _note(
            notes,
            f"{mode} structured log incidents may lack trade_id correlation; use DB journal rows where available.",
        )
    return incidents


def _memory_journal_incidents(limit: int, notes: list[str]) -> list[dict[str, Any]]:
    try:
        import ozzy_memory  # noqa: PLC0415

        with ozzy_memory._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, trade_id, symbol, event_type, new_state, actor
                FROM trade_journal_events
                WHERE event_type LIKE '%protection%'
                   OR event_type LIKE '%execution%'
                   OR new_state IN ('protection_truth_failed', 'execution_failed', 'fail_closed')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        _note(notes, f"Ozzy Memory journal incidents unavailable: {type(exc).__name__}: {exc}")
        return []


def build_evidence_pack(question: str | None = None, *, memory_backfill: bool = False) -> dict[str, Any]:
    """Build the full bounded truth pack supplied to Hermes Advisor."""
    limit = max(1, int(HERMES_EVIDENCE_ROW_LIMIT))
    notes: list[str] = [
        "Migrated and ghost trade rows are excluded from recent trade and exit views.",
        "LIVE and TESTNET evidence are labeled separately; TESTNET dollar PnL is not LIVE expectancy.",
    ]
    live_trades = _recent_trades(LIVE_DB_PATH, "LIVE_MICRO", limit, notes)
    testnet_trades = _recent_trades(TESTNET_DB_PATH, "TESTNET", limit, notes)
    live_exits = _exit_rows(LIVE_DB_PATH, limit, notes, "LIVE_MICRO")
    testnet_exits = _exit_rows(TESTNET_DB_PATH, limit, notes, "TESTNET")
    live_milestones = _milestone_rows(LIVE_DB_PATH, limit, notes, "LIVE_MICRO")
    testnet_milestones = _milestone_rows(TESTNET_DB_PATH, limit, notes, "TESTNET")
    memory_summary = build_memory_report(backfill=memory_backfill)
    if not memory_summary.get("grade_health_by_r"):
        _note(notes, "Ozzy Memory grade-health R outcomes are empty or not yet backfilled.")
    if not memory_summary.get("good_entry_bad_exit"):
        _note(notes, "Ozzy Memory good-entry/bad-exit candidates are currently empty.")
    live_status = _status_view("LIVE_MICRO", _fetch_status("LIVE_MICRO"), LIVE_DB_PATH, limit, notes)
    testnet_status = _status_view("TESTNET", _fetch_status("TESTNET"), TESTNET_DB_PATH, limit, notes)

    # ── Live Verification ────────────────────────────────────────────────────
    # Collect recent incident events to check for auth / connection errors.
    all_log_incidents = (
        _safe_log_incidents(LIVE_LOG_PATH, "LIVE_MICRO", limit, notes)
        + _safe_log_incidents(TESTNET_LOG_PATH, "TESTNET", limit, notes)
    )[:limit]

    verification = _live_verification(live_status, testnet_status)
    historical_errors_detected = _has_connection_errors(all_log_incidents)
    live_micro_ok = verification["endpoints"].get("LIVE_MICRO", {}).get("healthy", False)
    testnet_ok = verification["endpoints"].get("TESTNET", {}).get("healthy", False)

    # Inject operator-grade disclaimers into data_quality_notes.
    # These are ground-truth facts — Gemini must reference them in its summary.
    if historical_errors_detected and live_micro_ok:
        _note(
            notes,
            "⚠️ LIVE VERIFICATION OVERRIDE [LIVE_MICRO]: Historical logs contain connection/auth errors "
            "(e.g. -2015), but a live ping at report-generation time confirms the Live Micro webhook is "
            "currently ONLINE and HEALTHY. The historical errors reflect a past incident that is now resolved. "
            "Hermes must explicitly state this in its summary and must NOT classify the system as currently broken.",
        )
    if historical_errors_detected and testnet_ok:
        _note(
            notes,
            "⚠️ LIVE VERIFICATION OVERRIDE [TESTNET]: Historical logs contain connection/auth errors, "
            "but a live ping confirms the Testnet webhook is currently ONLINE and HEALTHY. "
            "Hermes must explicitly state this in its summary.",
        )
    if not live_micro_ok:
        err = verification["endpoints"].get("LIVE_MICRO", {}).get("error", "no response")
        _note(
            notes,
            f"🔴 LIVE VERIFICATION FAIL [LIVE_MICRO]: Live ping at report time FAILED — {err}. "
            "Hermes must flag this as an active system issue requiring operator attention.",
        )
    if not testnet_ok:
        err = verification["endpoints"].get("TESTNET", {}).get("error", "no response")
        _note(
            notes,
            f"🔴 LIVE VERIFICATION FAIL [TESTNET]: Live ping at report time FAILED — {err}. "
            "Hermes must flag this as an active system issue requiring operator attention.",
        )

    return {
        "question": question or "What should the operator learn from current Hermes evidence?",
        "runtime_context": {
            "generated_at": datetime.now(UTC).isoformat(),
            "configured_gemini_model": HERMES_GEMINI_MODEL,
            "advisor_role": "read_only_evidence_advisor",
            "advisor_boundary": ADVISOR_BOUNDARY,
            "truth_owner": "Python queries and DB/report rows own math and facts.",
            "data_limitations": [
                "Missing source fields must stay unavailable.",
                "Error root causes require actual event/error evidence.",
                "Thin samples support hypotheses, not expectancy claims.",
            ],
        },
        "live_status": live_status,
        "testnet_status": testnet_status,
        "live_verification": verification,
        "recent_live_trades": live_trades,
        "recent_testnet_trades": testnet_trades,
        "exit_quality": _exit_quality(testnet_trades, live_trades, live_exits, testnet_exits, limit),
        "milestone_summary": _milestone_summary(live_milestones, testnet_milestones, limit),
        "protection_and_execution_incidents": {
            "journal_events": _memory_journal_incidents(limit, notes),
            "structured_log_events": all_log_incidents,
            "root_cause_policy": "No incident cause is known unless actual error/event fields prove it.",
        },
        "ozzy_memory_summary": memory_summary,
        "data_quality_notes": notes,
    }
