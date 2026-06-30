from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from historical_ohlc import fetch_candles, evaluate_outcome_from_candles

REVIEWS_PATH = "/home/rick/ozzy-bot/signal_reviews.json"
FILTER_VERSION = "v2026-04-17-rsi-80-20"
FILTER_VERSION_REASON = "RSI exhaustion threshold raised to 80/20 after signal review data showed 4/4 blocked winners (8R lost) — rsi_exhaustion filter was too conservative"


def load_reviews(path: str = REVIEWS_PATH) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {"reviews": []}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"reviews": []}


def save_reviews(data: dict, path: str = REVIEWS_PATH) -> None:
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_review(review: dict[str, Any], path: str = REVIEWS_PATH) -> None:
    data = load_reviews(path)
    reviews = data.setdefault("reviews", [])
    review_id = review.get("id")
    if review_id and any(existing.get("id") == review_id for existing in reviews):
        return
    enriched = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "filter_version": FILTER_VERSION,
        "filter_version_reason": FILTER_VERSION_REASON,
        **review,
    }
    reviews.append(enriched)
    save_reviews(data, path)


def summarize_filter_impacts(reviews: list[dict], min_signals: int = 20) -> dict:
    filters: dict[str, dict] = {}
    for review in reviews:
        if review.get("decision") != "rejected":
            continue
        filter_name = review.get("filter_name") or "unknown"
        bucket = filters.setdefault(filter_name, {
            "signals": 0,
            "blocked_winners": 0,
            "blocked_losers": 0,
            "ambiguous": 0,
            "net_r_impact": 0.0,
            "flagged": False,
        })
        bucket["signals"] += 1
        outcome = review.get("outcome")
        r_multiple = review.get("r_multiple")
        if outcome == "win":
            bucket["blocked_winners"] += 1
        elif outcome == "loss":
            bucket["blocked_losers"] += 1
        elif outcome == "ambiguous":
            bucket["ambiguous"] += 1
        if isinstance(r_multiple, (int, float)):
            bucket["net_r_impact"] += float(r_multiple)

    for bucket in filters.values():
        bucket["net_r_impact"] = round(bucket["net_r_impact"], 4)
        bucket["flagged"] = bucket["signals"] >= min_signals and bucket["net_r_impact"] > 0
    return {"filters": filters, "minimum_sample": min_signals}


def backfill_reviews(path: str = REVIEWS_PATH) -> dict:
    data = load_reviews(path)
    updated = 0
    unavailable = 0
    for review in data.get("reviews", []):
        if review.get("outcome_status") in {"resolved", "ambiguous", "unavailable"}:
            continue
        symbol = review.get("symbol")
        ts = review.get("ts")
        entry = review.get("entry")
        sl = review.get("sl")
        tp = review.get("tp")
        if not (symbol and ts and entry is not None and sl is not None and tp is not None):
            review["outcome_status"] = "unavailable"
            review["outcome_reason"] = "missing trade levels or timestamp"
            unavailable += 1
            continue

        # Cap end time at now() — don't request future data from APIs
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # Ensure timezone-aware for comparison
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        requested_end = ts_dt + timedelta(hours=48)
        now_utc = datetime.now(timezone.utc)
        end_dt = min(requested_end, now_utc)

        # Skip if signal is too recent (not enough time for outcome to develop)
        if end_dt <= ts_dt:
            review["outcome_status"] = "pending"
            review["outcome_reason"] = "signal too recent for outcome analysis"
            unavailable += 1
            continue

        try:
            candles, meta = fetch_candles(symbol, ts, end_dt.isoformat())
        except Exception as exc:
            review["outcome_status"] = "unavailable"
            review["outcome_reason"] = f"ohlc fetch failed: {exc}"
            review["outcome_provider"] = None
            unavailable += 1
            continue
        if not meta.get("reliable"):
            review["outcome_status"] = "unavailable"
            review["outcome_reason"] = meta.get("reason")
            review["outcome_provider"] = meta.get("provider")
            unavailable += 1
            continue

        outcome = evaluate_outcome_from_candles(review.get("signal"), float(entry), float(sl), float(tp), candles, ts)
        review.update(outcome)
        review["outcome_provider"] = meta.get("provider")
        review["outcome_timeframe"] = meta.get("timeframe")
        updated += 1

    save_reviews(data, path)
    return {"updated": updated, "unavailable": unavailable, "total": len(data.get('reviews', []))}
