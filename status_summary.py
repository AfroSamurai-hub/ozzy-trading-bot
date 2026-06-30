"""Compact status payload helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from position_context import evaluate_position_context
from product_lifecycle import classify_lifecycle_items

ROOT = Path(__file__).resolve().parent


def _safe_context(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def latest_open_trades_by_symbol(db_path, limit: int = 50) -> dict[str, dict]:
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM trades
            WHERE exit_price IS NULL
              AND COALESCE(execution_state, '') NOT IN ('closed', 'execution_failed')
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception:
        return {}
    finally:
        if conn is not None:
            conn.close()
    return {str(row["symbol"]).upper(): dict(row) for row in rows}


def group_positions_by_strategy(positions: list[dict], trade_rows: dict[str, dict]) -> dict:
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "symbols": [], "unrealized_pnl": 0.0})
    for pos in positions:
        symbol = str(pos.get("symbol") or pos.get("tv_symbol") or "").upper()
        trade = trade_rows.get(symbol, {})
        label = trade.get("strategy_label") or trade.get("strategy") or "UNKNOWN"
        bucket = grouped[label]
        bucket["count"] += 1
        bucket["symbols"].append(symbol)
        bucket["unrealized_pnl"] += float(pos.get("profit") or 0.0)
    return {
        label: {
            "count": data["count"],
            "symbols": data["symbols"][:8],
            "unrealized_pnl": round(data["unrealized_pnl"], 2),
        }
        for label, data in grouped.items()
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        try:
            parsed = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _position_age_minutes(trade: dict) -> int | None:
    opened_at = _parse_dt(trade.get("ts"))
    if not opened_at:
        return None
    return int((datetime.now(UTC) - opened_at).total_seconds() // 60)


def _failure_label(context: dict, trade: dict, protection: dict) -> str:
    current_r = context.get("current_r")
    peak_r = context.get("peak_r")
    giveback = context.get("giveback_pct")
    setup_grade = str(trade.get("setup_grade") or "").upper()
    accounting = str(trade.get("accounting_status") or "clean").lower()

    if accounting not in {"", "clean", "unchecked"}:
        return "ACCOUNTING_NOISE"
    if protection and protection.get("healthy") is False:
        return "PROTECTION_RISK"
    if setup_grade == "B" and current_r is not None and float(current_r) <= -0.30 and (
        peak_r is None or float(peak_r) < 0.20
    ):
        return "GRADE_B_NO_PROGRESS"
    if peak_r is not None and current_r is not None and giveback is not None:
        if float(peak_r) >= 0.3 and float(current_r) <= -0.05 and float(giveback) >= 80.0:
            return "ROUNDTRIP_WINNER"
        if float(current_r) < 0.0 and float(giveback) >= 50.0:
            return "MOMENTUM_EXIT_BLEED"
    return ""


def _action_label_for(mode: str, context: dict, failure: str) -> str:
    label = context.get("management_label") or "HOLD"
    current_r = context.get("current_r")
    if failure == "PROTECTION_RISK":
        return "RECONCILE_REQUIRED"
    if failure == "GRADE_B_NO_PROGRESS" and current_r is not None:
        current = float(current_r)
        if str(mode).upper() == "TESTNET" and current <= -0.35:
            return "EXIT_REQUIRED"
        if current <= -0.30 and label == "HOLD":
            return "REDUCE_RISK"
    return label


def build_danger_board(
    *,
    mode: str,
    positions: list[dict],
    trade_rows: dict[str, dict],
    reconciliation: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return compact read-only open-position danger rows for /status."""
    protection = protection_summary(reconciliation)
    rows = []
    for pos in positions:
        symbol = str(pos.get("symbol") or pos.get("tv_symbol") or "").upper()
        trade = trade_rows.get(symbol, {})
        context = evaluate_position_context(pos, trade).to_dict()
        failure = _failure_label(context, trade, protection)
        label = _action_label_for(mode, context, failure)
        rows.append(
            {
                "mode": mode,
                "symbol": symbol,
                "side": pos.get("type") or trade.get("direction"),
                "strategy_label": trade.get("strategy_label") or trade.get("strategy") or "UNKNOWN",
                "current_R": context.get("current_r"),
                "peak_R": context.get("peak_r"),
                "giveback_pct": context.get("giveback_pct"),
                "age_min": _position_age_minutes(trade),
                "action_label": label,
                "failure_label": failure,
                "live_behavior": "alert_only" if str(mode).upper() == "LIVE" else "status_only",
            }
        )

    priority = {"RECONCILE_REQUIRED": 0, "EXIT_REQUIRED": 1, "REDUCE_RISK": 2, "PROTECT": 3, "HOLD": 4}
    rows.sort(
        key=lambda row: (
            priority.get(str(row.get("action_label")), 9),
            -(float(row.get("giveback_pct") or 0.0)),
            -(abs(float(row.get("current_R") or 0.0))),
        )
    )
    return rows[: max(0, int(limit))]


def summarize_reconciliation(reconciliation: dict | None) -> dict:
    reconciliation = reconciliation or {}
    return {
        "healthy": reconciliation.get("healthy"),
        "checked_at": reconciliation.get("checked_at"),
        "critical_mismatch_count": len(reconciliation.get("critical_mismatches") or []),
        "warning_count": len(reconciliation.get("warnings") or []),
        "stale_algo_order_count": reconciliation.get("stale_algo_order_count", 0),
        "reconciliation_is_stale": bool(reconciliation.get("reconciliation_is_stale", False)),
        "reconciliation_refresh_error": reconciliation.get("reconciliation_refresh_error"),
        "data_unavailable": bool(reconciliation.get("data_unavailable", False)),
        "source": reconciliation.get("source"),
    }


def protection_summary(reconciliation: dict | None) -> dict:
    reconciliation = reconciliation or {}
    return {
        "healthy": reconciliation.get("healthy"),
        "critical_mismatches": len(reconciliation.get("critical_mismatches") or []),
        "warnings": len(reconciliation.get("warnings") or []),
        "stale_algo_orders": reconciliation.get("stale_algo_order_count", 0),
        "reconciliation_is_stale": bool(reconciliation.get("reconciliation_is_stale", False)),
        "reconciliation_refresh_error": reconciliation.get("reconciliation_refresh_error"),
        "data_unavailable": bool(reconciliation.get("data_unavailable", False)),
    }


def recent_candidates_from_db(db_path, limit: int = 5) -> list[dict]:
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT gate_name, decision, reason, ts
            FROM trade_gates
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()
    return [dict(row) for row in rows]


def _normalize_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().upper()
    if normalized in {"", "ALL", "ANY", "UNIFIED"}:
        return None
    if normalized in {"LIVE_MICRO", "LIVE-MICRO"}:
        return "LIVE"
    if normalized in {"STANDARD_TESTNET", "STANDARD-TESTNET"}:
        return "TESTNET"
    return normalized


def _row_mode(row: dict) -> str:
    return _normalize_mode(str(row.get("mode") or row.get("execution_mode") or "")) or "-"


def recent_auto_protect_actions(limit: int = 5, mode: str | None = None) -> list[dict]:
    path = ROOT / "observer" / "auto_protect_actions.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows = [row for row in data if isinstance(row, dict)]
    wanted = _normalize_mode(mode)
    if wanted:
        rows = [row for row in rows if _row_mode(row) == wanted]
    rows.sort(key=lambda row: str(row.get("created_at") or row.get("ts") or ""), reverse=True)
    return rows[: max(0, int(limit))]


def _latest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def _file_age_minutes(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    return int((datetime.now(UTC).timestamp() - path.stat().st_mtime) // 60)


def build_memory_sync_summary() -> dict:
    preferred = Path.home() / "Obsidian" / "OzzyBot"
    fallback = Path.home() / "Documents" / "OzzyBot_Obsidian"
    root = preferred if preferred.exists() else fallback if fallback.exists() else None
    latest_daily = _latest_file(list((root / "Daily").glob("*.md")) if root else [])
    latest_report = _latest_file(list((ROOT / "reports").glob("cash_bleed_report_*.md")))
    latest_actions = ROOT / "observer" / "auto_protect_actions.json"
    return {
        "obsidian_export_configured": root is not None,
        "obsidian_root": str(root) if root else None,
        "latest_daily_note": latest_daily.name if latest_daily else None,
        "latest_daily_age_min": _file_age_minutes(latest_daily),
        "latest_cash_bleed_report": latest_report.name if latest_report else None,
        "latest_cash_bleed_report_age_min": _file_age_minutes(latest_report),
        "auto_protect_actions_age_min": _file_age_minutes(latest_actions if latest_actions.exists() else None),
    }


def build_product_sync_health(
    *,
    binance_testnet: bool,
    positions: list[dict],
    trade_rows: dict[str, dict],
    reconciliation: dict,
    no_new_entries_flag: bool,
) -> dict:
    protection = protection_summary(reconciliation)
    reconciliation_unavailable = bool(
        reconciliation.get("data_unavailable")
        or (protection.get("healthy") is None and reconciliation.get("reconciliation_refresh_error"))
    )
    position_symbols = {str(pos.get("symbol") or pos.get("tv_symbol") or "").upper() for pos in positions}
    db_symbols = set(trade_rows)
    orphan_symbols = [] if reconciliation_unavailable else sorted(symbol for symbol in position_symbols if symbol and symbol not in db_symbols)
    ghost_symbols = [] if reconciliation_unavailable else sorted(symbol for symbol in db_symbols if symbol and symbol not in position_symbols)
    mode = "TESTNET" if binance_testnet else "LIVE"
    status = "degraded" if reconciliation_unavailable else "ok"
    issues = ["exchange_reconciliation_unavailable"] if reconciliation_unavailable else []
    if not reconciliation_unavailable and protection.get("healthy") is False:
        status = "attention_required"
        issues.append("protection_truth_unhealthy")
    if orphan_symbols:
        status = "attention_required"
        issues.append("orphan_exchange_position")
    if ghost_symbols:
        status = "attention_required"
        issues.append("db_ghost_trade")
    if not binance_testnet and no_new_entries_flag:
        issues.append("live_micro_entries_blocked")
    lifecycle_items = classify_lifecycle_items(
        mode=mode,
        positions=positions,
        trade_rows=trade_rows,
        reconciliation=reconciliation,
    )
    operator_action_required = [
        {
            "symbol": item["symbol"],
            "state": item["state"],
            "reason": item["reason"],
        }
        for item in lifecycle_items
        if item["state"] in {"ORPHAN_EXCHANGE_POSITION", "DB_GHOST_TRADE", "OPEN_UNPROTECTED_MANAGEMENT_SUSPENDED"}
    ][:5]
    return {
        "status": status,
        "mode": mode,
        "db_exchange_sync": {
            "open_position_symbols": sorted(position_symbols),
            "db_open_symbols": sorted(db_symbols),
            "orphan_symbols": orphan_symbols,
            "db_ghost_symbols": ghost_symbols,
        },
        "protection_truth": protection,
        "lifecycle_items": lifecycle_items[:10],
        "operator_action_required": operator_action_required,
        "issues": issues[:8],
    }


def build_status_summary(
    *,
    mode: str,
    binance_testnet: bool,
    live_equity: float | None,
    positions: list[dict],
    trade_rows: dict[str, dict],
    daily_stop: dict,
    reconciliation: dict,
    active_symbols: list[str],
    db_path,
    active_cooldowns: int,
    no_new_entries_flag: bool = False,
    auto_protect_simulation_available: bool | None = None,
    testnet_auto_protect_enabled: bool = False,
    testnet_auto_protect_dry_run: bool = True,
    testnet_cash_ratchet_enabled: bool = False,
    live_auto_protect_enabled: bool = False,
) -> dict:
    blockers = []
    if daily_stop.get("live_trading_blocked_for_day") or daily_stop.get("live_blocked_for_day"):
        blockers.append(daily_stop.get("reason") or daily_stop.get("block_reason") or "daily_stop_active")
    if active_cooldowns:
        blockers.append(f"{active_cooldowns} active cooldowns")
    daily_block_active = bool(daily_stop.get("live_trading_blocked_for_day") or daily_stop.get("live_blocked_for_day"))
    entry_block_reasons = []
    if no_new_entries_flag:
        entry_block_reasons.append("LIVE_MICRO_NO_NEW_ENTRIES active")
    if daily_block_active:
        entry_block_reasons.append(daily_stop.get("reason") or daily_stop.get("block_reason") or "daily_stop_active")

    if auto_protect_simulation_available is None:
        auto_protect_simulation_available = bool(list((ROOT / "reports").glob("auto_protect_simulation_*.md")))

    section_key = "testnet" if binance_testnet else "live_micro"
    section = {
        "mode": mode,
        "equity": live_equity,
        "positions": len(positions),
        "active_symbols": active_symbols[:20],
        "blocked": bool(blockers),
    }
    live_micro_section = {
        **(section if section_key == "live_micro" else {"mode": "LIVE", "equity": None, "positions": None, "active_symbols": [], "blocked": False}),
        "new_entries_enabled": not (bool(no_new_entries_flag) or daily_block_active),
        "no_new_entries_flag": bool(no_new_entries_flag),
        "daily_block_active": daily_block_active,
        "entry_block_reasons": entry_block_reasons[:5],
        # Status hard-caps this as false; no live auto-protect rollout in this phase.
        "live_auto_protect_enabled": bool(live_auto_protect_enabled and False),
    }
    testnet_section = {
        **(section if section_key == "testnet" else {"mode": "TESTNET", "equity": None, "positions": None, "active_symbols": [], "blocked": False}),
        "auto_protect_simulation_available": bool(auto_protect_simulation_available),
        "auto_protect_enabled": bool(testnet_auto_protect_enabled),
        "auto_protect_dry_run": bool(testnet_auto_protect_dry_run),
        "cash_ratchet_enabled": bool(testnet_cash_ratchet_enabled),
        "recent_auto_protect_actions": recent_auto_protect_actions(limit=5, mode="TESTNET")
        if section_key == "testnet"
        else [],
    }
    memory_sync = build_memory_sync_summary()
    product_sync_health = build_product_sync_health(
        binance_testnet=binance_testnet,
        positions=positions,
        trade_rows=trade_rows,
        reconciliation=reconciliation,
        no_new_entries_flag=no_new_entries_flag,
    )
    scanner_state = {
        "mode": mode,
        "active_symbols_count": len(active_symbols),
        "entries_blocked": bool(no_new_entries_flag or daily_block_active),
        "entry_block_reasons": entry_block_reasons[:5],
    }
    summary = {
        "status": "running",
        "generated_at": datetime.now(UTC).isoformat(),
        "live_micro": live_micro_section,
        "testnet": testnet_section,
        "product_sync_health": product_sync_health,
        "memory_sync": memory_sync,
        "scanner_state": scanner_state,
        "positions_by_strategy_label": group_positions_by_strategy(positions, trade_rows),
        "danger_board": build_danger_board(
            mode=mode,
            positions=positions,
            trade_rows=trade_rows,
            reconciliation=reconciliation,
            limit=5,
        ),
        "active_blockers": blockers[:5],
        "protection": protection_summary(reconciliation),
        "reconciliation_summary": summarize_reconciliation(reconciliation),
        "context_warnings": [],
        "recent_candidates": recent_candidates_from_db(db_path, limit=5),
    }
    return summary
