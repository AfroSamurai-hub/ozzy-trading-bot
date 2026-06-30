# ============================================
# HERMES — Telegram notification client
# ============================================
import logging
import os
import re
import sqlite3

import requests

from config import BINANCE_TESTNET, MAX_LOT_SIZE, MIN_BALANCE_USD, PAPER_MODE, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

_API_BASE = "https://api.telegram.org"
_TIMEOUT  = 5

logger = logging.getLogger(__name__)


def _env_badge() -> str:
    """Return a short, unmistakable runtime label for Telegram cards."""
    name = os.getenv("HERMES_INSTANCE_NAME")
    if name:
        label = name.strip().upper()
    elif PAPER_MODE:
        label = "PAPER"
    elif BINANCE_TESTNET:
        label = "TESTNET"
    else:
        label = "LIVE"
    icon = "🔴" if label.startswith("LIVE") else "🔵" if label == "TESTNET" else "⚪"
    return f"{icon} <b>{label}</b>"


def _esc(val) -> str:
    """Escape < and > to prevent Telegram HTML entity parsing errors."""
    if val is None:
        return ""
    return str(val).replace("<", "&lt;").replace(">", "&gt;")


def _safe_error_text(exc: Exception | str) -> str:
    """Redact Telegram bot tokens from logs."""
    text = str(exc)
    if TELEGRAM_TOKEN:
        text = text.replace(TELEGRAM_TOKEN, "<redacted-telegram-token>")
    return re.sub(r"/bot[^/\s]+", "/bot<redacted>", text)


def _card(title: str, *lines: str, level: str = "info") -> str:
    """Build compact Telegram HTML cards with a consistent environment badge."""
    icons = {
        "ok": "🟢",
        "trade": "📲",
        "warn": "⚠️",
        "bad": "🛑",
        "info": "📊",
        "money": "💎",
    }
    body = "\n".join(line for line in lines if line)
    header = f"{_env_badge()} {icons.get(level, 'ℹ️')} <b>{title}</b>"
    separator = "\n<code>───────────────────────────</code>"
    return f"{header}{separator}\n{body}" if body else header


def _ensure_env_badge(text: str) -> str:
    """Prefix legacy/raw Telegram messages with the runtime environment badge."""
    if text.startswith(("🔴 <b>", "🔵 <b>", "⚪ <b>")):
        return text
    return f"{_env_badge()}\n{text}"


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"${float(value):,.2f}"


def _fmt_price(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.4f}".rstrip("0").rstrip(".")


def _fmt_timeframe(timeframe: str | int | None) -> str:
    raw = str(timeframe or "").strip().lower()
    if raw in {"15", "15m"}:
        return "15m"
    if raw in {"60", "1h", "h1"}:
        return "1h"
    return raw or "n/a"


def _loss_min_candidate_db_path(instance: str) -> str | None:
    if instance == "STANDARD_TESTNET":
        return "/home/rick/ozzy-bot/trades.db"
    if instance == "LIVE_MICRO":
        return "/home/rick/ozzy-bot/live_micro/trades_live.db"
    return None


def _loss_min_candidate_trade_is_open(instance: str, trade_id) -> bool:
    try:
        trade_id_int = int(trade_id)
    except (TypeError, ValueError):
        return False
    if trade_id_int <= 0:
        return False
    db_path = _loss_min_candidate_db_path(instance)
    if not db_path or not os.path.exists(db_path):
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT exit_price FROM trades WHERE id = ?", (trade_id_int,)).fetchone()
        return bool(row) and row[0] is None
    except Exception:
        return False


def _normalize_giveback_pct(value) -> float | None:
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= val <= 1.0:
        return val * 100.0
    return val


def send_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text = _ensure_env_badge(text)
    try:
        resp = requests.post(
            f"{_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id":    TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "HTML",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Telegram rejected message: %s %s", resp.status_code, _safe_error_text(resp.text))
    except Exception as e:
        logger.warning("Telegram send failed: %s", _safe_error_text(e))


def notify_setup_forming(symbol: str, signal: str, mins_to_close: int,
                         timeframe: str, threshold: float):
    side = "above" if signal == "BUY" else "below"
    threshold_display = round(float(threshold), 2)
    text = _card(
        "SETUP FORMING",
        f"<b>{symbol}</b> {signal} | {timeframe}",
        f"Close in {mins_to_close}m | {side} <code>{threshold_display}</code>",
        level="warn",
    )
    send_message(text)


def notify_approved(signal: str, symbol: str, entry: float,
                    sl: float, tp: float, lot: float,
                    risk_dollars: float, rr: float, atr: float,
                    paper: bool, note: str = "",
                    setup_grade: str | None = None,
                    timeframe: str | int | None = None,
                    strategy: str | None = None,
                    setup_version: str | None = None):
    atr_line = f"ATR: {round(atr, 4)}" if atr else "fallback"
    grade_str = f"<b>Grade {setup_grade}</b>" if setup_grade else "N/A"
    meta = " | ".join(
        part
        for part in (
            f"TF <b>{_fmt_timeframe(timeframe)}</b>" if timeframe else "",
            f"<code>{_esc(strategy)}</code>" if strategy else "",
            f"<code>{_esc(setup_version)}</code>" if setup_version else "",
        )
        if part
    )
    
    text = _card(
        "TRADE APPROVED",
        f"📈 <b>{signal} {symbol}</b> | {grade_str}",
        meta,
        f"🔹 <b>Entry:</b> <code>{_fmt_price(entry)}</code>",
        f"🎯 <b>Target TP:</b> <code>{_fmt_price(tp)}</code> (R:R 1:{rr:.2f})",
        f"🛡️ <b>Stop Loss:</b> <code>{_fmt_price(sl)}</code> ({atr_line})",
        f"💎 <b>Risk Cap:</b> <code>{_fmt_money(risk_dollars)}</code>",
        f"📦 <b>Order Qty:</b> <code>{lot}</code>",
        f"<i>{_esc(note)}</i>" if note else "",
        level="trade",
    )
    send_message(text)


def notify_rejected(reason: str, symbol: str, signal: str):
    text = _card(
        "SIGNAL REJECTED",
        f"📡 <b>{signal} {symbol}</b>",
        f"❌ <b>Reason:</b> <i>{_esc(reason)}</i>",
        level="bad",
    )
    send_message(text)


def notify_breakeven(symbol: str, position_id: str, entry: float, paper: bool):
    text = _card(
        "BREAKEVEN",
        f"<b>{symbol}</b> #{position_id}",
        f"SL moved to <code>{_fmt_price(entry)}</code>",
        level="ok",
    )
    send_message(text)


def notify_drawdown_halt(limit_pct: float):
    text = _card(
        "TRADING HALTED",
        f"Daily drawdown hit: <code>-{limit_pct}%</code>",
        "No new trades today.",
        level="bad",
    )
    send_message(text)


def notify_daily_risk_halt(reason: str):
    text = _card(
        "TRADING HALTED",
        _esc(reason),
        "No new trades until risk state is available.",
        level="bad",
    )
    send_message(text)


def notify_live_bootstrap_daily_stop(reason: str):
    text = _card(
        "LIVE BOOTSTRAP STOP",
        "No new LIVE MICRO entries today.",
        _esc(reason),
        level="bad",
    )
    send_message(text)


def notify_live_bootstrap_warning(warning: str):
    text = _card(
        "HIGH-RISK BOOTSTRAP",
        _esc(warning),
        "Target risk is loss at SL before exchange slippage and failure modes.",
        level="warn",
    )
    send_message(text)


def notify_trade_error(signal: str, symbol: str, error: str):
    text = _card(
        "EXECUTION ERROR",
        f"<b>{signal} {symbol}</b>",
        _esc(error),
        level="bad",
    )
    send_message(text)


def notify_entry_protection_verifying(signal: str, symbol: str, open_price: float, order_id: str | None):
    """Tell operators an entry exists before protection truth is settled."""
    order_line = f"Order <code>{order_id}</code>" if order_id else "Order id unavailable"
    text = _card(
        "ENTRY FILLED — PROTECTION VERIFYING",
        f"<b>{signal} {symbol}</b>",
        f"Open <code>{_fmt_price(open_price)}</code>",
        order_line,
        level="warn",
    )
    send_message(text)


def notify_execution_fail_closed(signal: str, symbol: str, reason: str):
    """Report an entry that was fail-closed before confirmation."""
    text = _card(
        "EXECUTION FAIL-CLOSED",
        f"<b>{signal} {symbol}</b>",
        _esc(reason),
        level="bad",
    )
    send_message(text)


def notify_execution_timeout_reconciled_flat(signal: str, symbol: str, reason: str):
    """Report a Binance timeout that was verified flat with no exposure."""
    text = _card(
        "EXECUTION TIMEOUT — RECONCILED FLAT",
        f"<b>{signal} {symbol}</b>",
        _esc(reason),
        "No position or protection orders found after reconciliation.",
        level="warn",
    )
    send_message(text)


def notify_testnet_protection_shadow_warning(signal: str, symbol: str, reason: str):
    """Report how LIVE protection finalization would react without closing testnet."""
    text = _card(
        "TESTNET SHADOW WARNING",
        f"<b>{signal} {symbol}</b>",
        _esc(reason),
        "TESTNET trade kept open.",
        level="warn",
    )
    send_message(text)


def notify_confirmed_with_protection_warning(
    signal: str,
    symbol: str,
    open_price: float,
    sl: float,
    tp: float | None,
):
    """Confirm only the SL truth when TP remains under warning."""
    tp_text = _fmt_price(tp) if tp is not None else "missing"
    text = _card(
        "CONFIRMED WITH WARNING",
        f"<b>{signal} {symbol}</b>",
        f"Open <code>{_fmt_price(open_price)}</code>",
        f"SL verified <code>{_fmt_price(sl)}</code> | TP <code>{tp_text}</code>",
        "TP missing or repair attempted.",
        level="warn",
    )
    send_message(text)


def notify_protection_confirmed(signal: str, symbol: str, open_price: float, sl: float, tp: float):
    """Confirm a filled entry only after protection truth passed."""
    if sl is None:
        notify_entry_protection_verifying(signal, symbol, open_price, None)
        return
    text = _card(
        "TRADE CONFIRMED",
        f"<b>{signal} {symbol}</b>",
        f"Open <code>{_fmt_price(open_price)}</code>",
        f"SL <code>{_fmt_price(sl)}</code> | TP <code>{_fmt_price(tp)}</code>",
        level="ok",
    )
    send_message(text)


def notify_trade_reconciled(symbol: str, signal: str, position_id: str,
                            open_price: float, sl: float | None, tp: float | None):
    if sl is None:
        notify_entry_protection_verifying(signal, symbol, open_price, position_id)
        return
    sl_text = _fmt_price(sl)
    tp_text = _fmt_price(tp) if tp is not None else "warning"
    text = _card(
        "TRADE CONFIRMED",
        f"<b>{signal} {symbol}</b> #{position_id}",
        f"Open <code>{_fmt_price(open_price)}</code>",
        f"SL <code>{sl_text}</code> | TP <code>{tp_text}</code>",
        level="ok",
    )
    send_message(text)


def notify_trade_unverified(symbol: str, signal: str, order_id: str | None):
    order_line = f"\nOrder: <code>{order_id}</code>" if order_id else ""
    text = _card(
        "TRADE UNVERIFIED",
        f"<b>{signal} {symbol}</b>{order_line}",
        "Position not confirmed after order.",
        level="warn",
    )
    send_message(text)


def notify_manual_exit_warning(symbol: str, position_id: str, reason: str, detail: str = ""):
    detail_line = f"\n{_esc(detail)}" if detail else ""
    text = _card(
        "MANUAL EXIT WARNING",
        f"<b>{symbol}</b> #{position_id}",
        f"{_esc(reason)}{detail_line}",
        level="warn",
    )
    send_message(text)


def notify_auto_exit_warning(symbol: str, position_id: str, trigger: str, exit_at: str):
    text = _card(
        "AUTO EXIT WARNING",
        f"<b>{symbol}</b> #{position_id}",
        f"{_esc(trigger)} | exit at <code>{exit_at}</code>",
        level="warn",
    )
    send_message(text)


def notify_auto_exit_closed(symbol: str, position_id: str, trigger: str):
    text = _card(
        "AUTO EXIT CLOSED",
        f"<b>{symbol}</b> #{position_id}",
        _esc(trigger),
        level="ok",
    )
    send_message(text)


def notify_auto_exit_error(symbol: str, position_id: str, trigger: str, error: str):
    text = _card(
        "AUTO EXIT ERROR",
        f"<b>{symbol}</b> #{position_id}",
        f"{_esc(trigger)}: {_esc(error)}",
        level="bad",
    )
    send_message(text)


def notify_startup(account_id: str, currency: str,
                   balance: float, equity: float, paper: bool):
    account = f"{account_id[:8]}...{account_id[-4:]}" if len(account_id) > 12 else account_id
    text = _card(
        "STARTED",
        f"Account <code>{account}</code>",
        f"Balance <code>{currency} {balance:,.2f}</code> | Equity <code>{currency} {equity:,.2f}</code>",
        f"Max lot <code>{MAX_LOT_SIZE}</code> | Min balance <code>${MIN_BALANCE_USD}</code>",
        level="ok",
    )
    send_message(text)


def notify_startup_error(reason: str):
    text = _card(
        "STARTUP WARNING",
        "Could not verify account.",
        _esc(reason),
        level="warn",
    )
    send_message(text)


def notify_daily_pnl_report(
    open_positions: int,
    equity: float | None,
    drawdown_pct: float | None,
    trades_today: int,
    paper_mode: bool,
):
    """08:00 SAST snapshot: positions, equity, day drawdown, trades placed today."""
    eq_txt = f"${equity:,.2f}" if equity is not None else "N/A"
    dd_txt = f"{drawdown_pct:+.2f}%" if drawdown_pct is not None else "N/A"
    text = _card(
        "DAILY REPORT",
        f"Equity <code>{eq_txt}</code> | DD <code>{dd_txt}</code>",
        f"Open <code>{open_positions}</code> | Trades today <code>{trades_today}</code>",
        level="info",
    )
    send_message(text)


def notify_gate_passed(gate_num: int, gate_name: str, symbol: str):
    text = _card(
        f"GATE {gate_num}/15 PASSED",
        f"🚪 <b>{symbol}</b> — {gate_name}",
        level="ok",
    )
    send_message(text)


def notify_gate_rejected(gate_num: int, gate_name: str, symbol: str, reason: str):
    text = _card(
        f"GATE {gate_num}/15 REJECTED",
        f"🚪 <b>{symbol}</b> — {gate_name}",
        f"❌ <b>Reason:</b> {reason}",
        level="bad",
    )
    send_message(text)


def notify_all_gates_passed(
    symbol: str,
    signal: str,
    entry: float,
    sl: float,
    tp: float,
    risk_dollars: float,
    setup_grade: str | None = None,
    timeframe: str | int | None = None,
    strategy: str | None = None,
    setup_version: str | None = None,
):
    grade_line = f"Grade: <b>{setup_grade}</b> | " if setup_grade else ""
    meta = " | ".join(
        part
        for part in (
            f"TF <b>{_fmt_timeframe(timeframe)}</b>" if timeframe else "",
            f"<code>{_esc(strategy)}</code>" if strategy else "",
            f"<code>{_esc(setup_version)}</code>" if setup_version else "",
        )
        if part
    )
    text = _card(
        "GATES PASSED",
        f"<b>{signal} {symbol}</b>" + (f" | {grade_line}" if grade_line else ""),
        meta,
        f"🔹 <b>Entry:</b> <code>{_fmt_price(entry)}</code>",
        f"🎯 <b>Target TP:</b> <code>{_fmt_price(tp)}</code>",
        f"🛡️ <b>Stop Loss:</b> <code>{_fmt_price(sl)}</code>",
        f"💎 <b>Risk Cap:</b> <code>{_fmt_money(risk_dollars)}</code>",
        "⚡ <i>Executing trade...</i>",
        level="ok",
    )
    send_message(text)


def notify_signal_check(symbol: str, status: str, reason: str, indicators: dict | None = None):
    """Status: 'fire', 'skip', 'error'"""
    emoji_map = {"fire": "📡", "skip": "📡", "error": "❌"}
    status_emoji = {"fire": "🟢", "skip": "⚪", "error": "🚨"}
    em = emoji_map.get(status, "📡")
    se = status_emoji.get(status, "⚪")

    ind_lines = ""
    if indicators:
        ind_lines = (
            f"\n🔹 <b>EMA200:</b> <code>{indicators.get('ema200', '?')}</code>"
            f"\n🔹 <b>SuperTrend:</b> <code>{indicators.get('supertrend_direction', '?')}</code>"
            f"\n🔹 <b>RSI:</b> <code>{indicators.get('rsi', '?')}</code>"
            f"\n🔹 <b>Volume Ratio:</b> <code>{indicators.get('volume_ratio', '?')}x</code>"
        )

    text = _card(
        f"SIGNAL CHECK: {symbol}",
        f"{se} <b>{status.upper()}:</b> {reason}",
        ind_lines if ind_lines else "",
        level="ok" if status == "fire" else "bad" if status == "error" else "info"
    )
    send_message(text)


def notify_milestone(trade_id: int, milestone: str, symbol: str, price: float, pnl: float):
    level = "money" if "tp" in milestone.lower() or pnl > 0 else "info"
    text = _card(
        f"MILESTONE: {milestone}",
        f"<b>{symbol}</b> #{trade_id}",
        f"🔹 <b>Price:</b> <code>{_fmt_price(price)}</code>",
        f"💰 <b>PnL:</b> <code>{_fmt_money(pnl)}</code>",
        level=level,
    )
    send_message(text)


def notify_proximity_alert(symbols_data: list):
    """Send combined proximity alert for symbols close to firing.

    symbols_data: list of dicts with keys:
        symbol, direction, close, ema200, ema_pct, st_dir, rsi,
        rsi_needed, volume_ratio, vol_needed, gates_away, blocking_gate
    """
    if not symbols_data:
        return
    
    lines = []
    
    for d in symbols_data:
        rsi_emoji = "🟢" if d.get("rsi_ok") else "🔶"
        vol_emoji = "🟢" if d.get("vol_ok") else "🔶"
        st_emoji = "🟢" if d.get("st_ok") else "🔶"
        ema_emoji = "🟢" if d.get("ema_ok") else "🔶"

        rsi_line = f"RSI: {d['rsi']:.1f}"
        if not d.get("rsi_ok"):
            rsi_line += f" (needs {d['rsi_needed']:+.1f})"

        vol_line = f"Volume: {d['volume_ratio']:.2f}x"
        if not d.get("vol_ok"):
            vol_line += f" (needs {d['vol_needed']:+.2f}x)"

        ema_side = "below" if d["direction"] == "long" else "above"
        ema_line = (
            f"EMA200: ${d['ema200']:.2f} "
            f"({abs(d['ema_pct']):.1f}% {ema_side})"
        )

        st_line = f"SuperTrend: {d['st_dir']}"
        blocking = d['blocking_gate'].replace("<", "&lt;").replace(">", "&gt;")
        
        gate_word = "gate" if d['gates_away'] == 1 else "gates"

        lines.append(
            f"🔑 <b>{d['symbol']}</b> → {d['direction'].upper()}\n"
            f"⚡ <i>{d['gates_away']} {gate_word} away — {blocking}</i>\n"
            f"  {rsi_emoji} {rsi_line}\n"
            f"  {vol_emoji} {vol_line}\n"
            f"  {ema_emoji} {ema_line}\n"
            f"  {st_emoji} {st_line}"
        )
    
    # We will construct a card since the parent card has a neat separator
    text = _card("NEAR SIGNAL ALIGNMENT", "\n\n".join(lines), level="warn")
    send_message(text)


def notify_hour_summary(summary: list, timestamp: str):
    """Send hour summary after signal generator completes all checks.

    summary: list of dicts with keys:
        symbol, status, reasons, close, ema200, st, rsi, vr
    """
    lines = []
    
    closest_symbol = None
    closest_gates = 999
    closest_reason = ""
    any_fired = False

    for row in summary:
        sym = row["symbol"]
        status = row.get("status", "SKIP")
        
        if status == "FIRE":
            any_fired = True
            reason_str = f"🟢 {row.get('signal', 'BUY')} sent to webhook"
            if row.get("timeframe"):
                reason_str += f" | {_fmt_timeframe(row.get('timeframe'))}"
            if row.get("strategy"):
                reason_str += f" | {row.get('strategy')}"
            if row.get("grade"):
                reason_str += f" | Grade {row.get('grade')}"
            status_indicator = "🟢 <b>SENT</b>"
        else:
            reasons = row.get("reasons", [])
            reason_str = "; ".join(reasons) if reasons else "no setup"
            # Escape < and > to avoid Telegram HTML parse errors
            reason_str = reason_str.replace("<", "&lt;").replace(">", "&gt;")
            status_indicator = "⚪ <b>SKIP</b>"
            
        lines.append(f"• <b>{sym}</b>: {status_indicator}\n  <code>└─ {reason_str}</code>")

        # Track closest symbol (fewest blocking gates)
        gates_away = row.get("gates_away", 999)
        if gates_away < closest_gates:
            closest_gates = gates_away
            closest_symbol = sym
            closest_reason = reason_str

    # Assessment line
    if any_fired:
        assessment = "🟢 <b>Signal sent — wait for webhook approval/confirmation</b>"
    elif closest_symbol and closest_gates <= 2:
        gate_word = "gate" if closest_gates == 1 else "gates"
        assessment = f"🟡 <b>{closest_symbol} closest ({closest_gates} {gate_word} away)</b>\n  <code>└─ {closest_reason}</code>"
    else:
        assessment = "🔴 <b>No setups close — market is quiet</b>"
        
    body = "\n".join(lines) + f"\n\n<b>Assessment:</b>\n{assessment}"
    text = _card(f"HOUR SCAN SUMMARY ({timestamp})", body, level="info")
    send_message(text)


def notify_heartbeat(equity: float, positions: int, symbols_watching: list[str], uptime_str: str, position_detail: str = ""):
    """Legacy heartbeat — kept for monitor compatibility but frequency reduced."""
    pos_line = f"Positions: {positions}"
    if position_detail:
        pos_line = f"Positions: {position_detail}"
    
    text = _card(
        "HEARTBEAT",
        f"💰 <b>Equity:</b> <code>${equity:,.2f}</code>",
        f"💼 <b>{pos_line}</b>",
        f"🔭 <b>Watching:</b> <code>{', '.join(symbols_watching)}</code>",
        f"⏱️ <b>Uptime:</b> <code>{uptime_str}</code>",
        level="info",
    )
    send_message(text)


def notify_trail_update(
    symbol: str,
    side: str,
    new_sl: float,
    current_pnl: float,
    stop_locked_pnl: float,
    peak_pnl: float,
):
    text = _card(
        "TRAIL UPDATE",
        f"<b>{symbol} {side}</b>",
        f"🛡️ <b>New Stop Loss:</b> <code>{_fmt_price(new_sl)}</code>",
        f"💰 <b>Current PnL:</b> <code>{_fmt_money(current_pnl)}</code>",
        f"🔒 <b>Stop-Locked PnL est.:</b> <code>{_fmt_money(stop_locked_pnl)}</code>",
        f"📈 <b>Peak PnL:</b> <code>{_fmt_money(peak_pnl)}</code>",
        level="trade",
    )
    send_message(text)


def notify_tp_hit(symbol: str, side: str, profit: float, duration: str):
    text = _card(
        "TAKE PROFIT HIT",
        f"🏆 <b>{symbol} {side}</b>",
        f"💰 <b>Net Profit:</b> <code>{_fmt_money(profit)}</code>",
        f"⏱️ <b>Duration:</b> <code>{duration}</code>",
        level="money",
    )
    send_message(text)


def notify_sl_hit(symbol: str, side: str, loss: float, duration: str):
    text = _card(
        "STOP LOSS HIT",
        f"🛑 <b>{symbol} {side}</b>",
        f"💸 <b>Net Loss:</b> <code>{_fmt_money(loss)}</code>",
        f"⏱️ <b>Duration:</b> <code>{duration}</code>",
        level="bad",
    )
    send_message(text)


def notify_trail_stopped(symbol: str, side: str, profit: float, peak_pnl: float):
    text = _card(
        "TRAILING STOP HIT",
        f"🎯 <b>{symbol} {side}</b>",
        f"💰 <b>Final profit:</b> <code>{_fmt_money(profit)}</code>",
        f"📈 <b>Peak PnL:</b> <code>{_fmt_money(peak_pnl)}</code>",
        level="money",
    )
    send_message(text)


def notify_system_event(event: str, detail: str = ""):
    """event: 'started', 'stopped', 'restarted', 'error'"""
    levels = {
        "started": "ok",
        "stopped": "bad",
        "restarted": "warn",
        "error": "bad",
        "warning": "warn",
    }
    text = _card(
        f"SYSTEM {event.upper()}",
        detail,
        level=levels.get(event, "info"),
    )
    send_message(text)


def notify_shadow(reason: str, symbol: str, signal: str, setup_grade: str | None = None):
    grade_str = f" | Grade {setup_grade}" if setup_grade else ""
    text = _card(
        "SHADOW SETUP DETECTED",
        f"⚪ <b>{signal} {symbol}</b>{grade_str}",
        f"📝 <b>Detail:</b> <i>{_esc(reason)}</i>",
        f"ℹ️ <i>Shadow-mode only — no orders submitted.</i>",
        level="info",
    )
    send_message(text)


def notify_shadow_exit(symbol: str, direction: str, entry: float, exit_price: float, net_pnl: float, exit_reason: str, setup_grade: str | None = None):
    pnl_str = f"{net_pnl:+.2f}"
    pnl_cap = f"${pnl_str}" if net_pnl >= 0 else f"-${abs(net_pnl):.2f}"
    
    emoji = "🟢 <b>SHADOW TP HIT</b>" if exit_reason == "tp" else "🔴 <b>SHADOW SL HIT</b>"
    level = "money" if exit_reason == "tp" else "bad"
    
    text = _card(
        "SHADOW TRADE CLOSED",
        f"{emoji} | <b>{symbol} {direction}</b>",
        f"🔹 <b>Entry:</b> <code>{_fmt_price(entry)}</code>",
        f"🔸 <b>Exit:</b> <code>{_fmt_price(exit_price)}</code>",
        f"💰 <b>Net PnL:</b> <code>{pnl_cap}</code> (fees & spread deducted)",
        f"Grade: <b>{setup_grade or 'C'}</b>",
        level=level,
    )
    send_message(text)


def notify_loss_minimization_candidate(candidate: dict):
    """Send Telegram alert for loss minimization candidate.
    Only ROUNDTRIP_CANDIDATE receives inline keyboard buttons.
    Other candidates are observe-only/advisory and do not get buttons.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    dry_run_test_alert = os.environ.get("DRY_RUN_TEST_ALERT", "").strip().lower() == "true"

    # Suppress notifications for seeded/demo candidates unless DRY_RUN_TEST_ALERT=true
    trade_id = candidate.get("trade_id")
    trade_id_str = str(trade_id or "")
    is_seeded_demo = (
        trade_id == 99999 
        or trade_id == 999999 
        or trade_id_str.startswith("999")
    )
    if is_seeded_demo and not dry_run_test_alert:
        logger.info(f"[TELEGRAM] Suppressed alert for seeded/demo loss-min candidate: {candidate.get('candidate_id')}")
        return

    instance = candidate.get("instance", "N/A")
    if not dry_run_test_alert and not _loss_min_candidate_trade_is_open(instance, trade_id):
        logger.info(
            "[TELEGRAM] Suppressed loss-min candidate with stale/non-open DB trade: %s",
            candidate.get("candidate_id"),
        )
        return

    # Extract fields
    instance = candidate.get("instance", "N/A")
    symbol = candidate.get("symbol", "N/A")
    side = candidate.get("side", "N/A")
    trade_id = candidate.get("trade_id", "N/A")
    grade = candidate.get("grade", "N/A")
    entry_price = candidate.get("entry_price")
    current_price = candidate.get("current_price")
    current_pnl = candidate.get("current_pnl")
    peak_pnl = candidate.get("peak_pnl")
    current_r = candidate.get("current_r")
    peak_r = candidate.get("peak_r")
    giveback_pct = _normalize_giveback_pct(candidate.get("giveback_pct"))
    age_minutes = candidate.get("age_minutes")
    recommendation = candidate.get("recommendation", "N/A")
    reason = candidate.get("reason", "N/A")
    cand_type = candidate.get("candidate_type", "N/A")
    cand_id = candidate.get("candidate_id", "N/A")

    # Update reason wording
    reason = reason.replace("OBSERVE ONLY — no auto-exit", "APPROVAL REQUIRED — no auto-exit unless Close Early is approved.")

    # Format values
    fmt_entry = _fmt_price(entry_price)
    fmt_current = _fmt_price(current_price)
    fmt_curr_pnl = _fmt_money(current_pnl)
    fmt_peak_pnl = _fmt_money(peak_pnl)
    fmt_curr_r = f"{current_r:.3f}R" if current_r is not None else "N/A"
    fmt_peak_r = f"{peak_r:.3f}R" if peak_r is not None else "N/A"
    fmt_giveback = f"{giveback_pct:.1f}%" if giveback_pct is not None else "N/A"
    fmt_age = f"{age_minutes:.1f}m" if age_minutes is not None else "N/A"

    # Derive dynamic header from instance type
    if instance == "STANDARD_TESTNET":
        header_text = "🔵 <b>TESTNET Loss Minimization Alert</b>"
    elif instance == "LIVE_MICRO":
        header_text = "🔴 <b>LIVE MICRO Loss Minimization Alert</b>"
    else:
        header_text = f"⚪ <b>{instance} Loss Minimization Alert</b>"

    lines = [
        f"• <b>Instance:</b> {instance}",
        f"• <b>Symbol:</b> <b>{symbol}</b>",
        f"• <b>Side:</b> {side}",
        f"• <b>Trade ID:</b> #{trade_id}",
        f"• <b>Grade:</b> {grade}",
        f"• <b>Entry Price:</b> <code>{fmt_entry}</code>",
        f"• <b>Current Price:</b> <code>{fmt_current}</code>",
        f"• <b>Current PnL:</b> <code>{fmt_curr_pnl}</code>",
        f"• <b>Peak PnL:</b> <code>{fmt_peak_pnl}</code>",
        f"• <b>Current R:</b> <code>{fmt_curr_r}</code>",
        f"• <b>Peak R:</b> <code>{fmt_peak_r}</code>",
        f"• <b>Giveback:</b> <code>{fmt_giveback}</code>",
        f"• <b>Age:</b> <code>{fmt_age}</code>",
        f"• <b>Recommendation:</b> <code>{_esc(recommendation)}</code>",
        f"• <b>Reason:</b> <i>{_esc(reason)}</i>",
        f"• <b>Candidate ID:</b> <code>{_esc(cand_id)}</code>",
        f"• <b>Status:</b> <code>{_esc(candidate.get('status', 'N/A'))}</code>",
        f"• <b>Created At:</b> <code>{_esc(candidate.get('created_at', 'N/A'))}</code>",
        f"• <b>Last Seen At:</b> <code>{_esc(candidate.get('last_seen_at', 'N/A'))}</code>",
    ]

    body = "\n".join(lines)
    separator = "\n<code>───────────────────────────</code>"
    text = f"{header_text}{separator}\n{body}"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    # Only ROUNDTRIP_CANDIDATE gets inline buttons!
    if cand_type == "ROUNDTRIP_CANDIDATE":
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "🛑 CLOSE EARLY", "callback_data": f"/lm_close {cand_id}"},
                    {"text": "👁️ WATCH", "callback_data": f"/lm_watch {cand_id}"},
                    {"text": "❌ REJECT", "callback_data": f"/lm_reject {cand_id}"}
                ]
            ]
        }

    try:
        resp = requests.post(
            f"{_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Telegram rejected LM message: %s %s", resp.status_code, _safe_error_text(resp.text))
    except Exception as e:
        logger.warning("Telegram LM send failed: %s", _safe_error_text(e))


def send_telegram_message(message: str):
    send_message(message)
