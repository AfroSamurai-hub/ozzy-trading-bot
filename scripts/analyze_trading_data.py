#!/usr/bin/env python3
"""
Analyze Trading Data and Generate AI Learning Insights

This script analyzes recent trading data to help the AI learn and improve.
It follows professional quant research practices to identify patterns,
calibrate confidence, and optimize strategy parameters.

Philosophy: "Evolve, not add and break" - Learn from data!
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import statistics

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.currency import format_currency, format_currency_signed, get_currency_code

def load_portfolio_data() -> Dict:
    """Load current portfolio state"""
    portfolio_file = PROJECT_ROOT / "logs/portfolio_state.json"
    if not portfolio_file.exists():
        print("❌ No portfolio data found!")
        return {}
    
    with open(portfolio_file, 'r') as f:
        return json.load(f)

def load_decisions_data() -> Dict:
    """Load decision history"""
    decisions_file = PROJECT_ROOT / "logs/decisions.json"
    if not decisions_file.exists():
        print("⚠️  No decisions data found!")
        return {"decisions": []}
    
    with open(decisions_file, 'r') as f:
        data = json.load(f)
        # Handle both old and new format
        if isinstance(data, dict) and "decisions" in data:
            return data
        return {"decisions": []}

def analyze_open_positions(portfolio: Dict) -> Dict[str, Any]:
    """Analyze current open positions"""
    positions = portfolio.get("positions", [])
    
    if not positions:
        return {
            "count": 0,
            "total_size": 0,
            "avg_pnl_pct": 0,
            "underwater_count": 0,
            "insights": []
        }
    
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    total_pnl_pct = sum(p.get("pnl_pct", 0) for p in positions)
    avg_pnl_pct = total_pnl_pct / len(positions)
    
    underwater = [p for p in positions if p.get("pnl", 0) < 0]
    
    # Analyze entry prices
    entry_prices = [p.get("entry_price", 0) for p in positions]
    current_price = positions[0].get("current_price", 0) if positions else 0
    
    insights = []
    
    # Check if all entries at same price (clustering)
    if len(set(entry_prices)) == 1 and len(positions) > 1:
        insights.append({
            "type": "clustering",
            "severity": "warning",
            "message": f"All {len(positions)} positions entered at same price ${entry_prices[0]:,.2f}",
            "recommendation": "Consider spreading entries over time to reduce timing risk"
        })
    
    # Check if currently underwater
    if len(underwater) == len(positions):
        insights.append({
            "type": "drawdown",
            "severity": "warning",
            "message": f"All {len(positions)} positions underwater (avg {avg_pnl_pct:.2f}%)",
            "recommendation": "Price moved against entries - validate entry timing strategy"
        })
    
    # Check confidence patterns
    confidences = [p.get("confidence", 0) for p in positions]
    if all(c == confidences[0] for c in confidences):
        insights.append({
            "type": "confidence",
            "severity": "info",
            "message": f"All positions have same confidence ({confidences[0]:.0%})",
            "recommendation": "AI may not be differentiating trade quality - check confidence calibration"
        })
    
    return {
        "count": len(positions),
        "total_size": sum(p.get("size", 0) for p in positions),
        "total_pnl": total_pnl,
        "avg_pnl_pct": avg_pnl_pct,
        "underwater_count": len(underwater),
        "underwater_pct": len(underwater) / len(positions) * 100 if positions else 0,
        "current_price": current_price,
        "avg_entry_price": statistics.mean(entry_prices) if entry_prices else 0,
        "price_move_pct": ((current_price - statistics.mean(entry_prices)) / statistics.mean(entry_prices) * 100) if entry_prices and current_price > 0 else 0,
        "insights": insights
    }

def analyze_ai_reasoning(portfolio: Dict) -> Dict[str, Any]:
    """Analyze AI reasoning patterns"""
    positions = portfolio.get("positions", [])
    
    if not positions:
        return {"pattern_usage": {}, "insights": []}
    
    # Extract patterns from reasons
    pattern_mentions = {}
    confidence_levels = []
    
    for pos in positions:
        reason = pos.get("reason", "")
        confidence = pos.get("confidence", 0)
        confidence_levels.append(confidence)
        
        # Count pattern mentions
        if "whale accumulation" in reason.lower():
            pattern_mentions["whale_accumulation"] = pattern_mentions.get("whale_accumulation", 0) + 1
        if "rsi" in reason.lower():
            pattern_mentions["rsi"] = pattern_mentions.get("rsi", 0) + 1
        if "volume" in reason.lower():
            pattern_mentions["volume"] = pattern_mentions.get("volume", 0) + 1
    
    insights = []
    
    # Check if over-relying on one pattern
    if pattern_mentions:
        most_used = max(pattern_mentions.items(), key=lambda x: x[1])
        usage_rate = most_used[1] / len(positions) * 100
        
        if usage_rate > 80:
            insights.append({
                "type": "pattern_overuse",
                "severity": "warning",
                "message": f"Pattern '{most_used[0]}' used in {usage_rate:.0f}% of trades",
                "recommendation": "AI may be over-fitting to one pattern - diversify pattern usage"
            })
    
    # Check confidence calibration
    if confidence_levels:
        avg_confidence = statistics.mean(confidence_levels)
        std_confidence = statistics.stdev(confidence_levels) if len(confidence_levels) > 1 else 0
        
        if std_confidence < 0.05:
            insights.append({
                "type": "confidence_flatline",
                "severity": "warning",
                "message": f"Low confidence variation (σ={std_confidence:.3f})",
                "recommendation": "AI not differentiating trade quality - retrain or adjust confidence calculation"
            })
    
    return {
        "pattern_usage": pattern_mentions,
        "avg_confidence": statistics.mean(confidence_levels) if confidence_levels else 0,
        "confidence_std": statistics.stdev(confidence_levels) if len(confidence_levels) > 1 else 0,
        "insights": insights
    }

def analyze_timing(portfolio: Dict) -> Dict[str, Any]:
    """Analyze entry timing"""
    positions = portfolio.get("positions", [])
    
    if not positions:
        return {"insights": []}
    
    # Parse entry times
    entry_times = []
    for pos in positions:
        try:
            entry_time = datetime.fromisoformat(pos.get("entry_time", ""))
            entry_times.append(entry_time)
        except:
            pass
    
    if not entry_times:
        return {"insights": []}
    
    insights = []
    
    # Check if all entries clustered in time
    if len(entry_times) > 1:
        time_span = (max(entry_times) - min(entry_times)).total_seconds() / 60  # minutes
        if time_span < 10 and len(positions) > 3:
            insights.append({
                "type": "time_clustering",
                "severity": "warning",
                "message": f"{len(positions)} positions opened in {time_span:.1f} minutes",
                "recommendation": "Rapid-fire entries = no time for market response - consider longer intervals"
            })
    
    # Check time of day
    if entry_times:
        avg_hour = statistics.mean([t.hour for t in entry_times])
        insights.append({
            "type": "time_of_day",
            "severity": "info",
            "message": f"Average entry time: {int(avg_hour):02d}:00 SAST",
            "recommendation": "Track win rate by time of day to find optimal trading hours"
        })
    
    return {
        "first_entry": min(entry_times).isoformat() if entry_times else None,
        "last_entry": max(entry_times).isoformat() if entry_times else None,
        "time_span_minutes": (max(entry_times) - min(entry_times)).total_seconds() / 60 if len(entry_times) > 1 else 0,
        "insights": insights
    }

def generate_recommendations(
    position_analysis: Dict,
    reasoning_analysis: Dict,
    timing_analysis: Dict,
    portfolio: Dict
) -> List[Dict]:
    """Generate actionable recommendations"""
    recommendations = []
    
    # Compile all insights
    all_insights = (
        position_analysis.get("insights", []) +
        reasoning_analysis.get("insights", []) +
        timing_analysis.get("insights", [])
    )
    
    # Priority 1: Critical issues
    critical = [i for i in all_insights if i.get("severity") == "critical"]
    if critical:
        recommendations.append({
            "priority": "CRITICAL",
            "action": "STOP_TRADING",
            "reason": critical[0]["message"],
            "details": critical[0]["recommendation"]
        })
    
    # Priority 2: Current performance issues
    if position_analysis.get("underwater_pct", 0) == 100:
        recommendations.append({
            "priority": "HIGH",
            "action": "VALIDATE_ENTRY_TIMING",
            "reason": "All positions currently negative",
            "details": f"Price moved {position_analysis.get('price_move_pct', 0):.2f}% against entries. "
                      "Consider: (1) waiting for better entry signals, (2) using limit orders, "
                      "(3) checking if pattern predictions are accurate."
        })
    
    # Priority 3: Pattern diversification
    pattern_usage = reasoning_analysis.get("pattern_usage", {})
    if len(pattern_usage) == 1:
        pattern_name = list(pattern_usage.keys())[0]
        recommendations.append({
            "priority": "MEDIUM",
            "action": "DIVERSIFY_PATTERNS",
            "reason": f"Using only '{pattern_name}' pattern",
            "details": "Single pattern = single point of failure. Enable more pattern types "
                      "or adjust pattern selection criteria to increase diversity."
        })
    
    # Priority 4: Confidence calibration
    if reasoning_analysis.get("confidence_std", 0) < 0.05:
        recommendations.append({
            "priority": "MEDIUM",
            "action": "RECALIBRATE_CONFIDENCE",
            "reason": "Confidence scores not varying between trades",
            "details": f"All trades around {reasoning_analysis.get('avg_confidence', 0):.0%} confidence. "
                      "AI should show more discrimination - adjust confidence calculation or retrain."
        })
    
    # Priority 5: Entry timing
    if timing_analysis.get("time_span_minutes", 0) < 10 and position_analysis.get("count", 0) > 3:
        recommendations.append({
            "priority": "LOW",
            "action": "SPREAD_ENTRIES",
            "reason": "Entries clustered in short time window",
            "details": "Opening multiple positions quickly = no time to assess market response. "
                      "Consider: (1) increase decision interval, (2) limit positions per hour, "
                      "(3) wait for price confirmation."
        })
    
    return recommendations

def print_analysis_report(portfolio: Dict):
    """Print comprehensive analysis report"""
    currency = get_currency_code()
    
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "📊 TRADING DATA ANALYSIS 📊" + " " * 31 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    # Portfolio overview
    print("💰 PORTFOLIO OVERVIEW")
    print("─" * 80)
    print(f"   Starting Capital:  {format_currency(portfolio.get('starting_capital', 0))}")
    print(f"   Current Capital:   {format_currency(portfolio.get('capital', 0))}")
    print(f"   Total Equity:      {format_currency(portfolio.get('total_equity', 0))}")
    print(f"   Total P&L:         {format_currency_signed(portfolio.get('total_pnl', 0))} "
          f"({portfolio.get('total_pnl', 0) / portfolio.get('starting_capital', 1) * 100:+.2f}%)")
    print()
    
    # Position analysis
    print("📈 POSITION ANALYSIS")
    print("─" * 80)
    pos_analysis = analyze_open_positions(portfolio)
    print(f"   Open Positions:    {pos_analysis['count']}/20")
    print(f"   Total Deployed:    {format_currency(pos_analysis['total_size'])}")
    print(f"   Current Price:     {format_currency(pos_analysis['current_price'])}")
    print(f"   Avg Entry Price:   {format_currency(pos_analysis['avg_entry_price'])}")
    print(f"   Price Movement:    {pos_analysis['price_move_pct']:+.2f}%")
    print(f"   Avg Position P&L:  {pos_analysis['avg_pnl_pct']:+.2f}%")
    print(f"   Underwater:        {pos_analysis['underwater_count']}/{pos_analysis['count']} "
          f"({pos_analysis['underwater_pct']:.0f}%)")
    print()
    
    # AI reasoning analysis
    print("🧠 AI REASONING ANALYSIS")
    print("─" * 80)
    reasoning_analysis = analyze_ai_reasoning(portfolio)
    print(f"   Avg Confidence:    {reasoning_analysis['avg_confidence']:.1%}")
    print(f"   Confidence StdDev: {reasoning_analysis['confidence_std']:.3f}")
    print(f"   Pattern Usage:")
    for pattern, count in reasoning_analysis['pattern_usage'].items():
        pct = count / pos_analysis['count'] * 100 if pos_analysis['count'] > 0 else 0
        print(f"      • {pattern}: {count} trades ({pct:.0f}%)")
    print()
    
    # Timing analysis
    print("⏰ TIMING ANALYSIS")
    print("─" * 80)
    timing_analysis = analyze_timing(portfolio)
    if timing_analysis.get('first_entry'):
        print(f"   First Entry:       {timing_analysis['first_entry']}")
        print(f"   Last Entry:        {timing_analysis['last_entry']}")
        print(f"   Time Span:         {timing_analysis['time_span_minutes']:.1f} minutes")
    else:
        print(f"   No timing data available")
    print()
    
    # Insights
    print("💡 KEY INSIGHTS")
    print("─" * 80)
    all_insights = (
        pos_analysis.get("insights", []) +
        reasoning_analysis.get("insights", []) +
        timing_analysis.get("insights", [])
    )
    
    if all_insights:
        for i, insight in enumerate(all_insights, 1):
            severity_emoji = {
                "critical": "🔴",
                "warning": "⚠️",
                "info": "ℹ️"
            }.get(insight['severity'], "•")
            
            print(f"   {severity_emoji} {insight['type'].upper()}")
            print(f"      Problem: {insight['message']}")
            print(f"      Action:  {insight['recommendation']}")
            print()
    else:
        print("   ✅ No significant issues detected")
        print()
    
    # Recommendations
    print("🎯 RECOMMENDATIONS")
    print("─" * 80)
    recommendations = generate_recommendations(
        pos_analysis,
        reasoning_analysis,
        timing_analysis,
        portfolio
    )
    
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            priority_emoji = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🟢"
            }.get(rec['priority'], "•")
            
            print(f"   {priority_emoji} [{rec['priority']}] {rec['action']}")
            print(f"      Why:  {rec['reason']}")
            print(f"      How:  {rec['details']}")
            print()
    else:
        print("   ✅ System performing well - continue current strategy")
        print()
    
    print("═" * 80)
    print()
    
    # Summary
    print("📋 QUICK SUMMARY")
    print("─" * 80)
    
    if pos_analysis['count'] == 0:
        print("   🟢 No positions open - ready to trade")
    elif pos_analysis['underwater_pct'] == 100:
        print("   🔴 All positions negative - review entry strategy")
    elif pos_analysis['underwater_pct'] > 50:
        print("   🟡 Most positions negative - monitor closely")
    else:
        print("   🟢 Positions mixed - normal trading activity")
    
    if reasoning_analysis['confidence_std'] < 0.05:
        print("   🟡 Confidence not varying - check AI calibration")
    else:
        print("   🟢 Confidence varying appropriately")
    
    if len(reasoning_analysis['pattern_usage']) == 1:
        print("   🟡 Using single pattern - consider diversifying")
    else:
        print("   🟢 Multiple patterns in use")
    
    print()
    print("═" * 80)

def main():
    print("\n🔍 Loading trading data...\n")
    
    portfolio = load_portfolio_data()
    if not portfolio:
        print("❌ No portfolio data to analyze!")
        return
    
    decisions = load_decisions_data()
    
    print_analysis_report(portfolio)
    
    print("\n💾 Analysis complete! Data logged for AI learning.\n")
    print("📚 Next steps:")
    print("   1. Review recommendations above")
    print("   2. Adjust strategy parameters if needed")
    print("   3. Continue testing to collect more data")
    print("   4. Compare before/after metrics over time")
    print()

if __name__ == "__main__":
    main()
