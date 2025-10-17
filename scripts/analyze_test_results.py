#!/usr/bin/env python3
"""
Complete analysis of overnight test results.
Run this tomorrow morning to get HONEST assessment.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_portfolio_state() -> Dict[str, Any]:
    """Load the final portfolio state."""
    portfolio_file = PROJECT_ROOT / "logs/portfolio_state.json"
    with open(portfolio_file, "r") as f:
        return json.load(f)


def analyze_positions(data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze all positions - open and closed."""
    positions = data.get("positions", [])
    closed_trades = data.get("closed_trades", [])
    
    # Open positions analysis
    open_positions = [p for p in positions if p.get("status") == "OPEN"]
    total_open_pnl = sum(p.get("unrealized_pnl", 0) for p in open_positions)
    
    # Closed trades analysis
    wins = [t for t in closed_trades if t.get("outcome") == "WIN"]
    losses = [t for t in closed_trades if t.get("outcome") == "LOSS"]
    
    total_closed_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades)
    
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    
    # Average win/loss
    avg_win = sum(t.get("realized_pnl", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("realized_pnl", 0) for t in losses) / len(losses) if losses else 0
    
    # Best and worst trades
    best_trade = max(closed_trades, key=lambda t: t.get("realized_pnl", 0)) if closed_trades else None
    worst_trade = min(closed_trades, key=lambda t: t.get("realized_pnl", 0)) if closed_trades else None
    
    return {
        "total_positions_opened": len(positions),
        "open_positions": len(open_positions),
        "closed_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_open_pnl": total_open_pnl,
        "total_closed_pnl": total_closed_pnl,
        "total_pnl": data.get("total_pnl", 0),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "final_capital": data.get("capital", 5000),
    }


def analyze_decision_patterns() -> Dict[str, Any]:
    """Analyze AI decision patterns."""
    decisions_file = PROJECT_ROOT / "logs/decisions.json"
    if not decisions_file.exists():
        return {}
    
    with open(decisions_file, "r") as f:
        data = json.load(f)
    
    decisions = data.get("decisions", [])
    
    buy_decisions = [d for d in decisions if d.get("action") == "BUY"]
    sell_decisions = [d for d in decisions if d.get("action") == "SELL"]
    skip_decisions = [d for d in decisions if d.get("action") == "SKIP"]
    
    # Average confidence
    avg_confidence = sum(d.get("confidence", 0) for d in buy_decisions) / len(buy_decisions) if buy_decisions else 0
    
    # Most common reasons
    reasons = {}
    for d in buy_decisions:
        reason = d.get("reasoning", "Unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    
    top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        "total_decisions": len(decisions),
        "buy_count": len(buy_decisions),
        "sell_count": len(sell_decisions),
        "skip_count": len(skip_decisions),
        "avg_confidence": avg_confidence,
        "top_reasons": top_reasons,
    }


def identify_bugs_and_issues(analysis: Dict[str, Any]) -> List[str]:
    """Identify critical bugs and issues."""
    issues = []
    
    # Bug #1: Over-leverage
    total_opened = analysis.get("total_positions_opened", 0)
    if total_opened * 250 > 5000:
        over_leverage = (total_opened * 250) - 5000
        issues.append(
            f"🐛 CRITICAL: Over-leveraged by ${over_leverage:.2f}! "
            f"Opened {total_opened} positions on $5,000 capital. "
            "Missing capital check before opening positions."
        )
    
    # Bug #2: Too aggressive
    if analysis.get("buy_count", 0) > 100:
        issues.append(
            f"⚠️ TOO AGGRESSIVE: Made {analysis.get('buy_count')} BUY decisions! "
            "AI is buying on every signal. Need cooldown or max position limit."
        )
    
    # Issue #3: Low win rate
    if analysis.get("win_rate", 0) < 50 and analysis.get("closed_trades", 0) > 10:
        issues.append(
            f"📉 LOW WIN RATE: {analysis.get('win_rate'):.1f}% (target: >55%). "
            "Pattern matching or TP/SL settings need adjustment."
        )
    
    # Issue #4: Unprofitable
    if analysis.get("total_pnl", 0) < 0 and analysis.get("closed_trades", 0) > 10:
        issues.append(
            f"💸 UNPROFITABLE: Total P&L is ${analysis.get('total_pnl'):.2f}. "
            "Strategy needs refinement before live trading."
        )
    
    return issues


def generate_recommendations(analysis: Dict[str, Any], issues: List[str]) -> List[str]:
    """Generate actionable recommendations."""
    recommendations = []
    
    # Fix #1: Add capital checks
    if "Over-leveraged" in str(issues):
        recommendations.append(
            "✅ ADD CAPITAL CHECK: Before opening position, verify: "
            "`if portfolio.capital < position_size: skip_trade()`"
        )
        recommendations.append(
            "✅ ADD MAX POSITIONS: Limit to 20 positions max (20 × $250 = $5,000)"
        )
    
    # Fix #2: Reduce aggressiveness
    if "TOO AGGRESSIVE" in str(issues):
        recommendations.append(
            "✅ ADD COOLDOWN: Don't open position if one was opened in last 5 minutes"
        )
        recommendations.append(
            "✅ INCREASE THRESHOLD: Raise confidence from 60% to 75% or 80%"
        )
    
    # Fix #3: Improve win rate
    if "LOW WIN RATE" in str(issues):
        recommendations.append(
            "✅ REFINE PATTERNS: Use only patterns with >70% historical win rate"
        )
        recommendations.append(
            "✅ ADJUST TP/SL: Try +2%/-1% or +4%/-2% ratios"
        )
    
    # Fix #4: Strategy overhaul
    if "UNPROFITABLE" in str(issues):
        recommendations.append(
            "⚠️ STRATEGY REVIEW: Analyze losing trades to find common patterns"
        )
        recommendations.append(
            "⚠️ CONSIDER: Different timeframes, indicators, or market conditions"
        )
    
    # Always recommend
    recommendations.append(
        "✅ RETEST: Run another 12-hour test with fixes applied"
    )
    
    return recommendations


def calculate_readiness_score(analysis: Dict[str, Any]) -> tuple[int, str]:
    """Calculate readiness for live trading (0-100)."""
    score = 0
    reasons = []
    
    # Win rate (40 points possible)
    win_rate = analysis.get("win_rate", 0)
    if win_rate >= 60:
        score += 40
        reasons.append(f"✅ Win rate: {win_rate:.1f}% (excellent)")
    elif win_rate >= 55:
        score += 30
        reasons.append(f"✅ Win rate: {win_rate:.1f}% (good)")
    elif win_rate >= 50:
        score += 20
        reasons.append(f"⚠️ Win rate: {win_rate:.1f}% (marginal)")
    else:
        reasons.append(f"❌ Win rate: {win_rate:.1f}% (too low)")
    
    # Profitability (30 points possible)
    total_pnl = analysis.get("total_pnl", 0)
    if total_pnl > 100:
        score += 30
        reasons.append(f"✅ P&L: +${total_pnl:.2f} (profitable)")
    elif total_pnl > 0:
        score += 20
        reasons.append(f"✅ P&L: +${total_pnl:.2f} (slightly profitable)")
    elif total_pnl > -50:
        score += 10
        reasons.append(f"⚠️ P&L: ${total_pnl:.2f} (small loss)")
    else:
        reasons.append(f"❌ P&L: ${total_pnl:.2f} (significant loss)")
    
    # Risk management (20 points possible)
    final_capital = analysis.get("final_capital", 5000)
    if final_capital >= 5000:
        score += 20
        reasons.append("✅ Capital preserved")
    elif final_capital >= 4500:
        score += 10
        reasons.append("⚠️ Small capital loss")
    else:
        reasons.append("❌ Significant capital loss")
    
    # Sample size (10 points possible)
    closed_trades = analysis.get("closed_trades", 0)
    if closed_trades >= 20:
        score += 10
        reasons.append(f"✅ Good sample size: {closed_trades} trades")
    elif closed_trades >= 10:
        score += 5
        reasons.append(f"⚠️ Adequate sample: {closed_trades} trades")
    else:
        reasons.append(f"❌ Too few trades: {closed_trades}")
    
    return score, "\n".join(reasons)


def print_report():
    """Print comprehensive analysis report."""
    print("\n" + "=" * 80)
    print("🔍 OVERNIGHT TEST ANALYSIS - COMPLETE HONEST REVIEW")
    print("=" * 80)
    
    # Load data
    portfolio_data = load_portfolio_state()
    
    # Run analysis
    position_analysis = analyze_positions(portfolio_data)
    decision_analysis = analyze_decision_patterns()
    
    # Merge analysis
    full_analysis = {**position_analysis, **decision_analysis}
    
    # Print portfolio summary
    print("\n📊 PORTFOLIO SUMMARY")
    print("-" * 80)
    print(f"Starting Capital:        ${5000:.2f}")
    print(f"Final Capital:           ${full_analysis.get('final_capital', 0):.2f}")
    print(f"Total P&L:               ${full_analysis.get('total_pnl', 0):.2f}")
    print(f"Return:                  {(full_analysis.get('total_pnl', 0) / 5000 * 100):.2f}%")
    
    # Print trading stats
    print("\n📈 TRADING STATISTICS")
    print("-" * 80)
    print(f"Total Positions Opened:  {full_analysis.get('total_positions_opened', 0)}")
    print(f"Still Open:              {full_analysis.get('open_positions', 0)}")
    print(f"Closed Trades:           {full_analysis.get('closed_trades', 0)}")
    print(f"  - Wins:                {full_analysis.get('wins', 0)}")
    print(f"  - Losses:              {full_analysis.get('losses', 0)}")
    print(f"Win Rate:                {full_analysis.get('win_rate', 0):.1f}%")
    
    # Print P&L breakdown
    print("\n💰 P&L BREAKDOWN")
    print("-" * 80)
    print(f"Open Positions P&L:      ${full_analysis.get('total_open_pnl', 0):.2f}")
    print(f"Closed Trades P&L:       ${full_analysis.get('total_closed_pnl', 0):.2f}")
    print(f"Average Win:             ${full_analysis.get('avg_win', 0):.2f}")
    print(f"Average Loss:            ${full_analysis.get('avg_loss', 0):.2f}")
    
    if full_analysis.get('best_trade'):
        best = full_analysis['best_trade']
        print(f"\nBest Trade:              +${best.get('realized_pnl', 0):.2f} "
              f"({best.get('symbol')} @ ${best.get('entry_price', 0):.2f})")
    
    if full_analysis.get('worst_trade'):
        worst = full_analysis['worst_trade']
        print(f"Worst Trade:             ${worst.get('realized_pnl', 0):.2f} "
              f"({worst.get('symbol')} @ ${worst.get('entry_price', 0):.2f})")
    
    # Print AI decision patterns
    print("\n🧠 AI DECISION PATTERNS")
    print("-" * 80)
    print(f"Total Decisions:         {full_analysis.get('total_decisions', 0)}")
    print(f"  - BUY:                 {full_analysis.get('buy_count', 0)}")
    print(f"  - SELL:                {full_analysis.get('sell_count', 0)}")
    print(f"  - SKIP:                {full_analysis.get('skip_count', 0)}")
    print(f"Average Confidence:      {full_analysis.get('avg_confidence', 0):.1f}%")
    
    if full_analysis.get('top_reasons'):
        print("\nTop Reasons for BUY:")
        for i, (reason, count) in enumerate(full_analysis['top_reasons'], 1):
            print(f"  {i}. {reason[:60]}... ({count} times)")
    
    # Identify bugs
    print("\n🐛 BUGS & ISSUES IDENTIFIED")
    print("-" * 80)
    issues = identify_bugs_and_issues(full_analysis)
    if issues:
        for issue in issues:
            print(f"\n{issue}")
    else:
        print("✅ No critical bugs detected!")
    
    # Generate recommendations
    print("\n💡 RECOMMENDATIONS")
    print("-" * 80)
    recommendations = generate_recommendations(full_analysis, issues)
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec}")
    
    # Calculate readiness score
    print("\n🎯 READINESS FOR LIVE TRADING")
    print("-" * 80)
    score, reasoning = calculate_readiness_score(full_analysis)
    print(f"\nReadiness Score: {score}/100")
    print(f"\n{reasoning}")
    
    if score >= 80:
        print("\n✅ VERDICT: READY for live trading with small capital ($100-$500)")
        print("   Recommend: Start with 1-2 week live test, then scale up")
    elif score >= 60:
        print("\n⚠️ VERDICT: NEEDS IMPROVEMENT before live trading")
        print("   Recommend: Fix identified issues, run another overnight test")
    else:
        print("\n❌ VERDICT: NOT READY for live trading")
        print("   Recommend: Significant strategy overhaul needed")
    
    # Final summary
    print("\n" + "=" * 80)
    print("📋 NEXT STEPS")
    print("=" * 80)
    
    if score >= 80:
        print("\n1. Review recommendations above")
        print("2. Implement any remaining fixes")
        print("3. Set up live trading account with $100-$500")
        print("4. Run 1-week live test")
        print("5. Monitor closely and iterate")
    elif score >= 60:
        print("\n1. Fix all critical bugs listed above")
        print("2. Implement recommended improvements")
        print("3. Run another 12-hour paper trading test")
        print("4. Re-analyze results")
        print("5. Only go live when score > 80")
    else:
        print("\n1. Analyze losing trades in detail")
        print("2. Reconsider strategy fundamentals")
        print("3. Test different parameters (TP/SL, confidence, cooldown)")
        print("4. Consider different patterns or indicators")
        print("5. Run multiple paper tests until profitable")
    
    print("\n" + "=" * 80)
    print("🎓 REMEMBER: Profitable paper trading ≠ guaranteed live success")
    print("   But unprofitable paper trading = guaranteed live failure!")
    print("   Take your time, iterate, and don't rush into live trading.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    print_report()
