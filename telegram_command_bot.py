#!/usr/bin/env python3
# ============================================
# TELEGRAM COMMAND BOT — Jarvis Interface
# ============================================
# Lightweight polling bot using requests (no extra deps).
# Parses natural-language-ish commands and routes to command_center.
#
# Usage in Telegram:
#   /status
#   /close BTCUSDT
#   /close BTCUSDT 50%
#   /breakeven ETHUSDT
#   /trail BTCUSDT atr 1.5
#   /sl BTCUSDT 94000
#   /tp BTCUSDT +10%
#   /scale BTCUSDT 2%
#
# Also accepts natural language (Hermes AI can generate these):
#   "Close half my BTC position"
#   "Move ETH stop to breakeven"
#   "Trail BTC at 1.5x ATR"

import time
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from logger import plain_log
from command_center import execute, CommandType

_API_BASE = "https://api.telegram.org"
_TIMEOUT = 5
_POLL_INTERVAL = 2  # seconds between getUpdates polls
_MAX_POLL_BACKOFF = 60

# Track processed updates by ID
_last_update_id = 0


def _safe_error_text(error: object) -> str:
    """Return an error string with Telegram bot credentials redacted."""
    text = str(error)
    if TELEGRAM_TOKEN:
        text = text.replace(TELEGRAM_TOKEN, "<redacted>")
    return re.sub(r"/bot[^/\s]+", "/bot<redacted>", text)


# ---------------------------------------------------------------------------
# Command parsers
# ---------------------------------------------------------------------------

def _send_reply(chat_id: int, text: str, parse_mode: str = "HTML"):
    """Send a reply message."""
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"{_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=_TIMEOUT,
        )
    except Exception as e:
        plain_log("TELEGRAM_CMD_ERROR", {"error": _safe_error_text(e)})


def parse_command(text: str) -> tuple[str, dict]:
    """
    Parse a command string into (command_type, kwargs).
    Supports both /slash commands and natural language.
    """
    text = text.strip()
    text = re.sub(r"^/([a-z_]+)@[a-z0-9_]+", r"/\1", text, flags=re.I)
    lower = text.lower()

    if lower in {"/help", "help", "commands"}:
        return "help", {}

    if lower in {"/cooldowns", "cooldowns", "active cooldowns", "loss cooldowns"}:
        return "cooldowns", {}

    scratch_match = re.fullmatch(r"/(approve_scratch|reject_scratch|watch_scratch)\s+(\S+)", text, re.I)
    if scratch_match:
        return scratch_match.group(1).lower(), {"alert_id": scratch_match.group(2)}

    # ── /status ──
    if lower == "/status" or lower in ("status", "positions", "open trades"):
        return "status", {}

    # ── /regime <symbol> [interval] ──
    m = re.match(r"/regime\s+(\w+)(?:\s+(\w+))?", text, re.I)
    if m:
        sym = m.group(1).upper()
        interval = m.group(2) or "1h"
        return "regime", {"symbol": sym, "interval": interval}

    if "regime" in lower or "market condition" in lower or "adx" in lower:
        sym = _extract_symbol(text)
        if sym:
            interval = "1h"
            m_int = re.search(r"\b(15m|1h|4h|5m|1d)\b", lower)
            if m_int:
                interval = m_int.group(1)
            return "regime", {"symbol": sym, "interval": interval}

    # ── /purge_stale_stops ──
    if lower in {"/purge_stale_stops", "/purge-stale-stops", "/purge stale stops", "purge stale stops"}:
        return "purge_stale_stops", {}

    # ── /close <symbol> [pct%] ──
    m = re.match(r"/close\s+(\w+)\s*(\d+%?)?", text, re.I)
    if m:
        sym = m.group(1).upper()
        pct_str = m.group(2) or ""
        pct = float(pct_str.replace("%", "")) if pct_str else None
        return "close", {"symbol": sym, "pct": pct}

    # Natural language: "close half my BTC position"
    if any(w in lower for w in ("close", "exit", "kill")):
        sym = _extract_symbol(text)
        pct = _extract_percentage(text)
        if sym:
            return "close", {"symbol": sym, "pct": pct}

    # ── /breakeven <symbol> ──
    m = re.match(r"/breakeven\s+(\w+)", text, re.I)
    if m:
        return "breakeven", {"symbol": m.group(1).upper()}

    if "breakeven" in lower or "move sl to entry" in lower:
        sym = _extract_symbol(text)
        if sym:
            return "breakeven", {"symbol": sym}

    # ── /trail <symbol> <mode> <param> ──
    m = re.match(r"/trail\s+(\w+)\s+(atr|percent|fixed)\s+([\d.]+)", text, re.I)
    if m:
        return "trail", {
            "symbol": m.group(1).upper(),
            "mode": m.group(2).lower(),
            "param": float(m.group(3)),
        }

    if "trail" in lower:
        sym = _extract_symbol(text)
        if sym:
            # Default to ATR trailing if not specified
            param = _extract_number_after(text, "atr") or _extract_number_after(text, "at") or 1.5
            return "trail", {"symbol": sym, "mode": "atr", "param": param}

    # ── /sl <symbol> <price|+pct%|-pct%> ──
    m = re.match(r"/sl\s+(\w+)\s+([+-]?[\d.]+%?)", text, re.I)
    if m:
        sym = m.group(1).upper()
        val = m.group(2)
        if "%" in val:
            return "update_sl", {"symbol": sym, "offset_pct": float(val.replace("%", ""))}
        return "update_sl", {"symbol": sym, "price": float(val)}

    if any(w in lower for w in ("stop loss", "sl ", "move sl")):
        sym = _extract_symbol(text)
        if sym:
            price = _extract_price(text)
            if price:
                return "update_sl", {"symbol": sym, "price": price}

    # ── /tp <symbol> <price|+pct%|-pct%> ──
    m = re.match(r"/tp\s+(\w+)\s+([+-]?[\d.]+%?)", text, re.I)
    if m:
        sym = m.group(1).upper()
        val = m.group(2)
        if "%" in val:
            return "update_tp", {"symbol": sym, "offset_pct": float(val.replace("%", ""))}
        return "update_tp", {"symbol": sym, "price": float(val)}

    # ── /panic ──
    if lower == "/panic" or lower in ("panic", "halt", "stop trading", "emergency stop"):
        return "panic", {}

    # ── /resume ──
    if lower == "/resume" or lower in ("resume", "start trading"):
        return "resume", {}

    if any(w in lower for w in ("take profit", "tp ", "move tp")):
        sym = _extract_symbol(text)
        if sym:
            price = _extract_price(text)
            if price:
                return "update_tp", {"symbol": sym, "price": price}

    return "", {}


def _extract_symbol(text: str) -> str | None:
    """Try to find a trading symbol in natural language."""
    # Look for common crypto symbols
    patterns = [
        r"\b(BTCUSDT|BTCUSD|ETHUSDT|ETHUSD|SOLUSDT|SOLUSD|XRPUSDT|XRPUSD|XAUUSD|EURUSD|GBPUSD|USDJPY)\b",
        r"\b(BTC|ETH|SOL|XRP|XAU|GOLD)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            sym = m.group(1).upper()
            # Expand short forms
            if sym == "BTC":
                return "BTCUSDT"
            if sym == "ETH":
                return "ETHUSDT"
            if sym == "SOL":
                return "SOLUSDT"
            if sym == "XRP":
                return "XRPUSDT"
            if sym == "XAU" or sym == "GOLD":
                return "XAUUSD"
            return sym
    return None


def _extract_percentage(text: str) -> float | None:
    """Extract a percentage like '50%' or 'half'."""
    m = re.search(r"(\d+)%", text)
    if m:
        return float(m.group(1))
    if "half" in text.lower():
        return 50.0
    if "quarter" in text.lower():
        return 25.0
    if "third" in text.lower():
        return 33.0
    return None


def _extract_price(text: str) -> float | None:
    """Extract a price value."""
    m = re.search(r"[\$\s]([\d,]+\.?\d*)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _extract_number_after(text: str, keyword: str) -> float | None:
    """Extract number after a keyword."""
    pat = rf"{keyword}\s+([\d.]+)"
    m = re.search(pat, text, re.I)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def _process_update(update: dict):
    """Handle a single Telegram update."""
    global _last_update_id
    update_id = update.get("update_id", 0)
    _last_update_id = max(_last_update_id, update_id)

    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    if not text:
        return

    # Security: only respond to authorized chat
    if str(chat_id) != str(TELEGRAM_CHAT_ID):
        plain_log("TELEGRAM_CMD_UNAUTHORIZED", {"chat_id": chat_id, "text": text})
        return

    plain_log("TELEGRAM_CMD_RECEIVED", {"chat_id": chat_id, "text": text})

    cmd_type, kwargs = parse_command(text)
    if not cmd_type:
        _send_reply(
            chat_id,
            "🤖 <b>Jarvis didn't understand.</b>\n\n"
            "Try:\n"
            "• <code>/status</code> — Show positions\n"
            "• <code>/close BTCUSDT</code> — Close full position\n"
            "• <code>/close BTCUSDT 50%</code> — Close half\n"
            "• <code>/breakeven BTCUSDT</code> — Move SL to entry\n"
            "• <code>/trail BTCUSDT atr 1.5</code> — Activate trailing stop\n"
            "• <code>/sl BTCUSDT 94000</code> — Update stop loss\n"
            "• <code>/tp BTCUSDT +10%</code> — Update take profit\n"
            "• <code>/regime BTCUSDT [1h]</code> — Show market trend/volatility\n"
            "• <code>/panic</code> — Emergency halt + cancel all orders\n"
            "• <code>/resume</code> — Resume trading\n\n"
            "Or say: <i>\"Close half my BTC position\"</i>"
        )
        return

    if cmd_type == "help":
        _send_reply(
            chat_id,
            "🤖 <b>OzzyBot commands</b>\n"
            "<code>/status</code>, <code>/cooldowns</code>, <code>/close SYMBOL [PCT%]</code>, "
            "<code>/breakeven SYMBOL</code>, <code>/trail SYMBOL atr 1.5</code>, "
            "<code>/regime SYMBOL 1h</code>, <code>/panic</code>, <code>/resume</code>",
        )
        return

    # Execute
    result = execute(cmd_type, **kwargs)
    _send_reply(chat_id, result.message)


def _bootstrap_update_id() -> None:
    """Fetch the latest update_id from Telegram and reset the poll offset.

    This prevents 409 Conflict loops when the bot token was previously polled
    by another process (or a crashed instance). Offset=-1 returns only the
    most recent update so we can start clean without reprocessing history.
    """
    global _last_update_id
    if not TELEGRAM_TOKEN:
        return
    try:
        resp = requests.get(
            f"{_API_BASE}/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"offset": -1, "limit": 1},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok") and data.get("result"):
            _last_update_id = int(data["result"][-1].get("update_id", 0))
            plain_log("TELEGRAM_CMD_BOOTSTRAP", {"last_update_id": _last_update_id})
    except Exception as e:
        plain_log("TELEGRAM_CMD_BOOTSTRAP_ERROR", {"error": _safe_error_text(e)})


def run():
    """Start the polling loop."""
    global _last_update_id
    _bootstrap_update_id()
    plain_log("TELEGRAM_CMD_BOT_START", {"status": "polling", "last_update_id": _last_update_id})
    backoff_seconds = _POLL_INTERVAL

    while True:
        try:
            resp = requests.get(
                f"{_API_BASE}/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": _last_update_id + 1, "limit": 10},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                backoff_seconds = _POLL_INTERVAL
                for upd in data.get("result", []):
                    try:
                        _process_update(upd)
                    except Exception as e:
                        plain_log("TELEGRAM_CMD_PROCESS_ERROR", {"error": _safe_error_text(e)})
            else:
                raise RuntimeError(f"Telegram getUpdates failed: {data.get('description', 'unknown response')}")
        except Exception as e:
            plain_log(
                "TELEGRAM_CMD_POLL_ERROR",
                {"error": _safe_error_text(e), "retry_in_seconds": backoff_seconds},
            )
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, _MAX_POLL_BACKOFF)
            continue

        time.sleep(_POLL_INTERVAL)


if __name__ == "__main__":
    run()
