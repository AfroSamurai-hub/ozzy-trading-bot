#!/usr/bin/env python3
"""
Hermes Signal Generator v1.0
Generates trading signals directly from Binance native data.

Runs standalone — no TradingView dependency.
Evaluates EMA200 + SuperTrend + RSI + Volume conditions and POSTs
matching signals to the local webhook (webhook.py) for 15-gate validation.

Usage:
    python signal_generator.py           # Live mode — sends signals
    python signal_generator.py --dry-run # Dry-run — evaluates only, no POST
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, "/home/rick/ozzy-bot")

from binance_indicators import get_live_indicators
from crypto_entry_policy import classify_crypto_entry
from logger import plain_log
from ozzy_memory import record_setup_event
import telegram_client

# ── Config ──────────────────────────────────────────────────────────
from dynamic_config import get_param
from config import (
    BINANCE_SYMBOLS,
    BINANCE_TESTNET,
    DYNAMIC_THRESHOLDS,
    build_crypto_entry_config,
    get_signal_strategy_for_symbol,
)
from lane_labels import ONE_HOUR_TREND, derive_entry_setup_label, derive_regime_label, webhook_port_from_url

_env_symbols_str = os.getenv("HERMES_SIGNAL_SYMBOLS", "").strip()
if _env_symbols_str:
    SYMBOLS = [s.strip() for s in _env_symbols_str.split(",") if s.strip()]
else:
    SYMBOLS = get_param("active_symbols", BINANCE_SYMBOLS)

TIMEFRAME = "1h"
WEBHOOK_URL = os.getenv("HERMES_WEBHOOK_URL", "http://localhost:5000/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET environment variable is missing")
BINANCE_FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"

# Entry thresholds
RSI_MIN = 30
RSI_MAX = 70
VOLUME_MIN_RATIO = 0.75

# ETH safety: block all LONG signals (short-only mode)
ETH_BLOCK_LONG = True

# Proximity alert cooldown (seconds)
PROXIMITY_COOLDOWN_SECONDS = 7200  # 2 hours
PROXIMITY_COOLDOWN_FILE = os.getenv("HERMES_PROXIMITY_COOLDOWN_FILE", "/home/rick/ozzy-bot/.cache/proximity_cooldown.json")


def _load_cooldowns() -> dict:
    """Load last proximity alert timestamps per symbol."""
    if os.path.exists(PROXIMITY_COOLDOWN_FILE):
        try:
            with open(PROXIMITY_COOLDOWN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cooldowns(cooldowns: dict):
    """Save proximity alert timestamps."""
    os.makedirs(os.path.dirname(PROXIMITY_COOLDOWN_FILE), exist_ok=True)
    with open(PROXIMITY_COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f)


def _analyze_proximity(
    symbol: str,
    close: float,
    ema200: float,
    st_dir: str,
    rsi: float,
    volume_ratio: float,
    strategy: str | None = None,
    rejection_reasons: list[str] | None = None,
) -> dict | None:
    """Analyze how close a symbol is to meeting all criteria.
    Returns proximity data dict if 1-2 gates away, else None.
    """
    # Long criteria
    long_ema_ok = close > ema200
    long_st_ok = st_dir == "long"
    long_rsi_ok = RSI_MIN < rsi < RSI_MAX
    long_vol_ok = volume_ratio >= VOLUME_MIN_RATIO
    long_score = sum([long_ema_ok, long_st_ok, long_rsi_ok, long_vol_ok])

    # Short criteria
    short_ema_ok = close < ema200
    short_st_ok = st_dir == "short"
    short_rsi_ok = RSI_MIN < rsi < RSI_MAX
    short_vol_ok = volume_ratio >= VOLUME_MIN_RATIO
    short_score = sum([short_ema_ok, short_st_ok, short_rsi_ok, short_vol_ok])

    if long_score >= short_score and long_score >= 2:
        direction = "long"
        score = long_score
        ema_ok = long_ema_ok
        st_ok = long_st_ok
        rsi_ok = long_rsi_ok
        vol_ok = long_vol_ok
    elif short_score >= 2:
        direction = "short"
        score = short_score
        ema_ok = short_ema_ok
        st_ok = short_st_ok
        rsi_ok = short_rsi_ok
        vol_ok = short_vol_ok
    else:
        return None

    classifier_reasons = [str(reason) for reason in (rejection_reasons or []) if str(reason).strip()]
    if len(classifier_reasons) > 2:
        return None
    gates_away = len(classifier_reasons) if classifier_reasons else 4 - score
    if gates_away > 2:
        return None

    # Determine blocking gate (first unmet gate in priority order)
    blocking = []
    if not ema_ok:
        blocking.append("EMA200 alignment")
    if not st_ok:
        blocking.append("SuperTrend direction")
    if not rsi_ok:
        if rsi <= RSI_MIN:
            blocking.append(f"RSI > {RSI_MIN}")
        else:
            blocking.append(f"RSI < {RSI_MAX}")
    if not vol_ok:
        blocking.append(f"volume >= {VOLUME_MIN_RATIO}x")
    blocking_gate = classifier_reasons[0] if classifier_reasons else blocking[0] if blocking else "none"

    ema_pct = ((close - ema200) / ema200) * 100 if ema200 else 0

    return {
        "symbol": symbol,
        "direction": direction,
        "close": close,
        "ema200": ema200,
        "ema_pct": ema_pct,
        "ema_ok": ema_ok,
        "st_dir": st_dir,
        "st_ok": st_ok,
        "rsi": rsi,
        "rsi_ok": rsi_ok,
        "rsi_needed": (RSI_MIN + 0.1) - rsi if rsi <= RSI_MIN else (RSI_MAX - 0.1) - rsi if rsi >= RSI_MAX else 0,
        "volume_ratio": volume_ratio,
        "vol_ok": vol_ok,
        "vol_needed": VOLUME_MIN_RATIO - volume_ratio if volume_ratio < VOLUME_MIN_RATIO else 0,
        "gates_away": gates_away,
        "blocking_gate": blocking_gate,
    }


def evaluate_symbol(symbol: str, live: dict, dry_run: bool) -> dict:
    """
    Evaluate entry conditions for a single symbol.
    Returns a dict with evaluation result and signal details.
    """
    result = {
        "symbol": symbol,
        "strategy": get_signal_strategy_for_symbol(symbol),
        "signal": None,
        "conditions_met": False,
        "reasons": [],
        "indicators": {
            "close": live.get("close"),
            "ema200": live.get("ema200"),
            "supertrend_direction": live.get("supertrend_direction"),
            "rsi": live.get("rsi"),
            "volume": live.get("volume"),
            "volume_avg20": live.get("volume_avg20"),
            "volume_ratio": None,
        },
    }

    close = live.get("close")
    ema200 = live.get("ema200")
    st_dir = live.get("supertrend_direction")
    rsi = live.get("rsi")
    volume = live.get("volume", 0.0)
    vol_avg20 = live.get("volume_avg20", 0.0)

    if vol_avg20 and vol_avg20 > 0:
        volume_ratio = volume / vol_avg20
    else:
        volume_ratio = 0.0
    result["indicators"]["volume_ratio"] = round(volume_ratio, 3)

    # Sanity checks
    if close is None or ema200 is None or st_dir is None or rsi is None:
        result["reasons"].append("missing indicator data")
        plain_log("SIGNAL_GEN_SKIP", {
            "symbol": symbol, "reason": "missing indicator data", "live": live,
        })
        return result

    strategy = result["strategy"]
    long_ok = close > ema200 and st_dir == "long"
    short_ok = close < ema200 and st_dir == "short"

    if long_ok and short_ok:
        result["reasons"].append("ambiguous — both long and short conditions met")
        plain_log("SIGNAL_GEN_SKIP", {"symbol": symbol, "reason": "ambiguous conditions"})
        return result

    if long_ok:
        if symbol in ("ETHUSD", "ETHUSDT") and ETH_BLOCK_LONG:
            result["reasons"].append("ETH LONG blocked (short-only safety)")
            plain_log("SIGNAL_GEN_ETH_BLOCK", {"symbol": symbol, "direction": "BUY"})
            return result
        candidate_signal = "BUY"

    elif short_ok:
        candidate_signal = "SELL"

    else:
        # Build rejection reason for logging
        reasons = []
        if close > ema200 and st_dir != "long":
            reasons.append(f"price above EMA200 but ST={st_dir}")
        elif close < ema200 and st_dir != "short":
            reasons.append(f"price below EMA200 but ST={st_dir}")
        else:
            if close <= ema200 and st_dir == "long":
                reasons.append("price below EMA200")
            if close >= ema200 and st_dir == "short":
                reasons.append("price above EMA200")
        result["reasons"] = reasons
        return result

    if strategy in {"pullback", "momentum", "trend_continuation"}:
        classification = classify_crypto_entry(
            candidate_signal,
            float(close),
            live,
            build_crypto_entry_config(DYNAMIC_THRESHOLDS, symbol),
            requested_strategy=strategy,
        )
        result["classification"] = classification
        if classification.get("mode") == "reject":
            result["reasons"] = list(classification.get("reasons") or ["asset profile rejected setup"])
            return result
    else:
        fallback_reasons = []
        if not (RSI_MIN < rsi < RSI_MAX):
            fallback_reasons.append(f"RSI {rsi} outside {RSI_MIN}-{RSI_MAX}")
        if volume_ratio < VOLUME_MIN_RATIO:
            fallback_reasons.append(f"volume ratio {volume_ratio:.2f} < {VOLUME_MIN_RATIO}")
        if fallback_reasons:
            result["reasons"] = fallback_reasons
            return result

    result["signal"] = candidate_signal
    result["conditions_met"] = True
    result["bias"] = "bullish" if candidate_signal == "BUY" else "bearish"
    result["structure"] = "python_generated"

    return result


def _strategy_for_symbol(symbol: str) -> str | None:
    """Return symbol-specific strategy hints for the webhook classifier."""
    return get_signal_strategy_for_symbol(symbol)


def build_payload(symbol: str, signal: str, entry: float) -> dict:
    """Build the Binance-native webhook payload with stable analytics labels."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    strategy = _strategy_for_symbol(symbol) or "unknown"
    structure = "bullish_bos" if signal == "BUY" else "bearish_bos"
    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol,
        "signal": signal,
        "entry": round(entry, 5),
        "bias": "bullish" if signal == "BUY" else "bearish",
        "structure": structure,
        "regime": "smc_pro",
        "version": "2.2.1",
        "source": "signal_generator",
        "source_service": "signal_generator",
        "strategy": strategy,
        "strategy_label": ONE_HOUR_TREND,
        "entry_setup_label": derive_entry_setup_label(strategy),
        "regime_label": derive_regime_label("smc_pro", structure=structure),
        "webhook_port": webhook_port_from_url(WEBHOOK_URL) or 5001,
        "execution_mode": "TESTNET" if BINANCE_TESTNET else "LIVE",
        "timeframe": "60",
        "timestamp": now_ms,
    }
    return payload


def _current_futures_price(symbol: str) -> float | None:
    """Fetch the current Binance Futures ticker price for the webhook entry anchor."""
    binance_symbol = symbol.replace("/", "").upper()
    if binance_symbol.endswith("USD") and not binance_symbol.endswith("USDT"):
        binance_symbol = f"{binance_symbol}T"
    try:
        resp = requests.get(BINANCE_FUTURES_TICKER_URL, params={"symbol": binance_symbol}, timeout=5)
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        plain_log("SIGNAL_GEN_LIVE_ENTRY_FETCH_FAILED", {"symbol": symbol, "error": str(e)})
        return None


def _redact_payload(payload: dict) -> dict:
    """Return a copy of a webhook payload safe for logs and dry-run output."""
    safe = dict(payload)
    if "secret" in safe:
        safe["secret"] = "<redacted>"
    return safe


def send_signal(payload: dict, dry_run: bool) -> dict:
    """POST signal to webhook. Returns response dict."""
    if dry_run:
        plain_log("SIGNAL_GEN_DRY_RUN", {"payload": _redact_payload(payload)})
        return {"status": "dry_run", "payload": payload}

    try:
        resp = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        plain_log("SIGNAL_GEN_SENT", {
            "symbol": payload["symbol"],
            "signal": payload["signal"],
            "status_code": resp.status_code,
        })
        return {"status": "sent", "status_code": resp.status_code, "response": resp.json()}
    except requests.exceptions.ConnectionError as e:
        plain_log("SIGNAL_GEN_ERROR", {"error": f"webhook unreachable: {e}"})
        return {"status": "error", "reason": f"webhook unreachable: {e}"}
    except requests.exceptions.Timeout:
        plain_log("SIGNAL_GEN_ERROR", {"error": "webhook timeout"})
        return {"status": "error", "reason": "webhook timeout"}
    except Exception as e:
        plain_log("SIGNAL_GEN_ERROR", {"error": str(e)})
        return {"status": "error", "reason": str(e)}


def run(dry_run: bool = False):
    """Main evaluation loop."""
    plain_log("SIGNAL_GEN_START", {
        "symbols": SYMBOLS,
        "timeframe": TIMEFRAME,
        "dry_run": dry_run,
    })

    summary = []
    signals_fired = []

    for symbol in SYMBOLS:
        plain_log("SIGNAL_GEN_CHECK", {"symbol": symbol, "timeframe": TIMEFRAME})
        live = get_live_indicators(symbol, TIMEFRAME)

        if not live:
            plain_log("SIGNAL_GEN_SKIP", {"symbol": symbol, "reason": "indicator fetch failed"})
            summary.append({
                "symbol": symbol,
                "status": "SKIP",
                "reason": "indicator fetch failed",
            })
            continue

        result = evaluate_symbol(symbol, live, dry_run)
        indicators = result["indicators"]

        if result["conditions_met"]:
            entry = _current_futures_price(symbol) or indicators["close"]
            payload = build_payload(symbol, result["signal"], entry)
            send_result = send_signal(payload, dry_run)

            log_entry = {
                "symbol": symbol,
                "signal": result["signal"],
                "entry": entry,
                "signal_candle_close": indicators["close"],
                "ema200": indicators["ema200"],
                "supertrend": indicators["supertrend_direction"],
                "rsi": indicators["rsi"],
                "volume_ratio": indicators["volume_ratio"],
                "webhook_status": send_result["status"],
            }
            plain_log("SIGNAL_GEN_FIRED", log_entry)
            try:
                record_setup_event(
                    symbol=symbol,
                    direction=result["signal"],
                    decision="fired",
                    timeframe=TIMEFRAME,
                    indicators=indicators,
                    proposed_entry=entry,
                    reason="signal generator fire",
                )
            except Exception as memory_error:
                plain_log("OZZY_MEMORY_ERROR", {"stage": "signal_generator_fire", "error": str(memory_error)})
            summary.append({"symbol": symbol, "status": "FIRE", **log_entry})
            signals_fired.append({"symbol": symbol, "payload": payload})
        else:
            log_entry = {
                "symbol": symbol,
                "status": "SKIP",
                "strategy": result.get("strategy"),
                "close": indicators["close"],
                "ema200": indicators["ema200"],
                "supertrend": indicators["supertrend_direction"],
                "rsi": indicators["rsi"],
                "volume_ratio": indicators["volume_ratio"],
                "reasons": result["reasons"],
            }
            plain_log("SIGNAL_GEN_RESULT", log_entry)
            try:
                record_setup_event(
                    symbol=symbol,
                    direction="NONE",
                    decision="skipped",
                    timeframe=TIMEFRAME,
                    reason="; ".join(result["reasons"]) or "no setup",
                    reason_json=result["reasons"],
                    indicators=indicators,
                    proposed_entry=indicators["close"],
                )
            except Exception as memory_error:
                plain_log("OZZY_MEMORY_ERROR", {"stage": "signal_generator_skip", "error": str(memory_error)})
            summary.append(log_entry)

    # ── Proximity analysis ────────────────────────────────────────────
    cooldowns = _load_cooldowns()
    now = time.time()
    proximity_symbols = []

    for row in summary:
        if row.get("status") == "FIRE":
            row["gates_away"] = 0
            continue
        # log_entry stores indicators directly on the row, not nested
        close = row.get("close") or row.get("entry")
        ema200 = row.get("ema200")
        st_dir = row.get("supertrend")
        rsi = row.get("rsi")
        vr = row.get("volume_ratio")
        if close is None or ema200 is None or st_dir is None or rsi is None or vr is None:
            row["gates_away"] = 999
            continue
        prox = _analyze_proximity(
            row["symbol"],
            close,
            ema200,
            st_dir,
            rsi,
            vr,
            strategy=row.get("strategy"),
            rejection_reasons=row.get("reasons"),
        )
        if prox:
            row["gates_away"] = prox["gates_away"]
            try:
                record_setup_event(
                    symbol=row["symbol"],
                    direction=prox["direction"].upper(),
                    decision="near",
                    timeframe=TIMEFRAME,
                    reason=prox["blocking_gate"],
                    reason_json={"gates_away": prox["gates_away"], "blocking_gate": prox["blocking_gate"]},
                    indicators=prox,
                    proposed_entry=prox["close"],
                )
            except Exception as memory_error:
                plain_log("OZZY_MEMORY_ERROR", {"stage": "signal_generator_near", "error": str(memory_error)})
            sym = row["symbol"]
            last_alert = cooldowns.get(sym, 0)
            if now - last_alert >= PROXIMITY_COOLDOWN_SECONDS:
                proximity_symbols.append(prox)
                cooldowns[sym] = now
        else:
            row["gates_away"] = 999

    if proximity_symbols:
        telegram_client.notify_proximity_alert(proximity_symbols)
        _save_cooldowns(cooldowns)

    # ── Hour summary ──────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%H:%M")
    telegram_client.notify_hour_summary(summary, ts)

    plain_log("SIGNAL_GEN_DONE", {
        "symbols_checked": len(SYMBOLS),
        "signals_fired": len(signals_fired),
        "proximity_alerts": len(proximity_symbols),
        "dry_run": dry_run,
    })

    return summary, signals_fired


def print_report(summary: list, signals_fired: list, dry_run: bool):
    """Print human-readable report to stdout."""
    mode_str = "DRY-RUN" if dry_run else "LIVE"
    print(f"\n{'='*60}")
    print(f"  SIGNAL GENERATOR REPORT — {mode_str}")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    print(f"\n{'Symbol':<10} {'Status':<8} {'Close':>10} {'EMA200':>10} {'ST':>6} {'RSI':>6} {'VolRt':>6} {'Reason/Signal'}")
    print("-" * 90)

    for row in summary:
        sym = row["symbol"]
        status = row["status"]
        close = row.get("close", "-")
        ema200 = row.get("ema200", "-")
        st = row.get("supertrend", "-")
        rsi = row.get("rsi", "-")
        vr = row.get("volume_ratio", "-")

        if status == "FIRE":
            reason = f"{row['signal']} @ {row['entry']}"
        elif status == "SKIP":
            reason = "; ".join(row.get("reasons", [])) or "no setup"
        else:
            reason = row.get("reason", "unknown")

        close_str = f"{close:>10.2f}" if isinstance(close, (int, float)) else f"{close:>10}"
        ema_str = f"{ema200:>10.2f}" if isinstance(ema200, (int, float)) else f"{ema200:>10}"
        rsi_str = f"{rsi:>6.1f}" if isinstance(rsi, (int, float)) else f"{rsi:>6}"
        vr_str = f"{vr:>6.2f}" if isinstance(vr, (int, float)) else f"{vr:>6}"

        print(f"{sym:<10} {status:<8} {close_str} {ema_str} {st:>6} {rsi_str} {vr_str} {reason}")

    print("-" * 90)
    print(f"\nTotal signals fired: {len(signals_fired)}")

    if dry_run and signals_fired:
        print("\n--- Payloads that WOULD be sent ---")
        for s in signals_fired:
            print(f"\n{s['symbol']}:")
            print(json.dumps(_redact_payload(s["payload"]), indent=2))
    elif signals_fired:
        print("\n--- Signals sent successfully ---")
        for s in signals_fired:
            print(f"  {s['symbol']}: {s['payload']['signal']} @ {s['payload']['entry']}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Signal Generator — Binance-native signal generation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate conditions but do not POST to webhook",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Check a single symbol instead of the default list",
    )
    args = parser.parse_args()

    symbols_override = [args.symbol.upper()] if args.symbol else None
    if symbols_override:
        global SYMBOLS
        SYMBOLS = symbols_override

    summary, signals_fired = run(dry_run=args.dry_run)
    print_report(summary, signals_fired, dry_run=args.dry_run)

    # A clean scan is successful even when no setup fires. Timer/service health
    # should represent scanner failures, not market inactivity.
    return 0


if __name__ == "__main__":
    sys.exit(main())
