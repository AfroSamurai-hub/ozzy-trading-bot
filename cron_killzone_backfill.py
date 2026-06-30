#!/usr/bin/env python3
"""
Cron job: Backfill kill_zone signal outcomes and report to Telegram.
Runs 24h after signals to give enough candle history for resolution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import telegram_client
from signal_review import backfill_reviews, load_reviews, summarize_filter_impacts
from historical_ohlc import provider_reliability_map

SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US500"]

def main():
    # Run backfill
    result = backfill_reviews()
    
    # Load updated data
    data = load_reviews()
    reviews = data.get("reviews", [])
    
    # Count outcomes
    resolved = [r for r in reviews if r.get("outcome_status") == "resolved"]
    pending = [r for r in reviews if r.get("outcome_status") not in ["resolved", "unavailable"]]
    unavailable = [r for r in reviews if r.get("outcome_status") == "unavailable"]
    
    # Get kill_zone specific stats
    kill_zone_reviews = [r for r in reviews if r.get("filter_name") == "kill_zone"]
    kill_zone_resolved = [r for r in kill_zone_reviews if r.get("outcome_status") == "resolved"]
    kill_zone_wins = [r for r in kill_zone_resolved if r.get("outcome") == "win"]
    kill_zone_losses = [r for r in kill_zone_resolved if r.get("outcome") == "loss"]
    
    # Build filter performance summary
    summary = summarize_filter_impacts(reviews, min_signals=3)
    reliability = provider_reliability_map(SYMBOLS)
    
    # Build report
    lines = [
        "<b>📊 KILL_ZONE BACKFILL REPORT</b>",
        f"<i>Ran: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>",
        "",
        f"<b>Backfill Results:</b>",
        f"  Updated: {result.get('updated', 0)}",
        f"  Unavailable: {result.get('unavailable', 0)}",
        "",
        f"<b>Overall Outcomes:</b>",
        f"  Resolved: {len(resolved)}",
        f"  Pending: {len(pending)}",
        f"  Unavailable: {len(unavailable)}",
        "",
        f"<b>Kill Zone Filter:</b>",
        f"  Total signals: {len(kill_zone_reviews)}",
        f"  Resolved: {len(kill_zone_resolved)}",
        f"  Winners blocked: {len(kill_zone_wins)}",
        f"  Losers blocked: {len(kill_zone_losses)}",
    ]
    
    # Add net R impact if we have resolved outcomes
    if kill_zone_resolved:
        net_r = sum(r.get("r_multiple", 0) for r in kill_zone_resolved if r.get("r_multiple"))
        lines.append(f"  Net R impact: {net_r:.2f}")
        if net_r > 0:
            lines.append("  ⚠️ <b>FILTER BLOCKING WINNERS</b>")
        elif net_r < 0:
            lines.append("  ✅ Filter working (blocking losers)")
    
    # Add filter performance table
    lines.extend(["", "<b>All Filter Performance:</b>"])
    filters = summary.get("filters", {})
    if filters:
        for name, bucket in sorted(filters.items()):
            flag = " ⚠️" if bucket.get("flagged") else ""
            lines.append(
                f"{name}: n={bucket['signals']} | W={bucket['blocked_winners']} L={bucket['blocked_losers']} | netR={bucket['net_r_impact']:.2f}{flag}"
            )
    else:
        lines.append("No rejected signals recorded.")
    
    # Send to Telegram
    message = "\n".join(lines)
    telegram_client.send_message(message)
    print(message)
    
    # Also print to stdout for cron logging
    return result

if __name__ == "__main__":
    main()
