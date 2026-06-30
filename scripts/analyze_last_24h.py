#!/usr/bin/env python3
"""Analyze last 24h of testnet data. Run every morning at 7 AM."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import trade_db


# Only count trades from when the new system was fully deployed.
SYSTEM_CUTOFF = "2026-05-16 00:00:00"


def main():
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    effective_cutoff = max(cutoff, SYSTEM_CUTOFF)
    report_dir = Path("/home/rick/ozzy-bot/reports")
    report_dir.mkdir(exist_ok=True)

    report = {
        "generated_at": datetime.now().isoformat(),
        "period_hours": 24,
        "symbols": {},
        "grades": {},
        "summary": {},
    }

    with trade_db._connect() as conn:
        # All trades in last 24h
        rows = conn.execute(
            "SELECT * FROM trades WHERE ts > ? ORDER BY ts DESC", (effective_cutoff,)
        ).fetchall()

        for r in rows:
            sym = r["symbol"]
            grade = r["setup_grade"] or "None"
            closed = r["exit_price"] is not None
            pnl = r["pnl"] or 0.0

            # Per symbol
            if sym not in report["symbols"]:
                report["symbols"][sym] = {
                    "count": 0, "wins": 0, "losses": 0, "pnl": 0.0, "open": 0
                }
            report["symbols"][sym]["count"] += 1
            if closed:
                report["symbols"][sym]["pnl"] += pnl
                if pnl > 0:
                    report["symbols"][sym]["wins"] += 1
                else:
                    report["symbols"][sym]["losses"] += 1
            else:
                report["symbols"][sym]["open"] += 1

            # Per grade
            if grade not in report["grades"]:
                report["grades"][grade] = {
                    "count": 0, "wins": 0, "losses": 0, "pnl": 0.0
                }
            report["grades"][grade]["count"] += 1
            if closed:
                report["grades"][grade]["pnl"] += pnl
                if pnl > 0:
                    report["grades"][grade]["wins"] += 1
                else:
                    report["grades"][grade]["losses"] += 1

        # Overall summary
        all_closed = [r for r in rows if r["exit_price"]]
        winners = [r for r in all_closed if (r["pnl"] or 0) > 0]
        total_pnl = sum((r["pnl"] or 0) for r in all_closed)
        avg_r = (
            sum((r["r_multiple"] or 0) for r in all_closed) / len(all_closed)
            if all_closed else 0.0
        )

        report["summary"] = {
            "total_trades": len(rows),
            "closed_trades": len(all_closed),
            "winners": len(winners),
            "losers": len(all_closed) - len(winners),
            "win_rate": round(len(winners) / len(all_closed) * 100, 1) if all_closed else 0.0,
            "total_pnl": round(total_pnl, 2),
            "avg_r": round(avg_r, 2),
        }

    # Write report
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = report_dir / f"daily_{date_str}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    s = report["summary"]
    print(f"📊 Daily Report: {date_str}")
    print(f"   Trades: {s['total_trades']} | Closed: {s['closed_trades']}")
    print(f"   Winners: {s['winners']} | Losers: {s['losers']} | WR: {s['win_rate']}%")
    print(f"   Total PnL: ${s['total_pnl']:.2f} | Avg R: {s['avg_r']}")
    print(f"   By symbol:")
    for sym, data in report["symbols"].items():
        wr = data["wins"] / (data["wins"] + data["losses"]) * 100 if (data["wins"] + data["losses"]) > 0 else 0
        print(f"      {sym:10} {data['count']} trades | {data['wins']}W/{data['losses']}L | PnL=${data['pnl']:.2f} | WR={wr:.0f}%")
    print(f"   Saved to: {report_path}")


if __name__ == "__main__":
    main()
