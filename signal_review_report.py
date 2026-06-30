#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import telegram_client
from historical_ohlc import provider_reliability_map
from signal_review import backfill_reviews, load_reviews, summarize_filter_impacts
from signal_review_importer import import_from_log

SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US500"]


def build_weekly_report(min_signals: int = 20) -> str:
    import_from_log()
    backfill_reviews()
    data = load_reviews()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    weekly = []
    for review in data.get("reviews", []):
        ts = review.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= since:
            weekly.append(review)

    summary = summarize_filter_impacts(weekly, min_signals=min_signals)
    reliability = provider_reliability_map(SYMBOLS)
    lines = ["<b>HERMES — WEEKLY FILTER REVIEW</b>", f"Signals reviewed: {len(weekly)}", f"Minimum sample for flagging: {min_signals}", ""]
    lines.append("<b>Reliable OHLC</b>")
    reliable = [symbol for symbol, meta in reliability.items() if meta["reliable"]]
    unreliable = [symbol for symbol, meta in reliability.items() if not meta["reliable"]]
    lines.append(", ".join(reliable) if reliable else "None")
    lines.append("<b>Unavailable OHLC</b>")
    lines.append(", ".join(unreliable) if unreliable else "None")
    lines.append("")
    lines.append("<b>Filters</b>")

    filters = summary.get("filters", {})
    if not filters:
        lines.append("No rejected signals recorded yet.")
    else:
        for name, bucket in sorted(filters.items()):
            flag = " ⚠️" if bucket["flagged"] else ""
            lines.append(
                f"{name}: n={bucket['signals']} | winners blocked={bucket['blocked_winners']} | losers blocked={bucket['blocked_losers']} | netR={bucket['net_r_impact']}{flag}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    text = build_weekly_report()
    telegram_client.send_message(text)
    print(text)
