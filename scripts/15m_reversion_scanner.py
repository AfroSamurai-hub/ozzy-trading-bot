#!/usr/bin/env python3
"""
OzzyBot 15-Minute Mean Reversion Volatility Extremes Scanner
Evaluates configured Binance symbols against Bollinger-RSI mean-reversion gates.
Natively calculates indicators on the last closed 15m candle and POSTs
exchange-ready SL/TP payloads to the configured webhook.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

# Set up paths to allow clean imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from local_indicators import get_live_indicators_dict
from logger import plain_log
from config import get_mean_reversion_live_lanes, get_symbol_strategy_profile
from lane_labels import MEAN_REVERSION_15M, webhook_port_from_url
import telegram_client

# -- Config ----------------------------------------------------------
DYNAMIC_CONFIG_PATH = Path(os.getenv("HERMES_DYNAMIC_CONFIG", str(ROOT / "config" / "dynamic_config_testnet.json")))
WEBHOOK_URL = os.getenv("HERMES_WEBHOOK_URL", "http://127.0.0.1:5001/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET environment variable is missing")
BINANCE_FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
TIMEFRAME = "15m"
MR_LONG_RSI_MAX = float(os.getenv("HERMES_MR_LONG_RSI_MAX", "35"))
MR_SHORT_RSI_MIN = float(os.getenv("HERMES_MR_SHORT_RSI_MIN", "65"))
MR_VOLUME_MIN = float(os.getenv("HERMES_MR_VOLUME_MIN", "0.90"))
MR_WICK_MIN = float(os.getenv("HERMES_MR_WICK_MIN", "0.25"))
MR_MIN_RR = float(os.getenv("HERMES_MR_MIN_RR", "2.5"))
MR_SL_ATR_MULT = float(os.getenv("HERMES_MR_SL_ATR_MULT", "0.5"))
MR_LIVE_LANES_RAW = os.getenv("HERMES_MR_LIVE_LANES", "")
# Support both legacy HERMES_MEAN_REV_SYMBOLS and newer HERMES_MR_LIVE_SYMBOLS.
_mr_live_raw = os.getenv("HERMES_MR_LIVE_SYMBOLS", "") or os.getenv("HERMES_MEAN_REV_SYMBOLS", "")
MR_LIVE_SYMBOLS = {s.strip().upper() for s in _mr_live_raw.split(",") if s.strip()}


def _parse_live_lanes(raw: str) -> set[tuple[str, str]]:
    """Parse SYMBOL:SIGNAL live-lane entries."""
    lanes: set[tuple[str, str]] = set()
    for item in raw.split(","):
        token = item.strip().upper()
        if not token or ":" not in token:
            continue
        symbol, signal = token.split(":", 1)
        symbol = symbol.strip()
        signal = signal.strip()
        if symbol and signal in {"BUY", "SELL"}:
            lanes.add((symbol, signal))
    return lanes


MR_LIVE_LANES = _parse_live_lanes(MR_LIVE_LANES_RAW) if MR_LIVE_LANES_RAW.strip() else get_mean_reversion_live_lanes()


def is_live_lane_enabled(symbol: str, signal: str) -> bool:
    """Return True when this mean-reversion symbol/direction is allowed to fire live."""
    symbol = symbol.upper()
    signal = signal.upper()
    if MR_LIVE_LANES:
        return (symbol, signal) in MR_LIVE_LANES
    return symbol in MR_LIVE_SYMBOLS


def _profile_context(symbol: str) -> dict:
    """Return audit context for the symbol's strategy profile."""
    profile = get_symbol_strategy_profile(symbol)
    mean_reversion = profile.get("mean_reversion") or {}
    return {
        "strategy": profile.get("signal_strategy") or profile.get("default_strategy") or "unknown",
        "mean_reversion_live_lanes": [str(direction).upper() for direction in mean_reversion.get("live_lanes", [])],
        "mean_reversion_profile": mean_reversion.get("profile"),
    }


def load_active_symbols() -> list[str]:
    """Load active symbols from explicit env or the dynamic config file."""
    env_symbols = [s.strip().upper() for s in os.getenv("HERMES_MEAN_REV_SYMBOLS", "").split(",") if s.strip()]
    if env_symbols:
        return env_symbols

    if not DYNAMIC_CONFIG_PATH.exists():
        print(f"⚠️ Dynamic config file missing at {DYNAMIC_CONFIG_PATH}. Using default symbols.")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "HYPEUSDT", "NEARUSDT", "BNBUSDT", "ONDOUSDT", "XAUUSDT"]
    try:
        with open(DYNAMIC_CONFIG_PATH, "r") as f:
            data = json.load(f)
            return data.get("active_symbols", [])
    except Exception as e:
        print(f"⚠️ Error reading active symbols from dynamic config: {e}")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "HYPEUSDT", "NEARUSDT", "BNBUSDT", "ONDOUSDT", "XAUUSDT"]


def current_futures_price(symbol: str) -> float | None:
    """Fetch a fresh Binance Futures ticker price for the webhook entry anchor."""
    binance_symbol = symbol.replace("/", "").upper()
    if binance_symbol.endswith("USD") and not binance_symbol.endswith("USDT"):
        binance_symbol = f"{binance_symbol}T"
    try:
        resp = requests.get(BINANCE_FUTURES_TICKER_URL, params={"symbol": binance_symbol}, timeout=5)
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        plain_log("MEAN_REV_LIVE_ENTRY_FETCH_FAILED", {"symbol": symbol, "error": str(e)})
        return None


def evaluate_mean_reversion(symbol: str, indicators: dict) -> dict:
    """
    Evaluate strict Bollinger-RSI Mean Reversion gates for a symbol.

    Gates:
      1. Price low pierce LBB (Long) or high pierce UBB (Short)
      2. RSI <= configured oversold threshold or >= configured overbought threshold
      3. Volume ratio >= configured floor
      4. Candlestick wick rejection >= configured floor
      5. Close inside the Bollinger Bands to confirm rejection/bounce
      6. Mid-band target must still clear the webhook's minimum RR
    """
    close = indicators["close"]
    high = indicators["high"]
    low = indicators["low"]
    open_p = indicators["open"]
    lbb, mbb, ubb = indicators["lbb"], indicators["mbb"], indicators["ubb"]
    rsi = indicators["rsi"]
    atr = indicators["atr"]
    vol_ratio = indicators["volume_ratio"]
    bottom_wick_pct = indicators["bottom_wick_pct"]
    top_wick_pct = indicators["top_wick_pct"]

    result = {
        "symbol": symbol,
        "signal": None,
        "conditions_met": False,
        "reasons": [],
        "sl": None,
        "tp": None,
        "rr": None,
        "gate_values": {
            "rsi": rsi,
            "volume_ratio": vol_ratio,
            "bottom_wick_pct": bottom_wick_pct,
            "top_wick_pct": top_wick_pct,
            "min_rr": MR_MIN_RR,
        },
    }

    # 1. LONG EVALUATION
    if low <= lbb:
        # Check RSI
        if rsi <= MR_LONG_RSI_MAX:
            # Check Volume Climax
            if vol_ratio >= MR_VOLUME_MIN:
                # Check Wick Rejection and Close Reentry
                if bottom_wick_pct >= MR_WICK_MIN and close > lbb:
                    # Dynamically calculate levels
                    sl = low - (MR_SL_ATR_MULT * atr)
                    tp = mbb
                    sl_dist = close - sl
                    rr = round((tp - close) / sl_dist, 2) if sl_dist > 0 else 0.0

                    if rr >= MR_MIN_RR:
                        result["signal"] = "BUY"
                        result["conditions_met"] = True
                        result["sl"] = round(sl, 5)
                        result["tp"] = round(tp, 5)
                        result["rr"] = rr
                    else:
                        result["reasons"].append(f"mid-band RR {rr:.2f} < {MR_MIN_RR:.2f}")
                else:
                    if bottom_wick_pct < MR_WICK_MIN:
                        result["reasons"].append(
                            f"weak bottom wick rejection {bottom_wick_pct * 100:.1f}% < {MR_WICK_MIN * 100:.0f}%"
                        )
                    if close <= lbb:
                        result["reasons"].append("closed outside lower band")
            else:
                result["reasons"].append(f"volume ratio {vol_ratio:.2f} < {MR_VOLUME_MIN:.2f}x")
        else:
            result["reasons"].append(f"RSI {rsi:.1f} not oversold (<= {MR_LONG_RSI_MAX:.1f})")

    # 2. SHORT EVALUATION
    elif high >= ubb:
        # Check RSI
        if rsi >= MR_SHORT_RSI_MIN:
            # Check Volume Climax
            if vol_ratio >= MR_VOLUME_MIN:
                # Check Wick Rejection and Close Reentry
                if top_wick_pct >= MR_WICK_MIN and close < ubb:
                    sl = high + (MR_SL_ATR_MULT * atr)
                    tp = mbb
                    sl_dist = sl - close
                    rr = round((close - tp) / sl_dist, 2) if sl_dist > 0 else 0.0

                    if rr >= MR_MIN_RR:
                        result["signal"] = "SELL"
                        result["conditions_met"] = True
                        result["sl"] = round(sl, 5)
                        result["tp"] = round(tp, 5)
                        result["rr"] = rr
                    else:
                        result["reasons"].append(f"mid-band RR {rr:.2f} < {MR_MIN_RR:.2f}")
                else:
                    if top_wick_pct < MR_WICK_MIN:
                        result["reasons"].append(
                            f"weak top wick rejection {top_wick_pct * 100:.1f}% < {MR_WICK_MIN * 100:.0f}%"
                        )
                    if close >= ubb:
                        result["reasons"].append("closed outside upper band")
            else:
                result["reasons"].append(f"volume ratio {vol_ratio:.2f} < {MR_VOLUME_MIN:.2f}x")
        else:
            result["reasons"].append(f"RSI {rsi:.1f} not overbought (>= {MR_SHORT_RSI_MIN:.1f})")

    else:
        result["reasons"].append("price did not pierce volatility bands")

    return result


def send_webhook_signal(symbol: str, signal: str, entry: float, sl: float, tp: float, rr: float) -> bool:
    """POST the validated mean reversion setup to the Testnet Webhook."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol,
        "signal": signal,
        "entry": round(entry, 5),
        "bias": "neutral",  # Mean reversion is dynamic range play
        "structure": "neutral_neutral",
        "regime": "smc_pro",
        "version": "2.2.1",
        "source": "signal_generator",
        "timeframe": "15",
        "timestamp": now_ms,
        "strategy": "mean_reversion",
        "strategy_label": MEAN_REVERSION_15M,
        "entry_setup_label": "BOLLINGER_RSI_MIDBAND",
        "source_service": "15m_mean_reversion_scanner",
        "webhook_port": webhook_port_from_url(WEBHOOK_URL) or 5001,
        "execution_mode": "TESTNET",
        "sl": sl,
        "tp": tp,
        "rr": rr,
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        resp.raise_for_status()
        resp_json = resp.json()
        status = resp_json.get("status", "unknown")
        reason = resp_json.get("reason", "none")

        plain_log(
            "MEAN_REV_SIGNAL_SENT",
            {
                "symbol": symbol,
                "signal": signal,
                "status": status,
                "reason": reason,
                "sl": sl,
                "tp": tp,
            },
        )
        return status == "approved" or status == "entry_filled"
    except Exception as e:
        plain_log("MEAN_REV_WEBHOOK_ERROR", {"symbol": symbol, "error": str(e)})
        return False


def run_scanner():
    """Execute evaluation scan over all active symbols."""
    active_symbols = load_active_symbols()

    # Filter out symbols that throw API kline errors (like Exness Forex pairs in Binance scanner)
    valid_symbols = []
    for s in active_symbols:
        if s.endswith("USD") and not s.endswith("USDT"):
            # Exclude direct Forex/MetaTrader pairs from Binance Futures Scanner
            continue
        valid_symbols.append(s)

    plain_log("MEAN_REV_SCANNER_START", {"symbols": valid_symbols, "timeframe": TIMEFRAME})

    summary = []
    signals_fired = []

    for symbol in valid_symbols:
        indicators = get_live_indicators_dict(symbol, TIMEFRAME, use_closed=True)
        if not indicators:
            summary.append({"symbol": symbol, "status": "SKIP", "reasons": ["indicator fetch failed"]})
            continue

        result = evaluate_mean_reversion(symbol, indicators)

        row = {
            "symbol": symbol,
            "close": indicators["close"],
            "ubb": indicators["ubb"],
            "mbb": indicators["mbb"],
            "lbb": indicators["lbb"],
            "rsi": indicators["rsi"],
            "volume_ratio": indicators["volume_ratio"],
        }

        if result["conditions_met"]:
            if not is_live_lane_enabled(symbol, result["signal"]):
                row.update(
                    {
                        "status": "SHADOW_SKIP",
                        "signal": result["signal"],
                        "sl": result["sl"],
                        "tp": result["tp"],
                        "rr": result["rr"],
                        "reasons": ["mean reversion lane not enabled live"],
                    }
                )
                plain_log("MEAN_REV_SHADOW_CANDIDATE", row)
                summary.append(row)
                continue

            # Signal fired! Send to Webhook
            sl, tp, rr = result["sl"], result["tp"], result["rr"]
            entry = current_futures_price(symbol) or indicators["close"]
            success = send_webhook_signal(symbol, result["signal"], entry, sl, tp, rr)

            row.update(
                {
                    "status": "FIRE",
                    "signal": result["signal"],
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "rr": rr,
                    "webhook_status": "sent" if success else "error",
                }
            )
            signals_fired.append(row)
            summary.append(row)
        else:
            row.update(
                {
                    "status": "SKIP",
                    "reasons": result["reasons"],
                    # Map gates_away for proximity analysis in hour summaries
                    "gates_away": len(result["reasons"]),
                }
            )
            summary.append(row)

    # ── Dispatch Telegram hourly summaries & alerts ──────────────────────
    ts = datetime.now(timezone.utc).strftime("%H:%M")

    # Map logs to standard TV schema keys for compatible client formatter
    telegram_rows = []
    for r in summary:
        row_copy = dict(r)
        # Rename keys for telegram_client compatibility
        row_copy["supertrend"] = "long" if r["close"] >= r["mbb"] else "short"
        row_copy["ema200"] = r["mbb"]
        telegram_rows.append(row_copy)

    telegram_client.notify_hour_summary(telegram_rows, f"{ts} MR")

    plain_log(
        "MEAN_REV_SCANNER_DONE",
        {
            "symbols_checked": len(valid_symbols),
            "signals_fired": len(signals_fired),
        },
    )


if __name__ == "__main__":
    run_scanner()
