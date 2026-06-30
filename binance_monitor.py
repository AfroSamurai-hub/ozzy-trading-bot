#!/usr/bin/env python3
# ============================================
# HERMES — Binance Futures Position Monitor v2
# ============================================
# Polls Binance open positions every 30 seconds.
# Responsibilities:
#   1. Move SL to breakeven once profit >= 1x SL distance
#   2. Trailing stop management (ATR-based, percent-based, fixed)
#   3. Tiered profit-taking (close portions at 1.5R, 2.5R, 3.5R)
#   4. Warn when position open > MAX_TRADE_HOURS
#   5. Report PnL status every 5 minutes
#   6. Send Telegram notifications for key events
#
# This is the QUEEN's bodyguard — executes protective actions automatically.
# The AI (Jarvis) can SET trailing modes via command_center, but this monitor
# handles the actual execution tick-by-tick.

import json
import os
import sys
import time
from datetime import UTC, datetime, timezone
from decimal import Decimal, InvalidOperation

sys.path.insert(0, '/home/rick/ozzy-bot')
_MONITOR_START_TIME = time.time()

import telegram_client
import trade_db
from binance_connector import (
    _format_quantity,
    _get_client,
    _place_sl_tp_order,
    close_position_qty,
    get_balance,
    get_open_positions,
    get_post_fill_protection_mode,
    has_exchange_protection,
    inspect_exchange_protection,
    move_sl_to_breakeven,
)
from command_center import _get_position_state
from config import (
    BINANCE_SYMBOLS,
    BREAKEVEN_TRIGGER,
    CHOCH_AUTO_CLOSE,
    EARLY_PROFIT_PROTECTION,
    LANES,
    MAX_TRADE_HOURS,
    MOMENTUM_EXIT_R,
    MOMENTUM_LOOKBACK_SECONDS,
    MONITOR_TRAIL_DEBUG_LOGS,
    PAPER_MODE,
    PROFIT_PROTECT_R,
    TIME_EXIT_HOURS,
    TIME_REDUCE_HOURS,
    TRAIL_ACTIVATION,
    TRAIL_DISTANCE,
)
from logger import plain_log

POLL_INTERVAL = 30  # seconds
REPORT_INTERVAL = 1800  # 30 minutes — only sends when positions are open or errors occur
UTC = UTC
MILESTONE_ERROR_BACKOFF_SECONDS = 15 * 60
SIDE_MISMATCH_ALERT_INTERVAL_SECONDS = 60 * 60

# Per-position in-memory state
_position_state = {}
PROTECTIVE_EXIT_TYPES = {
    "time_reduce",
    "time_exit",
    "momentum_exit",
    "profit_protect",
    "early_giveback",
    "roundtrip_guard_r1",
}
_logged_unmapped_tps = set()
ROUNDTRIP_GUARD_R1_PEAK_R = 0.30
ROUNDTRIP_GUARD_R1_CURRENT_R = -0.05
ROUNDTRIP_GUARD_R1_GIVEBACK_PCT = 80.0
ROUNDTRIP_GUARD_OBSERVER_DIR = os.getenv("HERMES_OBSERVER_DIR", "/home/rick/ozzy-bot/observer")
ROUNDTRIP_GUARD_CANDIDATE_TYPE = "ROUNDTRIP_CANDIDATE"
SLOT_PRESSURE_REVIEW_ENABLED = os.getenv("HERMES_SLOT_PRESSURE_REVIEW_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
SLOT_PRESSURE_REVIEW_MIN_AGE_MIN = float(os.getenv("HERMES_SLOT_PRESSURE_REVIEW_MIN_AGE_MIN", "240"))
SLOT_PRESSURE_REVIEW_MIN_PEAK_R = float(os.getenv("HERMES_SLOT_PRESSURE_REVIEW_MIN_PEAK_R", "0.10"))
SLOT_PRESSURE_REVIEW_MAX_PEAK_R = float(os.getenv("HERMES_SLOT_PRESSURE_REVIEW_MAX_PEAK_R", "0.50"))
SLOT_PRESSURE_REVIEW_MAX_CURRENT_R = float(os.getenv("HERMES_SLOT_PRESSURE_REVIEW_MAX_CURRENT_R", "0.35"))


def _row_get(row, key: str, default=None):
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        return row[key]
    except Exception:
        try:
            return row.get(key, default)
        except Exception:
            return default


def _open_trade_direction_mismatch(position: dict, state: dict) -> bool:
    """Return True when an exchange position no longer matches any open DB trade.

    Testnet can occasionally behave badly around reduce-only partial exits and
    leave a flipped exchange-side position while the DB still contains the old
    trade direction. In that state, milestone and trailing logic must stop
    firing because it will calculate exits from stale side/quantity anchors.
    """
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    exchange_side = position.get("type", "BUY")
    trade_id = state.get("trade_id")

    if trade_id:
        try:
            trade = trade_db.get_trade_by_id(trade_id)
            if trade and trade["direction"] == exchange_side:
                return False
        except Exception as e:
            plain_log("BINANCE_MONITOR_TRADE_LOOKUP_ERROR", {
                "symbol": tv_symbol,
                "trade_id": trade_id,
                "error": str(e),
            })

    try:
        open_trades = trade_db.get_open_trades(symbol)
    except Exception as e:
        plain_log("BINANCE_MONITOR_OPEN_TRADE_LOOKUP_ERROR", {"symbol": tv_symbol, "error": str(e)})
        return False

    matching = [t for t in open_trades if t["direction"] == exchange_side]
    if matching:
        state["trade_id"] = matching[0]["id"]
        return False

    if not open_trades:
        return False

    now = time.time()
    last_alert = float(state.get("_side_mismatch_alerted_at", 0) or 0)
    if now - last_alert > SIDE_MISMATCH_ALERT_INTERVAL_SECONDS:
        state["_side_mismatch_alerted_at"] = now
        db_sides = [t["direction"] for t in open_trades]
        db_ids = [t["id"] for t in open_trades]
        plain_log("BINANCE_MONITOR_SIDE_MISMATCH_BLOCKED", {
            "symbol": tv_symbol,
            "exchange_side": exchange_side,
            "db_sides": db_sides,
            "db_trade_ids": db_ids,
            "action": "management_suspended",
        })
        for trade in open_trades:
            try:
                trade_db.update_trade_accounting_status(
                    trade["id"],
                    "dirty",
                    f"Exchange side {exchange_side} does not match open DB trade side {trade['direction']}",
                )
            except Exception:
                pass
        _send_telegram(
            f"🚨 <b>POSITION STATE MISMATCH</b>\n"
            f"{tv_symbol} exchange side is {exchange_side}, but DB open trade side is {', '.join(db_sides)}.\n"
            f"Milestones/trailing suspended for this symbol until reconciled."
        )
    return True


def _get_state(symbol: str) -> dict:
    return _position_state.setdefault(symbol, {
        "breakeven_moved": False,
        "trailing_active": False,
        "current_sl": None,
        "long_warned": False,
        "last_report": 0,
        "entry_price": 0,
        "sl_price": None,
        "tp_price": None,
        "trade_id": None,
        "peak_pnl": 0,
        "worst_pnl": 0,
        "first_seen": 0,
        "original_qty": 0,
        "milestones_hit": [],
        "milestone_config": None,
        "choch_alerted": False,
        "tiered_exits": [],
    })


def _recover_state_from_db(state: dict, trade_id: int, symbol: str) -> None:
    """Restore monitor state from DB after restart."""
    try:
        trade_row = trade_db.get_trade_by_id(trade_id)
        if trade_row:
            try:
                state["timeframe"] = trade_row["timeframe"]
            except Exception:
                pass
            if trade_row["qty"]:
                db_qty = float(trade_row["qty"])
                if db_qty > 0:
                    state["original_qty"] = db_qty

        # Recover peak PnL from DB
        if trade_row and trade_row["peak_pnl"]:
            state["peak_pnl"] = float(trade_row["peak_pnl"])
        if trade_row and trade_row["peak_pnl"] and trade_row["risk_dollars"]:
            risk_dollars = float(trade_row["risk_dollars"])
            if risk_dollars > 0:
                state["_peak_r"] = max(float(state.get("_peak_r", 0)), float(trade_row["peak_pnl"]) / risk_dollars)

        # Recover milestones hit from exits table
        exits = trade_db.get_exits_for_trade(trade_id)
        hit = set(state.get("milestones_hit", []))
        for ex in exits:
            exit_type = ex["exit_type"]
            if exit_type:
                if exit_type.startswith("milestone_") or exit_type == "regime_aware_chop_profit_taken":
                    hit.add(exit_type)
                if exit_type in ("15m_time_decay_trim", "time_decay_trim"):
                    state["decay_trimmed"] = True
        state["milestones_hit"] = list(hit)

        # Recover current SL from binance_order_state so trailing stops compare correctly
        try:
            order_state = trade_db.get_binance_order_state(symbol)
            if order_state and order_state["current_sl"]:
                state["current_sl"] = float(order_state["current_sl"])
        except Exception:
            pass

        # Recover breakeven / trailing from milestones table
        if trade_db.milestone_exists(trade_id, "1R_breakeven"):
            state["breakeven_moved"] = True
            state["_peak_r"] = max(float(state.get("_peak_r", 0)), 1.0)
        if trade_db.milestone_exists(trade_id, "1.5R_trail_active"):
            state["trailing_active"] = True
    except Exception as e:
        plain_log("STATE_RECOVER_ERROR", {"trade_id": trade_id, "error": str(e)})


def _infer_exit_reason_from_orders(symbol: str, entry_price: float, breakeven_moved: bool, trailing_active: bool = False) -> tuple[str | None, float | None]:
    """
    Phase 2 — Poll Binance order history for the exact exit reason and fill price.
    Returns (reason, avg_price) or (None, None) if unavailable.
    """
    if PAPER_MODE:
        return None, None
    try:
        client = _get_client()
        orders = client.futures_get_all_orders(symbol=symbol, limit=20)
        if not orders:
            return None, None

        cutoff_ms = int((time.time() - 600) * 1000)
        reduce_orders = [
            o for o in orders
            if o.get("status") == "FILLED"
            and o.get("reduceOnly") is True
            and o.get("updateTime", 0) > cutoff_ms
        ]
        if not reduce_orders:
            return None, None

        reduce_orders.sort(key=lambda o: o.get("updateTime", 0), reverse=True)
        order = reduce_orders[0]
        order_type = order.get("type", "")
        avg_price = float(order.get("avgPrice", 0) or 0)

        if order_type in ("STOP_MARKET", "STOP"):
            if breakeven_moved and entry_price > 0:
                deviation = abs(avg_price - entry_price) / entry_price
                if deviation < 0.001:
                    return "breakeven", avg_price
            return "sl", avg_price
        elif order_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
            return "tp", avg_price
        elif order_type == "TRAILING_STOP_MARKET":
            return "trail", avg_price
        elif order_type == "MARKET":
            # Triggered STOP_MARKET / TRAILING_STOP_MARKET appear as MARKET when filled
            if trailing_active:
                return "trail", avg_price
            return "opposite", avg_price
        else:
            return "manual", avg_price
    except Exception as e:
        plain_log("EXIT_REASON_INFER_ERROR", {"symbol": symbol, "error": str(e)})
        return None, None


def _latest_protective_exit(trade_id: int):
    """Return the latest already-logged protective exit for a trade, if any."""
    try:
        exits = trade_db.get_exits_for_trade(trade_id)
    except Exception as e:
        plain_log("PROTECTIVE_EXIT_LOOKUP_ERROR", {"trade_id": trade_id, "error": str(e)})
        return None

    protective = [ex for ex in exits if ex["exit_type"] in PROTECTIVE_EXIT_TYPES]
    if not protective:
        return None
    return protective[-1]


def _reconciled_close_pnl(trade_id: int, state: dict, exit_price: float, fallback_pnl: float) -> dict:
    """Build a close PnL that agrees with side, entry, exit and partial exits."""
    trade_row = trade_db.get_trade_by_id(trade_id)

    def row_value(key: str, default=None):
        if not trade_row:
            return default
        try:
            if hasattr(trade_row, "keys") and key not in trade_row.keys():
                return default
            return trade_row[key]
        except Exception:
            try:
                return trade_row.get(key, default)
            except Exception:
                return default

    entry = float(state.get("entry_price") or row_value("entry_price", 0) or 0)
    direction = str(state.get("direction") or row_value("direction", "BUY") or "BUY")
    original_qty = float(state.get("original_qty") or row_value("qty", 0) or 0)
    partial_pnl = trade_db.get_realized_exit_pnl(trade_id)
    partial_qty_pct = trade_db.get_realized_exit_qty_pct(trade_id)
    if entry <= 0 or exit_price <= 0 or original_qty <= 0:
        return {
            "pnl": float(fallback_pnl or 0.0) + partial_pnl,
            "final_slice_pnl": float(fallback_pnl or 0.0),
            "remaining_qty": original_qty,
            "realized_partial_pnl": partial_pnl,
            "realized_partial_qty_pct": partial_qty_pct,
            "fallback_pnl": float(fallback_pnl or 0.0),
            "mismatch": False,
        }
    audit = trade_db.reconcile_trade_close_pnl(
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        original_qty=original_qty,
        realized_partial_pnl=partial_pnl,
        realized_partial_qty_pct=partial_qty_pct,
        fallback_pnl=fallback_pnl,
    )
    if audit["mismatch"]:
        plain_log(
            "TRADE_ACCOUNTING_MISMATCH_CORRECTED",
            {
                "trade_id": trade_id,
                "symbol": state.get("symbol") or (trade_row["symbol"] if trade_row else None),
                "direction": direction,
                "entry_price": entry,
                "exit_price": exit_price,
                "original_qty": original_qty,
                **audit,
            },
        )
    return audit


def _select_exchange_fill_cycle(direction: str, fills: list[dict]) -> dict:
    """Return the first complete flat-to-flat fill cycle for one trade."""
    direction = str(direction or "").upper()
    if direction not in {"BUY", "SELL"}:
        return {"complete": False, "fills": [], "error": "invalid_direction"}

    entry_side = direction
    exit_side = "BUY" if direction == "SELL" else "SELL"
    expected_position_side = "SHORT" if direction == "SELL" else "LONG"
    cycle: list[dict] = []
    open_qty = Decimal("0")
    saw_exit = False

    for fill in sorted(fills or [], key=lambda row: int(row.get("time") or 0)):
        position_side = str(fill.get("positionSide") or expected_position_side).upper()
        if position_side not in {expected_position_side, "BOTH"}:
            continue
        side = str(fill.get("side") or "").upper()
        if side not in {entry_side, exit_side}:
            continue
        try:
            qty = Decimal(str(fill.get("qty") or 0))
        except (InvalidOperation, ValueError):
            continue
        if qty <= 0:
            continue
        if not cycle and side != entry_side:
            continue

        cycle.append(fill)
        if side == entry_side:
            open_qty += qty
        else:
            saw_exit = True
            open_qty -= qty
            if open_qty < 0:
                return {"complete": False, "fills": cycle, "error": "exit_qty_exceeds_entry_qty"}
            if open_qty == 0:
                return {
                    "complete": saw_exit,
                    "fills": cycle,
                    "terminal_time_ms": int(fill.get("time") or 0),
                }

    return {"complete": False, "fills": cycle, "error": "incomplete_fill_cycle"}


def _terminal_fill_query_end_ms(trade) -> int | None:
    """Return a short settlement bound after the latest terminal exit intent."""
    trade_id = _row_get(trade, "id")
    if not trade_id:
        return None
    terminal_types = PROTECTIVE_EXIT_TYPES | {
        "sl", "tp", "trail", "breakeven", "opposite", "manual", "expiry",
    }
    exits = trade_db.get_exits_for_trade(int(trade_id))
    terminal = [row for row in exits if str(row["exit_type"] or "").lower() in terminal_types]
    if not terminal:
        return None
    parsed = datetime.fromisoformat(str(terminal[-1]["ts"]).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.astimezone(UTC).timestamp() * 1000) + 120_000


def _fetch_exchange_trade_ledger(trade) -> dict:
    """Fetch the closed trade's authoritative fills, fees, and funding."""
    symbol = str(_row_get(trade, "symbol", "") or "").upper()
    direction = str(_row_get(trade, "direction", "") or "").upper()
    raw_ts = str(_row_get(trade, "ts", "") or "").replace("Z", "+00:00")
    if not symbol or direction not in {"BUY", "SELL"} or not raw_ts:
        return {"complete": False, "error": "missing_trade_identity"}
    try:
        opened_at = datetime.fromisoformat(raw_ts)
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        start_ms = int(opened_at.astimezone(UTC).timestamp() * 1000)
        client = _get_client()
        end_ms = _terminal_fill_query_end_ms(trade)
        trade_query = {"symbol": symbol, "startTime": start_ms, "limit": 100}
        if end_ms is not None:
            trade_query["endTime"] = end_ms
        queried_fills = client.futures_account_trades(**trade_query)
        cycle = _select_exchange_fill_cycle(direction, queried_fills)
        if not cycle.get("complete"):
            return {
                "complete": False,
                "error": cycle.get("error") or "incomplete_fill_cycle",
                "queried_fill_count": len(queried_fills or []),
                "selected_fill_count": len(cycle.get("fills") or []),
            }
        fills = cycle["fills"]
        terminal_time_ms = int(cycle["terminal_time_ms"])
        funding_rows = client.futures_income_history(
            symbol=symbol,
            incomeType="FUNDING_FEE",
            startTime=start_ms,
            endTime=terminal_time_ms,
            limit=100,
        )
        funding = sum(float(row.get("income") or 0.0) for row in funding_rows or [])
        ledger = trade_db.reconcile_exchange_fill_ledger(direction, fills, funding=funding)
        ledger.update({
            "fill_count": len(fills),
            "queried_fill_count": len(queried_fills or []),
            "terminal_time_ms": terminal_time_ms,
            "funding_verified": True,
        })
        return ledger
    except Exception as e:
        plain_log("EXCHANGE_FILL_LEDGER_ERROR", {"symbol": symbol, "error": str(e)})
        return {"complete": False, "error": str(e)}


def _prune_state(open_symbols: set):
    # 1. Any symbol in memory state that is no longer open on Binance
    stale = [s for s in _position_state if s not in open_symbols and s != "_last_balance_report"]

    # 2. Any symbol that has an open trade in the database, but is no longer open on Binance
    try:
        db_open_trades = trade_db.get_open_trades()
        for ot in db_open_trades:
            ot_symbol = ot["symbol"]
            if ot_symbol and ot_symbol not in open_symbols and ot_symbol not in stale:
                # Add a grace period of 90 seconds (0.025 hours) for newly created database trades
                # to prevent race conditions where the database open trade is created before the
                # position is visible in get_open_positions()
                age_hours = _trade_open_age_hours(ot["id"], ot_symbol)
                if age_hours is not None and age_hours < 0.025:  # 90 seconds grace period
                    plain_log("MONITOR_PRUNE_GRACE_PERIOD", {
                        "symbol": ot_symbol,
                        "trade_id": ot["id"],
                        "age_seconds": round(age_hours * 3600, 2)
                    })
                    continue
                stale.append(ot_symbol)
    except Exception as e:
        plain_log("DB_OPEN_TRADES_QUERY_ERROR", {"error": str(e)})

    for s in stale:
        state = _position_state.pop(s, None)

        # Reconstruct state from DB if it was closed while the monitor was offline
        if state is None:
            try:
                db_open_for_s = trade_db.get_open_trades(s)
                if db_open_for_s:
                    db_trade = db_open_for_s[0]
                    tid = db_trade["id"]
                    state = {
                        "trade_id": tid,
                        "entry_price": float(db_trade["entry_price"] or 0),
                        "last_pnl": 0.0,
                        "last_price": float(db_trade["entry_price"] or 0),
                        "first_seen": time.time(),
                        "breakeven_moved": False,
                        "trailing_active": False,
                        "direction": db_trade["direction"] or "BUY",
                        "peak_pnl": 0.0,
                    }
                    _recover_state_from_db(state, tid, s)
            except Exception as db_err:
                plain_log("STATE_RECONSTRUCT_DB_ERROR", {"symbol": s, "error": str(db_err)})

        if state is None:
            continue

        plain_log("BINANCE_MONITOR_PRUNE", {"symbol": s, "reason": "position_closed"})
        # Back-fill SQLite trade journal
        try:
            tid = state.get("trade_id") if state else None
            if tid:
                existing_trade = trade_db.get_trade_by_id(tid)
                cleanup_ok = _cancel_stale_reduce_only_orders(s)
                if not cleanup_ok:
                    plain_log("BINANCE_ORDER_STATE_RETAINED", {
                        "symbol": s,
                        "trade_id": tid,
                        "reason": "terminal_exchange_cleanup_not_verified",
                    })
                    continue
                if existing_trade and existing_trade["exit_price"] is not None:
                    plain_log("BINANCE_MONITOR_PRUNE_SKIP_CLOSED", {
                        "symbol": s,
                        "trade_id": tid,
                        "exit_reason": existing_trade["exit_reason"],
                    })
                    try:
                        trade_db.delete_binance_order_state(s)
                        plain_log("BINANCE_ORDER_STATE_DELETED", {"symbol": s, "reason": "position_closed"})
                    except Exception as e:
                        plain_log("BINANCE_ORDER_STATE_DELETE_ERROR", {"symbol": s, "error": str(e)})
                    continue
                entry = state.get("entry_price", 0)
                last_pnl = state.get("last_pnl", 0)
                last_price = state.get("last_price", entry)
                age_hours = _trade_open_age_hours(tid, s)
                if age_hours is not None:
                    duration_min = int(age_hours * 60)
                else:
                    duration_min = int((time.time() - state.get("first_seen", time.time())) / 60)
                breakeven_moved = state.get("breakeven_moved", False)
                trailing_active = state.get("trailing_active", False)
                logged_protective_exit = _latest_protective_exit(tid)

                # Phase 2 — accurate order-based inference
                if logged_protective_exit:
                    exit_reason = logged_protective_exit["exit_type"]
                    order_avg_price = logged_protective_exit["price"]
                    plain_log("EXIT_REASON_PROTECTIVE", {
                        "symbol": s,
                        "trade_id": tid,
                        "reason": exit_reason,
                        "price": order_avg_price,
                    })
                    if order_avg_price and order_avg_price > 0:
                        last_price = order_avg_price
                else:
                    exit_reason, order_avg_price = _infer_exit_reason_from_orders(s, entry, breakeven_moved, trailing_active)
                if logged_protective_exit:
                    plain_log("EXIT_REASON_PROTECTIVE_FINAL", {
                        "symbol": s,
                        "trade_id": tid,
                        "reason": exit_reason,
                    })
                elif exit_reason:
                    plain_log("EXIT_REASON_ORDER", {"symbol": s, "reason": exit_reason, "avg_price": order_avg_price})
                    # Use actual fill price from order history when available
                    if order_avg_price and order_avg_price > 0:
                        last_price = order_avg_price
                else:
                    # Phase 1 — heuristic fallback
                    if abs(last_pnl) < 1.0 and breakeven_moved:
                        exit_reason = "breakeven"
                    elif trailing_active and last_pnl > 0:
                        exit_reason = "trail"
                    elif last_pnl > 0:
                        exit_reason = "opposite"
                    elif last_pnl < 0:
                        exit_reason = "sl"
                    else:
                        exit_reason = "unknown"
                    plain_log("EXIT_REASON_HEURISTIC", {"symbol": s, "reason": exit_reason})

                # Prefer Binance's fill ledger: it carries actual entry/exit
                # prices, realized PnL, commissions, and signed funding.
                ledger = _fetch_exchange_trade_ledger(existing_trade)
                if ledger.get("complete"):
                    trade_db.update_trade_fill(tid, ledger["entry_price"], ledger["entry_qty"])
                    last_price = ledger["exit_price"]
                    total_pnl = ledger["net_pnl"]
                    gross_pnl = ledger["gross_pnl"]
                    fees = ledger["fees"]
                    funding = ledger["funding"]
                    accounting_status = "clean"
                    accounting_notes = "exchange fills, commissions, and funding reconciled"
                else:
                    # Directional reconstruction is useful operationally but
                    # cannot be clean accounting when exchange costs are absent.
                    accounting = _reconciled_close_pnl(tid, {**state, "symbol": s}, last_price, last_pnl)
                    total_pnl = accounting["pnl"]
                    gross_pnl = total_pnl
                    fees = 0.0
                    funding = 0.0
                    accounting_status = "unchecked"
                    accounting_notes = (
                        "exchange fill ledger unavailable; directional close math excludes unverified costs"
                    )
                trade_db.close_trade(
                    trade_id=tid,
                    exit_price=last_price,
                    pnl=total_pnl,
                    gross_pnl=gross_pnl,
                    fees=fees,
                    funding=funding,
                    exit_reason=exit_reason,
                    duration_min=duration_min,
                    accounting_status=accounting_status,
                    accounting_notes=accounting_notes,
                )
                if not logged_protective_exit:
                    trade_db.log_exit(
                        trade_id=tid,
                        exit_type=exit_reason,
                        price=last_price,
                        qty_pct=_remaining_original_fraction(state, state.get("original_qty", 0)),
                        notes=f"Position closed via {exit_reason}",
                    )

                # Log TP milestone if applicable
                if exit_reason == "tp":
                    plain_log("MILESTONE_FILLED", {
                        "symbol": s,
                        "trade_id": tid,
                        "milestone": "2.5R_tp",
                        "price": last_price,
                        "qty": float(existing_trade["qty"] if existing_trade and existing_trade.get("qty") else 0) * 0.75
                    })
                    _log_fixed_milestone(tid, "2.5R_tp", last_price, last_pnl, s, state.get("direction", "BUY"))
                    plain_log("MILESTONE_PNL_RECORDED", {
                        "symbol": s,
                        "trade_id": tid,
                        "milestone": "2.5R_tp",
                        "pnl": last_pnl
                    })

                # Non-negotiable: Telegram alert on every close
                try:
                    direction = state.get("direction", "BUY")
                    hours, mins = divmod(duration_min, 60)
                    duration_str = f"{hours}h {mins}m" if hours else f"{mins}m"
                    peak = state.get("peak_pnl", 0)

                    if exit_reason == "tp":
                        telegram_client.notify_tp_hit(s, direction, total_pnl, duration_str)
                    elif exit_reason == "sl":
                        telegram_client.notify_sl_hit(s, direction, total_pnl, duration_str)
                    elif exit_reason == "trail":
                        telegram_client.notify_trail_stopped(s, direction, total_pnl, peak)
                    elif exit_reason == "breakeven":
                        _send_telegram(
                            f"🛡️ <b>BREAKEVEN CLOSE</b>\n"
                            f"{s} {direction}\n"
                            f"Entry: {entry:,.2f}  Exit: {last_price:,.2f}\n"
                            f"Duration: {duration_str}"
                        )
                    else:
                        emoji_pnl = "🟢" if total_pnl >= 0 else "🔴"
                        _send_telegram(
                            f"🏁 <b>TRADE CLOSED</b>\n"
                            f"{s} {direction}\n"
                            f"Entry: {entry:,.2f}\n"
                            f"Exit:  {last_price:,.2f}\n"
                            f"{emoji_pnl} PnL: ${total_pnl:+.2f}\n"
                            f"Peak: ${peak:+.2f}\n"
                            f"⏱ Duration: {duration_str}\n"
                            f"🎯 Reason: {exit_reason.upper()}"
                        )
                except Exception:
                    pass

                # Clean up binance_order_state so restart doesn't recover stale data
                try:
                    trade_db.delete_binance_order_state(s)
                    plain_log("BINANCE_ORDER_STATE_DELETED", {"symbol": s, "reason": "position_closed"})
                except Exception as e:
                    plain_log("BINANCE_ORDER_STATE_DELETE_ERROR", {"symbol": s, "error": str(e)})
        except Exception:
            pass


_telegram_warning_throttle = {}


def _send_telegram(message: str):
    try:
        # Check if this is a warning/failure
        is_warning = "⚠️" in message or "🚨" in message or "WARNING" in message.upper() or "FAILED" in message.upper()
        if is_warning:
            import re
            match = re.search(r'\b[A-Z0-9]+USDT\b', message)
            symbol = match.group(0) if match else "GLOBAL"

            # Determine msg type (e.g. the first bold line like <b>TRAILING STOP FAILED</b>)
            msg_type = "GENERAL_WARNING"
            type_match = re.search(r'<b>(.*?)</b>', message)
            if type_match:
                msg_type = type_match.group(1)

            now = time.time()
            throttle_key = (symbol, msg_type)
            last_sent = _telegram_warning_throttle.get(throttle_key, 0)
            if now - last_sent < 900:  # 15 minutes = 900 seconds
                plain_log("TELEGRAM_WARNING_THROTTLED", {
                    "symbol": symbol, "msg_type": msg_type, "message": message
                })
                return
            _telegram_warning_throttle[throttle_key] = now

        from telegram_client import send_message
        send_message(f"<b>BINANCE MONITOR</b>\n{message}")
    except Exception as e:
        plain_log("BINANCE_MONITOR_TELEGRAM_ERROR", {"error": str(e)})



def _extract_protective_orders(symbol: str) -> dict:
    """Fetch Binance open SL/TP orders for a symbol."""
    if PAPER_MODE:
        return {"sl": None, "tp": None, "orders": [], "algo_orders": []}
    try:
        client = _get_client()
        orders = client.futures_get_open_orders(symbol=symbol)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception as e:
            plain_log("BINANCE_ALGO_RECONCILE_ERROR", {"symbol": symbol, "error": str(e)})
            algo_orders = []
        combined_orders = list(orders) + list(algo_orders)
        sl_orders = [o for o in combined_orders if _monitor_order_type(o) in ("STOP_MARKET", "STOP")]
        tp_orders = [o for o in combined_orders if _monitor_order_type(o) in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT")]
        sl_order = sl_orders[-1] if sl_orders else None
        tp_order = tp_orders[-1] if tp_orders else None
        return {"sl": sl_order, "tp": tp_order, "orders": orders, "algo_orders": algo_orders}
    except Exception as e:
        plain_log("BINANCE_ORDER_RECONCILE_ERROR", {"symbol": symbol, "error": str(e)})
        return {"sl": None, "tp": None, "orders": [], "algo_orders": []}


def _order_stop_price(order: dict | None) -> float | None:
    if not order:
        return None
    for key in ("stopPrice", "triggerPrice", "price"):
        try:
            value = float(order.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return None


def _reconcile_order_state(position: dict) -> None:
    """Persist protective order state from Binance open orders."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    orders = _extract_protective_orders(symbol)
    sl_order = orders["sl"]
    tp_order = orders["tp"]
    sl_price = _order_stop_price(sl_order)
    tp_price = _order_stop_price(tp_order)
    entry = float(position.get("openPrice", 0) or 0)
    qty = float(position.get("volume", 0) or 0)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    original_sl_distance = cc_state.get("original_sl_distance")
    if not original_sl_distance and sl_price and entry:
        original_sl_distance = abs(entry - sl_price)
        cc_state["original_sl_distance"] = original_sl_distance
        cc_state["original_sl"] = sl_price
        cc_state["entry_price"] = entry

    # Fetch previous state for milestone fill detection
    try:
        prev_state = trade_db.get_binance_order_state(symbol)
    except Exception:
        prev_state = None

    prev_raw_state = {}
    if prev_state:
        try:
            if prev_state.get("raw_state_json"):
                prev_raw_state = json.loads(prev_state["raw_state_json"])
        except Exception:
            pass

        trade_id = state.get("trade_id") or prev_raw_state.get("trade_id")
        if trade_id:
            # We fetch all orders from Binance to verify what was filled
            try:
                client = _get_client()
                all_orders = client.futures_get_all_orders(symbol=symbol, limit=20)
            except Exception as e:
                plain_log("BINANCE_ORDERS_FETCH_ERROR", {"symbol": symbol, "error": str(e)})
                all_orders = []

            # Extract TP1 / TP2 prices and expected quantities from raw_state
            tp1_price = prev_raw_state.get("tp1_price")
            tp1_qty = prev_raw_state.get("tp1_qty")
            tp2_price = prev_raw_state.get("tp2_price")
            tp2_qty = prev_raw_state.get("tp2_qty")

            # Check open orders
            combined_orders = list(orders.get("orders", [])) + list(orders.get("algo_orders", []))

            # Reconcile expected milestone orders
            has_tp1_active = False
            has_tp2_active = False

            # 2. Classify active TAKE_PROFIT_MARKET orders by exchange-visible fields
            active_tp_orders = []
            pos_type = str(position.get("type") or "").upper()
            pos_vol = float(position.get("volume", 0) or 0)
            if pos_type in ("BUY", "LONG"):
                position_side = "LONG"
            elif pos_type in ("SELL", "SHORT"):
                position_side = "SHORT"
            else:
                position_side = "LONG" if pos_vol > 0 else "SHORT"
            opposite_exit_side = "SELL" if position_side == "LONG" else "BUY"

            for o in combined_orders:
                if _monitor_order_type(o) in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                    o_symbol = o.get("symbol")
                    o_pos_side = o.get("positionSide")
                    o_side = o.get("side")
                    o_status = str(o.get("status") or "NEW").upper()
                    o_qty = float(o.get("quantity") or o.get("origQty") or 0)
                    o_price = _order_stop_price(o)

                    if (
                        o_symbol == symbol and
                        o_pos_side == position_side and
                        o_side == opposite_exit_side and
                        o_status not in ("FILLED", "CANCELED", "EXPIRED", "REJECTED") and
                        o_qty > 0 and
                        o_price is not None and o_price > 0
                    ):
                        active_tp_orders.append({
                            "order": o,
                            "price": o_price,
                            "qty": o_qty
                        })

            mapped_indices = set()

            # 1. Try to map confidently by price proximity (within 0.2%)
            for idx, active_tp in enumerate(active_tp_orders):
                o_price = active_tp["price"]
                if tp1_price and abs(o_price - tp1_price) / tp1_price < 0.002:
                    has_tp1_active = True
                    mapped_indices.add(idx)
                elif tp2_price and abs(o_price - tp2_price) / tp2_price < 0.002:
                    has_tp2_active = True
                    mapped_indices.add(idx)

            # 3. If TP order exists but cannot be confidently mapped to TP1/TP2,
            # log MILESTONE_RECONCILED_UNMAPPED_TP, not tp_active=false.
            # In this case, we map unmapped TP orders to missing expected TPs.
            unmapped_tps = [active_tp for idx, active_tp in enumerate(active_tp_orders) if idx not in mapped_indices]
            for active_tp in unmapped_tps:
                tp_key = (tv_symbol, active_tp["price"], active_tp["qty"])
                if tp_key not in _logged_unmapped_tps:
                    plain_log("MILESTONE_RECONCILED_UNMAPPED_TP", {
                        "symbol": tv_symbol,
                        "price": active_tp["price"],
                        "qty": active_tp["qty"],
                        "orderId": active_tp["order"].get("orderId")
                    })
                    _logged_unmapped_tps.add(tp_key)

                # Map to missing TPs if possible to prevent reporting tp_active=false
                if tp1_price and not has_tp1_active:
                    has_tp1_active = True
                elif tp2_price and not has_tp2_active:
                    has_tp2_active = True

            # Emit MILESTONE_RECONCILED event
            plain_log("MILESTONE_RECONCILED", {
                "symbol": tv_symbol, "trade_id": trade_id, "tp1_active": has_tp1_active, "tp2_active": has_tp2_active
            })

            # Check if expected milestone order is missing on exchange and warn
            if tp1_price and float(tp1_qty or 0) > 0 and not has_tp1_active:
                if not trade_db.milestone_exists(trade_id, "milestone_0"):
                    plain_log("MILESTONE_RECONCILED_WARNING", {
                        "symbol": tv_symbol, "warning": "Expected TP1 milestone order is missing on exchange"
                    })

            # Detect if TP1 has been filled
            for o in all_orders:
                if o.get("status") == "FILLED" and o.get("type") in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                    o_id = str(o.get("orderId") or o.get("algoId") or "")
                    o_price = float(o.get("avgPrice") or o.get("stopPrice") or 0)
                    o_qty = float(o.get("executedQty") or o.get("origQty") or 0)

                    # Match TP1
                    is_tp1 = False
                    if str(prev_raw_state.get("tp1_detail", {}).get("orderId")) == o_id or (tp1_price and abs(o_price - tp1_price) / tp1_price < 0.002):
                        is_tp1 = True

                    if is_tp1 and not trade_db.milestone_exists(trade_id, "milestone_0"):
                        milestone_name = "milestone_0"
                        close_pct = 0.25

                        plain_log("MILESTONE_FILLED", {
                            "symbol": tv_symbol, "trade_id": trade_id, "milestone": milestone_name, "price": o_price, "qty": o_qty
                        })

                        direction = state.get("direction") or prev_state.get("side") or "BUY"
                        realized_pnl = trade_db.calculate_directional_pnl(direction, entry, o_price, o_qty)

                        # Log realized profit to DB/journal
                        trade_db.log_milestone(trade_id, milestone_name, o_price, realized_pnl)
                        trade_db.log_exit(
                            trade_id=trade_id,
                            exit_type=milestone_name,
                            price=o_price,
                            pnl_contribution=realized_pnl,
                            qty_pct=close_pct,
                            notes=f"Milestone TP1 filled on exchange @ {o_price:,.4f}",
                        )

                        plain_log("MILESTONE_PNL_RECORDED", {
                            "symbol": tv_symbol, "trade_id": trade_id, "milestone": milestone_name, "pnl": realized_pnl
                        })

                        telegram_client.notify_milestone(trade_id, milestone_name, tv_symbol, o_price, realized_pnl)

    try:
        trade_db.upsert_binance_order_state(
            symbol=symbol,
            tv_symbol=tv_symbol,
            side=position.get("type"),
            sl_order_id=str(sl_order.get("orderId") or sl_order.get("algoId")) if sl_order else None,
            tp_order_id=str(tp_order.get("orderId") or tp_order.get("algoId")) if tp_order else None,
            original_qty=state.get("original_qty") or qty,
            remaining_qty=qty,
            entry_price=entry,
            original_sl=cc_state.get("original_sl"),
            current_sl=sl_price,
            current_tp=tp_price,
            original_sl_distance=original_sl_distance,
            runner_status="open",
            raw_state={
                "open_order_count": len(orders["orders"]),
                "open_algo_order_count": len(orders.get("algo_orders", [])),
                "trade_id": state.get("trade_id"),
                "tp1_price": prev_raw_state.get("tp1_price") if prev_state else None,
                "tp1_qty": prev_raw_state.get("tp1_qty") if prev_state else None,
                "tp2_price": prev_raw_state.get("tp2_price") if prev_state else None,
                "tp2_qty": prev_raw_state.get("tp2_qty") if prev_state else None,
                "tp1_detail": prev_raw_state.get("tp1_detail") if prev_state else None,
                "tp2_detail": prev_raw_state.get("tp2_detail") if prev_state else None,
            },
        )
    except Exception as e:
        plain_log("BINANCE_ORDER_STATE_ERROR", {"symbol": symbol, "error": str(e)})


def _monitor_order_type(order: dict) -> str:
    return str(order.get("type") or order.get("orderType") or "").upper()


def _capture_open_protection(client, symbol: str) -> tuple[list[dict], list[dict]]:
    protection_types = {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
    normal_orders = [
        o for o in client.futures_get_open_orders(symbol=symbol)
        if _monitor_order_type(o) in protection_types
    ]
    try:
        algo_orders = [
            o for o in client.futures_get_open_algo_orders(symbol=symbol)
            if _monitor_order_type(o) in protection_types
        ]
    except Exception as e:
        plain_log("BINANCE_ALGO_FETCH_ERROR", {"symbol": symbol, "error": str(e)})
        algo_orders = []
    return normal_orders, algo_orders


def _cancel_captured_protection(client, symbol: str, normal_orders: list[dict], algo_orders: list[dict]) -> list[str]:
    errors = []
    for order in normal_orders:
        try:
            client.futures_cancel_order(symbol=symbol, orderId=order["orderId"])
            o_type = _monitor_order_type(order)
            if o_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                plain_log("MILESTONE_STALE_ORDER_CLEANED", {
                    "symbol": symbol,
                    "order_id": order.get("orderId"),
                    "price": _order_stop_price(order),
                    "type": "normal"
                })
        except Exception as e:
            errors.append(f"normal:{order.get('orderId')}: {e}")
            plain_log("BINANCE_PARTIAL_PROTECTION_CANCEL_ERROR", {
                "symbol": symbol,
                "orderId": order.get("orderId"),
                "error": str(e),
            })
    for order in algo_orders:
        try:
            client.futures_cancel_algo_order(symbol=symbol, algoId=order["algoId"])
            o_type = _monitor_order_type(order)
            if o_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                plain_log("MILESTONE_STALE_ORDER_CLEANED", {
                    "symbol": symbol,
                    "order_id": order.get("algoId"),
                    "price": _order_stop_price(order),
                    "type": "algo"
                })
        except Exception as e:
            errors.append(f"algo:{order.get('algoId')}: {e}")
            plain_log("BINANCE_PARTIAL_PROTECTION_CANCEL_ERROR", {
                "symbol": symbol,
                "algoId": order.get("algoId"),
                "error": str(e),
            })
    return errors


def _trade_anchor_price(trade_id: int | None, key: str) -> float | None:
    if not trade_id:
        return None
    try:
        row = trade_db.get_trade_by_id(trade_id)
        if row and row[key]:
            return float(row[key])
    except Exception:
        return None
    return None


def _refresh_remaining_protection_after_partial(position: dict, remaining_qty: float) -> bool:
    """Resize SL/TP protection to the post-partial remaining quantity.

    Binance reduce-only conditional orders are quantity-bound. After a partial
    close, old protection can become oversized or disappear, so the runner must
    be re-armed before the old captured orders are removed.
    """
    if PAPER_MODE:
        return True

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    side = position.get("type", "BUY")
    state = _get_state(symbol)
    close_side = "SELL" if side == "BUY" else "BUY"
    backoff_until = float(state.get("_partial_protection_refresh_backoff_until", 0) or 0)
    if time.time() < backoff_until:
        plain_log("BINANCE_PARTIAL_PROTECTION_REFRESH_BACKOFF", {
            "symbol": tv_symbol,
            "backoff_until": backoff_until,
            "reason": state.get("_partial_protection_refresh_backoff_reason"),
        })
        return False

    qty = _format_quantity(symbol, abs(float(remaining_qty or 0)))
    if qty <= 0:
        return True

    trade_id = state.get("trade_id")
    sl_price = (
        state.get("current_sl")
        or position.get("stopLoss")
        or state.get("sl_price")
        or _trade_anchor_price(trade_id, "sl")
    )
    tp_price = (
        position.get("takeProfit")
        or state.get("tp_price")
        or _trade_anchor_price(trade_id, "tp")
    )
    try:
        sl_price = float(sl_price or 0)
        tp_price = float(tp_price or 0)
    except (TypeError, ValueError):
        sl_price = 0.0
        tp_price = 0.0

    if sl_price <= 0 or tp_price <= 0:
        plain_log("BINANCE_PARTIAL_PROTECTION_REFRESH_SKIPPED", {
            "symbol": tv_symbol,
            "remaining_qty": qty,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "reason": "missing_sl_or_tp_anchor",
        })
        _send_telegram(
            f"⚠️ <b>PARTIAL PROTECTION REFRESH SKIPPED</b>\n"
            f"{tv_symbol} missing SL/TP anchor after partial close"
        )
        return False

    try:
        client = _get_client()
        old_normal, old_algo = _capture_open_protection(client, symbol)
        position_side = "LONG" if side == "BUY" else "SHORT"
        sl_result = _place_sl_tp_order(
            client=client,
            symbol=symbol,
            side=close_side,
            order_type="STOP_MARKET",
            stop_price=sl_price,
            quantity=qty,
            position_side=position_side,
        )
        tp_result = _place_sl_tp_order(
            client=client,
            symbol=symbol,
            side=close_side,
            order_type="TAKE_PROFIT_MARKET",
            stop_price=tp_price,
            quantity=qty,
            position_side=position_side,
        )
        if not sl_result.get("success") or not tp_result.get("success"):
            plain_log("BINANCE_PARTIAL_PROTECTION_REFRESH_FAILED_OLD_KEPT", {
                "symbol": tv_symbol,
                "remaining_qty": qty,
                "sl_result": {k: sl_result.get(k) for k in ("success", "error", "code")},
                "tp_result": {k: tp_result.get(k) for k in ("success", "error", "code")},
            })
            _send_telegram(
                f"🚨 <b>PARTIAL PROTECTION REFRESH FAILED</b>\n"
                f"{tv_symbol} old protection retained where available"
            )
            return False

        try:
            normal_now = client.futures_get_open_orders(symbol=symbol)
            algo_now = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception as e:
            plain_log("BINANCE_PARTIAL_PROTECTION_VERIFY_FETCH_ERROR", {"symbol": tv_symbol, "error": str(e)})
            normal_now, algo_now = [], []
        protected, detail = has_exchange_protection(
            symbol,
            open_orders=normal_now,
            algo_orders=algo_now,
            expected_side=close_side,
            expected_qty=qty,
            expected_sl=sl_price,
            expected_tp=tp_price,
            expected_position_side=position_side,
        )
        if not protected:
            plain_log("BINANCE_PARTIAL_PROTECTION_REFRESH_UNVERIFIED_OLD_KEPT", {
                "symbol": tv_symbol,
                "remaining_qty": qty,
                "detail": detail,
            })
            _send_telegram(
                f"🚨 <b>PARTIAL PROTECTION UNVERIFIED</b>\n"
                f"{tv_symbol} old protection retained where available"
            )
            return False

        cancel_errors = _cancel_captured_protection(client, symbol, old_normal, old_algo)
        state["current_sl"] = sl_price
        state["tp_price"] = tp_price
        try:
            trade_db.upsert_binance_order_state(
                symbol=symbol,
                tv_symbol=tv_symbol,
                side=side,
                sl_order_id=str(sl_result.get("orderId")) if sl_result.get("orderId") else None,
                tp_order_id=str(tp_result.get("orderId")) if tp_result.get("orderId") else None,
                remaining_qty=qty,
                current_sl=sl_price,
                current_tp=tp_price,
                runner_status="open",
                raw_state={"partial_refresh": True, "cancel_errors": cancel_errors},
            )
        except Exception as e:
            plain_log("BINANCE_PARTIAL_PROTECTION_STATE_ERROR", {"symbol": tv_symbol, "error": str(e)})
        plain_log("BINANCE_PARTIAL_PROTECTION_REFRESHED", {
            "symbol": tv_symbol,
            "remaining_qty": qty,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "cancel_errors": cancel_errors,
            "detail": detail,
        })
        return True
    except Exception as e:
        plain_log("BINANCE_PARTIAL_PROTECTION_REFRESH_ERROR", {"symbol": tv_symbol, "error": str(e)})
        _send_telegram(
            f"🚨 <b>PARTIAL PROTECTION REFRESH ERROR</b>\n"
            f"{tv_symbol}: {e}"
        )
        return False


def _position_protection_anchors(position: dict, state: dict) -> tuple[float, float]:
    """Resolve the intended SL/TP prices for an already-open position."""
    trade_id = state.get("trade_id")
    sl_price = (
        state.get("current_sl")
        or position.get("stopLoss")
        or state.get("sl_price")
        or _trade_anchor_price(trade_id, "sl")
    )
    tp_price = (
        state.get("tp_price")
        or position.get("takeProfit")
        or _trade_anchor_price(trade_id, "tp")
    )
    if (not sl_price or not tp_price) and trade_id:
        try:
            order_state = trade_db.get_binance_order_state(position["symbol"])
            if order_state:
                sl_price = sl_price or order_state["current_sl"] or order_state["original_sl"]
                tp_price = tp_price or order_state["current_tp"]
        except Exception as e:
            plain_log("BINANCE_PROTECTION_ANCHOR_STATE_ERROR", {
                "symbol": position.get("tv_symbol", position.get("symbol")),
                "error": str(e),
            })
    try:
        return float(sl_price or 0), float(tp_price or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0


def _repair_missing_protection_if_needed(position: dict) -> bool:
    """Repair live positions whose exchange-visible SL/TP protection is missing.

    The webhook already blocks new live entries when reconciliation sees a naked
    position. This monitor is the second line of defense: it attempts to re-arm
    both reduce-only SL and TP, verifies them on Binance, then retires any old
    captured protection only after the replacement is live.
    """
    if PAPER_MODE or get_post_fill_protection_mode() != "repair":
        return True

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    side = position.get("type", "BUY")
    close_side = "SELL" if side == "BUY" else "BUY"
    qty = _format_quantity(symbol, abs(float(position.get("volume", 0) or 0)))
    if qty <= 0:
        return True

    sl_price, tp_price = _position_protection_anchors(position, state)
    if sl_price <= 0 or tp_price <= 0:
        plain_log("BINANCE_PROTECTION_REPAIR_SKIPPED", {
            "symbol": tv_symbol,
            "reason": "missing_sl_or_tp_anchor",
            "sl_price": sl_price,
            "tp_price": tp_price,
            "qty": qty,
        })
        return False

    try:
        client = _get_client()
        normal_orders = client.futures_get_open_orders(symbol=symbol)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception as e:
            plain_log("BINANCE_ALGO_FETCH_ERROR", {"symbol": tv_symbol, "error": str(e)})
            algo_orders = []

        position_side = "LONG" if side == "BUY" else "SHORT"
        protected, detail = has_exchange_protection(
            symbol,
            open_orders=normal_orders,
            algo_orders=algo_orders,
            expected_side=close_side,
            expected_qty=qty,
            expected_sl=sl_price,
            expected_tp=tp_price,
            expected_position_side=position_side,
        )
        if protected:
            return True

        now = time.time()
        last_attempt = float(state.get("_protection_repair_last_at", 0) or 0)
        if now - last_attempt < 60:
            return False
        state["_protection_repair_last_at"] = now

        old_normal, old_algo = _capture_open_protection(client, symbol)

        # Check if matching STOP_MARKET closePosition=true SL already exists using the shared verifier
        from binance_connector import inspect_exchange_protection
        detail_ex = inspect_exchange_protection(
            symbol,
            open_orders=normal_orders,
            algo_orders=algo_orders,
            expected_side=close_side,
            expected_position_side=position_side,
            expected_sl=sl_price,
            expected_sl_qty=qty,
        )
        has_existing_close_pos = detail_ex.get("has_sl", False)

        if not has_existing_close_pos:
            sl_result = _place_sl_tp_order(
                client=client,
                symbol=symbol,
                side=close_side,
                order_type="STOP_MARKET",
                stop_price=sl_price,
                quantity=qty,
                position_side=position_side,
            )
        else:
            plain_log("BINANCE_SL_REPAIR_SKIPPED_HARD_SL_ACTIVE", {
                "symbol": tv_symbol,
                "reason": "Matching STOP_MARKET closePosition=true already exists (skip SL repair)"
            })
            sl_result = {"success": True}

        tp_result = _place_sl_tp_order(
            client=client,
            symbol=symbol,
            side=close_side,
            order_type="TAKE_PROFIT_MARKET",
            stop_price=tp_price,
            quantity=qty,
            position_side=position_side,
        )
        if not sl_result.get("success") or not tp_result.get("success"):
            plain_log("BINANCE_PROTECTION_REPAIR_FAILED", {
                "symbol": tv_symbol,
                "qty": qty,
                "detail": detail,
                "sl_result": {k: sl_result.get(k) for k in ("success", "error", "code")},
                "tp_result": {k: tp_result.get(k) for k in ("success", "error", "code")},
            })
            _send_telegram(
                f"🚨 <b>PROTECTION REPAIR FAILED</b>\n"
                f"{tv_symbol} {side}\n"
                f"SL/TP placement failed; entries remain blocked by reconciliation."
            )
            return False

        normal_now = client.futures_get_open_orders(symbol=symbol)
        try:
            algo_now = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception as e:
            plain_log("BINANCE_PROTECTION_REPAIR_VERIFY_ALGO_ERROR", {"symbol": tv_symbol, "error": str(e)})
            algo_now = []
        verified, verify_detail = has_exchange_protection(
            symbol,
            open_orders=normal_now,
            algo_orders=algo_now,
            expected_side=close_side,
            expected_qty=qty,
            expected_sl=sl_price,
            expected_tp=tp_price,
            expected_position_side=position_side,
        )
        if not verified:
            plain_log("BINANCE_PROTECTION_REPAIR_UNVERIFIED", {
                "symbol": tv_symbol,
                "qty": qty,
                "detail": verify_detail,
            })
            _send_telegram(
                f"🚨 <b>PROTECTION REPAIR UNVERIFIED</b>\n"
                f"{tv_symbol} {side}\n"
                f"New SL/TP not exchange-visible; entries remain blocked."
            )
            return False

        cancel_errors = _cancel_captured_protection(client, symbol, old_normal, old_algo)
        state["current_sl"] = sl_price
        state["tp_price"] = tp_price
        try:
            trade_db.upsert_binance_order_state(
                symbol=symbol,
                tv_symbol=tv_symbol,
                side=side,
                sl_order_id=str(sl_result.get("orderId")) if sl_result.get("orderId") else None,
                tp_order_id=str(tp_result.get("orderId")) if tp_result.get("orderId") else None,
                remaining_qty=qty,
                current_sl=sl_price,
                current_tp=tp_price,
                runner_status="open",
                raw_state={"auto_repair": True, "cancel_errors": cancel_errors},
            )
        except Exception as e:
            plain_log("BINANCE_PROTECTION_REPAIR_STATE_ERROR", {"symbol": tv_symbol, "error": str(e)})
        plain_log("BINANCE_PROTECTION_REPAIRED", {
            "symbol": tv_symbol,
            "qty": qty,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "detail": verify_detail,
            "cancel_errors": cancel_errors,
        })
        _send_telegram(
            f"🛡️ <b>PROTECTION REPAIRED</b>\n"
            f"{tv_symbol} {side}\n"
            f"SL {sl_price:,.4f} | TP {tp_price:,.4f}"
        )
        return True
    except Exception as e:
        plain_log("BINANCE_PROTECTION_REPAIR_ERROR", {"symbol": tv_symbol, "error": str(e)})
        return False


# ---------------------------------------------------------------------------
# Core protective logic
# ---------------------------------------------------------------------------

def _log_fixed_milestone(trade_id: int, milestone: str, price: float, pnl: float, tv_symbol: str, side: str):
    """Log a fixed milestone and optionally notify Telegram."""
    if trade_id and trade_db.log_milestone(trade_id, milestone, price, pnl):
        plain_log("MILESTONE", {
            "trade_id": trade_id, "milestone": milestone,
            "price": price, "pnl": pnl, "symbol": tv_symbol,
        })
        telegram_client.notify_milestone(trade_id, milestone, tv_symbol, price, pnl)
        # Legacy direct notifications for specific milestones
        if milestone == "1.5R_trail_active":
            _send_telegram(
                f"🎯 <b>TRAIL ACTIVE</b>\n"
                f"{tv_symbol} {side}\n"
                f"PnL: ${pnl:+.2f}"
            )
        elif milestone == "2R_trail_update":
            _send_telegram(
                f"📈 <b>2R HIT</b>\n"
                f"{tv_symbol} {side}\n"
                f"PnL: ${pnl:+.2f}  Trail locked"
            )


def _check_fixed_milestones(position: dict):
    """Track fixed R-multiple milestones: 1R, 1.5R, 2R, 2.5R."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    pnl = float(position.get("profit", 0))
    qty = float(position.get("volume", 0))

    if entry <= 0 or qty <= 0:
        return

    # Original SL distance in price terms
    sl_dist = cc_state.get("original_sl_distance")
    if not sl_dist:
        sl = position.get("stopLoss", 0)
        if sl:
            sl_dist = abs(entry - float(sl))
        else:
            sl_dist = abs(entry - current) * 0.4

    if sl_dist <= 0:
        return

    risk_dollars = sl_dist * qty
    if risk_dollars <= 0:
        return

    current_r = pnl / risk_dollars
    tid = state.get("trade_id")

    # 1R breakeven
    if current_r >= 1.0 and not trade_db.milestone_exists(tid, "1R_breakeven"):
        _log_fixed_milestone(tid, "1R_breakeven", current, pnl, tv_symbol, side)

    # 1.5R trail active
    if current_r >= 1.5 and not trade_db.milestone_exists(tid, "1.5R_trail_active"):
        _log_fixed_milestone(tid, "1.5R_trail_active", current, pnl, tv_symbol, side)

    # 2R trail update
    if current_r >= 2.0 and not trade_db.milestone_exists(tid, "2R_trail_update"):
        _log_fixed_milestone(tid, "2R_trail_update", current, pnl, tv_symbol, side)

    # 2.5R TP (logged on close, not here)


def _check_time_decay_exit(position: dict):
    """If 15m timeframe trade is open for >= 60m, in profit (net > 0), and hasn't hit milestone_1,
    trim 15% of the position and move the stop loss to entry (soft breakeven).
    """
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    tid = state.get("trade_id")
    if not tid:
        return

    # Check if this is a 15m trade
    timeframe = str(state.get("timeframe", ""))
    if timeframe != "15":
        return

    # Check if already trimmed via time decay
    if state.get("decay_trimmed"):
        return

    # Profit check (unrealized pnl > 0)
    pnl = float(position.get("profit", 0))
    if pnl <= 0:
        return

    # Age check (>= 60 minutes = 1.0 hour)
    age_hours = _trade_open_age_hours(tid, symbol)
    if age_hours is None or age_hours < 1.0:
        return

    # Target check: "hasn't hit Milestone 1"
    if trade_db.milestone_exists(tid, "milestone_1"):
        return

    # Execute the "Time-Decay Trim" (close 15% of the position)
    original_qty = state.get("original_qty", 0)
    if original_qty <= 0:
        return

    close_qty = original_qty * 0.15
    close_qty = _format_quantity(symbol, close_qty)

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")

    if PAPER_MODE:
        plain_log("PAPER_TIME_DECAY_TRIM", {
            "symbol": tv_symbol, "qty": close_qty,
        })
    else:
        res = _close_position_once(symbol, close_qty, reason="time_decay")
        if res.get("status") == "error":
            plain_log("BINANCE_TIME_DECAY_TRIM_ERROR", {
                "symbol": tv_symbol, "error": res.get("error"),
            })
            return

    # Move stop-loss to entry (soft breakeven)
    move_sl_to_breakeven(symbol, entry)
    state["breakeven_moved"] = True
    cc_state["breakeven_moved"] = True
    state["decay_trimmed"] = True

    # Log milestone and exit in DB
    try:
        trade_db.log_exit(
            trade_id=tid,
            exit_type="15m_time_decay_trim",
            price=current,
            pnl_contribution=pnl * 0.15,
            qty_pct=0.15,
            notes="15m Time-Decay Trim Executed (Closed 15% & SL to entry after 60m)",
        )
    except Exception as e:
        plain_log("DB_TIME_DECAY_TRIM_LOG_ERROR", {"trade_id": tid, "error": str(e)})

    # Dispatch notifications
    msg = (
        f"⏳ <b>TIME-DECAY TRIM</b>\n"
        f"{tv_symbol} {side} (15m strategy)\n"
        f"Trimmed 15% of position (closed {close_qty}) after 60m.\n"
        f"Stop-loss moved to entry: {entry:,.2f}\n"
        f"Current: {current:,.2f} | PnL: ${pnl:+.2f}"
    )
    plain_log("BINANCE_TIME_DECAY_TRIM_EXECUTED", {
        "symbol": tv_symbol, "qty": close_qty, "entry": entry, "current": current, "pnl": pnl
    })
    _send_telegram(msg)


def _check_breakeven(position: dict):
    """Move SL to entry price when profit >= BREAKEVEN_TRIGGER x SL distance."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    tid = state.get("trade_id")
    if state["breakeven_moved"] or cc_state.get("breakeven_moved"):
        return
    if tid and trade_db.milestone_exists(tid, "1R_breakeven"):
        state["breakeven_moved"] = True
        cc_state["breakeven_moved"] = True
        return

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    pnl = float(position.get("profit", 0))

    if pnl <= 0:
        return

    # True 1R check: profit in USD must exceed original SL distance × position size
    sl_dist = cc_state.get("original_sl_distance")
    qty = float(position.get("volume", 0))
    risk_amount = sl_dist * qty if sl_dist and qty else 0

    from dynamic_config import get_param
    breakeven_trigger_r = get_param("breakeven_trigger_r", BREAKEVEN_TRIGGER)
    if risk_amount > 0 and pnl >= (risk_amount * breakeven_trigger_r):
        move_sl_to_breakeven(symbol, entry)
        state["breakeven_moved"] = True
        cc_state["breakeven_moved"] = True
        # Also log the 1R breakeven milestone
        if tid:
            _log_fixed_milestone(tid, "1R_breakeven", current, pnl, tv_symbol, side)
        msg = (
            f"🛡️ <b>BREAKEVEN</b>\n"
            f"{tv_symbol} {side}\n"
            f"SL moved to entry: {entry:,.2f}\n"
            f"Current: {current:,.2f} | PnL: ${pnl:+.2f}"
        )
        plain_log("BINANCE_BREAKEVEN_TRIGGERED", {
            "symbol": tv_symbol, "entry": entry, "current": current, "pnl": pnl
        })
        _send_telegram(msg)


def _current_r_multiple_from_pnl(position: dict, state: dict) -> float | None:
    """Return current R based on realized PnL vs original risk amount."""
    pnl = float(position.get("profit", 0) or 0)
    cc_state = _get_position_state(position.get("tv_symbol", position["symbol"]))
    sl_dist = float(state.get("original_sl_distance") or cc_state.get("original_sl_distance") or 0)
    qty = float(position.get("volume", 0) or 0)
    if sl_dist <= 0 or qty <= 0:
        return None
    return pnl / (sl_dist * qty)


def _get_early_profit_config(lane_name: str | None) -> dict:
    """Return early-profit policy for the lane, falling back to the global config."""
    if lane_name:
        lane = LANES.get(lane_name)
        if lane and lane.early_profit_protection:
            return lane.early_profit_protection
    return EARLY_PROFIT_PROTECTION


def _check_early_profit_protection(position: dict):
    """Pickpocket rule: scale out on early spikes and move SL to breakeven."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    lane_name = state.get("lane")
    cfg = _get_early_profit_config(lane_name)
    if not cfg.get("enabled"):
        return

    current_r = _current_r_multiple_from_pnl(position, state)
    if current_r is None:
        return

    peak_r = float(state.get("_peak_r", 0) or 0)
    if current_r > peak_r:
        peak_r = current_r
        state["_peak_r"] = peak_r

    side = position.get("type", "BUY")
    qty = float(position.get("volume", 0) or 0)
    entry = float(position.get("openPrice", 0) or 0)
    current = float(position.get("currentPrice", 0) or 0)
    pnl = float(position.get("profit", 0) or 0)

    for key in ["first_scale", "second_scale"]:
        scale = cfg.get(key)
        if not scale:
            continue
        hit_key = f"early_profit_{key}"
        if state.get(hit_key):
            continue
        if current_r < scale["profit_r"]:
            continue

        close_pct = float(scale.get("close_pct", 0) or 0)
        close_qty = _format_quantity(symbol, qty * close_pct)
        if close_qty <= 0 or close_qty > qty:
            continue

        if not PAPER_MODE:
            res = _close_position_once(symbol, close_qty, reason=f"early_profit_{key}")
            if res.get("status") not in {"ok", "closed", "partial_closed"}:
                plain_log("EARLY_PROFIT_SCALE_ERROR", {
                    "symbol": tv_symbol, "key": key, "error": res.get("error"),
                })
                return
            remaining = qty - close_qty
            if remaining > 0:
                _refresh_remaining_protection_after_partial(position, remaining)

        state[hit_key] = True
        if scale.get("move_sl_to_breakeven") and entry > 0:
            move_sl_to_breakeven(symbol, entry)
            state["breakeven_moved"] = True
            cc_state["breakeven_moved"] = True

        partial_pnl = pnl * close_pct
        try:
            trade_db.log_exit(
                tid,
                f"early_profit_{key}",
                current,
                partial_pnl,
                qty_pct=close_pct,
                notes=f"Early profit scale {key} at {current_r:.2f}R",
            )
        except Exception:
            pass

        _send_telegram(
            f"💰 <b>EARLY PROFIT {key.upper()}</b>\n"
            f"{tv_symbol} {side}\n"
            f"Closed {int(close_pct * 100)}% @ {current:,.2f}\n"
            f"Locked: ${partial_pnl:+.2f} | R: {current_r:.2f}"
        )
        # A second scale must use a fresh exchange quantity snapshot.
        break


def _check_milestone_exits(position: dict):
    """DB-driven milestone exits. Config read from gate_thresholds per symbol."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    if _open_trade_direction_mismatch(position, state):
        return
    if not state.get("trade_id"):
        return

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    position_side = "LONG" if side == "BUY" else "SHORT"
    pnl = float(position.get("profit", 0))
    qty = float(position.get("volume", 0))
    if entry <= 0 or qty <= 0:
        return

    original_qty = state.get("original_qty", qty)
    if original_qty <= 0:
        return

    sl_dist = cc_state.get("original_sl_distance")
    if not sl_dist:
        trade_row = trade_db.get_trade_by_id(state.get("trade_id")) if state.get("trade_id") else None
        if trade_row:
            db_entry = float(trade_row["entry_price"] or entry)
            db_sl = float(trade_row["sl"] or 0)
            if db_entry > 0 and db_sl > 0:
                sl_dist = abs(db_entry - db_sl)
            elif float(trade_row["risk_dollars"] or 0) > 0 and float(trade_row["qty"] or 0) > 0:
                sl_dist = float(trade_row["risk_dollars"]) / float(trade_row["qty"])
        if not sl_dist:
            return
        cc_state["original_sl_distance"] = sl_dist

    # R-multiple — positive only when price moves in profit direction
    raw_r = (current - entry) / sl_dist if sl_dist > 0 else 0
    if side == "SELL":
        raw_r = -raw_r
    current_r = raw_r

    milestones = state.get("milestone_config")
    if milestones is None:
        milestones = trade_db.get_milestone_config(symbol)
        state["milestone_config"] = milestones

    # Dynamic Regime-Aware Milestone Injection for 1-hour trades
    timeframe = str(state.get("timeframe", ""))
    if timeframe == "60":
        adx_value = state.get("adx_value")
        adx_fetched_at = state.get("adx_fetched_at", 0)
        now = time.time()

        # 5-minute TTL cache to avoid rate-limiting
        if adx_value is None or (now - adx_fetched_at) > 300:
            try:
                from binance_indicators import calculate_adx
                adx_value = calculate_adx(symbol, interval="1h")
                state["adx_value"] = adx_value
                state["adx_fetched_at"] = now
                plain_log("REGIME_AWARE_ADX_QUERIED", {
                    "symbol": tv_symbol,
                    "adx": adx_value,
                })
            except Exception as e:
                plain_log("REGIME_AWARE_ADX_ERROR", {
                    "symbol": tv_symbol,
                    "error": str(e)
                })

        # Inject choppy milestone if ADX < 25
        if adx_value is not None and adx_value < 25.0:
            chop_gate = "regime_aware_chop_profit_taken"
            if not any(ms["gate_name"] == chop_gate for ms in milestones):
                # Copy list so we don't pollute the persistent milestone_config cache
                milestones = list(milestones)
                milestones.append({
                    "gate_name": chop_gate,
                    "threshold": 0.3,
                    "close_pct": 0.25
                })
                # Sort milestones by threshold to keep evaluation order logical
                milestones.sort(key=lambda x: x["threshold"])

    hit = set(state.get("milestones_hit", []))
    retry_after = state.setdefault("_milestone_retry_after", {})
    now = time.time()

    for ms in milestones:
        gate_name = ms["gate_name"]
        if gate_name in hit:
            continue
        if now < float(retry_after.get(gate_name, 0) or 0):
            continue
        if current_r >= ms["threshold"]:
            close_qty = qty * ms["close_pct"]
            close_qty = _format_quantity(symbol, close_qty)
            if close_qty > 0 and close_qty <= qty:
                if PAPER_MODE:
                    plain_log("PAPER_MILESTONE", {
                        "symbol": tv_symbol, "gate_name": gate_name,
                        "current_r": round(current_r, 2),
                        "qty": close_qty, "remaining": qty - close_qty,
                    })
                else:
                    res = _close_position_once(symbol, close_qty, reason=gate_name, position_side=position_side)
                    if res.get("status") not in {"ok", "closed", "partial_closed"}:
                        if res.get("status") == "skipped":
                            return
                        retry_after[gate_name] = time.time() + MILESTONE_ERROR_BACKOFF_SECONDS
                        plain_log("BINANCE_MILESTONE_ERROR", {
                            "symbol": tv_symbol, "gate_name": gate_name,
                            "error": res.get("error"),
                            "retry_after_seconds": MILESTONE_ERROR_BACKOFF_SECONDS,
                        })
                        continue

                remaining = qty - close_qty
                refresh_success = True
                if not PAPER_MODE and remaining > 0:
                    refresh_success = _refresh_remaining_protection_after_partial(position, remaining)

                hit.add(gate_name)
                state["milestones_hit"] = list(hit)

                if refresh_success:
                    partial_pnl = pnl * (close_qty / qty) if qty > 0 else 0
                    tid = state.get("trade_id")
                    if tid:
                        try:
                            trade_db.log_exit(
                                trade_id=tid,
                                exit_type=gate_name,
                                price=current,
                                pnl_contribution=partial_pnl,
                                qty_pct=ms["close_pct"],
                                notes=f"{gate_name}: closed {int(ms['close_pct']*100)}% at R={round(current_r, 2)}",
                            )
                        except Exception:
                            pass

                    label = f"{int(ms['close_pct']*100)}%"
                    _send_telegram(
                        f"🎯 <b>{gate_name.upper().replace('_', ' ')}</b>\n"
                        f"{'📈 LONG' if side == 'BUY' else '📉 SHORT'} {tv_symbol}\n"
                        f"Closed {label} @ {current:,.2f}\n"
                        f"💰 Partial PnL: ${partial_pnl:+.2f}\n"
                        f"📦 Remaining qty: {remaining}\n"
                        f"📊 Current R: {round(current_r, 2)}"
                    )
                    plain_log("BINANCE_MILESTONE", {
                        "symbol": tv_symbol, "gate_name": gate_name,
                        "current_r": round(current_r, 2),
                        "qty": close_qty, "remaining": remaining,
                        "partial_pnl": partial_pnl,
                    })
                else:
                    plain_log("BINANCE_MILESTONE_PARTIAL_SUCCESS_WITH_WARNING", {
                        "symbol": tv_symbol,
                        "gate_name": gate_name,
                        "qty": close_qty,
                        "remaining": remaining,
                        "warning": "Milestone close succeeded but protection refresh failed. Old protection kept where available."
                    })
                # A second milestone must use a fresh exchange quantity snapshot.
                break


def _estimate_stop_locked_pnl(position: dict, state: dict, new_sl: float) -> float:
    """Estimate gross PnL if the new protective stop is filled."""
    entry = float(state.get("entry_price") or position.get("openPrice") or 0)
    qty = abs(float(position.get("volume") or 0))
    side = position.get("type", state.get("direction", "BUY"))
    if entry <= 0 or qty <= 0 or new_sl <= 0:
        return 0.0

    locked_pnl = trade_db.calculate_directional_pnl(side, entry, float(new_sl), qty)
    trade_id = state.get("trade_id")
    if trade_id:
        try:
            locked_pnl += trade_db.get_realized_exit_pnl(int(trade_id))
        except Exception as e:
            plain_log("STOP_LOCKED_PNL_PARTIAL_FETCH_ERROR", {
                "symbol": position.get("tv_symbol", position.get("symbol")),
                "trade_id": trade_id,
                "error": str(e),
            })
    return locked_pnl


def _record_latest_peak(state: dict, pnl: float) -> float:
    peak = max(float(state.get("peak_pnl", 0) or 0), float(pnl or 0))
    state["peak_pnl"] = peak
    return peak


def _check_simple_trailing_stop(position: dict):
    """Symbol-agnostic trailing stop activated after breakeven at TRAIL_ACTIVATION x R."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    if state.get("_orphan_exchange_position"):
        plain_log("ORPHAN_MANAGEMENT_SUSPENDED", {
            "symbol": tv_symbol,
            "action": "simple_trailing_suspended",
        })
        return
    if _open_trade_direction_mismatch(position, state):
        return

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    pnl = float(position.get("profit", 0))
    qty = float(position.get("volume", 0))

    if MONITOR_TRAIL_DEBUG_LOGS:
        plain_log("TRAIL_DEBUG", {
            "symbol": symbol, "entry": entry, "current": current,
            "side": side, "pnl": pnl, "qty": qty,
            "breakeven_moved": state.get("breakeven_moved"),
            "trailing_active": state.get("trailing_active"),
            "original_sl_distance": cc_state.get("original_sl_distance"),
        })

    if entry <= 0 or qty <= 0:
        return

    # Original SL distance in price terms
    sl_dist = cc_state.get("original_sl_distance")
    if not sl_dist:
        sl = position.get("stopLoss", 0)
        if sl:
            sl_dist = abs(entry - float(sl))
        else:
            sl_dist = abs(entry - current) * 0.4

    if MONITOR_TRAIL_DEBUG_LOGS:
        plain_log("TRAIL_DEBUG", {
            "symbol": symbol, "sl_dist": sl_dist, "entry": entry,
            "current": current, "sl": position.get("stopLoss"),
            "original_sl_distance": cc_state.get("original_sl_distance"),
            "original_sl": cc_state.get("original_sl"),
        })

    # If SL was moved to breakeven (entry == SL), estimate from current price
    if sl_dist <= 0:
        sl_dist = abs(entry - current) * 0.4

    # Dollar risk = SL distance × position size
    risk_dollars = sl_dist * qty

    # Activation: profit must reach trail_activation_r × R
    from dynamic_config import get_param
    trail_activation_r = get_param("trail_activation_r", TRAIL_ACTIVATION)
    if not state["trailing_active"]:
        if pnl >= risk_dollars * trail_activation_r:
            state["trailing_active"] = True
            plain_log("BINANCE_TRAIL_ACTIVATED", {
                "symbol": tv_symbol, "side": side, "pnl": pnl,
                "risk_dollars": risk_dollars, "activation_r": trail_activation_r,
            })
            _send_telegram(
                f"🎯 <b>TRAIL ACTIVE</b>\n"
                f"{tv_symbol} {side}\n"
                f"PnL: ${pnl:+.2f}"
            )
        else:
            return

    # Trail distance in price terms (0.5R = 0.5 × sl_dist)
    # Tighten to 0.25R after the last configured milestone on the remaining runner
    from dynamic_config import get_param
    trail_distance = get_param("trail_distance_r", TRAIL_DISTANCE)
    milestones = state.get("milestone_config")
    if milestones is None:
        milestones = trade_db.get_milestone_config(symbol)
        state["milestone_config"] = milestones
    if milestones:
        last_gate = milestones[-1]["gate_name"]
        if last_gate in state.get("milestones_hit", []):
            trail_distance = 0.25
    trail_price_dist = sl_dist * trail_distance

    if side == "SELL":
        new_sl = current + trail_price_dist
    else:
        new_sl = current - trail_price_dist

    new_sl = round(new_sl, 2)

    # Only move SL if it tightens the stop
    old_sl = state.get("current_sl") or float(position.get("stopLoss") or 0)
    if old_sl:
        if side == "BUY" and new_sl <= old_sl:
            return
        if side == "SELL" and new_sl >= old_sl:
            return

    # Execute
    if not _update_sl_order(symbol, tv_symbol, side, new_sl, position):
        return
    state["current_sl"] = new_sl

    plain_log("BINANCE_SIMPLE_TRAIL_UPDATED", {
        "symbol": tv_symbol, "old_sl": old_sl, "new_sl": new_sl,
        "trail_r": trail_distance, "current_r": round(pnl / risk_dollars, 2) if risk_dollars > 0 else 0,
    })
    # Telegram trail update
    try:
        peak = _record_latest_peak(state, pnl)
        stop_locked_pnl = _estimate_stop_locked_pnl(position, state, new_sl)
        telegram_client.notify_trail_update(tv_symbol, side, new_sl, pnl, stop_locked_pnl, peak)
    except Exception:
        pass


def _check_trailing_stop(position: dict):
    """Execute trailing stop logic if activated via command_center."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    cc_state = _get_position_state(tv_symbol)

    trail_mode = cc_state.get("trail_mode", "off")
    if trail_mode == "off":
        return

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    pnl = float(position.get("profit", 0))
    param = float(cc_state.get("trail_param", 1.5))
    trigger_r = float(cc_state.get("trail_trigger_r", 1.0))

    if entry <= 0:
        return

    # Calculate current R multiple
    sl_dist = cc_state.get("original_sl_distance")
    if not sl_dist:
        # Fallback: estimate from position data
        sl = position.get("stopLoss", 0)
        if sl:
            sl_dist = abs(entry - float(sl))
        else:
            sl_dist = abs(entry - current) * 0.4  # rough guess

    current_r = abs(pnl / (entry * position.get("volume", 1))) / (sl_dist / entry) if sl_dist > 0 else 0

    if current_r < trigger_r:
        return  # Not enough profit to start trailing yet

    # Compute new trailing SL
    if trail_mode == "atr":
        # For simplicity: param * ATR ≈ param * (SL_distance / typical_sl_mult)
        # We use SL distance as a proxy for ATR
        trail_dist = sl_dist * (param / 1.5)  # normalize to typical 1.5x ATR SL
    elif trail_mode == "percent":
        trail_dist = entry * (param / 100)
    elif trail_mode == "fixed":
        trail_dist = param
    else:
        return

    if side == "BUY":
        new_sl = current - trail_dist
    else:
        new_sl = current + trail_dist

    new_sl = round(new_sl, 2)

    # Only move SL if it improves (tightens) the stop
    old_sl = float(position.get("stopLoss", 0))
    if old_sl:
        if side == "BUY" and new_sl <= old_sl:
            return
        if side == "SELL" and new_sl >= old_sl:
            return

    # Execute the trailing update
    if not _update_sl_order(symbol, tv_symbol, side, new_sl, position):
        return

    plain_log("BINANCE_TRAIL_UPDATED", {
        "symbol": tv_symbol, "old_sl": old_sl, "new_sl": new_sl,
        "mode": trail_mode, "param": param, "current_r": round(current_r, 2),
    })
    # Telegram trail update
    try:
        pnl = float(position.get("profit", 0))
        state = _get_state(symbol)
        peak = _record_latest_peak(state, pnl)
        stop_locked_pnl = _estimate_stop_locked_pnl(position, state, new_sl)
        telegram_client.notify_trail_update(tv_symbol, side, new_sl, pnl, stop_locked_pnl, peak)
    except Exception:
        pass


def _update_sl_order(binance_sym: str, tv_symbol: str, side: str, new_sl: float, position: dict):
    """Place a new SL before cancelling old SL orders."""
    if PAPER_MODE:
        plain_log("PAPER_TRAIL_UPDATE", {"symbol": tv_symbol, "new_sl": new_sl})
        return

    try:
        client = _get_client()
        amt = float(position.get("volume", 0))
        qty = abs(amt)
        qty = _format_quantity(binance_sym, qty)
        sl_side = "SELL" if side == "BUY" else "BUY"

        # Capture existing STOP orders before placing the replacement.
        open_orders = client.futures_get_open_orders(symbol=binance_sym)
        old_sl_orders = [o for o in open_orders if o.get("type") in ("STOP_MARKET", "STOP")]

        # ALSO capture existing ALGO stop orders before placing the replacement.
        try:
            open_algo = client.futures_get_open_algo_orders(symbol=binance_sym)
            old_algo_orders = [o for o in open_algo if o.get("orderType") in ("STOP_MARKET", "STOP")]
        except Exception as e:
            plain_log("BINANCE_ALGO_FETCH_ERROR", {"symbol": tv_symbol, "error": str(e)})
            old_algo_orders = []

        position_side = "LONG" if side == "BUY" else "SHORT"

        # Check for existing closePosition stop order in the same direction to avoid -4130 error
        has_existing_close_pos = False
        for o in old_sl_orders:
            o_side = o.get("side")
            o_ps = o.get("positionSide")
            o_cp = str(o.get("closePosition")).lower() == "true"
            if o_side == sl_side and o_ps == position_side and o_cp:
                has_existing_close_pos = True
                break

        if not has_existing_close_pos:
            for o in old_algo_orders:
                o_side = o.get("side") or o.get("side")  # API uses side
                o_ps = o.get("positionSide") or o.get("positionSide")
                o_cp = str(o.get("closePosition")).lower() == "true"
                if o_side == sl_side and o_ps == position_side and o_cp:
                    has_existing_close_pos = True
                    break

        if has_existing_close_pos:
            plain_log("TRAIL_ACTIVE_STATIC_SL", {
                "symbol": tv_symbol,
                "new_sl": new_sl,
                "reason": "Matching STOP_MARKET closePosition=true already exists (static SL doctrine)"
            })
            plain_log("TRAIL_SKIPPED_STATIC_HARD_SL", {
                "symbol": tv_symbol,
                "new_sl": new_sl,
                "reason": "Trailing is state/reporting only because hard SL already exists"
            })
            return False

        result = _place_sl_tp_order(
            client=client, symbol=binance_sym, side=sl_side,
            order_type="STOP_MARKET", stop_price=new_sl,
            position_side=position_side, close_position=True,
        )
        if not result["success"]:
            plain_log("BINANCE_TRAIL_REPLACE_FAILED_OLD_SL_KEPT", {
                "symbol": tv_symbol, "new_sl": new_sl, "error": result.get("error")
            })
            state = _get_state(binance_sym)
            now = time.time()
            last_warn = state.get("last_trail_warn_at", 0)
            if now - last_warn >= 900:  # 15 minutes = 900 seconds
                state["last_trail_warn_at"] = now
                _send_telegram(
                    f"⚠️ <b>TRAILING STOP FAILED</b>\n"
                    f"{tv_symbol} old SL kept live\n"
                    f"New SL rejected: {result.get('error')}"
                )
            return False

        for o in old_sl_orders:
            try:
                client.futures_cancel_order(symbol=binance_sym, orderId=o["orderId"])
            except Exception as e:
                plain_log("BINANCE_CANCEL_OLD_SL_ERROR", {
                    "symbol": tv_symbol, "orderId": o.get("orderId"), "error": str(e)
                })

        # Also cancel old ALGO stop orders
        for o in old_algo_orders:
            try:
                client.futures_cancel_algo_order(symbol=binance_sym, algoId=o["algoId"])
            except Exception as e:
                plain_log("BINANCE_CANCEL_OLD_ALGO_ERROR", {
                    "symbol": tv_symbol, "algoId": o.get("algoId"), "error": str(e)
                })
        try:
            trade_db.upsert_binance_order_state(
                symbol=binance_sym,
                tv_symbol=tv_symbol,
                current_sl=new_sl,
                sl_order_id=str(result.get("orderId")) if result.get("orderId") else None,
            )
        except Exception:
            pass
        _send_telegram(
            f"🏃 <b>TRAILING STOP</b>\n"
            f"{tv_symbol} SL updated to {new_sl:,.2f}\n"
            f"Current: {float(position.get('currentPrice', 0)):,.2f}"
        )
        return True
    except Exception as e:
        plain_log("BINANCE_TRAIL_ERROR", {"symbol": tv_symbol, "error": str(e)})
        return False


def _check_tiered_exits(position: dict):
    """Close portions of position at predetermined R multiples."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)

    entry = float(position.get("openPrice", 0))
    current = float(position.get("currentPrice", 0))
    side = position.get("type", "BUY")
    pnl = float(position.get("profit", 0))
    qty = float(position.get("volume", 0))
    if entry <= 0 or qty <= 0:
        return

    sl_dist = cc_state.get("original_sl_distance")
    if not sl_dist:
        sl = position.get("stopLoss", 0)
        if sl:
            sl_dist = abs(entry - float(sl))
        else:
            return

    current_r = abs(current - entry) / sl_dist if sl_dist > 0 else 0
    done = state.get("tiered_exits", [])

    tiers = [
        (1.5, 0.50, "50%"),
        (2.5, 0.25, "25%"),
        (3.5, 0.25, "25%"),
    ]

    for target_r, close_frac, label in tiers:
        key = f"tier_{target_r}"
        if key in done:
            continue
        if current_r >= target_r:
            close_qty = qty * close_frac
            close_qty = _format_quantity(symbol, close_qty)

            if PAPER_MODE:
                plain_log("PAPER_TIERED_EXIT", {
                    "symbol": tv_symbol, "tier": target_r, "qty": close_qty,
                })
            else:
                res = _close_position_once(symbol, close_qty, reason=f"tiered_{target_r}r")
                if res.get("status") not in {"ok", "closed", "partial_closed"}:
                    plain_log("BINANCE_TIERED_EXIT_ERROR", {
                        "symbol": tv_symbol, "tier": target_r, "error": res.get("error"),
                    })
                    continue

            done.append(key)
            state["tiered_exits"] = done
            _send_telegram(
                f"💰 <b>TIERED EXIT</b>\n"
                f"{tv_symbol} — Closed {label} at {target_r}R\n"
                f"Entry: {entry:,.2f} | Current: {current:,.2f}"
            )
            plain_log("BINANCE_TIERED_EXIT", {
                "symbol": tv_symbol, "tier": target_r, "qty": close_qty,
            })
            try:
                tid = state.get("trade_id")
                if tid:
                    trade_db.log_exit(
                        trade_id=tid,
                        exit_type="partial",
                        price=current,
                        qty_pct=close_frac,
                        notes=f"Tiered exit {label} at {target_r}R",
                    )
            except Exception:
                pass
            break


def _check_choch_reversal(position: dict):
    """If a ChoCh reversal alert was recently logged against this open position,
    remind the user and optionally close the position (if CHOCH_AUTO_CLOSE enabled).
    """
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)

    if state.get("choch_alerted"):
        return

    try:
        alerts = trade_db.get_recent_choch_alert(symbol, minutes=30)
        if alerts:
            state["choch_alerted"] = True
            _send_telegram(
                f"⚠️ <b>ChoCh REVERSAL ACTIVE</b>\n"
                f"{tv_symbol} — structure changed against open position.\n"
                f"Consider closing manually."
            )
            plain_log("BINANCE_CHOCH_REMINDER", {
                "symbol": tv_symbol,
                "gate_id": alerts[0]["id"],
            })

            if CHOCH_AUTO_CLOSE and not PAPER_MODE:
                close_qty = float(position.get("volume", 0) or 0)
                close_qty = _format_quantity(symbol, close_qty)
                pos_side = position.get("type", "BUY")
                if close_qty > 0:
                    res = _close_position_once(symbol, close_qty, reason="choch_reversal")
                    if res.get("status") not in {"ok", "closed", "partial_closed"}:
                        plain_log("BINANCE_CHOCH_CLOSE_ERROR", {
                            "symbol": tv_symbol, "error": res.get("error"),
                        })
                    else:
                        plain_log("BINANCE_CHOCH_CLOSE", {
                            "symbol": tv_symbol,
                            "side": "SELL" if pos_side == "BUY" else "BUY",
                            "qty": close_qty,
                        })
    except Exception:
        pass


def _check_trade_duration(position: dict):
    """Warn if position open longer than MAX_TRADE_HOURS."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)

    if state["long_warned"]:
        return

    update_time = position.get("updateTime")
    if update_time:
        open_time = datetime.fromtimestamp(update_time / 1000, tz=UTC)
        age_hours = (datetime.now(UTC) - open_time).total_seconds() / 3600

        if age_hours >= MAX_TRADE_HOURS:
            state["long_warned"] = True
            msg = (
                f"⏰ <b>TRADE AGE WARNING</b>\n"
                f"{tv_symbol} {position['type']} open for {age_hours:.1f}h\n"
                f"(max: {MAX_TRADE_HOURS}h)\n"
                f"Entry: ${position['openPrice']:,.2f}\n"
                f"Current: ${position['currentPrice']:,.2f}\n"
                f"PnL: ${position['profit']:+.2f}"
            )
            plain_log("BINANCE_TRADE_AGE_WARNING", {
                "symbol": tv_symbol, "age_hours": age_hours, "pnl": position["profit"]
            })
            _send_telegram(msg)


def _trade_open_age_hours(trade_id: int, symbol: str) -> float | None:
    """Return trade age from the DB open timestamp; skip if unavailable."""
    try:
        trade_row = trade_db.get_trade_by_id(trade_id)
    except Exception as e:
        plain_log("TRADE_AGE_LOOKUP_ERROR", {"symbol": symbol, "trade_id": trade_id, "error": str(e)})
        return None

    if not trade_row or not trade_row["ts"]:
        plain_log("TRADE_AGE_MISSING_TS", {"symbol": symbol, "trade_id": trade_id})
        return None

    try:
        raw_ts = str(trade_row["ts"]).replace("Z", "+00:00")
        opened_at = datetime.fromisoformat(raw_ts)
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - opened_at.astimezone(UTC)).total_seconds() / 3600
    except ValueError as e:
        plain_log("TRADE_AGE_PARSE_ERROR", {"symbol": symbol, "trade_id": trade_id, "ts": trade_row["ts"], "error": str(e)})
        return None


def _current_r_multiple(position: dict, state: dict) -> float | None:
    """Return current R where positive means the trade is winning for both BUY and SELL."""
    entry = float(state.get("entry_price", 0) or 0)
    sl_dist = float(state.get("original_sl_distance", 0) or 0)
    current_price = float(position.get("currentPrice", 0) or 0)
    direction = position.get("type", "BUY")

    if entry <= 0:
        entry = float(position.get("openPrice", 0) or 0)
        if entry > 0:
            state["entry_price"] = entry

    if entry <= 0 or sl_dist <= 0:
        try:
            order_state = trade_db.get_binance_order_state(position["symbol"])
            if order_state:
                if entry <= 0 and order_state["entry_price"]:
                    entry = float(order_state["entry_price"])
                    state["entry_price"] = entry
                if sl_dist <= 0 and order_state["original_sl_distance"]:
                    sl_dist = float(order_state["original_sl_distance"])
                    state["original_sl_distance"] = sl_dist
        except Exception as e:
            plain_log("R_MULTIPLE_ORDER_STATE_ERROR", {"symbol": position.get("symbol"), "error": str(e)})

    if sl_dist <= 0 and state.get("trade_id"):
        try:
            trade_row = trade_db.get_trade_by_id(state["trade_id"])
            if trade_row:
                if entry <= 0 and trade_row["entry_price"]:
                    entry = float(trade_row["entry_price"])
                    state["entry_price"] = entry
                if trade_row["risk_dollars"] and trade_row["qty"]:
                    sl_dist = float(trade_row["risk_dollars"]) / float(trade_row["qty"])
                    state["original_sl_distance"] = sl_dist
                elif trade_row["sl"] and entry > 0:
                    sl_dist = abs(entry - float(trade_row["sl"]))
                    state["original_sl_distance"] = sl_dist
        except Exception as e:
            plain_log("R_MULTIPLE_TRADE_STATE_ERROR", {"symbol": position.get("symbol"), "error": str(e)})

    if entry <= 0 or sl_dist <= 0 or current_price <= 0:
        return None
    if direction == "BUY":
        return (current_price - entry) / sl_dist
    return (entry - current_price) / sl_dist


def _protective_close(symbol: str, quantity: float, reason: str) -> dict:
    """Close a reduce-only quantity and return the broker result."""
    result = _close_position_once(symbol, quantity, reason=reason)
    if result.get("status") not in {"closed", "partial_closed"}:
        plain_log("PROTECTIVE_CLOSE_FAILED", {
            "symbol": symbol,
            "quantity": quantity,
            "reason": reason,
            "result": result,
        })
    return result


def _close_position_once(symbol: str, quantity: float, reason: str, **kwargs) -> dict:
    """Allow at most one successful quantity mutation per exchange snapshot."""
    state = _get_state(symbol)
    if state.get("_exit_action_claimed"):
        return {
            "status": "skipped",
            "reason": "exit_action_already_taken_for_snapshot",
            "claimed_by": state.get("_exit_action_reason"),
        }
    result = close_position_qty(symbol, quantity, reason=reason, **kwargs)
    if result.get("status") in {"ok", "closed", "partial_closed"}:
        state["_exit_action_claimed"] = True
        state["_exit_action_reason"] = reason
    return result


def _remaining_original_fraction(state: dict, remaining_qty: float) -> float:
    """Return a terminal slice as a fraction of immutable original quantity."""
    original_qty = abs(float(state.get("original_qty") or 0.0))
    qty = abs(float(remaining_qty or 0.0))
    if original_qty <= 0:
        return 1.0
    return min(1.0, qty / original_qty)


def _check_time_based_exit(position: dict):
    """Reduce or close positions that have been open too long with no progress."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    # Check if 1R was ever hit
    hit_1r = trade_db.milestone_exists(tid, "1R_breakeven")
    if hit_1r:
        return  # Trade proved itself, let it run

    age_hours = _trade_open_age_hours(tid, symbol)
    if age_hours is None:
        return

    qty = abs(float(position.get("volume", 0) or 0))
    if qty <= 0:
        return

    from dynamic_config import get_param
    time_exit_hours = get_param("time_exit_hours", TIME_EXIT_HOURS)
    time_reduce_hours = get_param("time_reduce_hours", TIME_REDUCE_HOURS)

    # close remaining if no 1R. Check before reduce so stale trades do not double-close in one poll.
    if age_hours >= time_exit_hours and not state.get("time_exited"):
        plain_log("TIME_BASED_EXIT", {
            "symbol": tv_symbol, "age_hours": age_hours,
            "reason": f"no_1R_in_{time_exit_hours}h"
        })
        result = _protective_close(tv_symbol, qty, "time_exit")
        if result.get("status") in {"closed", "partial_closed"}:
            state["time_exited"] = True
            trade_db.log_exit(
                tid,
                "time_exit",
                float(position.get("currentPrice", 0)),
                None,
                qty_pct=_remaining_original_fraction(state, qty),
                notes=f"No 1R in {time_exit_hours}h — close remaining",
            )
            _send_telegram(f"🚪 <b>TIME EXIT</b>\n{tv_symbol} open {age_hours:.1f}h with no 1R\nClosing remaining position")
        return

    # reduce 50% if no 1R
    if age_hours >= time_reduce_hours and not state.get("time_reduced"):
        reduce_qty = qty * 0.5
        if reduce_qty > 0:
            plain_log("TIME_BASED_REDUCE", {
                "symbol": tv_symbol, "age_hours": age_hours,
                "reduce_qty": reduce_qty, "reason": f"no_1R_in_{time_reduce_hours}h"
            })
            result = _protective_close(tv_symbol, reduce_qty, "time_reduce")
            if result.get("status") in {"closed", "partial_closed"}:
                state["time_reduced"] = True
                trade_db.log_exit(tid, "time_reduce", float(position.get("currentPrice", 0)), 0, qty_pct=0.5, notes=f"No 1R in {time_reduce_hours}h — reduce 50%")
                _send_telegram(f"⏰ <b>TIME REDUCE</b>\n{tv_symbol} open {age_hours:.1f}h with no 1R\nClosed 50% to reduce risk")


def _check_momentum_reversal(position: dict):
    """Close early if price gives back a material R-multiple from peak within the lookback window.

    Unlike the old rate-of-change rule, this uses continuous peak-R tracking so it does
    not stop out a trade that barely ticked green (e.g. HYPE 2026-06-15).  It only fires
    after the trade has achieved at least 0.5R and then gives back momentum_exit_r from
    that peak, or if the position is already in free-fall (current_r < -0.5R and dropping).
    """
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    direction = position.get("type", "BUY")
    current_r = _current_r_multiple(position, state)
    if current_r is None:
        return

    # Sparse 30-min R history is still useful for measuring recent velocity.
    now = time.time()
    r_history = state.get("_r_history", [])
    historical_peak_r = max((float(r) for _ts, r in r_history), default=0.0)

    # Update continuous peak R on every monitor tick (30s).  Include recent
    # sparse history so a monitor restart or state rebuild does not forget a
    # meaningful prior peak and leave a green-to-red trade unmanaged.
    peak_r = max(float(state.get("_peak_r", 0) or 0), historical_peak_r, current_r)
    state["_peak_r"] = peak_r

    if not r_history or (now - r_history[-1][0]) > 1800:
        r_history.append((now, current_r))
        r_history = r_history[-6:]
        state["_r_history"] = r_history

    from dynamic_config import get_param
    momentum_lookback_seconds = get_param("momentum_lookback_seconds", MOMENTUM_LOOKBACK_SECONDS)
    momentum_exit_r = get_param("momentum_exit_r", MOMENTUM_EXIT_R)

    # Recent velocity: largest R drop within lookback window.
    recent_velocity = 0.0
    if r_history:
        cutoff = now - momentum_lookback_seconds
        recent_r_values = [r for ts, r in r_history if ts >= cutoff]
        if recent_r_values:
            recent_velocity = current_r - max(recent_r_values)

    # Rule 1: catastrophic free-fall (already deep underwater and still dropping fast).
    catastrophic = current_r <= -0.5 and recent_velocity <= -momentum_exit_r

    # Rule 2: meaningful peak achieved and then gave back momentum_exit_r from that peak.
    # Require at least 0.5R peak so we don't stop out noise on trades that never went green.
    meaningful_peak = peak_r >= 0.5
    gave_back_from_peak = (peak_r - current_r) >= momentum_exit_r

    moved_against = catastrophic or (meaningful_peak and gave_back_from_peak)

    if moved_against and not state.get("momentum_exited"):
        qty = abs(float(position.get("volume", 0) or 0))
        plain_log("MOMENTUM_EXIT", {
            "symbol": tv_symbol, "peak_r": peak_r, "current_r": current_r,
            "recent_velocity": recent_velocity, "threshold": momentum_exit_r,
            "catastrophic": catastrophic, "gave_back_from_peak": gave_back_from_peak,
        })
        result = _protective_close(tv_symbol, qty, "momentum_exit")
        if result.get("status") in {"closed", "partial_closed"}:
            state["momentum_exited"] = True
            trade_db.log_exit(
                tid,
                "momentum_exit",
                float(position.get("currentPrice", 0)),
                None,
                qty_pct=_remaining_original_fraction(state, qty),
                notes=f"Peak {round(peak_r, 2)}R -> current {round(current_r, 2)}R (drop {round(peak_r - current_r, 2)}R)",
            )
            _send_telegram(
                f"⚡ <b>MOMENTUM EXIT</b>\n"
                f"{tv_symbol} {direction}\n"
                f"Peak {peak_r:.2f}R -> current {current_r:.2f}R\n"
                f"Closing to protect capital"
            )


def _check_early_giveback_guard(position: dict):
    """Close a small winner that gives back too much before the 1R profit-protect floor.

    This implements the configured early-profit protection guard for the gap between
    "trade went meaningfully green" and "trade hit full 1R protection."  Milestone
    partials still handle scale-outs; this guard prevents the remaining runner from
    round-tripping when peak R was real but not large enough for `_check_profit_protection`.
    """
    policy = EARLY_PROFIT_PROTECTION or {}
    if not policy.get("enabled", False):
        return

    guard = policy.get("giveback_guard") or {}
    min_peak_r = float(guard.get("min_peak_r", 0.30) or 0.30)
    giveback_pct = float(guard.get("giveback_pct", 50.0) or 50.0)
    reason = str(guard.get("reason", "early_giveback") or "early_giveback")

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid or state.get("early_giveback_exited"):
        return

    current_r = _current_r_multiple(position, state)
    if current_r is None:
        return

    r_history = state.get("_r_history", [])
    historical_peak_r = max((float(r) for _ts, r in r_history), default=0.0)
    peak_r = max(float(state.get("_peak_r", 0) or 0), historical_peak_r, current_r)
    try:
        trade = trade_db.get_trade_by_id(tid)
        risk_dollars = float(_row_get(trade, "risk_dollars", 0) or 0)
        peak_pnl = float(_row_get(trade, "peak_pnl", 0) or 0)
        if risk_dollars > 0 and peak_pnl > 0:
            peak_r = max(peak_r, peak_pnl / risk_dollars)
    except Exception as e:
        plain_log("EARLY_GIVEBACK_PEAK_READ_ERROR", {"symbol": tv_symbol, "trade_id": tid, "error": str(e)})
    state["_peak_r"] = peak_r

    if peak_r < min_peak_r:
        return

    floor_r = peak_r * max(0.0, 1.0 - (giveback_pct / 100.0))
    if current_r > floor_r:
        return

    qty = abs(float(position.get("volume", 0) or 0))
    if qty <= 0:
        return

    direction = position.get("type", "BUY")
    plain_log("EARLY_GIVEBACK_EXIT", {
        "symbol": tv_symbol,
        "peak_r": peak_r,
        "current_r": current_r,
        "floor_r": floor_r,
        "giveback_pct": giveback_pct,
    })
    result = _protective_close(tv_symbol, qty, reason)
    if result.get("status") in {"closed", "partial_closed"}:
        state["early_giveback_exited"] = True
        trade_db.log_exit(
            tid,
            reason,
            float(position.get("currentPrice", 0)),
            None,
            qty_pct=_remaining_original_fraction(state, qty),
            notes=f"Peak {round(peak_r, 2)}R gave back {giveback_pct:.1f}% to {round(current_r, 2)}R",
        )
        _send_telegram(
            f"🪙 <b>EARLY GIVEBACK EXIT</b>\n"
            f"{tv_symbol} {direction}\n"
            f"Peak {peak_r:.2f}R -> current {current_r:.2f}R\n"
            f"Closed to prevent green-to-red round trip"
        )


def _check_profit_protection(position: dict):
    """Close if trade hit 1R but reversed back to +0.3R (protect the win)."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    direction = position.get("type", "BUY")
    current_r = _current_r_multiple(position, state)
    if current_r is None:
        return

    # Track peak R achieved
    peak_r = float(state.get("_peak_r", 0) or 0)
    if current_r > peak_r:
        peak_r = current_r
        state["_peak_r"] = peak_r

    # Stop placement is not proof of price movement. Early-profit policy can
    # move the stop to breakeven below 1R, so only price-derived peak R or an
    # actual 1R milestone may activate this floor.
    hit_1r = trade_db.milestone_exists(tid, "1R_breakeven") or peak_r >= 1.0
    if not hit_1r:
        return
    if peak_r < 1.0:
        peak_r = 1.0
        state["_peak_r"] = peak_r

    from dynamic_config import get_param
    profit_protect_r = get_param("profit_protect_r", PROFIT_PROTECT_R)

    # Tiered profit protection: lock in more gains as the trade runs.
    # 1R -> protect 0.3R | 2R -> protect 0.8R | 3R+ -> protect 1.5R
    if peak_r >= 3.0:
        floor_r = max(profit_protect_r, 1.5)
    elif peak_r >= 2.0:
        floor_r = max(profit_protect_r, 0.8)
    elif peak_r >= 1.0:
        floor_r = profit_protect_r
    else:
        return

    if current_r <= floor_r and not state.get("profit_protected"):
        qty = abs(float(position.get("volume", 0) or 0))
        plain_log("PROFIT_PROTECT_EXIT", {
            "symbol": tv_symbol, "peak_r": peak_r, "current_r": current_r,
            "threshold": floor_r
        })
        result = _protective_close(tv_symbol, qty, "profit_protect")
        if result.get("status") in {"closed", "partial_closed"}:
            state["profit_protected"] = True
            trade_db.log_exit(
                tid,
                "profit_protect",
                float(position.get("currentPrice", 0)),
                None,
                qty_pct=_remaining_original_fraction(state, qty),
                notes=f"Hit {round(peak_r, 2)}R then pulled back to {round(current_r, 2)}R (floor {round(floor_r, 2)}R)",
            )
            _send_telegram(
                f"🛡️ <b>PROFIT PROTECT</b>\n"
                f"{tv_symbol} {direction}\n"
                f"Hit {peak_r:.2f}R but reversed to {current_r:.2f}R\n"
                f"Closing to protect gains"
            )


def _monitor_instance_name() -> str:
    instance = os.environ.get("HERMES_INSTANCE_NAME", "")
    port = os.environ.get("HERMES_PORT", "")
    return "LIVE_MICRO" if instance.strip().upper().replace("_", " ") == "LIVE MICRO" or port == "5001" else "STANDARD_TESTNET"


def _roundtrip_guard_candidate_id(instance: str, symbol: str, trade_id: int) -> str:
    return f"{instance}_{symbol}_{int(trade_id)}_{ROUNDTRIP_GUARD_CANDIDATE_TYPE}"


def _roundtrip_guard_upsert_candidate(
    *,
    instance: str,
    position: dict,
    trade,
    peak_r: float,
    current_r: float,
    peak_pnl: float,
    current_pnl: float,
    giveback_pct: float,
) -> bool:
    """Create/update a loss-min candidate for LIVE_MICRO without spamming alerts."""
    trade_id = int(_row_get(trade, "id"))
    symbol = position["symbol"]
    now_iso = datetime.now().isoformat()
    candidate_id = _roundtrip_guard_candidate_id(instance, symbol, trade_id)
    age_hours = _trade_open_age_hours(trade_id, symbol) or 0.0
    candidate = {
        "candidate_id": candidate_id,
        "candidate_type": ROUNDTRIP_GUARD_CANDIDATE_TYPE,
        "instance": instance,
        "trade_id": trade_id,
        "symbol": symbol,
        "side": position.get("type"),
        "grade": str(_row_get(trade, "setup_grade", "") or "").upper().strip(),
        "timeframe": _row_get(trade, "timeframe"),
        "entry_price": _row_get(trade, "entry_price"),
        "current_price": position.get("currentPrice"),
        "current_pnl": current_pnl,
        "peak_pnl": peak_pnl,
        "current_r": round(current_r, 4),
        "peak_r": round(peak_r, 4),
        "giveback_ratio": round(giveback_pct / 100.0, 6),
        "giveback_pct": round(giveback_pct, 2),
        "age_minutes": round(age_hours * 60.0, 1),
        "recommendation": "EXIT_REVIEW",
        "reason": (
            "Roundtrip Guard R1 triggered: "
            f"peak_r={peak_r:.3f}, current_r={current_r:.3f}, giveback={giveback_pct:.1f}%. "
            "LIVE_MICRO review only — no auto-exit."
        ),
        "status": "OPEN",
        "created_at": now_iso,
        "last_seen_at": now_iso,
    }

    os.makedirs(ROUNDTRIP_GUARD_OBSERVER_DIR, exist_ok=True)
    path = os.path.join(ROUNDTRIP_GUARD_OBSERVER_DIR, "loss_minimization_candidates.json")
    existing = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            existing = []
    by_id = {c.get("candidate_id"): c for c in existing if c.get("candidate_id")}
    is_new = candidate_id not in by_id or by_id[candidate_id].get("status") not in {"OPEN", "WATCHED"}
    if candidate_id in by_id:
        created_at = by_id[candidate_id].get("created_at") or candidate["created_at"]
        by_id[candidate_id].update(candidate)
        by_id[candidate_id]["created_at"] = created_at
        if by_id[candidate_id].get("status") == "CONDITION_CLEARED":
            by_id[candidate_id]["status"] = "OPEN"
            is_new = True
    else:
        by_id[candidate_id] = candidate

    with open(path, "w") as f:
        json.dump(list(by_id.values()), f, indent=2)

    if is_new:
        try:
            telegram_client.notify_loss_minimization_candidate(by_id[candidate_id])
        except Exception as e:
            plain_log("ROUNDTRIP_GUARD_R1_NOTIFY_ERROR", {"symbol": symbol, "trade_id": trade_id, "error": str(e)})
    return is_new


def _roundtrip_guard_safe_context(position: dict, state: dict) -> tuple[bool, dict]:
    """Validate that monitor state, DB state, exchange qty and SL visibility agree."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    trade_id = state.get("trade_id")
    detail = {"symbol": tv_symbol, "trade_id": trade_id}
    if not trade_id:
        detail["reason"] = "missing_trade_id"
        return False, detail

    try:
        trade = trade_db.get_trade_by_id(trade_id)
    except Exception as e:
        detail.update({"reason": "trade_lookup_failed", "error": str(e)})
        return False, detail

    if not trade or _row_get(trade, "exit_price") is not None or _row_get(trade, "execution_state") == "closed":
        detail["reason"] = "trade_not_open"
        return False, detail

    if _open_trade_direction_mismatch(position, state):
        detail["reason"] = "side_mismatch"
        return False, detail

    side = position.get("type", "BUY")
    if _row_get(trade, "direction") and _row_get(trade, "direction") != side:
        detail.update({"reason": "trade_side_mismatch", "trade_side": _row_get(trade, "direction"), "exchange_side": side})
        return False, detail

    exchange_qty = abs(float(position.get("volume", 0) or 0))
    if exchange_qty <= 0:
        detail["reason"] = "missing_exchange_position"
        return False, detail

    original_qty = float(_row_get(trade, "qty", 0) or 0)
    if original_qty <= 0:
        detail["reason"] = "missing_db_quantity"
        return False, detail
    try:
        exits = trade_db.get_exits_for_trade(trade_id)
    except Exception:
        exits = []
    realized_qty_pct = sum(float(_row_get(e, "qty_pct", 0) or 0) for e in exits)
    expected_qty = max(0.0, original_qty * (1.0 - realized_qty_pct))
    qty_tolerance = max(0.001, original_qty * 0.001)
    if abs(exchange_qty - expected_qty) > qty_tolerance:
        detail.update({
            "reason": "qty_mismatch",
            "exchange_qty": exchange_qty,
            "expected_qty": expected_qty,
            "qty_tolerance": qty_tolerance,
        })
        return False, detail

    sl_price = float(_row_get(trade, "sl", 0) or state.get("sl_price") or 0)
    if sl_price <= 0:
        detail["reason"] = "missing_sl_anchor"
        return False, detail

    try:
        client = _get_client()
        normal_orders = client.futures_get_open_orders(symbol=symbol)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception:
            algo_orders = []
    except Exception as e:
        detail.update({"reason": "protection_state_unknown", "error": str(e)})
        return False, detail

    close_side = "SELL" if side == "BUY" else "BUY"
    position_side = "LONG" if side == "BUY" else "SHORT"
    protection_detail = inspect_exchange_protection(
        symbol,
        open_orders=normal_orders,
        algo_orders=algo_orders,
        expected_side=close_side,
        expected_position_side=position_side,
        expected_sl=sl_price,
    )
    detail["protection_detail"] = protection_detail
    if not protection_detail.get("has_sl"):
        detail["reason"] = "sl_not_exchange_visible"
        return False, detail

    detail.update({"trade": trade, "exchange_qty": exchange_qty, "side": side})
    return True, detail


def _check_roundtrip_guard_r1(position: dict):
    """R1 guard: close TESTNET, create review candidate only for LIVE_MICRO."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    if state.get("_roundtrip_guard_r1_done"):
        return

    current_r = _current_r_multiple(position, state)
    if current_r is None:
        return

    current_pnl = float(position.get("profit", 0) or 0.0)
    peak_pnl = max(float(state.get("peak_pnl", 0) or 0.0), current_pnl)
    state["peak_pnl"] = peak_pnl
    trade_id = state.get("trade_id")
    if trade_id and peak_pnl > 0:
        try:
            trade_db.update_trade_peak(trade_id, peak_pnl, float(position.get("currentPrice", 0) or 0.0))
        except Exception as e:
            plain_log("ROUNDTRIP_GUARD_R1_PEAK_UPDATE_ERROR", {"symbol": tv_symbol, "trade_id": trade_id, "error": str(e)})

    peak_r = max(float(state.get("_peak_r", 0) or 0.0), current_r)
    if trade_id:
        try:
            trade = trade_db.get_trade_by_id(trade_id)
            risk_dollars = float(_row_get(trade, "risk_dollars", 0) or 0)
            db_peak_pnl = float(_row_get(trade, "peak_pnl", 0) or 0)
            peak_pnl = max(peak_pnl, db_peak_pnl)
            if risk_dollars > 0 and peak_pnl > 0:
                peak_r = max(peak_r, peak_pnl / risk_dollars)
        except Exception as e:
            plain_log("ROUNDTRIP_GUARD_R1_PEAK_READ_ERROR", {"symbol": tv_symbol, "trade_id": trade_id, "error": str(e)})
    state["_peak_r"] = peak_r

    if peak_pnl <= 0:
        return
    giveback_pct = ((peak_pnl - current_pnl) / peak_pnl) * 100.0
    if not (
        peak_r >= ROUNDTRIP_GUARD_R1_PEAK_R
        and current_r <= ROUNDTRIP_GUARD_R1_CURRENT_R
        and giveback_pct >= ROUNDTRIP_GUARD_R1_GIVEBACK_PCT
    ):
        return

    safe, detail = _roundtrip_guard_safe_context(position, state)
    if not safe:
        plain_log("ROUNDTRIP_GUARD_R1_SKIPPED", {
            "symbol": tv_symbol,
            "trade_id": trade_id,
            "peak_r": round(peak_r, 4),
            "current_r": round(current_r, 4),
            "peak_pnl": round(peak_pnl, 4),
            "current_pnl": round(current_pnl, 4),
            "giveback_pct": round(giveback_pct, 2),
            **detail,
        })
        return

    instance = _monitor_instance_name()
    payload = {
        "instance": instance,
        "symbol": tv_symbol,
        "trade_id": trade_id,
        "side": detail["side"],
        "peak_r": round(peak_r, 4),
        "current_r": round(current_r, 4),
        "peak_pnl": round(peak_pnl, 4),
        "current_pnl": round(current_pnl, 4),
        "giveback_pct": round(giveback_pct, 2),
    }
    plain_log("ROUNDTRIP_GUARD_R1_TRIGGERED", payload)

    if instance == "LIVE_MICRO":
        is_new = _roundtrip_guard_upsert_candidate(
            instance=instance,
            position=position,
            trade=detail["trade"],
            peak_r=peak_r,
            current_r=current_r,
            peak_pnl=peak_pnl,
            current_pnl=current_pnl,
            giveback_pct=giveback_pct,
        )
        state["_roundtrip_guard_r1_candidate_sent"] = True
        if not is_new:
            plain_log("ROUNDTRIP_GUARD_R1_CANDIDATE_UPDATED", {"symbol": tv_symbol, "trade_id": trade_id})
        return

    result = _protective_close(tv_symbol, detail["exchange_qty"], "roundtrip_guard_r1")
    if result.get("status") in {"closed", "partial_closed"}:
        state["_roundtrip_guard_r1_done"] = True
        trade_db.log_exit(
            trade_id,
            "roundtrip_guard_r1",
            float(position.get("currentPrice", 0) or 0.0),
            current_pnl,
            qty_pct=_remaining_original_fraction(state, detail["exchange_qty"]),
            notes=(
                f"R1 roundtrip guard: peak_r={peak_r:.2f}, current_r={current_r:.2f}, "
                f"giveback={giveback_pct:.1f}%"
            ),
        )
        _send_telegram(
            f"🛑 <b>ROUNDTRIP GUARD R1</b>\n"
            f"{tv_symbol} {detail['side']}\n"
            f"Peak {peak_r:.2f}R reversed to {current_r:.2f}R\n"
            f"Giveback {giveback_pct:.1f}% — closed TESTNET position."
        )


def _cancel_stale_reduce_only_orders(symbol: str) -> bool:
    """Cancel and verify orphaned protective orders for a flat symbol.

    Refuse cleanup if a position appeared since the monitor snapshot. This
    prevents terminal cleanup from cancelling protection for a new trade.
    """
    if PAPER_MODE:
        return True
    try:
        if any(p.get("symbol") == symbol for p in (get_open_positions() or [])):
            plain_log("TERMINAL_ORDER_CLEANUP_SKIPPED", {
                "symbol": symbol,
                "reason": "exchange_position_exists",
            })
            return False

        client = _get_client()
        failed = False

        def is_protective(order: dict) -> bool:
            reduce_only = str(order.get("reduceOnly", "")).lower() == "true"
            close_position = str(order.get("closePosition", "")).lower() == "true"
            order_type = str(order.get("orderType") or order.get("type") or "").upper()
            return (reduce_only or close_position) and order_type in {
                "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"
            }

        try:
            for order in client.futures_get_open_orders(symbol=symbol) or []:
                if not is_protective(order):
                    continue
                client.futures_cancel_order(symbol=symbol, orderId=order["orderId"])
        except Exception as e:
            plain_log("CANCEL_ALL_OPEN_ORDERS_ERROR", {"symbol": symbol, "error": str(e)})
            failed = True

        try:
            for order in client.futures_get_open_algo_orders(symbol=symbol) or []:
                if not is_protective(order):
                    continue
                client.futures_cancel_algo_order(symbol=symbol, algoId=order["algoId"])
        except Exception as e:
            plain_log("CANCEL_ALGO_ORDERS_ERROR", {"symbol": symbol, "error": str(e)})
            failed = True

        try:
            remaining = [
                order for order in (
                    (client.futures_get_open_orders(symbol=symbol) or [])
                    + (client.futures_get_open_algo_orders(symbol=symbol) or [])
                )
                if is_protective(order)
            ]
        except Exception as e:
            plain_log("TERMINAL_ORDER_CLEANUP_VERIFY_ERROR", {"symbol": symbol, "error": str(e)})
            return False

        if remaining:
            plain_log("TERMINAL_ORDER_CLEANUP_INCOMPLETE", {
                "symbol": symbol,
                "remaining_order_ids": [o.get("algoId") or o.get("orderId") for o in remaining],
            })
            return False
        plain_log("TERMINAL_ORDER_CLEANUP_VERIFIED", {"symbol": symbol})
        return not failed
    except Exception as e:
        plain_log("CANCEL_STALE_ORDERS_FAIL", {"symbol": symbol, "error": str(e)})
        return False


def _check_sluggish_invalidation(position: dict):
    """Trigger early invalidation close on LIVE MICRO for sluggish/dead trades."""
    if os.environ.get("HERMES_INSTANCE_NAME") != "LIVE MICRO":
        return

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")

    # 1. Orphan / DB ghost check
    if not tid:
        return
    try:
        trade = trade_db.get_trade_by_id(tid)
    except Exception:
        return
    if not trade or trade.get("execution_state") == "closed":
        return

    # 2. Side mismatch check
    if _open_trade_direction_mismatch(position, state):
        return
    direction = position.get("type", "BUY")
    if trade["direction"] != direction:
        return

    # 3. Quantity mismatch check
    original_qty = float(trade["qty"] or 0.0)
    if original_qty <= 0:
        return
    try:
        existing_exits = trade_db.get_exits_for_trade(tid)
    except Exception:
        existing_exits = []
    sum_qty_pct = sum([float(e["qty_pct"]) for e in existing_exits])
    db_expected_remaining_qty = original_qty * (1.0 - sum_qty_pct)
    exch_qty = abs(float(position.get("volume", 0) or 0))

    if abs(exch_qty - db_expected_remaining_qty) > 0.001:
        # Qty mismatch exists, safety abort!
        return

    # 4. Age Check (>= 75 minutes)
    age_hours = _trade_open_age_hours(tid, symbol)
    if age_hours is None:
        return
    age_minutes = age_hours * 60.0
    if age_minutes < 75.0:
        return

    # 5. Peak R check (< 0.10R)
    peak_r = float(state.get("_peak_r", 0) or 0)
    if peak_r >= 0.10:
        return

    # 6. Current R check (<= -0.35R)
    current_r = _current_r_multiple(position, state)
    if current_r is None or current_r > -0.35:
        return

    # 7. SL Protection verified check
    sl_price = float(trade.get("sl") or 0.0)
    if sl_price <= 0:
        return

    try:
        client = _get_client()
        normal_orders = client.futures_get_open_orders(symbol=symbol)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=symbol)
        except Exception:
            algo_orders = []
    except Exception as e:
        plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_FETCH_ORDERS_ERROR", {"symbol": tv_symbol, "error": str(e)})
        return

    position_side = "LONG" if direction == "BUY" else "SHORT"
    close_side = "SELL" if direction == "BUY" else "BUY"
    protection_detail = inspect_exchange_protection(
        symbol,
        open_orders=normal_orders,
        algo_orders=algo_orders,
        expected_side=close_side,
        expected_position_side=position_side,
        expected_sl_qty=exch_qty,
        expected_sl=sl_price
    )
    if not protection_detail.get("has_sl"):
        plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_SL_UNVERIFIED", {
            "symbol": tv_symbol,
            "trade_id": tid,
            "detail": protection_detail
        })
        return

    # Trigger early close
    current_pnl = float(position.get("profit", 0) or 0.0)
    plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_TRIGGERED", {
        "symbol": tv_symbol,
        "trade_id": tid,
        "side": direction,
        "age_minutes": round(age_minutes, 1),
        "peak_r": round(peak_r, 3),
        "current_r": round(current_r, 3),
        "current_pnl": round(current_pnl, 2)
    })

    result = _protective_close(tv_symbol, exch_qty, "LIVE_MICRO_SLUGGISH_INVALIDATION")

    if result.get("status") in {"closed", "partial_closed"}:
        exit_price = float(position.get("currentPrice", 0) or 0.0)

        try:
            trade_db.log_exit(
                trade_id=tid,
                exit_type="live_micro_sluggish_invalidation",
                price=exit_price,
                pnl_contribution=current_pnl,
                qty_pct=_remaining_original_fraction(state, exch_qty),
                notes=f"Sluggish invalidation triggered at {round(age_minutes, 1)}m (peak_r={round(peak_r, 2)}R, current_r={round(current_r, 2)}R)"
            )
        except Exception as e:
            plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_LOG_EXIT_ERROR", {"symbol": tv_symbol, "error": str(e)})

        try:
            trade_db.close_trade(
                trade_id=tid,
                exit_price=exit_price,
                pnl=current_pnl,
                gross_pnl=current_pnl,
                exit_reason="live_micro_sluggish_invalidation",
                duration_min=int(age_minutes)
            )
        except Exception as e:
            plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_CLOSE_TRADE_ERROR", {"symbol": tv_symbol, "error": str(e)})

        _send_telegram(
            f"⚠️ <b>LIVE MICRO SLUGGISH INVALIDATION</b>\n"
            f"{tv_symbol} {direction}\n"
            f"Trade open for {round(age_minutes, 1)}m with no progress (peak_r={round(peak_r, 2)}R)\n"
            f"Exited at {current_r:.2f}R (PnL: ${current_pnl:.2f}) to protect capital."
        )

        try:
            _cancel_stale_reduce_only_orders(symbol)
        except Exception as e:
            plain_log("LIVE_MICRO_SLUGGISH_INVALIDATION_CANCEL_ORDERS_ERROR", {"symbol": tv_symbol, "error": str(e)})


def _check_near_miss_duration_review(position: dict):
    """Send observe-only warning for near-miss winners open for too long on LIVE MICRO."""
    if os.environ.get("HERMES_INSTANCE_NAME") != "LIVE MICRO":
        return

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    if state.get("_near_miss_alert_sent"):
        return

    age_hours = _trade_open_age_hours(tid, symbol)
    if age_hours is None:
        return
    age_minutes = age_hours * 60.0
    if age_minutes < 180.0:
        return

    peak_r = float(state.get("_peak_r", 0) or 0)
    if not (peak_r >= 0.25 and peak_r < 0.50):
        return

    if trade_db.milestone_exists(tid, "milestone_0"):
        return

    current_r = _current_r_multiple(position, state)
    if current_r is None or current_r >= 0:
        return

    state["_near_miss_alert_sent"] = True
    current_pnl = float(position.get("profit", 0) or 0.0)

    plain_log("LIVE_MICRO_NEAR_MISS_DURATION_REVIEW", {
        "symbol": tv_symbol,
        "trade_id": tid,
        "age_minutes": round(age_minutes, 1),
        "peak_r": round(peak_r, 3),
        "current_r": round(current_r, 3),
        "current_pnl": round(current_pnl, 2),
        "recommendation": "REVIEW_ONLY"
    })

    _send_telegram(
        f"⏳ <b>LIVE_MICRO_NEAR_MISS_DURATION_REVIEW</b>\n"
        f"{tv_symbol} {position.get('type', 'BUY')}\n"
        f"Trade open for {round(age_minutes, 1)}m with no milestone_0 hit.\n"
        f"Peak R reached {peak_r:.2f}R, but currently in drawdown at {current_r:.2f}R (PnL: ${current_pnl:.2f}).\n"
        f"<b>Recommendation: REVIEW_ONLY</b> (Hold or Manual Exit if thesis is dead — No auto-close)."
    )


def _check_slot_pressure_duration_review(position: dict):
    """Send observe-only warning for old low-R winners that may be wasting a slot."""
    if not SLOT_PRESSURE_REVIEW_ENABLED:
        return
    if _monitor_instance_name() != "LIVE_MICRO":
        return

    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    if state.get("_slot_pressure_review_sent"):
        return

    age_hours = _trade_open_age_hours(tid, symbol)
    if age_hours is None:
        return
    age_minutes = age_hours * 60.0
    if age_minutes < SLOT_PRESSURE_REVIEW_MIN_AGE_MIN:
        return

    current_r = _current_r_multiple(position, state)
    if current_r is None:
        return

    peak_r = max(float(state.get("_peak_r", 0) or 0), current_r)
    if tid:
        try:
            trade = trade_db.get_trade_by_id(tid)
            risk_dollars = float(_row_get(trade, "risk_dollars", 0) or 0)
            peak_pnl = float(_row_get(trade, "peak_pnl", 0) or 0)
            if risk_dollars > 0 and peak_pnl > 0:
                peak_r = max(peak_r, peak_pnl / risk_dollars)
        except Exception as e:
            plain_log("SLOT_PRESSURE_REVIEW_PEAK_READ_ERROR", {"symbol": tv_symbol, "trade_id": tid, "error": str(e)})
    state["_peak_r"] = peak_r

    if peak_r < SLOT_PRESSURE_REVIEW_MIN_PEAK_R:
        return
    if peak_r >= SLOT_PRESSURE_REVIEW_MAX_PEAK_R:
        return
    if current_r > SLOT_PRESSURE_REVIEW_MAX_CURRENT_R:
        return

    state["_slot_pressure_review_sent"] = True
    current_pnl = float(position.get("profit", 0) or 0.0)
    plain_log("LIVE_MICRO_SLOT_PRESSURE_REVIEW", {
        "symbol": tv_symbol,
        "trade_id": tid,
        "side": position.get("type", "BUY"),
        "age_minutes": round(age_minutes, 1),
        "peak_r": round(peak_r, 3),
        "current_r": round(current_r, 3),
        "current_pnl": round(current_pnl, 2),
        "recommendation": "REVIEW_ONLY_TIGHTEN_TRAIL_OR_MANUAL_REDUCE",
    })

    _send_telegram(
        f"🧭 <b>LIVE_MICRO_SLOT_PRESSURE_REVIEW</b>\n"
        f"{tv_symbol} {position.get('type', 'BUY')}\n"
        f"Open {round(age_minutes, 1)}m with low capture.\n"
        f"Peak {peak_r:.2f}R, current {current_r:.2f}R, PnL ${current_pnl:.2f}.\n"
        f"<b>Recommendation: REVIEW_ONLY</b> — consider tighten trail/manual reduce if new higher-quality signals are blocked."
    )


def _report_pnl():
    """Send periodic PnL report / heartbeat."""
    now = time.time()
    if now - _position_state.get("_last_balance_report", 0) < REPORT_INTERVAL:
        return

    try:
        balance = get_balance()
        positions = get_open_positions()
        total_pnl = sum(float(p.get("profit", 0)) for p in positions)
        equity = float(balance.get("equity", 0))

        # Build uptime string
        uptime_str = "unknown"
        try:
            service_name = os.getenv("HERMES_MONITOR_SERVICE", "ozzybot-live-micro-monitor.service")
            import subprocess
            out = subprocess.check_output(
                ["systemctl", "--user", "show", service_name, "--property=ActiveEnterTimestamp"],
                text=True,
            )
            for line in out.strip().splitlines():
                if line.startswith("ActiveEnterTimestamp="):
                    ts_str = line.split("=", 1)[1]
                    if ts_str:
                        # systemctl output can be Mon 2026-06-01 10:05:43 CEST
                        # split by space to drop locale-specific short day name and timezone name
                        parts = ts_str.strip().split()
                        if len(parts) >= 3:
                            dt_str = f"{parts[1]} {parts[2]}"
                            from datetime import datetime
                            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                            now_dt = datetime.now()
                            delta = now_dt - dt
                            hours, rem = divmod(int(delta.total_seconds()), 3600)
                            mins, secs = divmod(rem, 60)
                            uptime_str = f"{hours}h {mins}m"
        except Exception:
            pass

        if uptime_str == "unknown":
            try:
                # Fallback to process uptime
                delta_secs = time.time() - _MONITOR_START_TIME
                hours, rem = divmod(int(delta_secs), 3600)
                mins, secs = divmod(rem, 60)
                uptime_str = f"{hours}h {mins}m"
            except Exception:
                pass

        if positions:
            pos_detail = ""
            for p in positions:
                sym = p.get("tv_symbol", p.get("symbol", "?"))
                pos_detail += f"{sym} {p.get('type','?')} ${float(p.get('profit',0)):+.2f}, "
            pos_detail = pos_detail.rstrip(", ")
            telegram_client.notify_heartbeat(
                equity, len(positions),
                BINANCE_SYMBOLS,
                uptime_str, pos_detail
            )
        # NOTE: idle heartbeat removed — use /status command or signal_generator hour summary instead

        _position_state["_last_balance_report"] = now
    except Exception as e:
        plain_log("BINANCE_PNL_REPORT_ERROR", {"error": str(e)})


def _get_client_for_instance(instance: str):
    """Return Binance client for standard testnet or live micro."""
    return _get_client()


def _get_db_path_for_instance(instance: str) -> str:
    """Return the active trade database path for the running process.

    The unified-core model makes ``trade_db.DB_PATH`` the source of truth.
    Instance names are retained for old reconciliation callers, but they must
    not silently route reads/writes into a second database.
    """
    return str(trade_db.DB_PATH)


def reconcile_missing_partial_exits(instance: str, trade_id: int, symbol: str) -> None:
    """
    Reconciles missing partial exits on Binance exchange by scanning recent fills
    and recording them in the exits table if they are missing.
    """
    import sqlite3
    from datetime import datetime

    db_path = _get_db_path_for_instance(instance)

    # 1. Fetch trade details from the database
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            trade_row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
            if not trade_row:
                plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "reason": "Trade not found in DB"
                })
                return
            trade = dict(trade_row)

            # Fetch existing exits
            exits_rows = conn.execute("SELECT * FROM exits WHERE trade_id = ?", (trade_id,)).fetchall()
            existing_exits = [dict(e) for e in exits_rows]
    except Exception as e:
        plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
            "trade_id": trade_id,
            "symbol": symbol,
            "error": f"DB error: {e!s}"
        })
        return

    original_qty = float(trade["qty"] or 0.0)
    if original_qty <= 0:
        return

    sum_qty_pct = sum([float(e["qty_pct"]) for e in existing_exits])
    db_expected_remaining_qty = original_qty * (1.0 - sum_qty_pct)

    # 2. Get current exchange position quantity
    try:
        client = _get_client_for_instance(instance)
        # Fetch position
        acct = client.futures_account()
        positions = acct.get("positions", [])
        exch_pos = None
        for p in positions:
            if p["symbol"] == symbol:
                exch_pos = p
                break

        if not exch_pos:
            exch_qty = 0.0
        else:
            exch_qty = abs(float(exch_pos.get("positionAmt", 0.0)))

    except Exception as e:
        plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
            "trade_id": trade_id,
            "symbol": symbol,
            "error": f"Binance position fetch error: {e!s}"
        })
        return

    # Check if exchange qty is lower than DB expected qty
    if exch_qty >= db_expected_remaining_qty - 0.001:
        if exch_qty > db_expected_remaining_qty + 0.001:
            plain_log("POSITION_QTY_MISMATCH", {
                "symbol": symbol,
                "trade_id": trade_id,
                "exchange_qty": exch_qty,
                "db_qty": db_expected_remaining_qty,
                "note": "Exchange quantity is larger than expected"
            })
        return

    unexplained_missing_qty = db_expected_remaining_qty - exch_qty

    # 3. Query recent filled orders or user trades
    try:
        try:
            entry_dt = datetime.strptime(trade["ts"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            entry_dt = datetime.fromisoformat(trade["ts"])

        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)

        entry_ts_ms = int(entry_dt.timestamp() * 1000)

        # Query account trades (fills) for this symbol
        trades_list = client.futures_account_trades(symbol=symbol, limit=50)

        # Filter trade fills
        relevant_fills = []
        for t in trades_list:
            fill_time = int(t["time"])
            opposite_side = "SELL" if trade["direction"] == "BUY" else "BUY"
            if fill_time >= entry_ts_ms and t["side"] == opposite_side:
                relevant_fills.append(t)

    except Exception as e:
        plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
            "trade_id": trade_id,
            "symbol": symbol,
            "error": f"Binance trades fetch error: {e!s}"
        })
        return

    # 4. Check which fills are already recorded in exits
    recorded_any = False
    for fill in relevant_fills:
        fill_id = str(fill["id"])
        order_id = str(fill["orderId"])
        fill_qty = float(fill["qty"])
        qty_pct = fill_qty / original_qty
        price = float(fill["price"])

        # Fill time parsing
        fill_time_ms = int(fill["time"])
        fill_dt = datetime.fromtimestamp(fill_time_ms / 1000, tz=timezone.utc)
        fill_time_str = fill_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Deterministic duplicate check on exits.notes
        already_recorded = False
        temporal_match_exit = None

        for ex in existing_exits:
            notes = ex.get("notes") or ""
            # Strict check using exact fill_id
            if f"fill_id={fill_id}" in notes or f"fill_id: {fill_id}" in notes:
                already_recorded = True
                break

            # If it is a reconstructed exchange fill, skip fallback checks
            if "exchange_bracket_fill" in notes or "reconstructed from exchange fill" in notes:
                continue

            # Fallback duplicate check for simple unit tests/mocks
            if fill_id in notes or order_id in notes:
                already_recorded = True
                break

            # Check temporal alignment with programmatic exits
            if ex.get("exit_type") != "exchange_bracket_fill":
                ex_ts_str = ex.get("ts")
                if ex_ts_str:
                    try:
                        try:
                            ex_dt = datetime.strptime(ex_ts_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            ex_dt = datetime.fromisoformat(ex_ts_str)
                        if ex_dt.tzinfo is None:
                            ex_dt = ex_dt.replace(tzinfo=timezone.utc)

                        diff_sec = abs((ex_dt - fill_dt).total_seconds())
                        if diff_sec <= 300: # 5 minutes
                            temporal_match_exit = ex
                            break
                    except Exception:
                        pass

        if already_recorded:
            continue

        # If we have a temporally matched programmatic exit, we replace it!
        if temporal_match_exit:
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.execute("DELETE FROM exits WHERE id = ?", (temporal_match_exit["id"],))
                    conn.commit()
                # Remove from existing_exits list
                existing_exits = [e for e in existing_exits if e["id"] != temporal_match_exit["id"]]
                plain_log("PARTIAL_EXIT_REPLACED", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "deleted_exit_id": temporal_match_exit["id"],
                    "deleted_exit_type": temporal_match_exit.get("exit_type"),
                    "deleted_exit_qty_pct": temporal_match_exit.get("qty_pct"),
                    "replaced_by_fill_id": fill_id
                })
            except Exception as e:
                plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "error": f"Failed to delete redundant exit: {e!s}"
                })
                continue

        # Record the actual exchange fill
        realized_pnl = float(fill.get("realizedPnl", 0.0))
        if realized_pnl == 0.0:
            if trade["direction"] == "BUY":
                realized_pnl = (price - trade["entry_price"]) * fill_qty
            else:
                realized_pnl = (trade["entry_price"] - price) * fill_qty

        notes = f"exchange_bracket_fill: reconstructed from exchange fill side={fill['side']} order_id={order_id} fill_id={fill_id} source=exchange_reconciliation"

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO exits (trade_id, ts, exit_type, price, pnl_contribution, qty_pct, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (trade_id, fill_time_str, "exchange_bracket_fill", price, realized_pnl, qty_pct, notes)
                )
                conn.commit()

            plain_log("PARTIAL_EXIT_RECORDED_FROM_EXCHANGE", {
                "trade_id": trade_id,
                "symbol": symbol,
                "order_id": order_id,
                "fill_id": fill_id,
                "qty": fill_qty,
                "qty_pct": qty_pct,
                "price": price,
                "pnl": realized_pnl
            })
            recorded_any = True

            # Fetch the newly inserted exit to get its ID and keep existing_exits correct
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                new_exit_row = conn.execute("SELECT * FROM exits WHERE trade_id = ? AND notes = ?", (trade_id, notes)).fetchone()
                if new_exit_row:
                    existing_exits.append(dict(new_exit_row))
                else:
                    existing_exits.append({
                        "id": 99999,  # fallback
                        "trade_id": trade_id,
                        "ts": fill_time_str,
                        "exit_type": "exchange_bracket_fill",
                        "price": price,
                        "pnl_contribution": realized_pnl,
                        "qty_pct": qty_pct,
                        "notes": notes
                    })

        except Exception as e:
            plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
                "trade_id": trade_id,
                "symbol": symbol,
                "error": f"DB insert error: {e!s}"
            })

    if not recorded_any and unexplained_missing_qty > 0.001:
        # Re-evaluate unexplained quantity now that we've processed all fills
        sum_qty_pct = sum([float(e["qty_pct"]) for e in existing_exits])
        db_expected_remaining_qty = original_qty * (1.0 - sum_qty_pct)
        new_unexplained = db_expected_remaining_qty - exch_qty
        if new_unexplained > 0.001:
            plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
                "trade_id": trade_id,
                "symbol": symbol,
                "reason": f"Unexplained quantity mismatch of {new_unexplained:.4f} exists but no matching exchange fills were identified"
            })

def _reconcile_orphan_positions(positions):
    """Compare Binance open positions against trades.db open trades to detect discrepancies."""
    if positions is None:
        return

    try:
        db_open = trade_db.get_open_trades()
    except Exception as e:
        plain_log("ORPHAN_RECONCILE_DB_ERROR", {"error": str(e)})
        return

    # Map db open trades by symbol
    db_by_sym = {}
    for ot in db_open:
        db_by_sym.setdefault(ot["symbol"], []).append(ot)

    # Map exchange positions by symbol
    exch_by_sym = {}
    for pos in positions:
        exch_by_sym.setdefault(pos["symbol"], []).append(pos)

    detected_orphans = []
    processed_db_ids = set()

    # 1. Inspect exchange positions and match against DB
    for pos in positions:
        symbol = pos["symbol"]
        exch_pos_type = pos.get("type", "BUY") # "BUY" or "SELL"
        exch_side = "LONG" if exch_pos_type == "BUY" else "SHORT"
        exch_qty = float(pos.get("volume", 0.0))
        entry_price = float(pos.get("openPrice", 0.0))
        mark_price = float(pos.get("currentPrice", 0.0))
        pnl = float(pos.get("profit", 0.0))

        db_candidates = db_by_sym.get(symbol, [])

        # Try to find matching trade by symbol and side
        matched_trade = None
        side_mismatched_trade = None
        for ot in db_candidates:
            ot_side = "LONG" if ot["direction"] == "BUY" else "SHORT"
            if ot_side == exch_side:
                matched_trade = ot
                break
            else:
                side_mismatched_trade = ot

        if matched_trade:
            # Case 4: Qty mismatch check with partial awareness
            processed_db_ids.add(matched_trade["id"])
            expected_remaining_qty = None
            try:
                order_state = trade_db.get_binance_order_state(symbol)
                if order_state and order_state["remaining_qty"] is not None:
                    expected_remaining_qty = float(order_state["remaining_qty"])
            except Exception:
                pass

            if expected_remaining_qty is None:
                try:
                    trade_id = matched_trade["id"]
                    db_path = trade_db.DB_PATH
                    import sqlite3
                    with sqlite3.connect(db_path) as conn:
                        conn.row_factory = sqlite3.Row
                        row = conn.execute(
                            "SELECT COALESCE(SUM(qty_pct), 0.0) AS sum_qty_pct FROM exits WHERE trade_id = ?",
                            (trade_id,)
                        ).fetchone()
                        sum_qty_pct = float(row["sum_qty_pct"] or 0.0)
                    original_qty = float(matched_trade["qty"] or 0.0)
                    expected_remaining_qty = original_qty * (1.0 - sum_qty_pct)
                except Exception:
                    expected_remaining_qty = float(matched_trade["qty"] or 0.0)

            if abs(exch_qty - expected_remaining_qty) <= 0.001:
                plain_log("POSITION_QTY_RECONCILED", {
                    "symbol": symbol,
                    "trade_id": matched_trade["id"],
                    "exchange_qty": exch_qty,
                    "expected_qty": expected_remaining_qty
                })
                try:
                    trade_db.upsert_binance_order_state(
                        symbol=symbol,
                        remaining_qty=exch_qty
                    )
                except Exception as e:
                    plain_log("BINANCE_ORDER_STATE_ERROR", {"symbol": symbol, "error": str(e)})
            else:
                # Still try to reconcile missing partial exits to resolve discrepancy
                try:
                    reconcile_missing_partial_exits(_monitor_instance_name(), matched_trade["id"], symbol)
                except Exception:
                    pass
                plain_log("POSITION_QTY_MISMATCH", {
                    "symbol": symbol,
                    "trade_id": matched_trade["id"],
                    "exchange_qty": exch_qty,
                    "db_qty": expected_remaining_qty
                })
                try:
                    trade_db.upsert_binance_order_state(symbol=symbol, remaining_qty=exch_qty)
                except Exception as e:
                    plain_log("BINANCE_ORDER_STATE_ERROR", {"symbol": symbol, "error": str(e)})
                plain_log("POSITION_QTY_RECONCILED", {
                    "symbol": symbol,
                    "trade_id": matched_trade["id"],
                    "exchange_qty": exch_qty,
                    "expected_qty": exch_qty,
                    "previous_expected_qty": expected_remaining_qty,
                    "accounting_noisy": True,
                    "reason": "exchange_position_is_management_truth",
                })
        elif side_mismatched_trade:
            # Case 3: Side mismatch
            processed_db_ids.add(side_mismatched_trade["id"])
            plain_log("POSITION_SIDE_MISMATCH", {
                "symbol": symbol,
                "trade_id": side_mismatched_trade["id"],
                "exchange_side": exch_side,
                "db_direction": side_mismatched_trade["direction"]
            })
        else:
            # Case 1: Orphan exchange position (exists on exchange, no DB open trade)
            # Find DB candidates (recent closed/shadow trades for symbol)
            candidates = []
            try:
                db_path = trade_db.DB_PATH
                import sqlite3
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT id, symbol, direction, exit_price, exit_reason, execution_state FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT 5",
                        (symbol,)
                    ).fetchall()
                    for r in rows:
                        candidates.append({
                            "trade_id": r["id"],
                            "symbol": r["symbol"],
                            "direction": r["direction"],
                            "exit_price": r["exit_price"],
                            "exit_reason": r["exit_reason"],
                            "execution_state": r["execution_state"]
                        })
            except Exception:
                pass

            orphan_info = {
                "symbol": symbol,
                "side": exch_side,
                "qty": exch_qty,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "unrealized_pnl": pnl,
                "candidates": candidates
            }
            detected_orphans.append(orphan_info)

            plain_log("ORPHAN_EXCHANGE_POSITION", {
                "symbol": symbol,
                "side": exch_side,
                "qty": exch_qty,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "unrealized_pnl": pnl,
                "candidate_ids": [c["trade_id"] for c in candidates]
            })

    # 2. Case 2: DB row exists, but exchange position is missing
    for ot in db_open:
        if ot["id"] not in processed_db_ids:
            if ot["symbol"] not in exch_by_sym:
                plain_log("DB_GHOST_TRADE", {
                    "symbol": ot["symbol"],
                    "trade_id": ot["id"]
                })

    # 3. Write all detected orphan positions to observer-local file
    observer_dir = "/home/rick/ozzy-bot/observer"
    os.makedirs(observer_dir, exist_ok=True)
    orphan_file = os.path.join(observer_dir, "orphan_positions.json")
    try:
        with open(orphan_file, "w") as f:
            json.dump(detected_orphans, f, indent=2)
    except Exception as e:
        plain_log("ORPHAN_FILE_WRITE_ERROR", {"error": str(e)})


def run():
    trade_db.seed_milestone_thresholds()
    plain_log("BINANCE_MONITOR_START", {"version": "v2", "features": ["breakeven", "trailing", "tiered", "duration", "milestones"]})
    telegram_client.notify_system_event("started", "Binance Monitor v2.3 — features: breakeven, trailing, tiered, duration, milestones")
    while True:
        try:
            positions = get_open_positions()
            _reconcile_orphan_positions(positions)
            open_symbols = set()

            for pos in positions:
                symbol = pos["symbol"]
                tv_symbol = pos.get("tv_symbol", symbol)
                open_symbols.add(symbol)

                # Initialize state on first sight
                state = _get_state(symbol)
                # Every item in ``positions`` is one fresh exchange snapshot.
                # Quantity-changing policies share this latch so only the
                # highest-priority successful action can mutate that snapshot.
                state["_exit_action_claimed"] = False
                state["_exit_action_reason"] = None
                direction = pos.get("type", "BUY")
                state["direction"] = direction
                if state["first_seen"] == 0:
                    state["first_seen"] = time.time()
                    state["entry_price"] = float(pos.get("openPrice", 0))
                    state["original_qty"] = float(pos.get("volume", 0))
                    state["sl_price"] = pos.get("stopLoss")
                    state["tp_price"] = pos.get("takeProfit")
                    # Binance positions do not carry SL/TP. Never claim a first-seen
                    # position is confirmed before the protected execution path says so.
                    try:
                        sl = pos.get("stopLoss")
                        tp = pos.get("takeProfit")
                        entry = float(pos.get("openPrice", 0))
                        if sl is not None:
                            telegram_client.notify_trade_reconciled(
                                tv_symbol, direction, f"new_{symbol}", entry, sl, tp
                            )
                        else:
                            telegram_client.notify_entry_protection_verifying(
                                direction, tv_symbol, entry, f"new_{symbol}"
                            )
                    except Exception:
                        pass
                    # Link to SQLite trade journal FIRST so we can use DB SL for cc_state
                    try:
                        open_trades = trade_db.get_open_trades(symbol)
                        for ot in open_trades:
                            if ot["direction"] == direction:
                                state["trade_id"] = ot["id"]
                                try:
                                    state["timeframe"] = ot["timeframe"]
                                except Exception:
                                    pass
                                break
                    except Exception:
                        pass

                    # Recover state from DB after restart (prevents re-firing milestones/breakeven)
                    tid = state.get("trade_id")
                    if tid:
                        _recover_state_from_db(state, tid, symbol)
                        state["_db_recovered_at"] = time.time()

                # Re-sync state from DB on every monitor cycle if trade_id exists
                # This prevents state drift if monitor missed events or DB was updated externally
                tid = state.get("trade_id")
                if tid:
                    last_recovered = state.get("_db_recovered_at", 0)
                    if not last_recovered or (time.time() - last_recovered) > 300:
                        _recover_state_from_db(state, tid, symbol)
                        state["_db_recovered_at"] = time.time()

                    # Sync with command_center registry
                    cc_state = _get_position_state(tv_symbol)
                    if cc_state.get("original_sl") is None:
                        sl_val = None
                        sl_dist = None
                        sl_source = "none"

                        # 1. Try Binance position SL
                        if pos.get("stopLoss"):
                            sl_val = float(pos["stopLoss"])
                            sl_source = "binance_position"

                        # 2. Try DB trade record for exact SL, distance, ATR
                        if sl_val is None and state.get("trade_id"):
                            try:
                                trade_row = trade_db.get_trade_by_id(state["trade_id"])
                                if trade_row:
                                    # Exact SL price
                                    if trade_row["sl"]:
                                        sl_val = float(trade_row["sl"])
                                        sl_source = "db_sl"
                                    # Exact distance from risk/qty
                                    if sl_dist is None and trade_row["risk_dollars"] and trade_row["qty"]:
                                        sl_dist = float(trade_row["risk_dollars"]) / float(trade_row["qty"])
                                        sl_source = "db_risk_qty"
                                    # Geometric: |entry - tp| / rr
                                    if sl_dist is None and trade_row["entry_price"] and trade_row["tp"] and trade_row["rr"]:
                                        sl_dist = abs(float(trade_row["entry_price"]) - float(trade_row["tp"])) / float(trade_row["rr"])
                                        sl_source = "db_geometric"
                                    # ATR-based estimate (5x = our hard-stop multiplier)
                                    if sl_dist is None and trade_row["atr"]:
                                        sl_dist = float(trade_row["atr"]) * 5.0
                                        sl_source = "db_atr"
                            except Exception:
                                pass

                        # 3. Last-resort dynamic estimate from current price
                        if sl_dist is None:
                            current_price = float(pos.get("currentPrice", 0))
                            entry_price = state["entry_price"]
                            if entry_price > 0 and current_price > 0:
                                sl_dist = abs(entry_price - current_price) * 0.4
                                sl_source = "dynamic_estimate"

                        # Derive sl_val from sl_dist if we only have distance
                        if sl_val is None and sl_dist and state["entry_price"] > 0:
                            sl_val = state["entry_price"] - sl_dist if direction == "BUY" else state["entry_price"] + sl_dist

                        cc_state["original_sl"] = sl_val
                        cc_state["original_tp"] = float(pos.get("takeProfit", 0)) if pos.get("takeProfit") else None
                        cc_state["entry_price"] = state["entry_price"]
                        entry_val = cc_state["entry_price"]
                        if sl_val and entry_val:
                            cc_state["original_sl_distance"] = abs(entry_val - sl_val)

                        plain_log("SL_RESOLVED", {
                            "symbol": tv_symbol,
                            "trade_id": state.get("trade_id"),
                            "sl_source": sl_source,
                            "sl_val": sl_val,
                            "sl_dist": sl_dist,
                            "original_sl_distance": cc_state.get("original_sl_distance"),
                        })

                if _open_trade_direction_mismatch(pos, state):
                    continue

                # Keep last known price/pnl for exit inference
                _reconcile_order_state(pos)
                _repair_missing_protection_if_needed(pos)

                # Keep last known price/pnl for exit inference
                current_price = float(pos.get("currentPrice", 0))
                current_pnl = float(pos.get("profit", 0))
                state["last_price"] = current_price
                state["last_pnl"] = current_pnl

                # Track peak PnL / peak price in DB
                tid = state.get("trade_id")
                if tid:
                    trade_db.update_trade_peak(tid, current_pnl, current_price)

                _check_time_decay_exit(pos)
                _check_breakeven(pos)
                _check_early_profit_protection(pos)
                _check_fixed_milestones(pos)
                _check_milestone_exits(pos)
                _check_choch_reversal(pos)
                _check_simple_trailing_stop(pos)
                _check_trailing_stop(pos)
                _check_trade_duration(pos)
                _check_time_based_exit(pos)
                _check_roundtrip_guard_r1(pos)
                _check_early_giveback_guard(pos)
                _check_profit_protection(pos)
                _check_momentum_reversal(pos)
                _check_sluggish_invalidation(pos)
                _check_near_miss_duration_review(pos)
                _check_slot_pressure_duration_review(pos)

            _prune_state(open_symbols)
            _report_pnl()

        except Exception as e:
            plain_log("BINANCE_MONITOR_ERROR", {"error": str(e)})

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
