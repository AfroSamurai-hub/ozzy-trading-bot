#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime

from bot import calculate_atr_levels
from config import ASSETS, MIN_RR
from signal_review import append_review, load_reviews

LOG_FILE = "/home/rick/ozzy-bot/trades.log"


def _review_id(ts: str, decision: str, symbol: str, signal: str, entry: float) -> str:
    return f"{ts}:{decision}:{symbol}:{signal}:{round(float(entry), 5)}"


def _parse_filter_name(reason: str) -> str:
    text = (reason or "").lower()
    if "outside trading hours" in text:
        return "kill_zone"
    if "max concurrent positions" in text:
        return "max_positions"
    if "supertrend" in text:
        return "supertrend_conflict"
    if "rsi exhaustion" in text:
        return "rsi_exhaustion"
    if "low volume" in text:
        return "volume_confirmation"
    if "sl" in text and "below" in text:
        return "sl_too_tight"
    if "sl" in text and "above" in text:
        return "sl_too_wide"
    if "r:r" in text:
        return "rr_below_minimum"
    if "live indicator fetch failed" in text:
        return "live_data_fetch"
    return "unknown"


def _project_levels(signal: str, entry: float, symbol: str, live: dict | None = None):
    asset = ASSETS.get(symbol, ASSETS["XAUUSD"])
    atr = (live or {}).get("atr")
    if atr:
        sl, tp, _ = calculate_atr_levels(signal, float(entry), float(atr), asset["atr_sl_mult"], rr=MIN_RR)
        return sl, tp, "taapi_atr"
    offset = float(asset["default_offset"])
    if signal == "BUY":
        return round(entry - offset, 5), round(entry + offset * MIN_RR, 5), "default_offset"
    return round(entry + offset, 5), round(entry - offset * MIN_RR, 5), "default_offset"


def import_from_log(log_path: str = LOG_FILE) -> dict:
    existing = load_reviews()["reviews"]
    existing_ids = {item.get("id") for item in existing}
    last_signal_by_symbol = {}
    last_taapi_by_symbol = {}
    imported = 0

    with open(log_path, "r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw.startswith("{"):
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = data.get("event")
            symbol = data.get("symbol")
            if event == "SIGNAL_IN" and symbol:
                last_signal_by_symbol[symbol] = data
                continue
            if event == "TAAPI_BULK" and symbol:
                last_taapi_by_symbol[symbol] = data
                continue
            if event == "REJECTED" and symbol:
                signal_data = last_signal_by_symbol.get(symbol, {})
                entry = signal_data.get("entry", data.get("entry"))
                signal = signal_data.get("signal", data.get("signal"))
                if entry is None or signal is None:
                    continue
                ts = signal_data.get("ts") or data.get("ts")
                live = last_taapi_by_symbol.get(symbol)
                sl, tp, level_source = _project_levels(signal, float(entry), symbol, live=live)
                review_id = _review_id(ts, "rejected", symbol, signal, float(entry))
                if review_id in existing_ids:
                    continue
                append_review({
                    "id": review_id,
                    "ts": ts,
                    "decision": "rejected",
                    "symbol": symbol,
                    "signal": signal,
                    "entry": float(entry),
                    "sl": sl,
                    "tp": tp,
                    "rr": round(abs(tp - float(entry)) / abs(float(entry) - sl), 4) if sl != entry else None,
                    "filter_name": _parse_filter_name(data.get("reason", "")),
                    "filter_value": {"reason": data.get("reason")},
                    "filter_reason": data.get("reason"),
                    "level_source": level_source,
                    "outcome": None,
                    "outcome_status": None,
                    "r_multiple": None,
                })
                existing_ids.add(review_id)
                imported += 1
                continue

            if event == "APPROVED" and symbol:
                entry = data.get("entry")
                signal = data.get("signal")
                ts = data.get("ts")
                if entry is None or signal is None or ts is None:
                    continue
                review_id = _review_id(ts, "approved", symbol, signal, float(entry))
                if review_id in existing_ids:
                    continue
                append_review({
                    "id": review_id,
                    "ts": ts,
                    "decision": "approved",
                    "symbol": symbol,
                    "signal": signal,
                    "entry": float(entry),
                    "sl": data.get("sl"),
                    "tp": data.get("tp"),
                    "rr": data.get("rr"),
                    "filter_name": None,
                    "filter_value": None,
                    "filter_reason": None,
                    "level_source": data.get("atr_source"),
                    "risk_dollars": data.get("risk_dollars"),
                    "reward_dollars": data.get("reward_dollars"),
                    "outcome": None,
                    "outcome_status": None,
                    "r_multiple": None,
                })
                existing_ids.add(review_id)
                imported += 1
    return {"imported": imported, "total_reviews": len(load_reviews()["reviews"])}


if __name__ == "__main__":
    result = import_from_log()
    print(json.dumps(result, indent=2))
