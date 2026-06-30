from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_review import load_reviews, summarize_filter_impacts

REVIEWS_PATH = "/home/rick/ozzy-bot/signal_reviews.json"
LOG_PATH = "/home/rick/ozzy-bot/trades.log"
RECENT_EVENT_TYPES = {"SIGNAL_IN", "APPROVED", "REJECTED", "SETUP_FORMING", "SETUP_CONFLICT"}


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    for parser in (
        lambda text: datetime.fromisoformat(text.replace("Z", "+00:00")),
        lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
    ):
        try:
            dt = parser(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)


def _iter_recent_log_events(log_paths: list[str | Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for log_path in log_paths:
        path = Path(log_path)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw.startswith("{"):
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if payload.get("event") not in RECENT_EVENT_TYPES:
                    continue
                events.append({
                    "ts": payload.get("ts"),
                    "event": payload.get("event"),
                    "symbol": payload.get("symbol"),
                    "signal": payload.get("signal"),
                    "entry": payload.get("entry"),
                    "reason": payload.get("reason"),
                })
    events.sort(key=lambda item: _parse_ts(item.get("ts")), reverse=True)
    return events


def load_recent_log_events(log_path: str = LOG_PATH, limit: int = 50, log_paths: list[str | Path] | None = None) -> list[dict[str, Any]]:
    paths = log_paths if log_paths is not None else [log_path]
    events = _iter_recent_log_events(paths)
    return events[:limit]


def _build_symbol_summary(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "symbol": None,
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "wins": 0,
        "losses": 0,
        "pending": 0,
        "unavailable": 0,
    })
    for review in reviews:
        symbol = review.get("symbol") or "UNKNOWN"
        bucket = summary[symbol]
        bucket["symbol"] = symbol
        bucket["total"] += 1
        if review.get("decision") == "approved":
            bucket["approved"] += 1
        elif review.get("decision") == "rejected":
            bucket["rejected"] += 1
        outcome = review.get("outcome")
        status = review.get("outcome_status")
        if outcome == "win":
            bucket["wins"] += 1
        elif outcome == "loss":
            bucket["losses"] += 1
        elif status == "pending":
            bucket["pending"] += 1
        elif status == "unavailable":
            bucket["unavailable"] += 1
    return sorted(summary.values(), key=lambda item: (-item["total"], item["symbol"]))


def _latest_signals(reviews: list[dict[str, Any]], limit: int = 30) -> list[dict[str, Any]]:
    ordered = sorted(reviews, key=lambda item: _parse_ts(item.get("ts")), reverse=True)
    return ordered[:limit]


def _totals(reviews: list[dict[str, Any]]) -> dict[str, int]:
    decisions = Counter(review.get("decision") for review in reviews)
    statuses = Counter(review.get("outcome_status") for review in reviews)
    resolved_total = sum(1 for review in reviews if review.get("outcome") in {"win", "loss", "ambiguous"} or review.get("outcome_status") == "resolved")
    return {
        "reviews_total": len(reviews),
        "approved_total": decisions.get("approved", 0),
        "rejected_total": decisions.get("rejected", 0),
        "resolved_total": resolved_total,
        "pending_total": statuses.get("pending", 0),
        "unavailable_total": statuses.get("unavailable", 0),
    }


def _filter_rows(reviews: list[dict[str, Any]], min_signals: int = 20) -> list[dict[str, Any]]:
    summary = summarize_filter_impacts(reviews, min_signals=min_signals)
    rows = []
    for filter_name, bucket in summary.get("filters", {}).items():
        rows.append({
            "filter_name": filter_name,
            **bucket,
        })
    rows.sort(key=lambda item: (-item["signals"], item["filter_name"]))
    return rows


def build_review_dashboard_context(
    reviews_path: str = REVIEWS_PATH,
    log_path: str = LOG_PATH,
    log_paths: list[str | Path] | None = None,
    min_signals: int = 20,
) -> dict[str, Any]:
    reviews = load_reviews(reviews_path).get("reviews", [])
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "totals": _totals(reviews),
        "latest_signals": _latest_signals(reviews),
        "filters": _filter_rows(reviews, min_signals=min_signals),
        "symbols": _build_symbol_summary(reviews),
        "recent_events": load_recent_log_events(log_path=log_path, log_paths=log_paths),
    }
