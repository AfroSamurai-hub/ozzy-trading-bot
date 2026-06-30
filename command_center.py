#!/usr/bin/env python3
# ============================================
# COMMAND CENTER — Jarvis Trade Control Engine
# ============================================
# Validates and executes trade management commands with guardrails.
# The AI (Hermes) can CALL this engine but cannot bypass validation.
#
# Rule: The queen (bot) executes. The advisor (AI) suggests.
# This engine is the gatekeeper between suggestion and execution.

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import trade_db
from binance_connector import (
    TV_TO_BINANCE,
    ProtectionOrderRef,
    _format_quantity,
    _get_client,
    _map_symbol,
    _place_sl_tp_order,
    close_position,
    get_balance,
    get_open_positions,
    verify_protection_order,
)
from binance_connector import (
    move_sl_to_breakeven as _connector_move_breakeven,
)
from config import (
    ASSETS,  # noqa: F401  # exposed for tests
    HALT_FILE,
    MAX_POSITIONS,
    MIN_RR,
    PAPER_MODE,
    RISK_PCT,
)
from logger import plain_log


class CommandType(Enum):
    STATUS = "status"
    STATUS_DEEP = "status_deep"
    CLOSE = "close"
    PARTIAL_CLOSE = "partial_close"
    BREAKEVEN = "breakeven"
    TRAIL = "trail"
    UPDATE_SL = "update_sl"
    UPDATE_TP = "update_tp"
    SCALE_IN = "scale_in"
    SET_MODE = "set_mode"
    PANIC = "panic"
    RESUME = "resume"
    REGIME = "regime"
    PURGE_STALE_STOPS = "purge_stale_stops"
    APPROVE_SCRATCH = "approve_scratch"
    REJECT_SCRATCH = "reject_scratch"
    WATCH_SCRATCH = "watch_scratch"
    ADOPT_ORPHAN = "adopt_orphan"
    CLOSE_ORPHAN = "close_orphan"
    LM_CLOSE = "lm_close"
    LM_WATCH = "lm_watch"
    LM_REJECT = "lm_reject"
    COOLDOWNS = "cooldowns"



class TrailMode(Enum):
    OFF = "off"
    ATR = "atr"           # Trail at N x ATR
    PERCENT = "percent"   # Trail at N% behind price
    FIXED = "fixed"       # Trail at fixed price distance


def _command_db_path_for_instance(instance: str | None = None) -> str:
    """Return the active command-center trade DB path.

    Legacy scratch/loss-minimization alerts still carry instance labels, but
    the unified runtime stores all trade state in ``trade_db.DB_PATH``.
    """
    return str(trade_db.DB_PATH)


@dataclass
class CommandResult:
    success: bool
    command: str
    message: str
    details: dict
    requires_confirmation: bool = False
    confirmation_prompt: str = ""


# ---------------------------------------------------------------------------
# In-memory position state for dynamic SL/TP tracking
# ---------------------------------------------------------------------------
_position_registry: dict[str, dict] = {}


def _get_position_state(symbol: str) -> dict:
    """Return mutable state for a tracked position."""
    return _position_registry.setdefault(symbol, {
        "original_sl": None,
        "original_tp": None,
        "entry_price": None,
        "original_sl_distance": None,
        "trail_mode": TrailMode.OFF.value,
        "trail_param": None,       # e.g. 1.5 for ATR, 0.02 for percent
        "trail_trigger_r": 1.0,    # Start trailing after this R multiple
        "breakeven_moved": False,
        "tiered_exits_done": [],   # Which tiered exits have fired
        "command_history": [],
    })


def _log_command(symbol: str, cmd_type: str, params: dict, result: dict):
    entry = {
        "ts": time.time(),
        "type": cmd_type,
        "params": params,
        "result": result,
    }
    state = _get_position_state(symbol)
    state["command_history"].append(entry)
    plain_log("COMMAND_AUDIT", {"symbol": symbol, "entry": entry})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _get_position(symbol: str) -> dict | None:
    """Fetch a single open position by TradingView symbol."""
    positions = get_open_positions()
    tv_sym = symbol.upper()
    for pos in positions:
        if pos.get("tv_symbol") == tv_sym or pos.get("symbol") == _map_symbol(tv_sym):
            return pos
    return None


def _get_sl_tp_from_orders(binance_symbol: str) -> tuple[float | None, float | None]:
    """Query open orders to find SL and TP prices for a position.

    Binance Futures stores SL/TP as separate STOP_MARKET / TAKE_PROFIT_MARKET
    orders — they are NOT included in the position object. Depending on the
    endpoint Binance uses for the symbol/account, protective orders may appear
    in either standard open orders or ALGO open orders.
    """
    if PAPER_MODE:
        return None, None
    try:
        client = _get_client()
        sl_price = None
        tp_price = None

        def _assign_from_order(order: dict) -> None:
            nonlocal sl_price, tp_price
            otype = _order_type(order)
            trigger = order.get("stopPrice") or order.get("triggerPrice") or order.get("price")
            try:
                price = float(trigger or 0) or None
            except (TypeError, ValueError):
                price = None
            if otype in ("STOP_MARKET", "STOP"):
                sl_price = price
            elif otype in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                tp_price = price

        for o in client.futures_get_open_orders(symbol=binance_symbol):
            _assign_from_order(o)

        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=binance_symbol)
        except Exception as e:
            plain_log("BINANCE_STATUS_ALGO_FETCH_ERROR", {"symbol": binance_symbol, "error": str(e)})
            algo_orders = []

        for o in algo_orders:
            _assign_from_order(o)
        return sl_price, tp_price
    except Exception:
        return None, None


def _daily_risk_used() -> float:
    """Estimate daily risk currently allocated in open positions."""
    positions = get_open_positions()
    total_risk = 0.0
    for pos in positions:
        entry = float(pos.get("openPrice", 0))
        sl = float(pos.get("stopLoss", 0) or entry)
        if entry and sl:
            sl_dist = abs(entry - sl)
            qty = float(pos.get("volume", pos.get("positionAmt", 0)))
            # Approximate: this is already committed risk
            total_risk += sl_dist * qty
    return total_risk


def _position_amt_for_symbol(positions: list[dict], symbol: str) -> float:
    """Return the raw Binance position amount for a symbol from position rows."""
    for pos in positions or []:
        if pos.get("symbol") == symbol:
            try:
                return float(pos.get("positionAmt", 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _order_type(order: dict) -> str:
    """Return the normalized order type for normal or ALGO order payloads."""
    return str(order.get("type") or order.get("orderType") or "").upper()


def _truthy_order_flag(value) -> bool:
    """Return True for bool/string exchange flags."""
    return value is True or str(value).lower() == "true"


def _is_reduce_only_protection(order: dict) -> bool:
    """Return whether an order is a reduce-only stop/take-profit protection order."""
    return _order_type(order) in {
        "STOP",
        "STOP_MARKET",
        "TAKE_PROFIT",
        "TAKE_PROFIT_MARKET",
    } and (
        _truthy_order_flag(order.get("reduceOnly"))
        or _truthy_order_flag(order.get("closePosition"))
        or _truthy_order_flag(order.get("close_position"))
    )


def _capture_protection_orders(client, binance_sym: str, expected_types: set[str]) -> tuple[list[dict], list[dict]]:
    """Return existing normal and ALGO protective orders for a symbol."""
    open_orders = client.futures_get_open_orders(symbol=binance_sym)
    old_normal = [o for o in open_orders if _order_type(o) in expected_types]
    try:
        open_algo = client.futures_get_open_algo_orders(symbol=binance_sym)
        old_algo = [o for o in open_algo if _order_type(o) in expected_types]
    except Exception as e:
        plain_log("BINANCE_ALGO_FETCH_ERROR", {"symbol": binance_sym, "error": str(e)})
        old_algo = []
    return old_normal, old_algo


def _cancel_captured_orders(client, binance_sym: str, normal_orders: list[dict], algo_orders: list[dict]) -> list[str]:
    """Cancel previously captured normal and ALGO orders after replacement is verified."""
    errors = []
    for order in normal_orders:
        try:
            client.futures_cancel_order(symbol=binance_sym, orderId=order["orderId"])
        except Exception as e:
            errors.append(f"normal:{order.get('orderId')}: {e}")
            plain_log("BINANCE_CANCEL_OLD_ORDER_ERROR", {
                "symbol": binance_sym,
                "orderId": order.get("orderId"),
                "error": str(e),
            })
    for order in algo_orders:
        try:
            client.futures_cancel_algo_order(symbol=binance_sym, algoId=order["algoId"])
        except Exception as e:
            errors.append(f"algo:{order.get('algoId')}: {e}")
            plain_log("BINANCE_CANCEL_OLD_ALGO_ERROR", {
                "symbol": binance_sym,
                "algoId": order.get("algoId"),
                "error": str(e),
            })
    return errors


def _replace_protection_order_verified(
    *,
    symbol: str,
    binance_sym: str,
    side: str,
    order_type: str,
    stop_price: float,
    quantity: float,
    expected_old_types: set[str],
) -> tuple[bool, str, dict]:
    """Place and verify replacement protection before canceling old orders."""
    client = _get_client()
    old_normal, old_algo = _capture_protection_orders(client, binance_sym, expected_old_types)
    result = _place_sl_tp_order(
        client=client,
        symbol=binance_sym,
        side=side,
        order_type=order_type,
        stop_price=stop_price,
        quantity=quantity,
        position_side="LONG" if side == "SELL" else "SHORT",
    )
    detail = {
        "symbol": symbol,
        "binance_symbol": binance_sym,
        "order_type": order_type,
        "stop_price": stop_price,
        "quantity": quantity,
        "old_normal_count": len(old_normal),
        "old_algo_count": len(old_algo),
        "replacement": result,
    }
    if not result.get("success"):
        plain_log("PROTECTION_REPLACE_NEW_ORDER_FAILED_OLD_KEPT", detail)
        return False, "Replacement order failed; old protection was kept live", detail

    protection_ref = result.get("protection_ref")
    if isinstance(protection_ref, dict):
        protection_ref = ProtectionOrderRef(**protection_ref)
    verified, verify_detail = verify_protection_order(client, protection_ref)
    detail["verification"] = verify_detail
    if not verified:
        plain_log("PROTECTION_REPLACE_VERIFY_FAILED_OLD_KEPT", detail)
        return False, "Replacement order could not be verified; old protection was kept live", detail

    cancel_errors = _cancel_captured_orders(client, binance_sym, old_normal, old_algo)
    detail["cancel_errors"] = cancel_errors
    plain_log("PROTECTION_REPLACE_VERIFIED", detail)

    try:
        import trade_db

        kwargs = {"symbol": binance_sym, "tv_symbol": symbol}
        if order_type in {"STOP_MARKET", "STOP"}:
            kwargs["current_sl"] = stop_price
            kwargs["sl_order_id"] = str(result.get("orderId")) if result.get("orderId") else None
        else:
            kwargs["current_tp"] = stop_price
            kwargs["tp_order_id"] = str(result.get("orderId")) if result.get("orderId") else None
        trade_db.upsert_binance_order_state(**kwargs)
    except Exception as e:
        plain_log("BINANCE_ORDER_STATE_UPDATE_ERROR", {"symbol": binance_sym, "error": str(e)})

    if cancel_errors:
        return True, f"Replacement verified; old-order cancel warnings: {len(cancel_errors)}", detail
    return True, "Replacement verified and old protection canceled", detail


def _validate_sl_guardrail(symbol: str, new_sl: float) -> tuple[bool, str]:
    """Ensure new SL is not wider than original (tighter = safer)."""
    state = _get_position_state(symbol)
    original_sl = state.get("original_sl")
    entry = state.get("entry_price")

    if original_sl is None or entry is None:
        return True, "No original SL anchor — allowing command"

    original_dist = abs(entry - original_sl)
    new_dist = abs(entry - new_sl)

    if new_dist > original_dist * 1.05:  # 5% tolerance for rounding
        return False, (
            f"❌ GUARDRAIL BLOCKED: New SL distance ({new_dist:.2f}) "
            f"is wider than original ({original_dist:.2f}). "
            f"The queen protects capital — SL can only tighten."
        )
    return True, ""


def _validate_tp_guardrail(symbol: str, new_tp: float) -> tuple[bool, str]:
    """Ensure TP is not removed entirely and maintains minimum RR."""
    state = _get_position_state(symbol)
    entry = state.get("entry_price")
    original_sl = state.get("original_sl")

    if entry is None or original_sl is None:
        return True, ""

    if new_tp == 0 or new_tp == entry:
        return False, "❌ GUARDRAIL BLOCKED: Removing TP is not allowed."

    sl_dist = abs(entry - original_sl)
    tp_dist = abs(new_tp - entry)
    effective_rr = tp_dist / sl_dist if sl_dist > 0 else 0

    if effective_rr < MIN_RR * 0.8:  # Allow 20% slack for partial profit-taking
        return False, (
            f"❌ GUARDRAIL BLOCKED: Effective R:R ({effective_rr:.2f}) "
            f"would drop below minimum ({MIN_RR})."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _count_recent_errors_24h() -> dict:
    import json
    import os
    from datetime import datetime, timedelta

    error_counts = {
        "-2015": 0,
        "-4061": 0,
        "-4130": 0,
        "ReadTimeout": 0,
        "TRAILING STOP FAILED": 0
    }

    log_file = "/home/rick/ozzy-bot/trades.log"
    if not os.path.exists(log_file):
        return error_counts

    now = datetime.now()
    cutoff = now - timedelta(hours=24)

    try:
        with open(log_file) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    ts_str = entry.get("ts")
                    if not ts_str:
                        continue
                    # Parse timestamp format "YYYY-MM-DD HH:MM:SS"
                    entry_time = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
                    if entry_time < cutoff:
                        continue

                    entry_str = str(entry)
                    if "-2015" in entry_str:
                        error_counts["-2015"] += 1
                    if "-4061" in entry_str:
                        error_counts["-4061"] += 1
                    if "-4130" in entry_str:
                        error_counts["-4130"] += 1
                    if "ReadTimeout" in entry_str:
                        error_counts["ReadTimeout"] += 1
                    if "TRAILING STOP FAILED" in entry_str or "TRAIL_REPLACE_FAILED" in entry_str:
                        error_counts["TRAILING STOP FAILED"] += 1
                except Exception:
                    pass
    except Exception:
        pass
    return error_counts


def build_command_center_status() -> str:
    """Helper to build rich Telegram-safe status message."""
    raw_positions = get_open_positions() or []
    positions = [p for p in raw_positions if float(p.get("volume", 0)) > 0]
    balance = get_balance()

    from datetime import datetime

    import trade_db
    from config import BINANCE_API_KEY, BINANCE_TESTNET, LIVE_MICRO_NO_NEW_ENTRIES
    mode_str = "TESTNET" if BINANCE_TESTNET else "LIVE_MICRO"
    lock_str = "LOCKED" if LIVE_MICRO_NO_NEW_ENTRIES else "UNLOCKED"

    lines = [
        "💼 <b>HERMES COMMAND CENTER</b>",
        f"Mode: <code>{mode_str}</code>"
    ]
    if BINANCE_API_KEY:
        lines.append(f"Live lock status: <code>{lock_str}</code>")
    lines.append("")

    equity = float(balance.get('equity', 0) or 0)
    bal_val = float(balance.get('balance', 0) or 0)
    lines.append(
        f"<b>Account:</b>\n"
        f"• Equity: ${equity:.2f}\n"
        f"• Balance: ${bal_val:.2f}\n"
        f"• Positions: {len(positions)} / {MAX_POSITIONS}\n"
    )

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today_realized_pnl = 0.0
    today_trades_count = 0
    best_pnl = -9999999.0
    best_symbol = None
    best_direction = None
    known_all = True

    try:
        import sqlite3
        with sqlite3.connect(trade_db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT DISTINCT t.id, t.symbol, t.direction, t.pnl
                FROM trades t
                JOIN exits e ON t.id = e.trade_id
                WHERE e.qty_pct = 1.0 AND e.ts LIKE ?
                """,
                (f"{today_str}%",)
            )
            today_trades = [dict(row) for row in cursor.fetchall()]

            today_trades_count = len(today_trades)
            for t in today_trades:
                p = t.get("pnl")
                if p is None:
                    known_all = False
                else:
                    today_realized_pnl += p
                    if p > best_pnl:
                        best_pnl = p
                        best_symbol = t.get("symbol")
                        best_direction = t.get("direction")
    except Exception as e:
        known_all = False
        plain_log("STATUS_DB_READ_ERROR", {"error": str(e)})

    open_unrealized_pnl = 0.0
    for pos in positions:
        open_unrealized_pnl += float(pos.get("profit", 0) or 0)

    realized_str = f"${today_realized_pnl:+.2f}" if known_all else "unknown"
    net_str = f"${today_realized_pnl + open_unrealized_pnl:+.2f}" if known_all else "unknown"

    lines.append(
        f"<b>PnL Summary:</b>\n"
        f"• Today Realized PnL: <b>{realized_str}</b>\n"
        f"• Open Unrealized PnL: <b>${open_unrealized_pnl:+.2f}</b>\n"
        f"• Today Net PnL: <b>{net_str}</b>\n"
        f"• Closed Trades Today: {today_trades_count}"
    )

    if today_trades_count > 0 and best_symbol:
        lines.append(f"• Best Closed Trade: {best_symbol} ({best_direction}) <b>${best_pnl:+.2f}</b>\n")
    else:
        lines.append("")

    lines.append("<b>Open Positions:</b>")
    if not positions:
        lines.append("• No open positions.")
    else:
        for pos in positions:
            sym = pos.get("tv_symbol", pos.get("symbol", "?"))
            side = pos.get("type", "?")
            entry = float(pos.get("openPrice", 0) or 0)
            current = float(pos.get("currentPrice", 0) or 0)
            pnl = float(pos.get("profit", 0) or 0)

            binance_sym = pos.get("symbol", _map_symbol(sym))
            sl_price, tp_price = _get_sl_tp_from_orders(binance_sym)

            sl_val = sl_price if sl_price is not None else float(pos.get("stopLoss", 0) or 0)
            tp_val = tp_price if tp_price is not None else float(pos.get("takeProfit", 0) or 0)

            if PAPER_MODE:
                prot_status = "PROTECTED"
                sl_str = f"{sl_val:.2f}" if sl_val else "—"
                tp_str = f"{tp_val:.2f}" if tp_val else "—"
            else:
                if not sl_val or sl_val <= 0:
                    prot_status = "MISSING"
                elif not tp_val or tp_val <= 0:
                    prot_status = "WARNING"
                else:
                    prot_status = "PROTECTED"
                sl_str = f"{sl_val:.2f}" if sl_val else "—"
                tp_str = f"{tp_val:.2f}" if tp_val else "—"

            lines.append(
                f"• <b>{sym} {side}</b>\n"
                f"  Entry: {entry:.2f} | Current: {current:.2f}\n"
                f"  PnL: ${pnl:+.2f}\n"
                f"  SL: {sl_str} | TP: {tp_str}\n"
                f"  Protection: <code>{prot_status}</code>\n"
            )

    errs = _count_recent_errors_24h()
    try:
        import loss_cooldowns
        cooldown_count = len(loss_cooldowns.load_cooldowns())
    except Exception:
        cooldown_count = 0

    lines.append(
        f"<b>Risk & Health (last 24h):</b>\n"
        f"• Live new entries lock status: <code>{lock_str}</code>\n"
        f"• HERMES_RISK_PCT: {RISK_PCT * 100:.1f}%\n"
        f"• Active Loss Cooldowns: <code>{cooldown_count}</code>\n"
        f"• API Errors:\n"
        f"  - -2015 (Invalid credentials): {errs['-2015']}\n"
        f"  - -4061 (Invalid position side): {errs['-4061']}\n"
        f"  - -4130 (Duplicate close position): {errs['-4130']}\n"
        f"  - ReadTimeout (Network issue): {errs['ReadTimeout']}\n"
        f"  - TRAILING STOP FAILED: {errs['TRAILING STOP FAILED']}"
    )

    return "\n".join(lines)


def cmd_status() -> CommandResult:
    """Return summary of all open positions and account status."""
    try:
        msg = build_command_center_status()
        return CommandResult(
            success=True,
            command="status",
            message=msg,
            details={},
        )
    except Exception as e:
        plain_log("STATUS_RICH_FALLBACK", {"error": str(e)})
        fallback_msg = f"💼 <b>HERMES COMMAND CENTER</b>\n⚠️ STATUS_RICH_FALLBACK - Rich status builder failed.\nError: <code>{e!s}</code>"
        return CommandResult(
            success=False,
            command="status",
            message=fallback_msg,
            details={"error": str(e)},
        )


def cmd_status_deep() -> CommandResult:
    """Return deep status report including partial exit tracking."""
    try:
        import sqlite3

        import trade_db
        from binance_connector import get_open_positions

        raw_positions = get_open_positions() or []
        positions = [p for p in raw_positions if float(p.get("volume", 0)) > 0]

        lines = [
            "🔍 <b>HERMES DEEP STATUS REPORT</b>",
            ""
        ]

        if not positions:
            lines.append("• No open positions.")
        else:
            for pos in positions:
                symbol = pos["symbol"]
                exch_qty = float(pos.get("volume", 0.0))

                db_path = trade_db.DB_PATH
                matched_trade = None
                try:
                    with sqlite3.connect(db_path) as conn:
                        conn.row_factory = sqlite3.Row
                        db_open_trades = conn.execute(
                            "SELECT * FROM trades WHERE symbol = ? AND exit_price IS NULL",
                            (symbol,)
                        ).fetchall()
                        if db_open_trades:
                            matched_trade = dict(db_open_trades[0])
                except Exception:
                    pass

                if matched_trade:
                    trade_id = matched_trade["id"]
                    try:
                        with sqlite3.connect(db_path) as conn:
                            conn.row_factory = sqlite3.Row
                            row = conn.execute(
                                "SELECT COALESCE(SUM(qty_pct), 0.0) AS sum_qty_pct FROM exits WHERE trade_id = ?",
                                (trade_id,)
                            ).fetchone()
                            sum_qty_pct = float(row["sum_qty_pct"] or 0.0)
                        original_qty = float(matched_trade["qty"] or 0.0)
                        expected_qty = original_qty * (1.0 - sum_qty_pct)
                    except Exception:
                        expected_qty = float(matched_trade["qty"] or 0.0)

                    track_status = "GREEN" if abs(exch_qty - expected_qty) <= 0.001 else "AMBER"

                    lines.append(
                        f"• <b>{symbol}</b> (Trade #{trade_id})\n"
                        f"  Exchange Qty: <code>{exch_qty:.4f}</code>\n"
                        f"  DB Expected Qty: <code>{expected_qty:.4f}</code>\n"
                        f"  Partial Exit Tracking: <b>{track_status}</b>\n"
                    )
                else:
                    lines.append(
                        f"• <b>{symbol}</b> (Orphan position)\n"
                        f"  Exchange Qty: <code>{exch_qty:.4f}</code>\n"
                        f"  Partial Exit Tracking: <b>RED (Orphan)</b>\n"
                    )

        return CommandResult(
            success=True,
            command="status_deep",
            message="\n".join(lines),
            details={"positions_count": len(positions)}
        )
    except Exception as e:
        plain_log("STATUS_DEEP_ERROR", {"error": str(e)})
        return CommandResult(
            success=False,
            command="status_deep",
            message=f"❌ status_deep failed: {e!s}",
            details={"error": str(e)}
        )


def cmd_cooldowns() -> CommandResult:
    """Return summary of all active same-symbol loss cooldowns."""
    try:
        from datetime import datetime

        import loss_cooldowns
        cooldowns = loss_cooldowns.load_cooldowns()
        if not cooldowns:
            return CommandResult(
                success=True,
                command="cooldowns",
                message="❄️ <b>No active loss cooldowns.</b>\nAll symbols are fully available for trading.",
                details={}
            )

        lines = ["❄️ <b>Active Loss Cooldowns:</b>\n"]
        for c in cooldowns:
            expires_str = c.get("expires_at", "unknown")
            try:
                dt = datetime.fromisoformat(expires_str)
                expires_formatted = dt.strftime("%Y-%m-%d %H:%M:%S SAST")
            except Exception:
                expires_formatted = expires_str

            lines.append(
                f"• <b>{c.get('symbol')} {c.get('side')} ({c.get('instance')})</b>\n"
                f"  Setup: {c.get('setup_grade')} | Strategy: {c.get('strategy')}\n"
                f"  Loss: {c.get('realized_pnl'):.2f} USD\n"
                f"  Expires: <code>{expires_formatted}</code>\n"
            )
        return CommandResult(
            success=True,
            command="cooldowns",
            message="\n".join(lines),
            details={"count": len(cooldowns)}
        )
    except Exception as e:
        return CommandResult(
            success=False,
            command="cooldowns",
            message=f"❌ Error loading cooldowns: {e}",
            details={"error": str(e)}
        )


def cmd_close(symbol: str, pct: float | None = None) -> CommandResult:
    """Close a position fully or partially."""
    symbol = symbol.upper()
    pos = _get_position(symbol)
    if not pos:
        return CommandResult(
            success=False, command="close",
            message=f"❌ No open position found for {symbol}",
            details={},
        )

    binance_sym = _map_symbol(symbol)
    qty = float(pos.get("positionAmt", pos.get("volume", 0)))
    qty = abs(qty)

    if pct is not None:
        if not (0 < pct <= 100):
            return CommandResult(
                success=False, command="close",
                message="❌ Percentage must be 1-100", details={},
            )
        close_qty = qty * (pct / 100)
        close_qty = _format_quantity(binance_sym, close_qty)

        # Partial close via market order with reduceOnly
        if not PAPER_MODE:
            client = _get_client()
            side = "SELL" if float(pos.get("positionAmt", qty)) > 0 else "BUY"
            client.futures_create_order(
                symbol=binance_sym, side=side, type="MARKET",
                quantity=close_qty, reduceOnly=True,
            )

        msg = f"✅ Closed {pct:.0f}% of {symbol} ({close_qty} units)"
        _log_command(symbol, "partial_close", {"pct": pct}, {"success": True})
    else:
        result = close_position(binance_sym)
        msg = f"✅ Closed {symbol} completely"
        _log_command(symbol, "close", {}, result)

    return CommandResult(
        success=True, command="close", message=msg,
        details={"symbol": symbol, "pct": pct},
    )


def cmd_breakeven(symbol: str) -> CommandResult:
    """Move SL to entry price."""
    symbol = symbol.upper()
    pos = _get_position(symbol)
    if not pos:
        return CommandResult(
            success=False, command="breakeven",
            message=f"❌ No open position for {symbol}", details={},
        )

    entry = float(pos.get("openPrice", 0))
    binance_sym = _map_symbol(symbol)

    _connector_move_breakeven(binance_sym, entry)
    _get_position_state(symbol)["breakeven_moved"] = True
    _log_command(symbol, "breakeven", {}, {"entry": entry})

    return CommandResult(
        success=True, command="breakeven",
        message=f"🛡️ {symbol} SL moved to breakeven (entry: {entry:.2f})",
        details={"entry": entry},
    )


def cmd_trail(symbol: str, mode: str, param: float, trigger_r: float = 1.0) -> CommandResult:
    """Activate trailing stop for a position."""
    symbol = symbol.upper()
    pos = _get_position(symbol)
    if not pos:
        return CommandResult(
            success=False, command="trail",
            message=f"❌ No open position for {symbol}", details={},
        )

    try:
        trail_mode = TrailMode(mode.lower())
    except ValueError:
        return CommandResult(
            success=False, command="trail",
            message=f"❌ Invalid trail mode: {mode}. Use: atr, percent, fixed", details={},
        )

    state = _get_position_state(symbol)
    state["trail_mode"] = trail_mode.value
    state["trail_param"] = param
    state["trail_trigger_r"] = trigger_r

    _log_command(symbol, "trail", {"mode": mode, "param": param, "trigger_r": trigger_r}, {})

    return CommandResult(
        success=True, command="trail",
        message=(
            f"🏃 {symbol} trailing stop ACTIVATED\n"
            f"Mode: {mode.upper()} | Param: {param}\n"
            f"Starts trailing after profit reaches {trigger_r}R"
        ),
        details={"mode": mode, "param": param, "trigger_r": trigger_r},
    )


def cmd_update_sl(symbol: str, price: float | None = None, offset_pct: float | None = None) -> CommandResult:
    """Update stop loss to absolute price or percentage offset from entry."""
    symbol = symbol.upper()
    pos = _get_position(symbol)
    if not pos:
        return CommandResult(
            success=False, command="update_sl",
            message=f"❌ No open position for {symbol}", details={},
        )

    entry = float(pos.get("openPrice", 0))
    current = float(pos.get("currentPrice", 0))
    side = pos.get("type", "BUY")

    if offset_pct is not None:
        # offset_pct positive = tighter SL (safer)
        # offset_pct negative = wider SL (blocked by guardrail)
        new_sl = entry * (1 - offset_pct / 100) if side == "BUY" else entry * (1 + offset_pct / 100)
    elif price is not None:
        new_sl = price
    else:
        return CommandResult(
            success=False, command="update_sl",
            message="❌ Provide either price= or offset_pct=", details={},
        )

    new_sl = round(new_sl, 2)
    ok, reason = _validate_sl_guardrail(symbol, new_sl)
    if not ok:
        return CommandResult(
            success=False, command="update_sl", message=reason, details={},
        )

    binance_sym = _map_symbol(symbol)
    if not PAPER_MODE:
        amt = float(pos.get("positionAmt", pos.get("volume", 0)) or 0)
        qty = abs(amt)
        qty = _format_quantity(binance_sym, qty)
        sl_side = "SELL" if side == "BUY" else "BUY"
        ok, replace_msg, replace_detail = _replace_protection_order_verified(
            symbol=symbol,
            binance_sym=binance_sym,
            side=sl_side,
            order_type="STOP_MARKET",
            stop_price=new_sl,
            quantity=qty,
            expected_old_types={"STOP_MARKET", "STOP"},
        )
        if not ok:
            _log_command(symbol, "update_sl", {"new_sl": new_sl}, {"success": False, **replace_detail})
            return CommandResult(
                success=False,
                command="update_sl",
                message=f"❌ {symbol} SL replacement blocked: {replace_msg}",
                details=replace_detail,
            )

    _log_command(symbol, "update_sl", {"new_sl": new_sl}, {})
    return CommandResult(
        success=True, command="update_sl",
        message=f"🛡️ {symbol} SL updated to {new_sl:.2f}",
        details={"new_sl": new_sl, "entry": entry},
    )


def cmd_update_tp(symbol: str, price: float | None = None, offset_pct: float | None = None) -> CommandResult:
    """Update take profit to absolute price or percentage offset from entry."""
    symbol = symbol.upper()
    pos = _get_position(symbol)
    if not pos:
        return CommandResult(
            success=False, command="update_tp",
            message=f"❌ No open position for {symbol}", details={},
        )

    entry = float(pos.get("openPrice", 0))
    side = pos.get("type", "BUY")

    if offset_pct is not None:
        new_tp = entry * (1 + offset_pct / 100) if side == "BUY" else entry * (1 - offset_pct / 100)
    elif price is not None:
        new_tp = price
    else:
        return CommandResult(
            success=False, command="update_tp",
            message="❌ Provide either price= or offset_pct=", details={},
        )

    new_tp = round(new_tp, 2)
    ok, reason = _validate_tp_guardrail(symbol, new_tp)
    if not ok:
        return CommandResult(
            success=False, command="update_tp", message=reason, details={},
        )

    binance_sym = _map_symbol(symbol)
    if not PAPER_MODE:
        amt = float(pos.get("positionAmt", pos.get("volume", 0)) or 0)
        qty = abs(amt)
        qty = _format_quantity(binance_sym, qty)
        tp_side = "SELL" if side == "BUY" else "BUY"
        ok, replace_msg, replace_detail = _replace_protection_order_verified(
            symbol=symbol,
            binance_sym=binance_sym,
            side=tp_side,
            order_type="TAKE_PROFIT_MARKET",
            stop_price=new_tp,
            quantity=qty,
            expected_old_types={"TAKE_PROFIT_MARKET", "TAKE_PROFIT"},
        )
        if not ok:
            _log_command(symbol, "update_tp", {"new_tp": new_tp}, {"success": False, **replace_detail})
            return CommandResult(
                success=False,
                command="update_tp",
                message=f"❌ {symbol} TP replacement blocked: {replace_msg}",
                details=replace_detail,
            )

    _log_command(symbol, "update_tp", {"new_tp": new_tp}, {})
    return CommandResult(
        success=True, command="update_tp",
        message=f"🎯 {symbol} TP updated to {new_tp:.2f}",
        details={"new_tp": new_tp, "entry": entry},
    )


def cmd_panic() -> CommandResult:
    """Emergency halt: close positions, then cancel leftovers only after flat confirmation."""
    # 1. Create HALT file — webhook will reject all new signals
    try:
        with open(HALT_FILE, "w") as f:
            f.write(f"HALTED {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        plain_log("PANIC_HALT_FILE_ERROR", {"error": str(e)})
        return CommandResult(
            success=False, command="panic",
            message=f"❌ Failed to create HALT file: {e}", details={},
        )

    closed_symbols = []
    cancelled_symbols = []
    errors = []
    if not PAPER_MODE:
        try:
            client = _get_client()
            positions = client.futures_position_information()
            for pos in positions:
                amt = float(pos.get("positionAmt", 0))
                if amt != 0:
                    sym = pos["symbol"]
                    try:
                        close_res = close_position(sym)
                        positions_after = client.futures_position_information()
                        remaining_amt = _position_amt_for_symbol(positions_after, sym)
                        if abs(remaining_amt) == 0:
                            client.futures_cancel_all_open_orders(symbol=sym)
                            closed_symbols.append(sym)
                            cancelled_symbols.append(sym)
                        else:
                            reason = (
                                f"{sym}: panic close failed; position still open "
                                f"({remaining_amt}); protective orders retained"
                            )
                            errors.append(reason)
                            plain_log("PANIC_CLOSE_NOT_FLAT_ORDERS_RETAINED", {
                                "symbol": sym,
                                "close_result": close_res,
                                "remaining_amt": remaining_amt,
                            })
                            try:
                                import telegram_client

                                telegram_client.notify_system_event(
                                    "PANIC_CLOSE_FAILED",
                                    (
                                        f"{sym} still open after panic close attempt. "
                                        "Protective orders were NOT cancelled."
                                    ),
                                )
                            except Exception as tg_error:
                                plain_log("PANIC_ALERT_ERROR", {"symbol": sym, "error": str(tg_error)})
                    except Exception as e:
                        errors.append(f"{sym}: {e}")
                        plain_log("PANIC_CLOSE_ERROR_ORDERS_RETAINED", {"symbol": sym, "error": str(e)})
        except Exception as e:
            errors.append(f"positions_fetch: {e}")
            plain_log("PANIC_POSITIONS_ERROR", {"error": str(e)})

    plain_log("PANIC_TRIGGERED", {
        "halt_file": HALT_FILE,
        "closed": closed_symbols,
        "cancelled": cancelled_symbols,
        "errors": errors,
    })
    msg = (
        "🛑 <b>PANIC TRIGGERED</b>\n"
        f"HALT file created: <code>{HALT_FILE}</code>\n"
        f"Positions confirmed closed: {', '.join(closed_symbols) or 'none'}\n"
        f"Leftover orders cancelled after flat confirmation: {', '.join(cancelled_symbols) or 'none'}\n"
        f"Errors: {len(errors)}"
    )
    return CommandResult(
        success=not errors,
        command="panic",
        message=msg,
        details={
            "closed_symbols": closed_symbols,
            "cancelled_symbols": cancelled_symbols,
            "errors": errors,
        },
    )


def cmd_pause(reason: str = "operator") -> CommandResult:
    """Create HALT file and pause trading."""
    try:
        halt_path = Path(HALT_FILE)
        halt_path.write_text(f"{reason}\n{datetime.now(UTC).isoformat()}\n")
        trade_db.log_system_event("halt", {"reason": reason}, source="telegram")
        return CommandResult(
            success=True, command="pause",
            message=f"⏸️ <b>Trading paused.</b>\nReason: {reason}",
            details={},
        )
    except Exception as e:
        plain_log("PAUSE_ERROR", {"error": str(e)})
        return CommandResult(
            success=False, command="pause",
            message=f"❌ Failed to create HALT file: {e}", details={},
        )


def cmd_resume() -> CommandResult:
    """Remove HALT file and resume trading after verifying the monitor is active."""
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "ozzybot-monitor.service"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        return CommandResult(
            success=False, command="resume",
            message="❌ Monitor service is not active. Cannot resume trading.",
            details={},
        )

    if os.path.exists(HALT_FILE):
        try:
            os.remove(HALT_FILE)
            plain_log("RESUME_TRIGGERED", {"halt_file": HALT_FILE})
        except Exception as e:
            plain_log("RESUME_ERROR", {"error": str(e)})
            return CommandResult(
                success=False, command="resume",
                message=f"❌ Failed to remove HALT file: {e}", details={},
            )

    trade_db.log_system_event("resume", {}, source="telegram")
    subprocess.run(["systemctl", "--user", "start", "ozzybot-signal.timer"], check=False)
    subprocess.run(["systemctl", "--user", "start", "ozzybot-15m-reversion.timer"], check=False)
    return CommandResult(
        success=True, command="resume",
        message="✅ <b>Trading resumed.</b>\nHALT file removed. Signal timers started.",
        details={},
    )


def cmd_regime(symbol: str, interval: str = "1h") -> CommandResult:
    """Query live trend and volatility regime for a given symbol."""
    symbol = symbol.upper()
    binance_sym = _map_symbol(symbol)

    try:
        from binance_indicators import calculate_adx, get_live_indicators

        # 1. Fetch current price
        client = _get_client()
        ticker = client.futures_symbol_ticker(symbol=binance_sym)
        price = float(ticker["price"])

        # 2. Get ADX and other indicators
        adx_value = calculate_adx(binance_sym, interval=interval)
        indicators = get_live_indicators(binance_sym, interval=interval)

        if adx_value is None or not indicators or indicators.get("atr") is None:
            return CommandResult(
                success=False, command="regime",
                message=f"❌ Failed to calculate market regime for {symbol}. Try again.",
                details={}
            )

        atr_val = indicators["atr"]
        atr_pct = (atr_val / price) * 100.0

        # 3. Determine trend regime
        # Threshold standard is 25.0
        is_trending = adx_value >= 25.0
        regime_type = "📈 <b>TRENDING</b>" if is_trending else "🔄 <b>CHOPPY / RANGE</b>"
        regime_desc = (
            "Market exhibits strong directional momentum. Winners should be allowed to run."
            if is_trending
            else "Market is range-bound or choppy. Tighten targets and take quick profits."
        )

        lines = [
            f"📊 <b>REGIME REPORT: {symbol} ({interval})</b>",
            f"Current Price: <code>${price:.2f}</code>",
            f"Market Regime: {regime_type}",
            f"Trend Strength (ADX 14): <code>{adx_value:.2f}</code>",
            f"Volatility (ATR 14): <code>{atr_val:.2f}</code> (<code>{atr_pct:.2f}%</code> of price)",
            f"\n<i>{regime_desc}</i>"
        ]

        return CommandResult(
            success=True,
            command="regime",
            message="\n".join(lines),
            details={
                "symbol": symbol,
                "interval": interval,
                "price": price,
                "adx": adx_value,
                "atr": atr_val,
                "atr_pct": atr_pct,
                "is_trending": is_trending
            }
        )

    except Exception as e:
        plain_log("REGIME_COMMAND_ERROR", {"symbol": symbol, "error": str(e)})
        return CommandResult(
            success=False, command="regime",
            message=f"❌ Error fetching regime report for {symbol}: {e}",
            details={}
        )


def cmd_purge_stale_stops() -> CommandResult:
    """Cancel orphaned reduce-only SL/TP orders when no matching exchange position exists."""
    if PAPER_MODE:
        return CommandResult(
            success=True,
            command="purge_stale_stops",
            message="ℹ️ Paper mode — no exchange stale stops to purge.",
            details={"cancelled_normal": [], "cancelled_algo": [], "errors": []},
        )

    client = _get_client()
    positions = client.futures_position_information()
    active_position_symbols = {
        p.get("symbol")
        for p in positions or []
        if abs(float(p.get("positionAmt", 0) or 0)) > 0
    }
    candidate_symbols = set(active_position_symbols)
    candidate_symbols.update(TV_TO_BINANCE.values())

    cancelled_normal = []
    cancelled_algo = []
    errors = []

    for sym in sorted(s for s in candidate_symbols if s):
        try:
            normal_orders = client.futures_get_open_orders(symbol=sym)
        except Exception as e:
            normal_orders = []
            errors.append(f"{sym} normal fetch: {e}")
            plain_log("PURGE_STALE_STOPS_NORMAL_FETCH_ERROR", {"symbol": sym, "error": str(e)})

        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=sym)
        except Exception as e:
            algo_orders = []
            errors.append(f"{sym} algo fetch: {e}")
            plain_log("PURGE_STALE_STOPS_ALGO_FETCH_ERROR", {"symbol": sym, "error": str(e)})

        if sym in active_position_symbols:
            continue

        for order in normal_orders or []:
            if not _is_reduce_only_protection(order):
                continue
            try:
                order_id = order.get("orderId")
                client.futures_cancel_order(symbol=sym, orderId=order_id)
                cancelled_normal.append({"symbol": sym, "orderId": order_id, "type": _order_type(order)})
            except Exception as e:
                errors.append(f"{sym} normal cancel {order.get('orderId')}: {e}")
                plain_log("PURGE_STALE_STOPS_NORMAL_CANCEL_ERROR", {
                    "symbol": sym,
                    "orderId": order.get("orderId"),
                    "error": str(e),
                })

        for order in algo_orders or []:
            if not _is_reduce_only_protection(order):
                continue
            try:
                algo_id = order.get("algoId")
                client.futures_cancel_algo_order(symbol=sym, algoId=algo_id)
                cancelled_algo.append({"symbol": sym, "algoId": algo_id, "type": _order_type(order)})
            except Exception as e:
                errors.append(f"{sym} algo cancel {order.get('algoId')}: {e}")
                plain_log("PURGE_STALE_STOPS_ALGO_CANCEL_ERROR", {
                    "symbol": sym,
                    "algoId": order.get("algoId"),
                    "error": str(e),
                })

    details = {
        "active_position_symbols": sorted(active_position_symbols),
        "cancelled_normal": cancelled_normal,
        "cancelled_algo": cancelled_algo,
        "errors": errors,
    }
    plain_log("PURGE_STALE_STOPS", details)
    return CommandResult(
        success=not errors,
        command="purge_stale_stops",
        message=(
            "🧹 <b>Stale stop purge complete</b>\n"
            f"Normal cancelled: {len(cancelled_normal)}\n"
            f"ALGO cancelled: {len(cancelled_algo)}\n"
            f"Errors: {len(errors)}"
        ),
        details=details,
    )


# ---------------------------------------------------------------------------
# Scratch Exit Approval Bridge Handlers
# ---------------------------------------------------------------------------

def calculate_trade_age(ts_str):
    """Parse trade start timestamp and calculate age in hours."""
    from datetime import datetime
    try:
        ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        elapsed = datetime.now() - ts_dt
        return elapsed.total_seconds() / 3600.0
    except Exception:
        return 0.0


def is_position_fresh(timeframe, age_hours):
    """Determine if a position is fresh based on its timeframe and age."""
    try:
        tf = str(timeframe).lower().strip()
        if tf in ["15", "15m"]:
            fresh_window = 1.5  # 90 minutes
        elif tf in ["60", "60m", "1h"]:
            fresh_window = 6.0  # 6 hours
        else:
            val = float(tf)
            if val <= 15:
                fresh_window = 1.5
            else:
                fresh_window = 6.0
    except Exception:
        fresh_window = 6.0
    return age_hours < fresh_window


def cmd_approve_scratch(alert_id: str) -> CommandResult:
    """Validate and execute a pending scratch exit approval request."""
    import sqlite3
    from datetime import datetime

    if not alert_id:
        return CommandResult(success=False, command="approve_scratch", message="❌ Missing ALERT_ID", details={})

    observer_dir = "/home/rick/ozzy-bot/observer"
    queue_path = os.path.join(observer_dir, "action_queue.json")
    scoreboard_path = os.path.join(observer_dir, "alert_scoreboard.json")
    decision_log_path = os.path.join(observer_dir, "decision_log.md")

    # 1. Check if alert exists in action queue
    if not os.path.exists(queue_path):
        return CommandResult(success=False, command="approve_scratch", message="❌ Queue file not found", details={"reason": "position not found"})

    try:
        with open(queue_path) as f:
            queue = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Failed to load queue: {e}", details={"reason": "exchange error"})

    alert = None
    for a in queue:
        if a.get("alert_id") == alert_id:
            alert = a
            break

    if not alert:
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Alert {alert_id} not found in queue", details={"reason": "position not found"})

    # 2. Check alert status is pending_approval
    status = alert.get("status")
    if status != "pending_approval":
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Alert status is '{status}', not pending_approval", details={"reason": "position not found"})

    # 3. Check alert not expired
    expires_at_str = alert.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                return CommandResult(success=False, command="approve_scratch", message="❌ Alert has expired", details={"reason": "expired"})
        except Exception:
            return CommandResult(success=False, command="approve_scratch", message="❌ Invalid alert expiration", details={"reason": "protection anomaly"})

    instance = alert.get("instance")
    trade_id = alert.get("trade_id")
    symbol = alert.get("symbol")
    side = alert.get("side")
    qty_to_close = float(alert.get("qty", 0))

    db_path = _command_db_path_for_instance(instance)

    # 4. Check if trade is still open in DB and get its details
    trade_exists = False
    trade_open = False
    timeframe = "1h"
    ts_start = None
    risk_dollars = 0.0
    peak_pnl = 0.0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT exit_price, timeframe, ts, risk_dollars, peak_pnl FROM trades WHERE id = ?", (trade_id,))
            row = cursor.fetchone()
            if row:
                trade_exists = True
                exit_price, timeframe, ts_start, risk_dollars, peak_pnl = row
                if exit_price is None:
                    trade_open = True
    except Exception as e:
        return CommandResult(success=False, command="approve_scratch", message=f"❌ DB read error: {e}", details={"reason": "exchange error"})

    if not trade_exists:
        return CommandResult(success=False, command="approve_scratch", message="❌ Trade not found in database", details={"reason": "ERROR_TRADE_NOT_FOUND"})

    if not trade_open:
        return CommandResult(success=False, command="approve_scratch", message="❌ Trade is already closed in database", details={"reason": "position not found"})

    # 5. Check if exchange position still matches symbol and side
    positions = get_open_positions()
    if positions is None:
        return CommandResult(success=False, command="approve_scratch", message="❌ Failed to fetch open positions from exchange", details={"reason": "exchange error"})

    pos = None
    mapped_sym = _map_symbol(symbol)
    for p in positions:
        if p.get("symbol") == mapped_sym:
            pos = p
            break

    if not pos:
        return CommandResult(success=False, command="approve_scratch", message=f"❌ No active exchange position found for {symbol}", details={"reason": "position not found"})

    # Position side matching
    pos_type = pos.get("type") # "BUY" (long) or "SELL" (short)
    if side == "LONG" and pos_type != "BUY":
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Side mismatch: Trade is LONG but exchange position is {pos_type}", details={"reason": "side mismatch"})
    if side == "SHORT" and pos_type != "SELL":
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Side mismatch: Trade is SHORT but exchange position is {pos_type}", details={"reason": "side mismatch"})

    # 6. Check Fresh Position Guard
    if ts_start:
        age_hours = calculate_trade_age(ts_start)
        if is_position_fresh(timeframe, age_hours):
            return CommandResult(success=False, command="approve_scratch", message=f"❌ Fresh Position Guard: trade is only {age_hours:.2f}h old", details={"reason": "protection anomaly"})

    # 7. Check milestone_reached
    milestone_reached = False
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM milestones WHERE trade_id = ?", (trade_id,))
            count_m = cursor.fetchone()[0]
            if count_m > 0:
                milestone_reached = True
    except Exception:
        pass
    if risk_dollars and risk_dollars > 0 and peak_pnl and peak_pnl >= risk_dollars:
        milestone_reached = True

    if milestone_reached:
        return CommandResult(success=False, command="approve_scratch", message="❌ Milestone already reached: scratch exit not allowed", details={"reason": "protection anomaly"})

    # 8. Check current PnL is still inside scratch zone or tolerance
    curr_pnl = float(pos.get("profit", 0.0))
    scratch_min = float(alert.get("scratch_zone_min", -2.50))
    scratch_max = float(alert.get("scratch_zone_max", 5.00))
    tolerance = 1.0  # Configure USD tolerance buffer
    if not ((scratch_min - tolerance) <= curr_pnl <= (scratch_max + tolerance)):
        return CommandResult(
            success=False, command="approve_scratch",
            message=f"❌ Current PnL (${curr_pnl:+.2f}) is outside scratch zone (${scratch_min:.2f} to ${scratch_max:.2f})",
            details={"reason": "no longer in scratch zone"}
        )

    # 9. Check close quantity matches actual exchange position (within 0.001 tolerance)
    exchange_qty = float(pos.get("volume", 0.0))
    if abs(qty_to_close - exchange_qty) > 0.001:
        # Refresh the alert in-place and request re-approval
        alert["qty"] = exchange_qty
        try:
            with open(queue_path, "w") as f:
                json.dump(queue, f, indent=2)
        except Exception:
            pass
        return CommandResult(
            success=False,
            command="approve_scratch",
            message=f"⚠️ Qty mismatch: Alert had {qty_to_close} but exchange position is {exchange_qty}. Alert has been refreshed to {exchange_qty}. Please re-approve.",
            details={"reason": "qty_mismatch_refreshed", "new_qty": exchange_qty}
        )

    # 10. Prevent duplicate approvals (double execution block)
    # Immediately mark as executed in memory and write to queue file before making exchange call
    alert["status"] = "executed"
    alert["resolved"] = True
    try:
        with open(queue_path, "w") as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Failed to update queue file: {e}", details={"reason": "exchange error"})

    # 11. Execution via existing trusted close path
    try:
        # Note: close_position handles Hedge Mode and reduceOnly order generation
        res = close_position(mapped_sym)
        if res.get("status") == "error":
            # Revert status if execution failed
            alert["status"] = "pending_approval"
            alert["resolved"] = False
            with open(queue_path, "w") as f:
                json.dump(queue, f, indent=2)
            return CommandResult(
                success=False, command="approve_scratch",
                message=f"❌ Exchange order error: {res.get('error')}",
                details={"reason": "exchange error"}
            )
    except Exception as e:
        # Revert status if exception occurred
        alert["status"] = "pending_approval"
        alert["resolved"] = False
        with open(queue_path, "w") as f:
            json.dump(queue, f, indent=2)
        return CommandResult(success=False, command="approve_scratch", message=f"❌ Execution exception: {e}", details={"reason": "exchange error"})

    # Post-close verification & updates
    post_positions = get_open_positions()
    post_pos = None
    if post_positions is not None:
        for p in post_positions:
            if p.get("symbol") == mapped_sym:
                post_pos = p
                break

    post_qty = float(post_pos.get("volume", 0.0)) if post_pos else 0.0
    is_reduced = post_qty < exchange_qty

    # Update SQLite trades table - log exit reason
    try:
        exit_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_price=?,
                    pnl=?,
                    exit_reason='scratch_exit_approved',
                    execution_state='closed'
                WHERE id=?
                """,
                (pos.get("currentPrice"), curr_pnl, trade_id)
            )
            # Insert into exits table for trade journal alignment
            conn.execute(
                "INSERT INTO exits (trade_id, price, qty_pct, ts, pnl_contribution, exit_type) VALUES (?, ?, ?, ?, ?, ?)",
                (trade_id, pos.get("currentPrice"), 1.0, exit_ts, curr_pnl, "scratch_exit_approved")
            )
            conn.commit()
    except Exception as dbe:
        plain_log("APPROVE_DB_UPDATE_ERROR", {"trade_id": trade_id, "error": str(dbe)})

    # Update alert scoreboard
    if os.path.exists(scoreboard_path):
        try:
            with open(scoreboard_path) as f:
                sb = json.load(f)
            sb["unresolved"] = max(0, sb.get("unresolved", 1) - 1)
            hist = sb.setdefault("alert_history", {})
            hist_item = hist.setdefault(alert_id, {})
            hist_item["resolved"] = True
            hist_item["decision"] = "SCRATCH_EXIT_APPROVED"
            hist_item["score"] = "helpful"
            hist_item["timestamp_resolved"] = datetime.now().isoformat()
            hist_item["final_pnl"] = curr_pnl
            with open(scoreboard_path, "w") as f:
                json.dump(sb, f, indent=2)
        except Exception as e:
            plain_log("APPROVE_SCOREBOARD_UPDATE_ERROR", {"error": str(e)})

    # Update decision_log.md
    if os.path.exists(decision_log_path):
        try:
            with open(decision_log_path, "a") as f:
                f.write(f"\n### [EXECUTION] APPROVED SCRATCH CLOSE | {symbol} (Trade ID: {trade_id})\n")
                f.write(f"- **Alert ID**: {alert_id}\n")
                f.write(f"- **Execution Timestamp**: {datetime.now().isoformat()}\n")
                f.write(f"- **Exit Price**: {pos.get('currentPrice')}\n")
                f.write(f"- **PnL Realized**: ${curr_pnl:+.2f}\n")
                f.write("- **Status**: Successfully executed reduce-only market close order on exchange.\n\n")
        except Exception as e:
            plain_log("APPROVE_DECISION_LOG_UPDATE_ERROR", {"error": str(e)})

    plain_log("SCRATCH_EXIT_APPROVED_SUCCESS", {"alert_id": alert_id, "trade_id": trade_id, "pnl": curr_pnl})

    return CommandResult(
        success=True,
        command="approve_scratch",
        message=(
            f"✅ <b>Scratch exit approved and executed for {symbol} (Trade #{trade_id})</b>\n"
            f"• Closed quantity: {qty_to_close} units (reduce-only)\n"
            f"• Exit price: {pos.get('currentPrice')}\n"
            f"• Final PnL: ${curr_pnl:+.2f}\n"
            f"• Scoreboard unresolved count decremented."
        ),
        details={"alert_id": alert_id, "trade_id": trade_id, "final_pnl": curr_pnl, "is_reduced": is_reduced}
    )


def cmd_reject_scratch(alert_id: str) -> CommandResult:
    """Reject a pending scratch exit request."""
    from datetime import datetime

    if not alert_id:
        return CommandResult(success=False, command="reject_scratch", message="❌ Missing ALERT_ID", details={})

    observer_dir = "/home/rick/ozzy-bot/observer"
    queue_path = os.path.join(observer_dir, "action_queue.json")
    scoreboard_path = os.path.join(observer_dir, "alert_scoreboard.json")
    decision_log_path = os.path.join(observer_dir, "decision_log.md")

    if not os.path.exists(queue_path):
        return CommandResult(success=False, command="reject_scratch", message="❌ Queue file not found", details={})

    try:
        with open(queue_path) as f:
            queue = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="reject_scratch", message=f"❌ Failed to load queue: {e}", details={})

    alert = None
    for a in queue:
        if a.get("alert_id") == alert_id:
            alert = a
            break

    if not alert:
        return CommandResult(success=False, command="reject_scratch", message=f"❌ Alert {alert_id} not found in queue", details={})

    alert["status"] = "rejected"
    alert["resolved"] = True

    try:
        with open(queue_path, "w") as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="reject_scratch", message=f"❌ Failed to update queue: {e}", details={})

    # Update scoreboard
    if os.path.exists(scoreboard_path):
        try:
            with open(scoreboard_path) as f:
                sb = json.load(f)
            sb["unresolved"] = max(0, sb.get("unresolved", 1) - 1)
            hist = sb.setdefault("alert_history", {})
            hist_item = hist.setdefault(alert_id, {})
            hist_item["resolved"] = True
            hist_item["decision"] = "REJECTED"
            with open(scoreboard_path, "w") as f:
                json.dump(sb, f, indent=2)
        except Exception as e:
            plain_log("REJECT_SCOREBOARD_UPDATE_ERROR", {"error": str(e)})

    # Update decision log
    if os.path.exists(decision_log_path):
        try:
            with open(decision_log_path, "a") as f:
                f.write(f"\n### [DECISION] REJECTED SCRATCH EXIT | {alert.get('symbol')} (Trade ID: {alert.get('trade_id')})\n")
                f.write(f"- **Alert ID**: {alert_id}\n")
                f.write(f"- **Timestamp**: {datetime.now().isoformat()}\n")
                f.write("- **Status**: Operator explicitly rejected scratch exit request. Position remains open.\n\n")
        except Exception as e:
            plain_log("REJECT_DECISION_LOG_UPDATE_ERROR", {"error": str(e)})

    return CommandResult(
        success=True,
        command="reject_scratch",
        message=f"❌ <b>Scratch exit rejected for {alert.get('symbol')} (#{alert.get('trade_id')})</b>\n• Alert marked as rejected and resolved.",
        details={"alert_id": alert_id}
    )


def cmd_watch_scratch(alert_id: str) -> CommandResult:
    """Place a pending scratch exit request on watchlist."""
    from datetime import datetime

    if not alert_id:
        return CommandResult(success=False, command="watch_scratch", message="❌ Missing ALERT_ID", details={})

    observer_dir = "/home/rick/ozzy-bot/observer"
    queue_path = os.path.join(observer_dir, "action_queue.json")
    scoreboard_path = os.path.join(observer_dir, "alert_scoreboard.json")
    decision_log_path = os.path.join(observer_dir, "decision_log.md")

    if not os.path.exists(queue_path):
        return CommandResult(success=False, command="watch_scratch", message="❌ Queue file not found", details={})

    try:
        with open(queue_path) as f:
            queue = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="watch_scratch", message=f"❌ Failed to load queue: {e}", details={})

    alert = None
    for a in queue:
        if a.get("alert_id") == alert_id:
            alert = a
            break

    if not alert:
        return CommandResult(success=False, command="watch_scratch", message=f"❌ Alert {alert_id} not found in queue", details={})

    alert["status"] = "watching"
    alert["resolved"] = True

    try:
        with open(queue_path, "w") as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="watch_scratch", message=f"❌ Failed to update queue: {e}", details={})

    # Update scoreboard
    if os.path.exists(scoreboard_path):
        try:
            with open(scoreboard_path) as f:
                sb = json.load(f)
            sb["unresolved"] = max(0, sb.get("unresolved", 1) - 1)
            hist = sb.setdefault("alert_history", {})
            hist_item = hist.setdefault(alert_id, {})
            hist_item["resolved"] = True
            hist_item["decision"] = "WATCH"
            with open(scoreboard_path, "w") as f:
                json.dump(sb, f, indent=2)
        except Exception as e:
            plain_log("WATCH_SCOREBOARD_UPDATE_ERROR", {"error": str(e)})

    # Update decision log
    if os.path.exists(decision_log_path):
        try:
            with open(decision_log_path, "a") as f:
                f.write(f"\n### [DECISION] WATCH SCRATCH EXIT | {alert.get('symbol')} (Trade ID: {alert.get('trade_id')})\n")
                f.write(f"- **Alert ID**: {alert_id}\n")
                f.write(f"- **Timestamp**: {datetime.now().isoformat()}\n")
                f.write("- **Status**: Operator placed position on watch. No immediate exit taken.\n\n")
        except Exception as e:
            plain_log("WATCH_DECISION_LOG_UPDATE_ERROR", {"error": str(e)})

    return CommandResult(
        success=True,
        command="watch_scratch",
        message=f"👀 <b>Watching scratch exit for {alert.get('symbol')} (#{alert.get('trade_id')})</b>\n• Alert marked as watching.",
        details={"alert_id": alert_id}
    )


def cmd_lm_close(candidate_id: str) -> CommandResult:
    """Validate and execute a pending ROUNDTRIP_CANDIDATE close early approval request."""
    import sqlite3
    from datetime import datetime

    if not candidate_id:
        return CommandResult(success=False, command="lm_close", message="❌ Missing candidate_id", details={})

    stale_msg = (
        "❌ <b>candidate expired/stale</b>\n"
        "• This alert is no longer active in the current candidate set.\n"
        "• Refresh observer state and use the latest candidate ID."
    )

    observer_dir = "/home/rick/ozzy-bot/observer"
    lm_path = os.path.join(observer_dir, "loss_minimization_candidates.json")
    decision_log_path = os.path.join(observer_dir, "loss_minimization_decision_log.md")

    if not os.path.exists(lm_path):
        return CommandResult(success=False, command="lm_close", message="❌ Candidate JSON file not found", details={"reason": "not_found"})

    try:
        with open(lm_path) as f:
            candidates = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="lm_close", message=f"❌ Failed to load candidates: {e}", details={"reason": "exchange_error"})

    cand = None
    for c in candidates:
        if c.get("candidate_id") == candidate_id:
            cand = c
            break

    if not cand:
        return CommandResult(success=False, command="lm_close", message=stale_msg, details={"reason": "stale_missing"})

    # Validate candidate type is ROUNDTRIP_CANDIDATE
    if cand.get("candidate_type") != "ROUNDTRIP_CANDIDATE":
        return CommandResult(
            success=False,
            command="lm_close",
            message="❌ Command only allowed for ROUNDTRIP_CANDIDATE",
            details={"reason": "invalid_type"}
        )

    # 7. Stale alert handling
    alert_time_str = cand.get("reopened_at") or cand.get("created_at")
    is_stale = False
    if alert_time_str:
        try:
            alert_time = datetime.fromisoformat(alert_time_str)
            if (datetime.now() - alert_time).total_seconds() > 900.0:
                is_stale = True
        except Exception:
            pass

    # If alert is older than 15m, and candidate is no longer valid, we do not close.
    if is_stale and cand.get("status") != "OPEN":
        return CommandResult(
            success=False,
            command="lm_close",
            message="❌ <b>candidate stale/condition cleared</b>\n• Alert is older than 15m and candidate is no longer valid.",
            details={"reason": "stale_cleared"}
        )

    # Validate candidate is OPEN
    if cand.get("status") != "OPEN":
        return CommandResult(
            success=False,
            command="lm_close",
            message=f"❌ Candidate status is '{cand.get('status')}', not OPEN",
            details={"reason": "not_open"}
        )

    instance = cand.get("instance")
    trade_id = cand.get("trade_id")
    symbol = cand.get("symbol")
    side = cand.get("side")

    db_path = _command_db_path_for_instance(instance)

    # Validate trade still open in DB
    trade_exists = False
    trade_open = False
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT exit_price FROM trades WHERE id = ?", (trade_id,))
            row = cursor.fetchone()
            if row:
                trade_exists = True
                exit_price = row[0]
                if exit_price is None:
                    trade_open = True
    except Exception as e:
        return CommandResult(success=False, command="lm_close", message=f"❌ DB read error: {e}", details={"reason": "exchange_error"})

    if not trade_exists:
        return CommandResult(success=False, command="lm_close", message="❌ Trade not found in database", details={"reason": "ERROR_TRADE_NOT_FOUND"})

    if not trade_open:
        if is_stale:
            return CommandResult(
                success=False,
                command="lm_close",
                message="❌ <b>candidate stale/condition cleared</b>\n• Alert is older than 15m and trade is already closed in database.",
                details={"reason": "stale_cleared"}
            )
        return CommandResult(success=False, command="lm_close", message="❌ Trade is already closed in database", details={"reason": "trade_closed"})

    # Validate exchange position still open
    positions = get_open_positions()
    if positions is None:
        return CommandResult(success=False, command="lm_close", message="❌ Failed to fetch open positions from exchange", details={"reason": "exchange_error"})

    pos = None
    mapped_sym = _map_symbol(symbol)
    for p in positions:
        if p.get("symbol") == mapped_sym:
            pos = p
            break

    if not pos:
        if is_stale:
            return CommandResult(
                success=False,
                command="lm_close",
                message="❌ <b>candidate stale/condition cleared</b>\n• Alert is older than 15m and exchange position is already closed.",
                details={"reason": "stale_cleared"}
            )
        return CommandResult(success=False, command="lm_close", message=f"❌ No active exchange position found for {symbol}", details={"reason": "no_position"})

    # Validate side matches
    pos_type = pos.get("type") # "BUY" (long) or "SELL" (short)
    if side == "LONG" and pos_type != "BUY":
        return CommandResult(success=False, command="lm_close", message=f"❌ Side mismatch: Trade is LONG but exchange position is {pos_type}", details={"reason": "side_mismatch"})
    if side == "SHORT" and pos_type != "SELL":
        return CommandResult(success=False, command="lm_close", message=f"❌ Side mismatch: Trade is SHORT but exchange position is {pos_type}", details={"reason": "side_mismatch"})

    # Fetch live remaining quantity directly from exchange position
    exchange_qty = float(pos.get("volume", 0.0))
    if exchange_qty <= 0:
        return CommandResult(success=False, command="lm_close", message="❌ Exchange position quantity is zero", details={"reason": "zero_qty"})

    # Prevent duplicate approvals: set in-memory and save to JSON
    cand["status"] = "APPROVED_CLOSED"
    cand["resolved_at"] = datetime.now().isoformat()
    try:
        with open(lm_path, "w") as f:
            json.dump(candidates, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="lm_close", message=f"❌ Failed to save candidate status: {e}", details={"reason": "exchange_error"})

    # Submit the close order using live remaining quantity
    try:
        res = close_position(mapped_sym, position_side=side)
        if res.get("status") == "error":
            # Revert candidate status if exchange order failed
            cand["status"] = "OPEN"
            cand.pop("resolved_at", None)
            with open(lm_path, "w") as f:
                json.dump(candidates, f, indent=2)
            return CommandResult(
                success=False,
                command="lm_close",
                message=f"❌ Exchange order error: {res.get('error')}",
                details={"reason": "exchange_error"}
            )
    except Exception as e:
        # Revert candidate status if exception occurred
        cand["status"] = "OPEN"
        cand.pop("resolved_at", None)
        with open(lm_path, "w") as f:
            json.dump(candidates, f, indent=2)
        return CommandResult(success=False, command="lm_close", message=f"❌ Execution exception: {e}", details={"reason": "exchange_error"})

    # Update SQLite trades table - log exit reason: roundtrip_early_exit_approved
    curr_pnl = float(pos.get("profit", 0.0))
    current_price = float(pos.get("currentPrice", 0.0))
    exit_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_price=?,
                    pnl=?,
                    exit_reason='roundtrip_early_exit_approved',
                    execution_state='closed'
                WHERE id=?
                """,
                (current_price, curr_pnl, trade_id)
            )
            conn.execute(
                "INSERT INTO exits (trade_id, price, qty_pct, ts, pnl_contribution, exit_type) VALUES (?, ?, ?, ?, ?, ?)",
                (trade_id, current_price, 1.0, exit_ts, curr_pnl, "roundtrip_early_exit_approved")
            )
            conn.commit()
    except Exception as dbe:
        plain_log("LM_CLOSE_DB_UPDATE_ERROR", {"trade_id": trade_id, "error": str(dbe)})

    # Log to decision_log.md
    try:
        with open(decision_log_path, "a") as f:
            f.write(f"\n### [EXECUTION] APPROVED ROUNDTRIP EARLY EXIT | {symbol} (Trade ID: {trade_id})\n")
            f.write(f"- **Candidate ID**: {candidate_id}\n")
            f.write(f"- **Execution Timestamp**: {datetime.now().isoformat()}\n")
            f.write(f"- **Exit Price**: {current_price}\n")
            f.write(f"- **PnL Realized**: ${curr_pnl:+.2f}\n")
            f.write("- **Status**: Successfully executed reduce-only market close order on exchange.\n\n")
    except Exception as e:
        plain_log("LM_CLOSE_DECISION_LOG_ERROR", {"error": str(e)})

    plain_log("LM_CLOSE_APPROVED_SUCCESS", {"candidate_id": candidate_id, "trade_id": trade_id, "pnl": curr_pnl})

    return CommandResult(
        success=True,
        command="lm_close",
        message=(
            f"✅ <b>ROUNDTRIP early exit approved and executed for {symbol} (Trade #{trade_id})</b>\n"
            f"• Closed quantity: {exchange_qty} units (reduce-only)\n"
            f"• Exit price: {current_price}\n"
            f"• Final PnL: ${curr_pnl:+.2f}\n"
            f"• Candidate ID: <code>{candidate_id}</code>\n"
            f"• Log exit reason: roundtrip_early_exit_approved"
        ),
        details={"candidate_id": candidate_id, "trade_id": trade_id, "final_pnl": curr_pnl}
    )


def cmd_lm_watch(candidate_id: str) -> CommandResult:
    """Place a loss minimization candidate on watchlist and suppress alerts for 15 minutes."""
    from datetime import datetime

    if not candidate_id:
        return CommandResult(success=False, command="lm_watch", message="❌ Missing candidate_id", details={})
    stale_msg = (
        "❌ <b>candidate expired/stale</b>\n"
        "• This alert is no longer active in the current candidate set.\n"
        "• Refresh observer state and use the latest candidate ID."
    )

    observer_dir = "/home/rick/ozzy-bot/observer"
    lm_path = os.path.join(observer_dir, "loss_minimization_candidates.json")
    if not os.path.exists(lm_path):
        return CommandResult(success=False, command="lm_watch", message="❌ Candidate JSON file not found", details={"reason": "not_found"})

    try:
        with open(lm_path) as f:
            candidates = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="lm_watch", message=f"❌ Failed to load candidates: {e}", details={"reason": "exchange_error"})

    cand = None
    for c in candidates:
        if c.get("candidate_id") == candidate_id:
            cand = c
            break

    if not cand:
        return CommandResult(success=False, command="lm_watch", message=stale_msg, details={"reason": "stale_missing"})

    cand["status"] = "WATCHED"
    cand["watched_at"] = datetime.now().isoformat()

    try:
        with open(lm_path, "w") as f:
            json.dump(candidates, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="lm_watch", message=f"❌ Failed to update candidate: {e}", details={"reason": "exchange_error"})

    return CommandResult(
        success=True,
        command="lm_watch",
        message=(
            f"👁️ <b>Candidate marked WATCHED</b>\n"
            f"• Candidate ID: <code>{candidate_id}</code>\n"
            f"• Repeat alerts suppressed for 15 minutes."
        ),
        details={"candidate_id": candidate_id}
    )


def cmd_lm_reject(candidate_id: str) -> CommandResult:
    """Reject a loss minimization candidate and suppress future alerts unless severity worsens."""
    from datetime import datetime

    if not candidate_id:
        return CommandResult(success=False, command="lm_reject", message="❌ Missing candidate_id", details={})
    stale_msg = (
        "❌ <b>candidate expired/stale</b>\n"
        "• This alert is no longer active in the current candidate set.\n"
        "• Refresh observer state and use the latest candidate ID."
    )

    observer_dir = "/home/rick/ozzy-bot/observer"
    lm_path = os.path.join(observer_dir, "loss_minimization_candidates.json")
    if not os.path.exists(lm_path):
        return CommandResult(success=False, command="lm_reject", message="❌ Candidate JSON file not found", details={"reason": "not_found"})

    try:
        with open(lm_path) as f:
            candidates = json.load(f)
    except Exception as e:
        return CommandResult(success=False, command="lm_reject", message=f"❌ Failed to load candidates: {e}", details={"reason": "exchange_error"})

    cand = None
    for c in candidates:
        if c.get("candidate_id") == candidate_id:
            cand = c
            break

    if not cand:
        return CommandResult(success=False, command="lm_reject", message=stale_msg, details={"reason": "stale_missing"})

    cand["status"] = "REJECTED"
    cand["rejected_at"] = datetime.now().isoformat()
    cand["rejected_current_r"] = cand.get("current_r")
    cand["rejected_current_pnl"] = cand.get("current_pnl")
    cand["rejected_recommendation"] = cand.get("recommendation")

    try:
        with open(lm_path, "w") as f:
            json.dump(candidates, f, indent=2)
    except Exception as e:
        return CommandResult(success=False, command="lm_reject", message=f"❌ Failed to update candidate: {e}", details={"reason": "exchange_error"})

    return CommandResult(
        success=True,
        command="lm_reject",
        message=(
            f"❌ <b>Candidate marked REJECTED</b>\n"
            f"• Candidate ID: <code>{candidate_id}</code>\n"
            f"• Alerts suppressed unless severity worsens."
        ),
        details={"candidate_id": candidate_id}
    )


def cmd_adopt_orphan(symbol: str, side: str, qty: float, entry_price: float, trade_id: int | None = None) -> CommandResult:
    """Adopt an orphan position by creating a new DB trade or relinking an existing closed one."""
    import sqlite3

    if not symbol or not side or not qty:
        return CommandResult(success=False, command="adopt_orphan", message="❌ Missing required parameters: symbol, side, qty", details={})

    side = side.upper()
    if side not in ("LONG", "SHORT"):
        return CommandResult(success=False, command="adopt_orphan", message=f"❌ Invalid side '{side}', must be LONG or SHORT", details={})

    mapped_sym = _map_symbol(symbol)
    pos_type = "BUY" if side == "LONG" else "SELL"

    # 1. Fetch current open positions from exchange to validate orphan existence
    positions = get_open_positions()
    if positions is None:
        return CommandResult(success=False, command="adopt_orphan", message="❌ Failed to fetch open positions from exchange", details={})

    pos = None
    for p in positions:
        if p.get("symbol") == mapped_sym:
            pos = p
            break

    if not pos:
        return CommandResult(success=False, command="adopt_orphan", message=f"❌ No active exchange position found for {symbol}", details={})

    # Side matching
    exch_pos_type = pos.get("type") # "BUY" or "SELL"
    if exch_pos_type != pos_type:
        return CommandResult(
            success=False, command="adopt_orphan",
            message=f"❌ Side mismatch: Operator wants to adopt {side} but exchange position is {exch_pos_type}",
            details={"exchange_side": exch_pos_type}
        )

    # Qty matching (within tolerance)
    exch_qty = float(pos.get("volume", 0.0))
    if abs(exch_qty - qty) > 0.01:
        return CommandResult(
            success=False, command="adopt_orphan",
            message=f"❌ Quantity mismatch: Operator specifies {qty} but exchange position is {exch_qty}",
            details={"exchange_qty": exch_qty}
        )

    # 2. Check that no DB open trade already exists for this symbol and side
    db_path = trade_db.DB_PATH

    try:
        open_trades = trade_db.get_open_trades(symbol)
        for ot in open_trades:
            if ot["direction"] == pos_type:
                return CommandResult(
                    success=False, command="adopt_orphan",
                    message=f"❌ Symbol {symbol} already has an active open trade #{ot['id']} in the database",
                    details={"existing_trade_id": ot["id"]}
                )
    except Exception as e:
        return CommandResult(success=False, command="adopt_orphan", message=f"❌ DB read error: {e}", details={})

    # 3. Perform adoption/relinking
    adopted_trade_id = None
    if trade_id:
        # Relink mode
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT symbol, direction FROM trades WHERE id = ?", (trade_id,))
                row = cursor.fetchone()
                if not row:
                    return CommandResult(
                        success=False, command="adopt_orphan",
                        message=f"❌ Candidate trade #{trade_id} not found in database",
                        details={"trade_id": trade_id}
                    )
                if row["symbol"] != symbol or row["direction"] != pos_type:
                    return CommandResult(
                        success=False, command="adopt_orphan",
                        message=f"❌ Candidate trade #{trade_id} symbol/direction mismatch. Candidate: {row['symbol']} {row['direction']}, Orphan: {symbol} {pos_type}",
                        details={}
                    )

                # Relink by clearing closed columns and setting state
                conn.execute(
                    """
                    UPDATE trades
                    SET exit_price = NULL,
                        pnl = NULL,
                        exit_reason = NULL,
                        source = 'orphan_adopted',
                        execution_state = 'protection_verified'
                    WHERE id = ?
                    """,
                    (trade_id,)
                )
                conn.commit()
                adopted_trade_id = trade_id
        except Exception as e:
            return CommandResult(success=False, command="adopt_orphan", message=f"❌ DB write error: {e}", details={})
    else:
        # Create brand new trade
        try:
            adopted_trade_id = trade_db.log_trade(
                signal_id=None,
                symbol=symbol,
                direction=pos_type,
                entry_price=entry_price,
                qty=qty,
                sl=None,
                tp=None,
                rr=2.0,
                regime="trend",
                strategy="reversal",
                timeframe="1h",
                mode="live" if not PAPER_MODE else "paper",
                setup_grade="A",
                risk_dollars=0.0,
                reward_dollars=0.0,
                atr=0.0,
                volume_ratio=1.0,
                context={},
                execution_state="protection_verified"
            )
            # Update source to 'orphan_adopted'
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE trades SET source = 'orphan_adopted' WHERE id = ?", (adopted_trade_id,))
                conn.commit()
        except Exception as e:
            return CommandResult(success=False, command="adopt_orphan", message=f"❌ DB log_trade error: {e}", details={})

    # Clear matching key from local cache
    orphan_path = "/home/rick/ozzy-bot/observer/orphan_positions.json"
    if os.path.exists(orphan_path):
        try:
            with open(orphan_path) as f:
                orphans = json.load(f)
            remaining_orphans = [o for o in orphans if not (o["symbol"] == symbol and o["side"] == side)]
            with open(orphan_path, "w") as f:
                json.dump(remaining_orphans, f, indent=2)
        except Exception:
            pass

    plain_log("ORPHAN_ADOPTED", {"trade_id": adopted_trade_id, "symbol": symbol, "side": side, "qty": qty})

    return CommandResult(
        success=True,
        command="adopt_orphan",
        message=f"✅ <b>Orphan position adopted successfully</b>\n• Trade ID: #{adopted_trade_id}\n• Symbol: {symbol}\n• Side: {side}\n• Source set to 'orphan_adopted'\n• State set to 'protection_verified'",
        details={"trade_id": adopted_trade_id, "symbol": symbol, "side": side}
    )


def cmd_close_orphan(symbol: str, side: str, qty: float) -> CommandResult:
    """Close an orphan position on exchange after validation."""
    if not symbol or not side or not qty:
        return CommandResult(success=False, command="close_orphan", message="❌ Missing required parameters: symbol, side, qty", details={})

    side = side.upper()
    if side not in ("LONG", "SHORT"):
        return CommandResult(success=False, command="close_orphan", message=f"❌ Invalid side '{side}', must be LONG or SHORT", details={})

    mapped_sym = _map_symbol(symbol)
    pos_type = "BUY" if side == "LONG" else "SELL"

    # 1. Fetch current open positions from exchange to validate orphan existence
    positions = get_open_positions()
    if positions is None:
        return CommandResult(success=False, command="close_orphan", message="❌ Failed to fetch open positions from exchange", details={})

    pos = None
    for p in positions:
        if p.get("symbol") == mapped_sym:
            pos = p
            break

    if not pos:
        return CommandResult(success=False, command="close_orphan", message=f"❌ No active exchange position found for {symbol}", details={})

    # Side matching
    exch_pos_type = pos.get("type") # "BUY" or "SELL"
    if exch_pos_type != pos_type:
        return CommandResult(
            success=False, command="close_orphan",
            message=f"❌ Side mismatch: Operator wants to close {side} but exchange position is {exch_pos_type}",
            details={"exchange_side": exch_pos_type}
        )

    # Qty matching
    exch_qty = float(pos.get("volume", 0.0))
    if abs(exch_qty - qty) > 0.01:
        return CommandResult(
            success=False, command="close_orphan",
            message=f"❌ Quantity mismatch: Operator specifies {qty} but exchange position is {exch_qty}",
            details={"exchange_qty": exch_qty}
        )

    # 2. Execute reduce-only market close on exchange
    try:
        res = close_position(mapped_sym)
        if res.get("status") == "error":
            return CommandResult(
                success=False, command="close_orphan",
                message=f"❌ Exchange order error: {res.get('error')}",
                details={"reason": "exchange error"}
            )
    except Exception as e:
        return CommandResult(success=False, command="close_orphan", message=f"❌ Close execution exception: {e}", details={})

    # Clear matching key from local cache
    orphan_path = "/home/rick/ozzy-bot/observer/orphan_positions.json"
    if os.path.exists(orphan_path):
        try:
            with open(orphan_path) as f:
                orphans = json.load(f)
            remaining_orphans = [o for o in orphans if not (o["symbol"] == symbol and o["side"] == side)]
            with open(orphan_path, "w") as f:
                json.dump(remaining_orphans, f, indent=2)
        except Exception:
            pass

    plain_log("ORPHAN_CLOSED", {"symbol": symbol, "side": side, "qty": qty})

    return CommandResult(
        success=True,
        command="close_orphan",
        message=f"✅ <b>Orphan position closed successfully</b>\n• Symbol: {symbol}\n• Side: {side}\n• Qty: {qty} units closed (reduce-only)",
        details={"symbol": symbol, "side": side, "qty": qty}
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def execute(command_type: str, **kwargs) -> CommandResult:
    """Main entry point — routes to the correct command handler."""
    try:
        cmd = CommandType(command_type.lower())
    except ValueError:
        return CommandResult(
            success=False, command=command_type,
            message=f"❌ Unknown command: {command_type}",
            details={"available": [c.value for c in CommandType]},
        )

    plain_log("COMMAND_RECEIVED", {"type": command_type, "params": kwargs})

    if cmd == CommandType.STATUS:
        return cmd_status()
    elif cmd == CommandType.STATUS_DEEP:
        return cmd_status_deep()
    elif cmd == CommandType.CLOSE:
        return cmd_close(kwargs.get("symbol"), kwargs.get("pct"))
    elif cmd == CommandType.PARTIAL_CLOSE:
        return cmd_close(kwargs.get("symbol"), kwargs.get("pct", 50))
    elif cmd == CommandType.BREAKEVEN:
        return cmd_breakeven(kwargs.get("symbol"))
    elif cmd == CommandType.TRAIL:
        return cmd_trail(
            kwargs.get("symbol"), kwargs.get("mode", "atr"),
            kwargs.get("param", 1.5), kwargs.get("trigger_r", 1.0)
        )
    elif cmd == CommandType.UPDATE_SL:
        return cmd_update_sl(
            kwargs.get("symbol"), kwargs.get("price"), kwargs.get("offset_pct")
        )
    elif cmd == CommandType.UPDATE_TP:
        return cmd_update_tp(
            kwargs.get("symbol"), kwargs.get("price"), kwargs.get("offset_pct")
        )
    elif cmd == CommandType.PANIC:
        return cmd_panic()
    elif cmd == CommandType.RESUME:
        return cmd_resume()
    elif cmd == CommandType.REGIME:
        return cmd_regime(kwargs.get("symbol"), kwargs.get("interval", "1h"))
    elif cmd == CommandType.PURGE_STALE_STOPS:
        return cmd_purge_stale_stops()
    elif cmd == CommandType.APPROVE_SCRATCH:
        return cmd_approve_scratch(kwargs.get("alert_id"))
    elif cmd == CommandType.REJECT_SCRATCH:
        return cmd_reject_scratch(kwargs.get("alert_id"))
    elif cmd == CommandType.WATCH_SCRATCH:
        return cmd_watch_scratch(kwargs.get("alert_id"))
    elif cmd == CommandType.LM_CLOSE:
        return cmd_lm_close(kwargs.get("candidate_id"))
    elif cmd == CommandType.LM_WATCH:
        return cmd_lm_watch(kwargs.get("candidate_id"))
    elif cmd == CommandType.LM_REJECT:
        return cmd_lm_reject(kwargs.get("candidate_id"))
    elif cmd == CommandType.COOLDOWNS:
        return cmd_cooldowns()
    elif cmd == CommandType.ADOPT_ORPHAN:
        return cmd_adopt_orphan(
            kwargs.get("symbol"), kwargs.get("side"), kwargs.get("qty"),
            kwargs.get("entry_price"), kwargs.get("trade_id")
        )
    elif cmd == CommandType.CLOSE_ORPHAN:
        return cmd_close_orphan(
            kwargs.get("symbol"), kwargs.get("side"), kwargs.get("qty")
        )
    elif cmd == CommandType.SET_MODE:
        # For future use: set position management mode (conservative/aggressive)
        return CommandResult(
            success=True, command="set_mode",
            message="Mode setting not yet implemented", details={},
        )

    return CommandResult(
        success=False, command=command_type,
        message="Command handler missing", details={},
    )
