#!/usr/bin/env python3
"""
📊 DAILY LEARNING REPORT - Milestone 1.2.5

Generates comprehensive daily report combining:
1. Pattern Performance Analysis
2. Volume Confirmation Analysis
3. Overall System Health
4. Actionable Next Steps

Usage:
    python3 generate_daily_report.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_pattern_performance import PatternPerformanceAnalyzer
from scripts.analyze_volume_impact import VolumeImpactAnalyzer
from scripts.track_trade_outcomes import TradeOutcomeTracker


def generate_daily_report():
    """Generate comprehensive daily learning report"""
    
    print("="*70)
    print("📊 OZZY DAILY LEARNING REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Initialize analyzers
    tracker = TradeOutcomeTracker()
    pattern_analyzer = PatternPerformanceAnalyzer()
    volume_analyzer = VolumeImpactAnalyzer()
    
    # Get overall stats
    stats = tracker.get_stats()
    
    # SECTION 1: System Health
    print("\n" + "="*70)
    print("🏥 SYSTEM HEALTH")
    print("="*70)
    print(f"Total Labeled Trades: {stats['total_labeled']}")
    print(f"Pending Trades: {stats['pending_trades']}")
    print(f"\nOverall Performance:")
    print(f"  Win Rate: {stats['win_rate']}")
    print(f"  Avg P&L: {stats['avg_pnl']}")
    print(f"\nOutcome Breakdown:")
    for outcome, count in stats['outcome_breakdown'].items():
        print(f"  {outcome}: {count}")
    
    # SECTION 2: Pattern Performance
    print("\n" + "="*70)
    print("🎯 PATTERN PERFORMANCE ANALYSIS")
    print("="*70)
    pattern_report = pattern_analyzer.generate_report(detailed=False)
    print(pattern_report)
    
    # SECTION 3: Volume Impact
    print("\n" + "="*70)
    print("📊 VOLUME CONFIRMATION ANALYSIS")
    print("="*70)
    volume_report = volume_analyzer.generate_report()
    print(volume_report)
    
    # SECTION 4: Integrated Actions
    print("\n" + "="*70)
    print("🎯 INTEGRATED ACTION PLAN")
    print("="*70)
    
    # Get pattern actions
    pattern_stats = pattern_analyzer.calculate_pattern_stats()
    pattern_actions = pattern_analyzer.generate_actions(pattern_stats)
    
    # Get volume analysis
    volume_analysis = volume_analyzer.analyze_volume_impact()
    
    print("\n📋 PRIORITY ACTIONS:")
    print("-" * 70)
    
    action_num = 1
    
    # Volume filter (highest priority if confirmed)
    if volume_analysis['validation']['status'] in ['CONFIRMED', 'PROMISING']:
        delta = volume_analysis['delta']['win_rate_improvement']
        print(f"{action_num}. ✅ IMPLEMENT VOLUME FILTER (Milestone 1.10)")
        print(f"   Impact: +{delta*100:.0f} percentage points win rate")
        print(f"   Action: Require >1.5× volume for all trades")
        action_num += 1
    
    # Pattern-specific actions
    disable_patterns = [a for a in pattern_actions if a['action'] == 'DISABLE']
    boost_patterns = [a for a in pattern_actions if a['action'] == 'BOOST']
    
    if disable_patterns:
        print(f"\n{action_num}. ❌ DISABLE LOW PERFORMERS (Milestone 1.9)")
        for action in disable_patterns:
            print(f"   - {action['pattern']}: {action['win_rate']*100:.0f}% WR (threshold: 40%)")
        action_num += 1
    
    if boost_patterns:
        print(f"\n{action_num}. 📈 BOOST HIGH PERFORMERS (Milestone 1.9)")
        for action in boost_patterns:
            print(f"   - {action['pattern']}: {action['win_rate']*100:.0f}% WR → confidence {action['current_confidence']*100:.0f}% → {action['suggested_confidence']*100:.0f}%")
        action_num += 1
    
    # Data collection priority
    if stats['total_labeled'] < 50:
        print(f"\n{action_num}. 📊 COLLECT MORE DATA (Milestone 1.3)")
        print(f"   Current: {stats['total_labeled']} trades | Target: 50+")
        print(f"   Action: Continue Paper Trading Week")
        action_num += 1
    
    # SECTION 5: Research Progress
    print("\n" + "="*70)
    print("📚 RESEARCH VALIDATION PROGRESS")
    print("="*70)
    
    milestones = []
    
    # Pattern Performance (1.9)
    pattern_validation = pattern_analyzer.validate_against_research(pattern_stats)
    avg_top_wr = pattern_validation.get('avg_top_win_rate', 0)
    milestones.append({
        'number': '1.9',
        'name': 'Pattern Filtering',
        'status': pattern_validation['status'],
        'progress': f"Top patterns: {avg_top_wr*100:.0f}% WR (target: 70-84%)"
    })
    
    # Volume Confirmation (1.10)
    volume_validation = volume_analysis['validation']
    delta = volume_analysis['delta']['win_rate_improvement']
    milestones.append({
        'number': '1.10',
        'name': 'Volume Confirmation',
        'status': volume_validation['status'],
        'progress': f"+{delta*100:.0f} points improvement (target: +23)"
    })
    
    for m in milestones:
        status_emoji = {
            'CONFIRMED': '✅',
            'ON_TRACK': '✅',
            'PROMISING': '🟡',
            'PRELIMINARY': '⏸️',
            'INSUFFICIENT_DATA': '❌',
            'NEEDS_IMPROVEMENT': '⚠️'
        }
        emoji = status_emoji.get(m['status'], '❓')
        print(f"{emoji} Milestone {m['number']}: {m['name']}")
        print(f"   Status: {m['status']}")
        print(f"   {m['progress']}")
    
    # SECTION 6: Next Steps
    print("\n" + "="*70)
    print("🔗 NEXT STEPS")
    print("="*70)
    print("1. Continue collecting trade data (target: 50+ trades)")
    print("2. Build Regime Performance Analyzer (Day 4)")
    print("3. Build Confidence Calibrator (Day 5)")
    print("4. Build Learning Engine with auto-updates (Day 6)")
    print("5. Complete all 5 quality reports (Day 7)")
    print("="*70)


if __name__ == '__main__':
    generate_daily_report()
