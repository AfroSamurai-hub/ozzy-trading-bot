#!/usr/bin/env python3
"""
Quick analysis of portfolio data only (when decisions.json is empty)
"""
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def analyze_portfolio():
    """Analyze portfolio state only"""
    portfolio_file = PROJECT_ROOT / "logs/portfolio_state.json"
    
    with open(portfolio_file, "r") as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    closed_trades = data.get("closed_trades", [])
    total_pnl = data.get("total_pnl", 0)
    capital = data.get("capital", 5000)
    
    print("\n" + "=" * 80)
    print("📊 PORTFOLIO ANALYSIS - 7.5 HOUR TEST (INTERRUPTED BY REBOOT)")
    print("=" * 80)
    
    # Basic stats
    print("\n📈 BASIC STATISTICS")
    print("-" * 80)
    print(f"Starting Capital:        $5,000.00")
    print(f"Current Capital:         ${capital:,.2f}")
    print(f"Total Positions Opened:  {len(positions)}")
    print(f"Closed Trades:           {len(closed_trades)}")
    print(f"Total P&L:               ${total_pnl:,.2f}")
    print(f"Return:                  {(total_pnl / 5000 * 100):.2f}%")
    
    # Calculate over-leverage
    total_invested = len(positions) * 250
    over_leverage = total_invested - 5000
    print(f"\n💰 CAPITAL ANALYSIS")
    print("-" * 80)
    print(f"Total Deployed:          ${total_invested:,.2f}")
    print(f"Over-Leverage:           ${over_leverage:,.2f}")
    print(f"Leverage Ratio:          {(total_invested / 5000):.1f}x")
    
    # Time analysis
    if positions:
        first_time = datetime.fromisoformat(positions[0].get("entry_time"))
        last_time = datetime.fromisoformat(positions[-1].get("entry_time"))
        duration = last_time - first_time
        hours = duration.total_seconds() / 3600
        
        print(f"\n⏰ TIME ANALYSIS")
        print("-" * 80)
        print(f"First Position:          {first_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Last Position:           {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:                {hours:.2f} hours")
        print(f"Positions/Hour:          {len(positions) / hours:.1f}")
        print(f"Positions/Minute:        {len(positions) / (hours * 60):.2f}")
    
    # Price and P&L analysis
    open_positions = [p for p in positions if p.get("status") == "OPEN"]
    
    if open_positions:
        avg_entry = sum(p.get("entry_price", 0) for p in open_positions) / len(open_positions)
        avg_pnl = sum(p.get("unrealized_pnl", 0) for p in open_positions) / len(open_positions)
        avg_pnl_pct = sum(p.get("pnl_pct", 0) for p in open_positions) / len(open_positions)
        
        print(f"\n📊 POSITION ANALYSIS")
        print("-" * 80)
        print(f"Open Positions:          {len(open_positions)}")
        print(f"Average Entry Price:     ${avg_entry:,.2f}")
        print(f"Average P&L per Position: ${avg_pnl:,.2f}")
        print(f"Average P&L %:           {avg_pnl_pct:.2f}%")
    
    # P&L distribution
    profitable = [p for p in open_positions if p.get("unrealized_pnl", 0) > 0]
    losing = [p for p in open_positions if p.get("unrealized_pnl", 0) < 0]
    breakeven = [p for p in open_positions if p.get("unrealized_pnl", 0) == 0]
    
    print(f"\n💹 P&L DISTRIBUTION")
    print("-" * 80)
    print(f"Profitable:              {len(profitable)} ({len(profitable)/len(open_positions)*100:.1f}%)")
    print(f"Losing:                  {len(losing)} ({len(losing)/len(open_positions)*100:.1f}%)")
    print(f"Breakeven:               {len(breakeven)} ({len(breakeven)/len(open_positions)*100:.1f}%)")
    
    if profitable:
        best_pos = max(profitable, key=lambda p: p.get("unrealized_pnl", 0))
        print(f"\nBest Position:           +${best_pos.get('unrealized_pnl', 0):.2f} ({best_pos.get('pnl_pct', 0):.2f}%)")
    
    if losing:
        worst_pos = min(losing, key=lambda p: p.get("unrealized_pnl", 0))
        print(f"Worst Position:          ${worst_pos.get('unrealized_pnl', 0):.2f} ({worst_pos.get('pnl_pct', 0):.2f}%)")
    
    # Near TP/SL analysis
    near_tp = [p for p in open_positions if p.get("pnl_pct", 0) >= 2.5]
    near_sl = [p for p in open_positions if p.get("pnl_pct", 0) <= -1.2]
    
    print(f"\n🎯 RISK ANALYSIS")
    print("-" * 80)
    print(f"Near Take Profit (≥2.5%): {len(near_tp)}")
    print(f"Near Stop Loss (≤-1.2%):  {len(near_sl)}")
    
    # Identify critical bugs
    print(f"\n🐛 BUGS IDENTIFIED")
    print("-" * 80)
    
    bugs = []
    if len(positions) * 250 > 5000:
        bugs.append(f"🚨 CRITICAL: Over-leverage by ${over_leverage:,.2f}!")
        bugs.append(f"   → Bot opened {len(positions)} positions on $5,000 capital")
        bugs.append(f"   → Missing capital check before opening positions")
    
    if len(positions) > 100:
        bugs.append(f"⚠️ TOO AGGRESSIVE: {len(positions)} positions in {hours:.1f} hours")
        bugs.append(f"   → Opening ~{len(positions) / hours:.1f} positions per hour")
        bugs.append(f"   → Need max position limit and/or cooldown")
    
    if len(closed_trades) == 0 and len(positions) > 50:
        bugs.append(f"⚠️ NO CLOSED TRADES: {len(positions)} positions, 0 closures")
        bugs.append(f"   → Either Bitcoin didn't move ±3%/±1.5%")
        bugs.append(f"   → Or TP/SL logic isn't working")
    
    if bugs:
        for bug in bugs:
            print(bug)
    else:
        print("✅ No critical bugs detected!")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 80)
    
    print("\n1. ✅ ADD CAPITAL CHECK (CRITICAL):")
    print("   Before opening position:")
    print("   if portfolio.capital < position_size:")
    print("       skip_trade()")
    
    print("\n2. ✅ ADD MAX POSITION LIMIT (CRITICAL):")
    print("   if len(open_positions) >= 20:")
    print("       skip_trade()")
    
    print("\n3. ✅ ADD TRADING COOLDOWN (RECOMMENDED):")
    print("   Don't open position if one opened in last 2-5 minutes")
    print("   This prevents opening 44 positions per hour!")
    
    print("\n4. ⚠️ VERIFY TP/SL LOGIC:")
    print("   0 positions closed in 7.5 hours seems unusual")
    print("   Check if TP/SL monitoring is working correctly")
    
    print("\n5. ✅ RUN NEW TEST WITH FIXES:")
    print("   Apply all fixes and run full 12-hour test")
    print("   Monitor with new Slack visual updates")
    
    # Readiness score
    print(f"\n🎯 READINESS FOR LIVE TRADING")
    print("-" * 80)
    
    score = 0
    reasons = []
    
    # Can't calculate win rate (no closed trades)
    reasons.append("❌ No closed trades: Can't calculate win rate")
    
    # Profitability
    if total_pnl < 0:
        reasons.append(f"❌ Unprofitable: ${total_pnl:.2f} loss")
    
    # Risk management
    if capital < 5000:
        reasons.append(f"❌ Over-leverage: {(total_invested / 5000):.1f}x capital")
    
    # Sample size
    reasons.append(f"⚠️ Incomplete test: Only 7.5 hours (interrupted)")
    
    print(f"\nReadiness Score: {score}/100")
    print(f"\n" + "\n".join(reasons))
    
    print("\n❌ VERDICT: NOT READY for live trading")
    print("   Critical bugs must be fixed first!")
    print("   Need complete 12-hour test with fixes applied")
    
    # Next steps
    print(f"\n📋 NEXT STEPS")
    print("-" * 80)
    print("\n1. Apply critical fixes (capital check + max positions)")
    print("2. Add cooldown to reduce aggressiveness")
    print("3. Verify TP/SL logic is working")
    print("4. Run new 12-hour test with all fixes")
    print("5. Monitor with visual Slack updates")
    print("6. Re-analyze results")
    print("7. Only go live when:")
    print("   ✅ No over-leverage")
    print("   ✅ Reasonable position count (≤20 at a time)")
    print("   ✅ Some positions close (TP/SL working)")
    print("   ✅ Win rate >55%")
    print("   ✅ Profitable overall")
    
    print("\n" + "=" * 80)
    print("💡 KEY INSIGHT: Over-leverage bug is SEVERE")
    print("   Bot would have lost real money if this was live!")
    print("   Paper trading saved you from a disaster!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    try:
        analyze_portfolio()
    except FileNotFoundError:
        print("❌ Portfolio state file not found!")
        print("   Expected: ~/ozzy-simple/logs/portfolio_state.json")
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
