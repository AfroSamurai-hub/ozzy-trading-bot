"""Read-only lifecycle classification for DB/exchange product sync."""

from __future__ import annotations


def _symbol(value: dict) -> str:
    return str(value.get("symbol") or value.get("tv_symbol") or "").upper()


def _side(value: dict) -> str:
    return str(value.get("type") or value.get("direction") or value.get("side") or "").upper()


def _qty(value: dict) -> float | None:
    for key in ("volume", "qty", "positionAmt"):
        raw = value.get(key)
        if raw not in (None, ""):
            try:
                return abs(float(raw))
            except Exception:
                return None
    return None


def _trade_id(trade: dict) -> int | None:
    raw = trade.get("id") or trade.get("trade_id")
    try:
        return int(raw)
    except Exception:
        return None


def _protection_for_symbol(reconciliation: dict | None, symbol: str) -> dict:
    reconciliation = reconciliation or {}
    result = {"has_sl": None, "has_tp": None, "protected": None, "reason": None}
    for key in ("critical_mismatches", "warnings"):
        for row in reconciliation.get(key) or []:
            if not isinstance(row, dict) or str(row.get("symbol") or "").upper() != symbol:
                continue
            reason = row.get("reason") or row.get("mismatch") or row.get("type") or key
            result.update(
                {
                    "has_sl": row.get("has_sl", result["has_sl"]),
                    "has_tp": row.get("has_tp", result["has_tp"]),
                    "protected": False if key == "critical_mismatches" else result["protected"],
                    "reason": reason,
                }
            )
    if result["protected"] is None and (reconciliation or {}).get("healthy") is True:
        result["protected"] = True
    return result


def classify_lifecycle_items(
    *,
    mode: str,
    positions: list[dict],
    trade_rows: dict[str, dict],
    reconciliation: dict | None = None,
) -> list[dict]:
    """Classify current DB/exchange sync state without taking action."""
    mode = str(mode or "").upper()
    items: list[dict] = []
    position_by_symbol = {_symbol(pos): pos for pos in positions if _symbol(pos)}
    symbols = sorted(set(position_by_symbol) | set(trade_rows))

    for symbol in symbols:
        pos = position_by_symbol.get(symbol)
        trade = trade_rows.get(symbol, {})
        protection = _protection_for_symbol(reconciliation, symbol)
        exchange_exists = pos is not None
        db_exists = bool(trade)
        state = "UNKNOWN_NEEDS_RECONCILE"
        monitor_action_allowed = False
        reason = "unknown"

        if exchange_exists and not db_exists:
            state = "ORPHAN_EXCHANGE_POSITION"
            reason = "exchange_position_without_open_db_trade"
        elif db_exists and not exchange_exists:
            state = "DB_GHOST_TRADE"
            reason = "open_db_trade_without_exchange_position"
        elif exchange_exists and db_exists:
            db_side = _side(trade)
            exchange_side = _side(pos)
            if db_side and exchange_side and db_side != exchange_side:
                state = "OPEN_UNPROTECTED_MANAGEMENT_SUSPENDED"
                reason = "db_exchange_side_mismatch"
            elif protection.get("protected") is False:
                state = "OPEN_UNPROTECTED_MANAGEMENT_SUSPENDED"
                reason = protection.get("reason") or "protection_truth_failed"
            elif protection.get("protected") is True:
                state = "OPEN_PROTECTED"
                monitor_action_allowed = True
                reason = "db_exchange_and_protection_agree"
            else:
                state = "UNKNOWN_NEEDS_RECONCILE"
                reason = "protection_truth_unknown"

        items.append(
            {
                "mode": mode,
                "symbol": symbol,
                "state": state,
                "side": _side(pos or trade),
                "db_trade_id": _trade_id(trade) if db_exists else None,
                "db_qty": _qty(trade) if db_exists else None,
                "exchange_qty": _qty(pos) if exchange_exists else None,
                "db_status": trade.get("execution_state") if db_exists else None,
                "exchange_position_exists": exchange_exists,
                "sl_visible": protection.get("has_sl"),
                "tp_visible": protection.get("has_tp"),
                "protection_truth": protection.get("protected"),
                "monitor_action_allowed": monitor_action_allowed,
                "reason": reason,
            }
        )
    return items
