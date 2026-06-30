"""Read-only LIVE state reconciliation for exchange, DB, and protection truth."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

import trade_db
from binance_connector import (
    get_balance,
    get_open_algo_orders,
    get_open_orders,
    get_open_positions,
    has_exchange_protection,
)

_last_reconcile: dict | None = None
RECONCILE_CACHE_PATH = Path(
    os.getenv("HERMES_RECONCILE_CACHE_PATH", "/home/rick/ozzy-bot/.cache/live_reconcile_state.json")
)


def _is_transient_exchange_error(error: Exception | str) -> bool:
    text = str(error).lower()
    markers = (
        "timeout",
        "timed out",
        "read timed out",
        "code=-1007",
        "temporarily unavailable",
        "temporary failure",
        "connection reset",
        "connection aborted",
        "remote end closed connection",
    )
    return any(marker in text for marker in markers)


def _save_reconcile_cache(state: dict) -> None:
    """Persist the last authoritative snapshot for fail-soft status reads."""
    try:
        RECONCILE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RECONCILE_CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str), encoding="utf-8")
        tmp.replace(RECONCILE_CACHE_PATH)
    except Exception:
        # Status cache persistence must never affect trading/reconciliation logic.
        pass


def _load_reconcile_cache() -> dict | None:
    try:
        if not RECONCILE_CACHE_PATH.exists():
            return None
        data = json.loads(RECONCILE_CACHE_PATH.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _mark_cached_after_refresh_error(cached: dict, error: Exception | str) -> dict:
    state = dict(cached)
    warnings = list(state.get("warnings") or [])
    warning = f"using cached reconciliation after exchange refresh failed: {error}"
    if warning not in warnings:
        warnings.append(warning)
    state.update(
        {
            "warnings": warnings,
            "reconciliation_is_stale": True,
            "reconciliation_refresh_error": str(error),
            "source": "cached_after_refresh_error",
            "transient_exchange_error": _is_transient_exchange_error(error),
        }
    )
    return state


def _unavailable_state(error: Exception | str) -> dict:
    return {
        "healthy": None,
        "equity_usd": None,
        "critical_mismatches": [],
        "warnings": [f"reconciliation unavailable: {error}"],
        "positions": [],
        "db_open_trades": [],
        "normal_open_order_count": None,
        "algo_open_order_count": None,
        "stale_algo_order_count": 0,
        "stale_algo_orders": [],
        "checked_at": None,
        "dry_run": True,
        "reconciliation_is_stale": True,
        "reconciliation_refresh_error": str(error),
        "source": "unavailable_after_refresh_error",
        "data_unavailable": True,
        "transient_exchange_error": _is_transient_exchange_error(error),
    }


def _row_symbol(row) -> str | None:
    return row["symbol"] if hasattr(row, "keys") else row.get("symbol")


def _algo_order_type(order: dict) -> str:
    return str(order.get("type") or order.get("orderType") or "").upper()


def _truthy(value) -> bool:
    return value is True or str(value).lower() == "true"


def _stale_algo_order_detail(order: dict) -> dict:
    order_type = _algo_order_type(order)
    stale_protection = (
        order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
        and (_truthy(order.get("reduceOnly")) or _truthy(order.get("closePosition")))
    )
    return {
        "symbol": order.get("symbol"),
        "order_type": order_type or None,
        "algo_id": order.get("algoId"),
        "client_algo_id": order.get("clientAlgoId"),
        "reduce_only": _truthy(order.get("reduceOnly")),
        "close_position": _truthy(order.get("closePosition")),
        "severity": "warning" if stale_protection else "critical",
    }


def reconcile_snapshot(  # noqa: PLR0913
    *,
    equity: float | None,
    positions: list[dict],
    normal_orders: list[dict],
    algo_orders: list[dict],
    db_open_trades: list,
    order_states: list,
) -> dict:
    """Classify drift without modifying exchange or DB state."""
    warnings = []
    critical = []
    position_symbols = [p.get("symbol") for p in positions if p.get("symbol")]
    db_symbols = {_row_symbol(row) for row in db_open_trades if _row_symbol(row)}

    seen = set()
    duplicates = set()
    for symbol in position_symbols:
        if symbol in seen:
            duplicates.add(symbol)
        seen.add(symbol)
    critical.extend(f"duplicate exchange position rows for {symbol}" for symbol in sorted(duplicates))

    for position in positions:
        symbol = position.get("symbol")
        if not symbol:
            continue
        if symbol not in db_symbols:
            critical.append(f"exchange position {symbol} has no open DB trade")
        _protected, detail = has_exchange_protection(symbol, normal_orders, algo_orders)
        if not detail["has_sl"]:
            critical.append(
                f"exchange position {symbol} missing protection SL={detail['has_sl']} TP={detail['has_tp']}"
            )
        elif not detail["has_tp"]:
            warnings.append(f"exchange position {symbol} missing TP while SL is verified")

    position_symbol_set = set(position_symbols)
    warnings.extend(
        f"DB open trade {symbol} has no exchange position" for symbol in sorted(db_symbols - position_symbol_set)
    )
    for state in order_states:
        symbol = _row_symbol(state)
        if symbol and symbol not in position_symbol_set:
            warnings.append(f"persisted order state {symbol} has no exchange position")

    stale_algo_orders = [
        _stale_algo_order_detail(order)
        for order in algo_orders
        if order.get("symbol") and order.get("symbol") not in position_symbol_set
    ]
    for stale in stale_algo_orders:
        symbol = stale["symbol"]
        order_type = stale["order_type"] or "UNKNOWN"
        detail = f"stale algo order {symbol} {order_type} has no exchange position"
        if stale["severity"] == "warning":
            warnings.append(detail)
        else:
            critical.append(f"unsafe {detail}")

    return {
        "healthy": not critical,
        "equity_usd": equity,
        "critical_mismatches": critical,
        "warnings": warnings,
        "positions": sorted(position_symbol_set),
        "db_open_trades": sorted(db_symbols),
        "normal_open_order_count": len(normal_orders),
        "algo_open_order_count": len(algo_orders),
        "stale_algo_order_count": len(stale_algo_orders),
        "stale_algo_orders": stale_algo_orders,
        "checked_at": datetime.now(UTC).isoformat(),
        "dry_run": True,
    }


def reconcile_live_state(dry_run: bool = True, fail_soft: bool = False) -> dict:
    """Fetch a read-only live snapshot and store its last classification.

    fail_soft=True is for /status and Doctor only: transient exchange timeouts
    return the last cached authoritative snapshot instead of inventing a
    critical mismatch. Trading gates keep fail_soft=False and still fail closed.
    """
    del dry_run  # Reconciliation is intentionally read-only in this phase.
    global _last_reconcile
    try:
        balance = get_balance()
        positions = get_open_positions()
        if positions is None:
            raise RuntimeError("exchange positions unavailable")
        _last_reconcile = reconcile_snapshot(
            equity=float(balance.get("equity", 0) or 0),
            positions=positions,
            normal_orders=get_open_orders(),
            algo_orders=get_open_algo_orders(),
            db_open_trades=trade_db.get_open_trades(),
            order_states=trade_db.get_binance_order_states(),
        )
        _save_reconcile_cache(_last_reconcile)
    except Exception as e:
        if fail_soft:
            cached = _last_reconcile or _load_reconcile_cache()
            _last_reconcile = _mark_cached_after_refresh_error(cached, e) if cached else _unavailable_state(e)
        else:
            _last_reconcile = {
                "healthy": False,
                "equity_usd": None,
                "critical_mismatches": [f"reconciliation unavailable: {e}"],
                "warnings": [],
                "stale_algo_order_count": 0,
                "stale_algo_orders": [],
                "checked_at": datetime.now(UTC).isoformat(),
                "dry_run": True,
            }
    return _last_reconcile


def get_last_reconcile_state(load_cache: bool = True) -> dict:
    """Return last live reconcile state without causing exchange calls."""
    cached = _last_reconcile or (_load_reconcile_cache() if load_cache else None)
    return cached or {
        "healthy": None,
        "critical_mismatches": [],
        "warnings": ["reconciliation has not run in this process"],
        "stale_algo_order_count": 0,
        "stale_algo_orders": [],
        "checked_at": None,
        "dry_run": True,
    }
