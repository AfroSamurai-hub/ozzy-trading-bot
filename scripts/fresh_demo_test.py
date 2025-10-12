#!/usr/bin/env python3
"""
Fresh Demo Test Script - Initialize and track R10,000 demo trading
"""

import sqlite3
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

from demo_utils import (
    DEFAULT_STARTING_BALANCE,
    ensure_demo_database,
    get_demo_db_path,
    initialize_demo_database,
)

# Ensure scripts directory exists
script_dir = Path(__file__).parent
script_dir.mkdir(exist_ok=True)

def init_demo_database():
    """Initialize fresh demo trading database"""
    print("🚀 Initializing Fresh Demo Test Database...")
    
    path = get_demo_db_path()
    if os.path.exists(path):
        print("   ♻️  Removed existing demo database")
    initialize_demo_database(path, overwrite=True)
    
    print("✅ Demo database initialized successfully!")
    print(f"   📊 Starting Capital: R{DEFAULT_STARTING_BALANCE:,.2f}")
    print(f"   📅 Start Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   💾 Database: {path}")
    print(f"   🎯 Ready to start demo trading!")

def get_demo_status():
    """Get current demo trading status"""
    path = ensure_demo_database()
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    # Get config
    cursor.execute('SELECT * FROM demo_config ORDER BY id DESC LIMIT 1')
    config = cursor.fetchone()
    
    if not config:
        print("❌ No demo config found!")
        conn.close()
        return
    
    starting_capital = config[1]
    current_balance = config[2]
    start_date = datetime.fromisoformat(config[3])
    total_trades = config[4]
    total_pnl = config[5]
    
    # Calculate days running
    days_running = (datetime.now(timezone.utc) - start_date).days
    if days_running == 0:
        days_running_str = "< 1 day"
    else:
        days_running_str = f"{days_running} days"
    
    # Get trade statistics
    cursor.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
            MAX(pnl) as best_trade,
            MIN(pnl) as worst_trade,
            AVG(pnl) as avg_trade
        FROM demo_trades 
        WHERE status = 'closed' AND pnl IS NOT NULL
    ''')
    trade_stats = cursor.fetchone()
    
    total_closed_trades = trade_stats[0] or 0
    winning_trades = trade_stats[1] or 0
    losing_trades = trade_stats[2] or 0
    best_trade = trade_stats[3] or 0
    worst_trade = trade_stats[4] or 0
    avg_trade = trade_stats[5] or 0
    
    win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
    
    # Calculate gain/loss
    total_gain_loss = current_balance - starting_capital
    gain_loss_percent = (total_gain_loss / starting_capital * 100)
    
    # Calculate max drawdown
    cursor.execute('SELECT MIN(balance_after) FROM demo_trades WHERE balance_after IS NOT NULL')
    min_balance_result = cursor.fetchone()
    min_balance = min_balance_result[0] if min_balance_result[0] else starting_capital
    max_drawdown = ((starting_capital - min_balance) / starting_capital * 100) if min_balance < starting_capital else 0
    
    conn.close()
    
    # Display status
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  💰 FRESH DEMO TEST - STATUS REPORT                         ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  📊 CAPITAL TRACKING:                                        ║")
    print(f"║     Starting Capital:  R{starting_capital:,.2f}                         ║")
    print(f"║     Current Balance:   R{current_balance:,.2f}                         ║")
    
    if total_gain_loss >= 0:
        print(f"║     Total Gain:        R{total_gain_loss:,.2f} (+{gain_loss_percent:.2f}%) 🔥              ║")
    else:
        print(f"║     Total Loss:        R{total_gain_loss:,.2f} ({gain_loss_percent:.2f}%) 📉              ║")
    
    print(f"║     Days Running:      {days_running_str}                                ║")
    print(f"║                                                              ║")
    print(f"║  📈 TRADING STATS:                                           ║")
    print(f"║     Total Closed Trades: {total_closed_trades}                                  ║")
    
    if total_closed_trades > 0:
        print(f"║     Winning Trades:    {winning_trades} ({win_rate:.1f}%)                        ║")
        print(f"║     Losing Trades:     {losing_trades} ({100-win_rate:.1f}%)                         ║")
        print(f"║     Average per Trade: R{avg_trade:.2f}                              ║")
        print(f"║                                                              ║")
        print(f"║  💎 BEST/WORST:                                              ║")
        print(f"║     Best Trade:   +R{best_trade:.2f}                                  ║")
        print(f"║     Worst Trade:  R{worst_trade:.2f}                                  ║")
        print(f"║     Max Drawdown: {max_drawdown:.1f}%                                    ║")
    else:
        print(f"║     No closed trades yet                                      ║")
    
    print(f"║                                                              ║")
    
    # Trading readiness assessment
    if total_closed_trades >= 20:  # Need at least 20 trades for meaningful assessment
        if win_rate >= 55 and gain_loss_percent > 0 and max_drawdown < 15:
            print(f"║  🎯 ASSESSMENT: ✅ LOOKING GOOD FOR LIVE TRADING!            ║")
        elif win_rate >= 50 and gain_loss_percent > 0:
            print(f"║  🎯 ASSESSMENT: ⚠️  PROMISING, NEEDS MORE DATA               ║")
        else:
            print(f"║  🎯 ASSESSMENT: ❌ NEEDS IMPROVEMENT BEFORE LIVE             ║")
    else:
        print(f"║  🎯 ASSESSMENT: ⏳ NEED MORE TRADES ({20-total_closed_trades} more)               ║")
    
    print("╚══════════════════════════════════════════════════════════════╝")

def generate_daily_report():
    """Generate daily summary report"""
    path = ensure_demo_database()
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    # Get daily summaries
    cursor.execute('''
        SELECT date, starting_balance, ending_balance, trades_count, win_rate, 
               daily_pnl, daily_pnl_percent, best_trade, worst_trade
        FROM demo_daily_summary
        ORDER BY date DESC
        LIMIT 10
    ''')
    daily_data = cursor.fetchall()
    
    if not daily_data:
        print("📅 No daily data available yet")
        conn.close()
        return
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  📅 DEMO TEST - DAILY BREAKDOWN                              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    
    for day_data in daily_data:
        date = day_data[0]
        start_bal = day_data[1]
        end_bal = day_data[2]
        trades = day_data[3]
        win_rate = day_data[4]
        daily_pnl = day_data[5]
        daily_pnl_pct = day_data[6]
        best = day_data[7] or 0
        worst = day_data[8] or 0
        
        if daily_pnl >= 0:
            pnl_icon = "🔥"
        else:
            pnl_icon = "📉"
        
        print(f"║  {date}: R{start_bal:,.0f} → R{end_bal:,.0f} ({daily_pnl_pct:+.2f}%) {pnl_icon}       ║")
        print(f"║     Trades: {trades}, Win Rate: {win_rate:.1f}%, Best: +R{best:.0f}, Worst: R{worst:.0f}  ║")
        print(f"║                                                              ║")
    
    print("╚══════════════════════════════════════════════════════════════╝")
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(description='Fresh Demo Test Management')
    parser.add_argument('--init', action='store_true', help='Initialize fresh demo database')
    parser.add_argument('--status', action='store_true', help='Show current demo status')
    parser.add_argument('--daily-report', action='store_true', help='Show daily breakdown')
    
    args = parser.parse_args()
    
    if args.init:
        init_demo_database()
    elif args.status:
        get_demo_status()
    elif args.daily_report:
        generate_daily_report()
    else:
        print("Usage: python fresh_demo_test.py [--init|--status|--daily-report]")

if __name__ == "__main__":
    main()
