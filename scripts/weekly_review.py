#!/usr/bin/env python3
"""Weekly review: analyze last 7 days, recommend config changes. Run every Sunday."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import trade_db


# Only count trades from when the new system was fully deployed.
# Before this date: old monitor bugs, no state recovery, broken quantity plumbing.
# After this date: real data.
SYSTEM_CUTOFF = "2026-05-16 00:00:00"


def main():
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    # Use the later of (7 days ago) or (system deployment)
    effective_cutoff = max(cutoff, SYSTEM_CUTOFF)
    report_dir = Path("/home/rick/ozzy-bot/reports")
    report_dir.mkdir(exist_ok=True)

    report = {
        "generated_at": datetime.now().isoformat(),
        "period_days": 7,
        "recommendation": {},
        "symbols": {},
        "grades": {},
        "hours": {},
        "summary": {},
    }

    LEGACY_SYMBOLS = {"ETHUSD", "BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}

    with trade_db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE ts > ? ORDER BY ts DESC", (effective_cutoff,)
        ).fetchall()

        for r in rows:
            sym = r["symbol"]
            grade = r["setup_grade"] or "None"
            hour = r["ts"][11:13] if len(r["ts"]) > 13 else "??"
            closed = r["exit_price"] is not None
            pnl = r["pnl"] or 0.0
            is_binance = sym.endswith("USDT")

            # Symbol stats (all)
            if sym not in report["symbols"]:
                report["symbols"][sym] = {"count": 0, "wins": 0, "losses": 0, "pnl": 0.0, "binance": is_binance}
            report["symbols"][sym]["count"] += 1
            if closed:
                report["symbols"][sym]["pnl"] += pnl
                if pnl > 0:
                    report["symbols"][sym]["wins"] += 1
                else:
                    report["symbols"][sym]["losses"] += 1

            # Grade stats (Binance only for recommendations)
            if is_binance:
                if grade not in report["grades"]:
                    report["grades"][grade] = {"count": 0, "wins": 0, "losses": 0, "pnl": 0.0}
                report["grades"][grade]["count"] += 1
                if closed:
                    report["grades"][grade]["pnl"] += pnl
                    if pnl > 0:
                        report["grades"][grade]["wins"] += 1
                    else:
                        report["grades"][grade]["losses"] += 1

            # Hour stats (Binance only)
            if is_binance:
                if hour not in report["hours"]:
                    report["hours"][hour] = {"count": 0, "wins": 0, "losses": 0}
                report["hours"][hour]["count"] += 1
                if closed:
                    if pnl > 0:
                        report["hours"][hour]["wins"] += 1
                    else:
                        report["hours"][hour]["losses"] += 1

        # All trades summary
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

        # Binance-only summary (for live recommendations)
        binance_rows = [r for r in rows if r["symbol"].endswith("USDT")]
        binance_closed = [r for r in binance_rows if r["exit_price"]]
        binance_winners = [r for r in binance_closed if (r["pnl"] or 0) > 0]
        binance_pnl = sum((r["pnl"] or 0) for r in binance_closed)
        binance_avg_r = (
            sum((r["r_multiple"] or 0) for r in binance_closed) / len(binance_closed)
            if binance_closed else 0.0
        )

        report["binance_summary"] = {
            "total_trades": len(binance_rows),
            "closed_trades": len(binance_closed),
            "winners": len(binance_winners),
            "losers": len(binance_closed) - len(binance_winners),
            "win_rate": round(len(binance_winners) / len(binance_closed) * 100, 1) if binance_closed else 0.0,
            "total_pnl": round(binance_pnl, 2),
            "avg_r": round(binance_avg_r, 2),
        }

        # Recommendations based on BINANCE ONLY data
        rec = {}
        wr = report["binance_summary"]["win_rate"]
        avg_r_val = report["binance_summary"]["avg_r"]
        binance_closed_count = report["binance_summary"]["closed_trades"]

        # Early-stage override: not enough live data to make aggressive
        # or conservative calls. Use base case until we have 5+ closed trades.
        if binance_closed_count < 5:
            rec["risk_pct"] = 0.02
            rec["max_positions"] = 3
            rec["rationale"] = f"Base case: only {binance_closed_count} closed trades. Not enough data for aggressive or conservative tuning. Run base config."
        elif wr >= 50 and avg_r_val >= 2.5:
            rec["risk_pct"] = 0.025
            rec["max_positions"] = 4
            rec["rationale"] = "Bull case: high WR and avg R. Can afford slightly more risk."
        elif wr >= 40 and avg_r_val >= 2.0:
            rec["risk_pct"] = 0.02
            rec["max_positions"] = 3
            rec["rationale"] = "Base case: solid but conservative. Stay the course."
        else:
            rec["risk_pct"] = 0.015
            rec["max_positions"] = 2
            rec["rationale"] = "Bear case: below targets. Tighten up until performance improves."

        # Grade recommendations (Binance only)
        for grade, data in report["grades"].items():
            if data["count"] < 2:
                continue
            g_wr = data["wins"] / (data["wins"] + data["losses"]) * 100 if (data["wins"] + data["losses"]) > 0 else 0
            if g_wr >= 60:
                rec[f"grade_{grade}_multiplier"] = 1.25
            elif g_wr >= 45:
                rec[f"grade_{grade}_multiplier"] = 1.0
            elif g_wr >= 30:
                rec[f"grade_{grade}_multiplier"] = 0.75
            else:
                rec[f"grade_{grade}_multiplier"] = 0.0

        # Symbol recommendations (USDT only, ignore legacy)
        # Early-stage: all proven symbols start active until data says stop
        PROVEN_SYMBOLS = {"SOLUSDT", "ETHUSDT", "LINKUSDT", "DOGEUSDT"}
        for sym, data in report["symbols"].items():
            if sym in LEGACY_SYMBOLS:
                continue
            closed_count = data["wins"] + data["losses"]
            if closed_count < 2 and sym in PROVEN_SYMBOLS:
                # Not enough data on this symbol yet — keep it active
                rec[f"symbol_{sym}_status"] = "active (early stage)"
                continue
            if data["count"] < 1:
                continue
            s_wr = data["wins"] / closed_count * 100 if closed_count > 0 else 0
            if s_wr >= 50 and data["pnl"] > 0:
                rec[f"symbol_{sym}_status"] = "active"
            elif s_wr >= 30 and data["pnl"] > -20:
                rec[f"symbol_{sym}_status"] = "watch"
            else:
                rec[f"symbol_{sym}_status"] = "pause"

        report["recommendation"] = rec

    # Write
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = report_dir / f"weekly_{date_str}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print
    s = report["summary"]
    bs = report["binance_summary"]
    rec = report["recommendation"]
    print("=" * 55)
    print("📊 WEEKLY REVIEW")
    print("=" * 55)
    print(f"Period: Since {effective_cutoff[:10]} (system v2 deployed)")
    print(f"")
    print(f"ALL TRADES (including legacy):")
    print(f"   Trades: {s['total_trades']} | Closed: {s['closed_trades']}")
    print(f"   Winners: {s['winners']} | Losers: {s['losers']} | WR: {s['win_rate']}%")
    print(f"   Total PnL: ${s['total_pnl']:.2f}")
    print(f"")
    print(f"BINANCE FUTURES ONLY (USDT pairs — what matters for live):")
    print(f"   Trades: {bs['total_trades']} | Closed: {bs['closed_trades']}")
    print(f"   Winners: {bs['winners']} | Losers: {bs['losers']} | WR: {bs['win_rate']}%")
    print(f"   Total PnL: ${bs['total_pnl']:.2f} | Avg R: {bs['avg_r']}")
    print(f"")
    print("🎯 LIVE CONFIG RECOMMENDATION (based on Binance data):")
    print(f"   Risk per trade: {rec.get('risk_pct', 0.02) * 100}%")
    print(f"   Max positions: {rec.get('max_positions', 3)}")
    print(f"   Rationale: {rec.get('rationale', 'N/A')}")
    print("")
    print("   Grade multipliers:")
    for k, v in rec.items():
        if k.startswith("grade_"):
            print(f"      {k}: {v}x")
    print("")
    print("   Symbol status:")
    for k, v in rec.items():
        if k.startswith("symbol_"):
            print(f"      {k}: {v}")
    print("")
    print(f"📁 Saved to: {report_path}")
    print("=" * 55)


if __name__ == "__main__":
    main()
