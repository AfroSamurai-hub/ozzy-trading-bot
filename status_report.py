#!/usr/bin/env python3
"""
Hermes Visual Status Reporter
Prints a color-coded market status table for all tracked symbols.
Also shows equity, open positions, last trade, and bot uptime.

Usage:
    python status_report.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/rick/ozzy-bot")

from binance_indicators import get_live_indicators
from binance_connector import get_balance, get_open_positions
from logger import plain_log
import config

# ── ANSI Colors ─────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"

# v2026-06-17 — Pull symbol universe from config so the report stays truthful.
SYMBOLS = config.TESTNET_SYMBOLS
TIMEFRAME = "1h"  # status report uses 1h for responsiveness; OpenClaw uses config.TIMEFRAME
TRADES_DB = "/home/rick/ozzy-bot/trades.db"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "c5cbc69a59bff9f5c2630cca677400f5")


def color(val: str, color_code: str) -> str:
    return f"{color_code}{val}{C_RESET}"


def get_bot_uptime() -> str:
    """Estimate webhook uptime from systemd."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", "ozzybot-webhook.service", "--property=ActiveEnterTimestamp", "--timestamp=unix"],
            text=True,
        )
        for line in out.strip().splitlines():
            if line.startswith("ActiveEnterTimestamp="):
                ts_str = line.split("=", 1)[1]
                if ts_str and ts_str.startswith("@"):
                    epoch = int(ts_str[1:])
                    now = int(datetime.now(timezone.utc).timestamp())
                    delta = max(0, now - epoch)
                    hours, rem = divmod(delta, 3600)
                    mins, secs = divmod(rem, 60)
                    return f"{hours}h {mins}m {secs}s"
    except Exception:
        pass
    return "unknown"


def get_last_trade() -> dict | None:
    """Fetch the most recent trade from SQLite."""
    try:
        conn = sqlite3.connect(TRADES_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM trades ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        plain_log("STATUS_REPORT_DB_ERROR", {"error": str(e)})
    return None


def evaluate_conditions(symbol: str, live: dict) -> dict:
    """Evaluate entry conditions. Returns dict with signal info."""
    close = live.get("close")
    ema200 = live.get("ema200")
    st_dir = live.get("supertrend_direction")
    rsi = live.get("rsi")
    volume = live.get("volume", 0.0)
    vol_avg20 = live.get("volume_avg20", 0.0)
    vol_ratio = volume / vol_avg20 if vol_avg20 else 0.0

    result = {
        "symbol": symbol,
        "close": close,
        "ema200": ema200,
        "st_dir": st_dir,
        "st_value": live.get("supertrend_value"),
        "rsi": rsi,
        "vol_ratio": vol_ratio,
        "signal": None,
        "status": "WAIT",
        "reasons": [],
    }

    if any(v is None for v in (close, ema200, st_dir, rsi)):
        result["reasons"].append("missing data")
        return result

    # LONG conditions
    long_ok = (
        close > ema200
        and st_dir == "long"
        and 30 < rsi < 70
        and vol_ratio >= 1.2
    )
    # SHORT conditions
    short_ok = (
        close < ema200
        and st_dir == "short"
        and 30 < rsi < 70
        and vol_ratio >= 1.2
    )

    if long_ok and short_ok:
        result["reasons"].append("ambiguous")
        return result

    if long_ok:
        result["signal"] = "BUY"
        result["status"] = "READY"
    elif short_ok:
        result["signal"] = "SELL"
        result["status"] = "READY"
    else:
        if close > ema200 and st_dir != "long":
            result["reasons"].append("ST conflict")
        elif close < ema200 and st_dir != "short":
            result["reasons"].append("ST conflict")
        else:
            if close <= ema200 and st_dir == "long":
                result["reasons"].append("price < EMA200")
            if close >= ema200 and st_dir == "short":
                result["reasons"].append("price > EMA200")
        if rsi is not None and (rsi <= 30 or rsi >= 70):
            result["reasons"].append(f"RSI {rsi:.1f} extreme")
        if vol_ratio < 1.2:
            result["reasons"].append(f"vol {vol_ratio:.2f}x")

    return result


def format_row(r: dict) -> dict:
    """Format values with color codes for display."""
    sym = r["symbol"].replace("USDT", "")
    close = r["close"]
    ema200 = r["ema200"]
    st_dir = r["st_dir"]
    st_val = r["st_value"]
    rsi = r["rsi"]
    vr = r["vol_ratio"]
    signal = r["signal"]
    status = r["status"]
    reasons = r["reasons"]

    # Value color coding
    close_str = f"{close:,.2f}" if close else "-"
    ema_str = f"{ema200:,.2f}" if ema200 else "-"
    st_str = f"{st_dir} ({st_val:.2f})" if st_dir and st_val else "-"
    rsi_str = f"{rsi:.1f}" if rsi else "-"
    vr_str = f"{vr:.2f}x"

    if rsi and (rsi > 70 or rsi < 30):
        rsi_str = color(rsi_str, C_RED)
    if vr < 0.5:
        vr_str = color(vr_str, C_RED)
    elif vr < 1.2:
        vr_str = color(vr_str, C_YELLOW)
    else:
        vr_str = color(vr_str, C_GREEN)

    # Signal / Status
    if status == "READY":
        sig_str = color(signal, C_GREEN)
        stat_str = color("✅ READY", C_GREEN)
    elif status == "WAIT":
        sig_str = color("NONE", C_DIM)
        reason_txt = reasons[0] if reasons else "waiting"
        stat_str = color(f"⏳ {reason_txt}", C_YELLOW)
    else:
        sig_str = "-"
        stat_str = color("⚠️ " + "; ".join(reasons), C_RED)

    return {
        "symbol": sym,
        "price": close_str,
        "ema200": ema_str,
        "st": st_str,
        "rsi": rsi_str,
        "vr": vr_str,
        "signal": sig_str,
        "status": stat_str,
    }


def print_header(title: str):
    print(f"\n{C_BOLD}{C_BLUE}{'='*70}{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}  {title}{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}{'='*70}{C_RESET}\n")


def main():
    print_header("HERMES BOT STATUS REPORT")

    # ── Market Table ────────────────────────────────────────────────
    rows = []
    for symbol in SYMBOLS:
        live = get_live_indicators(symbol, TIMEFRAME)
        if not live:
            rows.append({
                "symbol": symbol.replace("USDT", ""),
                "price": color("ERROR", C_RED),
                "ema200": "-",
                "st": "-",
                "rsi": "-",
                "vr": "-",
                "signal": "-",
                "status": color("❌ fetch failed", C_RED),
            })
            continue
        result = evaluate_conditions(symbol, live)
        rows.append(format_row(result))

    # Print table
    hdr = f"{'Sym':<6} {'Price':>12} {'EMA200':>12} {'SuperTrend':>16} {'RSI':>6} {'Vol':>7} {'Signal':>6} {'Status'}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['symbol']:<6} {r['price']:>12} {r['ema200']:>12} "
            f"{r['st']:>16} {r['rsi']:>6} {r['vr']:>7} {r['signal']:>6}  {r['status']}"
        )

    # ── Equity & Positions ──────────────────────────────────────────
    print_header("ACCOUNT SNAPSHOT")
    bal = get_balance()
    positions = get_open_positions()

    eq = bal.get("equity", 0)
    avail = bal.get("available", 0)
    curr = bal.get("currency", "USDT")

    print(f"  Equity:    {color(f'{eq:,.2f} {curr}', C_BOLD)}")
    print(f"  Available: {avail:,.2f} {curr}")
    print(f"  Positions: {len(positions)} open")

    if positions:
        print(f"\n  {'Symbol':<10} {'Side':<6} {'Entry':>12} {'Mark':>12} {'PnL':>14}")
        print("  " + "-" * 60)
        for p in positions:
            pnl = p.get("profit", 0)
            pnl_color = C_GREEN if pnl >= 0 else C_RED
            print(
                f"  {p.get('symbol','?'):<10} {p.get('type','?'):<6} "
                f"{p.get('openPrice',0):>12.2f} {p.get('currentPrice',0):>12.2f} "
                f"{color(f'{pnl:+.2f}', pnl_color):>14}"
            )

    # ── Last Trade ──────────────────────────────────────────────────
    print_header("LAST TRADE")
    last = get_last_trade()
    if last:
        ts = last.get("ts", "?")
        pnl = last.get("pnl")
        pnl_str = f"{pnl:+.2f}" if pnl is not None else "?"
        pnl_color = C_GREEN if pnl and pnl >= 0 else C_RED
        print(f"  Symbol:     {last.get('symbol', '?')}")
        print(f"  Direction:  {last.get('direction', '?')}")
        print(f"  Entry:      {last.get('entry_price', '?'):.2f}")
        print(f"  Exit:       {last.get('exit_price', '?'):.2f}" if last.get("exit_price") else "  Exit:       (still open)")
        print(f"  PnL:        {color(pnl_str, pnl_color)}")
        print(f"  Exit reason:{last.get('exit_reason', 'N/A')}")
        print(f"  Time:       {ts}")
    else:
        print("  No trades found in database.")

    # ── Bot Health ──────────────────────────────────────────────────
    print_header("BOT HEALTH")
    uptime = get_bot_uptime()
    print(f"  Webhook uptime: {uptime}")
    print(f"  Data source:    Binance native (no TAAPI dependency)")
    print(f"  Testnet symbols:{len(config.TESTNET_SYMBOLS)} — {', '.join(config.TESTNET_SYMBOLS)}")
    print(f"  Live-micro symb:{len(config.LIVE_MICRO_SYMBOLS)} — {', '.join(config.LIVE_MICRO_SYMBOLS)}")
    print(f"  Shadow-only:    {', '.join(config.SHADOW_ONLY_SYMBOLS)}")
    print(f"  Timeframe:      {TIMEFRAME}")
    print(f"  Report time:    {datetime.now(timezone.utc).isoformat()}")
    print(f"\n{C_DIM}Tip: Run `python signal_generator.py --dry-run` to preview signals.{C_RESET}")
    print()


if __name__ == "__main__":
    main()
