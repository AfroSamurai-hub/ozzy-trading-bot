#!/usr/bin/env python3
"""
24/7 Baseline Test - Analyze performance by hour
Tests if baseline strategy works around the clock or only during high liquidity hours
"""

import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict

from demo_utils import ensure_demo_database, get_demo_db_path

def analyze_by_hour():
    """Analyze trading performance by hour of day"""
    
    # Connect to demo database
    try:
        demo_db = ensure_demo_database(get_demo_db_path())
    except Exception as exc:
        print(f"❌ Demo database error: {exc}")
        return
    
    conn = sqlite3.connect(demo_db)
    cursor = conn.cursor()
    
    # Get all completed trades
    cursor.execute('''
        SELECT entry_time, pnl, symbol, side 
        FROM demo_trades 
        WHERE status = 'closed' AND pnl IS NOT NULL
        ORDER BY entry_time
    ''')
    
    trades = cursor.fetchall()
    
    if not trades:
        print("📊 No trades found yet")
        return
    
    # Group by hour ranges
    hour_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0, 'pnls': []})
    
    for trade in trades:
        entry_time = datetime.strptime(trade[0], "%Y-%m-%d %H:%M:%S")
        hour = entry_time.hour
        pnl = trade[1]
        
        # Determine hour range
        if 0 <= hour < 6:
            hour_range = "00:00-06:00 (Overnight)"
        elif 6 <= hour < 12:
            hour_range = "06:00-12:00 (Morning)"
        elif 12 <= hour < 18:
            hour_range = "12:00-18:00 (Afternoon)"
        else:
            hour_range = "18:00-24:00 (Evening)"
        
        hour_stats[hour_range]['trades'] += 1
        hour_stats[hour_range]['total_pnl'] += pnl
        hour_stats[hour_range]['pnls'].append(pnl)
        if pnl > 0:
            hour_stats[hour_range]['wins'] += 1
    
    # Display results
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  📊 24/7 BASELINE TEST - PERFORMANCE BY HOUR                ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    
    total_trades = sum(stats['trades'] for stats in hour_stats.values())
    total_wins = sum(stats['wins'] for stats in hour_stats.values())
    total_pnl = sum(stats['total_pnl'] for stats in hour_stats.values())
    overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    print(f"║  Overall Performance:                                        ║")
    print(f"║     Total Trades: {total_trades:<10} Win Rate: {overall_win_rate:.1f}%{'':>18} ║")
    print(f"║     Total P&L: R{total_pnl:+,.2f}{'':>35} ║")
    print(f"║                                                              ║")
    
    # Hour breakdown
    print(f"║  Performance by Time of Day:                                 ║")
    print(f"║                                                              ║")
    
    for hour_range in ["00:00-06:00 (Overnight)", "06:00-12:00 (Morning)", 
                       "12:00-18:00 (Afternoon)", "18:00-24:00 (Evening)"]:
        if hour_range in hour_stats:
            stats = hour_stats[hour_range]
            trades = stats['trades']
            wins = stats['wins']
            win_rate = (wins / trades * 100) if trades > 0 else 0
            avg_pnl = stats['total_pnl'] / trades if trades > 0 else 0
            total_pnl = stats['total_pnl']
            
            # Determine performance icon
            if win_rate >= 55:
                icon = "✅"
            elif win_rate >= 45:
                icon = "⚠️"
            else:
                icon = "❌"
            
            print(f"║  {hour_range:<20}                    ║")
            print(f"║     Trades: {trades:<3} | Win Rate: {win_rate:5.1f}% | Avg: R{avg_pnl:+6.2f} {icon}    ║")
            print(f"║                                                              ║")
    
    # Analysis and recommendations
    print(f"║  🎯 ANALYSIS:                                                 ║")
    
    if overall_win_rate >= 55:
        print(f"║     ✅ SUCCESS! 24/7 trading works (>{overall_win_rate:.1f}% win rate)        ║")
        print(f"║     📈 Baseline strategy is robust across all hours          ║")
        print(f"║     🚀 RECOMMENDATION: Keep 24/7 trading enabled             ║")
    elif overall_win_rate >= 50:
        print(f"║     ⚠️  MIXED RESULTS ({overall_win_rate:.1f}% win rate)                        ║")
        print(f"║     📊 Some hours work better than others                    ║")
        print(f"║     🔧 RECOMMENDATION: Filter out worst performing hours     ║")
    else:
        print(f"║     ❌ POOR PERFORMANCE ({overall_win_rate:.1f}% win rate)                     ║")
        print(f"║     🕐 Time restrictions needed for profitability            ║")
        print(f"║     🔄 RECOMMENDATION: Revert to 8am-8pm trading hours       ║")
    
    print(f"║                                                              ║")
    
    # Show worst and best hours
    if hour_stats:
        best_hour = max(hour_stats.items(), key=lambda x: (x[1]['wins'] / x[1]['trades']) if x[1]['trades'] > 2 else 0)
        worst_hour = min(hour_stats.items(), key=lambda x: (x[1]['wins'] / x[1]['trades']) if x[1]['trades'] > 2 else 1)
        
        if best_hour[1]['trades'] > 2:
            best_win_rate = best_hour[1]['wins'] / best_hour[1]['trades'] * 100
            print(f"║  Best Hours: {best_hour[0]:<20} ({best_win_rate:.1f}%)       ║")
        
        if worst_hour[1]['trades'] > 2:
            worst_win_rate = worst_hour[1]['wins'] / worst_hour[1]['trades'] * 100
            print(f"║  Worst Hours: {worst_hour[0]:<20} ({worst_win_rate:.1f}%)      ║")
    
    print("╚══════════════════════════════════════════════════════════════╝")
    
    # Next steps
    print()
    print("📋 Next Steps:")
    if overall_win_rate >= 55:
        print("  1. ✅ 24/7 trading validated - keep current config")
        print("  2. 🚀 Proceed to 10% gain test (Phase 2)")
        print("  3. 📊 Monitor for 1 more day to confirm consistency")
    elif overall_win_rate >= 50:
        print("  1. 🔍 Identify worst performing hours")
        print("  2. ⚙️  Create time filter to avoid bad hours")
        print("  3. 🧪 Test filtered hours for 24 hours")
    else:
        print("  1. 🔄 Revert to 8am-8pm trading hours")
        print("  2. ✅ Stick with proven baseline approach")
        print("  3. 🚀 Proceed to 10% gain test with time restriction")
    
    conn.close()

def main():
    analyze_by_hour()

if __name__ == "__main__":
    main()
