#!/usr/bin/env python3
"""
500 Trade Sanity Check - Progress tracker to 500 trades
"""

import sqlite3
import os

def check_progress():
    """Check progress toward 500 trades"""
    
    conn = sqlite3.connect('ozzy_simple.db')
    cursor = conn.cursor()
    
    # Get current baseline trade count
    cursor.execute('''
    SELECT 
      COUNT(*) as current_total,
      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
      ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate,
      ROUND(SUM(pnl), 2) as total_pnl,
      ROUND(AVG(pnl), 2) as avg_pnl
    FROM trades
    WHERE entry_reason LIKE 'BASELINE_%'
    ''')
    
    result = cursor.fetchone()
    current_total, wins, win_rate, total_pnl, avg_pnl = result
    
    target = 500
    remaining = target - current_total
    progress_pct = (current_total / target) * 100
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  🎯 SANITY CHECK PROGRESS TO 500 TRADES                     ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Current Trades: {current_total:<10} Target: {target:<10}            ║")
    print(f"║  Remaining:      {remaining:<10} Progress: {progress_pct:.1f}%{'':>11} ║")
    print(f"║                                                              ║")
    print(f"║  📊 CURRENT PERFORMANCE:                                     ║")
    print(f"║     Win Rate:        {win_rate}%{'':>30} ║")
    print(f"║     Total P&L:       R{total_pnl:,.2f}{'':>25} ║")
    print(f"║     Avg per Trade:   R{avg_pnl:.2f}{'':>25} ║")
    print(f"║     Total Wins:      {wins}{'':>30} ║")
    
    # Progress bar
    filled = int(progress_pct / 5)  # 20 blocks total
    bar = "█" * filled + "░" * (20 - filled)
    print(f"║                                                              ║")
    print(f"║  Progress: [{bar}] {progress_pct:.1f}%{'':>10} ║")
    
    # Show recent trades
    if current_total > 0:
        print("║                                                              ║")
        print("║  🕒 RECENT TRADES:                                           ║")
        cursor.execute('''
            SELECT symbol, side, pnl, entry_timestamp 
            FROM trades 
            WHERE pnl IS NOT NULL
            ORDER BY entry_timestamp DESC 
            LIMIT 5
        ''')
        recent = cursor.fetchall()
        
        for trade in recent[:5]:  # Show last 5
            symbol = trade[0]
            side = trade[1]
            pnl = trade[2]
            time = trade[3][-8:-3] if trade[3] else "N/A"  # Just time
            pnl_icon = "✅" if pnl and pnl > 0 else "❌"
            pnl_value = pnl if pnl is not None else 0
            print(f"║     {time} {symbol} {side}: R{pnl_value:+6.2f} {pnl_icon}{'':>15} ║")
    
    # Estimate completion time
    if current_total >= 10:  # Need some data for estimation
        cursor.execute('''
        SELECT 
          (julianday('now') - julianday(MIN(entry_timestamp))) * 24 as hours_so_far
        FROM trades
        WHERE entry_reason LIKE 'BASELINE_%'
        ''')
        hours_so_far = cursor.fetchone()[0]
        
        if hours_so_far > 0:
            trades_per_hour = current_total / hours_so_far
            hours_remaining = remaining / trades_per_hour if trades_per_hour > 0 else 0
            
            print(f"║                                                              ║")
            print(f"║  ⏱️  ESTIMATE:                                               ║")
            print(f"║     Rate: {trades_per_hour:.1f} trades/hour{'':>25} ║")
            
            if hours_remaining < 24:
                print(f"║     ETA: {hours_remaining:.1f} hours to 500 trades{'':>20} ║")
            else:
                days_remaining = hours_remaining / 24
                print(f"║     ETA: {days_remaining:.1f} days to 500 trades{'':>21} ║")
    
    print(f"║                                                              ║")
    
    # Assessment
    if win_rate >= 55:
        verdict = "✅ LOOKING GOOD!"
        color = "green"
    elif win_rate >= 50:
        verdict = "⚠️  ACCEPTABLE"
        color = "yellow"
    else:
        verdict = "❌ CONCERNING"
        color = "red"
    
    print(f"║  🎯 CURRENT VERDICT: {verdict}{'':>25} ║")
    print(f"║                                                              ║")
    
    if remaining <= 10:
        print(f"║  🚀 ALMOST THERE! {remaining} more trades for full confidence!   ║")
    elif remaining <= 25:
        print(f"║  🔥 GETTING CLOSE! {remaining} more trades needed.              ║")
    else:
        print(f"║  ⏳ PATIENCE! {remaining} more trades for 500 target.            ║")
    
    print("╚══════════════════════════════════════════════════════════════╝")
    
    conn.close()
    
    return current_total, remaining, win_rate

def main():
    check_progress()

if __name__ == "__main__":
    main()