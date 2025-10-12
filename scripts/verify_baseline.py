#!/usr/bin/env python3
"""
BASELINE VERIFICATION SCRIPT
Verifies baseline trading performance before proceeding with optimization
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

def format_currency(amount):
    """Format amount as currency with color"""
    if amount > 0:
        return f"\033[92mR{amount:,.2f}\033[0m"  # Green for profit
    elif amount < 0:
        return f"\033[91mR{amount:,.2f}\033[0m"  # Red for loss
    else:
        return f"R{amount:,.2f}"

def format_percentage(value, decimals=1):
    """Format percentage with color"""
    if value > 60:
        return f"\033[92m{value:.{decimals}f}%\033[0m"  # Green for good
    elif value > 50:
        return f"\033[93m{value:.{decimals}f}%\033[0m"  # Yellow for ok
    else:
        return f"\033[91m{value:.{decimals}f}%\033[0m"  # Red for bad

def verify_baseline():
    """Main verification function"""
    
    # Database path
    db_path = Path(__file__).parent.parent / "ozzy_simple.db"
    
    if not db_path.exists():
        print(f"\033[91m❌ ERROR: Database not found at {db_path}\033[0m")
        sys.exit(1)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("╔════════════════════════════════════════════════════════╗")
    print("║  BASELINE VERIFICATION REPORT                          ║")
    print("╚════════════════════════════════════════════════════════╝")
    print("="*60 + "\n")
    
    # 1. Get total trades
    cursor.execute("SELECT COUNT(*) FROM trades WHERE exit_timestamp IS NOT NULL")
    total_trades = cursor.fetchone()[0]
    
    # Separate baseline and test trades
    cursor.execute("""
        SELECT COUNT(*) FROM trades 
        WHERE exit_timestamp IS NOT NULL 
        AND (entry_reason LIKE 'BASELINE_%' OR entry_reason NOT LIKE 'TEST%')
    """)
    baseline_trades = cursor.fetchone()[0]
    
    test_trades = total_trades - baseline_trades
    
    # 2. Calculate win rate
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
            COUNT(CASE WHEN pnl <= 0 THEN 1 END) as losses
        FROM trades 
        WHERE exit_timestamp IS NOT NULL
    """)
    wins, losses = cursor.fetchone()
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    # 3. Calculate P&L statistics
    cursor.execute("""
        SELECT 
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl,
            AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
            AVG(CASE WHEN pnl <= 0 THEN pnl END) as avg_loss,
            MAX(pnl) as max_win,
            MIN(pnl) as min_loss
        FROM trades
        WHERE exit_timestamp IS NOT NULL
    """)
    total_pnl, avg_pnl, avg_win, avg_loss, max_win, min_loss = cursor.fetchone()
    
    # Handle None values
    total_pnl = total_pnl or 0
    avg_pnl = avg_pnl or 0
    avg_win = avg_win or 0
    avg_loss = avg_loss or 0
    max_win = max_win or 0
    min_loss = min_loss or 0
    
    # 4. Baseline vs Test breakdown
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
            COUNT(*) as total,
            SUM(pnl) as total_pnl
        FROM trades 
        WHERE exit_timestamp IS NOT NULL 
        AND (entry_reason LIKE 'BASELINE_%' OR entry_reason NOT LIKE 'TEST%')
    """)
    baseline_wins, baseline_total, baseline_pnl = cursor.fetchone()
    baseline_win_rate = (baseline_wins / baseline_total * 100) if baseline_total > 0 else 0
    baseline_pnl = baseline_pnl or 0
    
    # Print Overall Statistics
    print("📊 OVERALL STATISTICS")
    print("─" * 60)
    print(f"Total Trades:           {total_trades}")
    print(f"Baseline Trades:        {baseline_trades} {'✅' if baseline_trades >= 100 else '⚠️'}")
    print(f"Test Trades:            {test_trades}")
    print(f"Win Rate:               {format_percentage(win_rate)} ({wins}W/{losses}L) {'✅' if win_rate >= 55 else '⚠️'}")
    print(f"Average P&L:            {format_currency(avg_pnl)} per trade")
    print(f"Total P&L:              {format_currency(total_pnl)}")
    print(f"Best Trade:             {format_currency(max_win)}")
    print(f"Worst Trade:            {format_currency(min_loss)}")
    
    if avg_win != 0 and avg_loss != 0:
        profit_factor = abs(avg_win / avg_loss)
        print(f"Profit Factor:          {profit_factor:.2f}x")
    
    print()
    
    # Verification Status
    if baseline_trades >= 100:
        print("✅ BASELINE READY: Have {} baseline trades (need 100+)".format(baseline_trades))
        if 55 <= win_rate <= 70:
            print("✅ WIN RATE HEALTHY: {:.1f}% is in target range (55-70%)".format(win_rate))
        else:
            print("⚠️  WIN RATE WARNING: {:.1f}% is outside target range (55-70%)".format(win_rate))
        print("✅ Ready to proceed with systematic optimization!")
    else:
        needed = 100 - baseline_trades
        print(f"⚠️  NOT READY: Need {needed} more baseline trades before optimization")
        print(f"   Current: {baseline_trades}/100 trades")
    
    print("\n" + "─" * 60)
    
    # Performance Breakdown
    if test_trades > 0:
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
                COUNT(*) as total,
                SUM(pnl) as total_pnl
            FROM trades 
            WHERE exit_timestamp IS NOT NULL 
            AND (entry_reason LIKE 'TEST%' OR entry_reason NOT LIKE 'BASELINE_%')
        """)
        test_wins, test_total, test_pnl = cursor.fetchone()
        test_win_rate = (test_wins / test_total * 100) if test_total > 0 else 0
        test_pnl = test_pnl or 0
        
        print("\n📈 PERFORMANCE BREAKDOWN")
        print("─" * 60)
        print(f"BASELINE Performance ({baseline_trades} trades):")
        print(f"  Win Rate: {format_percentage(baseline_win_rate)}")
        print(f"  Total P&L: {format_currency(baseline_pnl)}")
        print(f"  Avg P&L: {format_currency(baseline_pnl/baseline_trades if baseline_trades > 0 else 0)}/trade")
        print()
        print(f"TEST Performance ({test_trades} trades):")
        print(f"  Win Rate: {format_percentage(test_win_rate)}")
        print(f"  Total P&L: {format_currency(test_pnl)}")
        print(f"  Avg P&L: {format_currency(test_pnl/test_trades if test_trades > 0 else 0)}/trade")
        print("\n" + "─" * 60)
    
    # 5. Last 10 trades summary
    cursor.execute("""
        SELECT 
            id,
            entry_timestamp,
            exit_timestamp,
            symbol,
            side,
            pnl,
            CASE 
                WHEN entry_reason LIKE 'BASELINE_%' THEN 'BASELINE'
                WHEN entry_reason LIKE 'TEST%' THEN 'TEST'
                ELSE 'UNKNOWN'
            END as trade_type
        FROM trades
        WHERE exit_timestamp IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
    """)
    
    last_trades = cursor.fetchall()
    
    print("\n🔥 LAST 10 TRADES")
    print("─" * 60)
    print(f"{'ID':<5} {'Symbol':<10} {'Side':<6} {'P&L':<15} {'Type':<10} {'Exit Time'}")
    print("─" * 60)
    
    for trade in last_trades:
        trade_id, entry_time, exit_time, symbol, side, pnl, trade_type = trade
        pnl_str = format_currency(pnl) if pnl else "R0.00"
        exit_dt = datetime.fromisoformat(exit_time).strftime("%m-%d %H:%M") if exit_time else "Open"
        print(f"{trade_id:<5} {symbol:<10} {side:<6} {pnl_str:<15} {trade_type:<10} {exit_dt}")
    
    # Symbol breakdown
    print("\n📊 SYMBOL BREAKDOWN")
    print("─" * 60)
    cursor.execute("""
        SELECT 
            symbol,
            COUNT(*) as trades,
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
            SUM(pnl) as total_pnl
        FROM trades
        WHERE exit_timestamp IS NOT NULL
        GROUP BY symbol
        ORDER BY trades DESC
    """)
    
    symbol_stats = cursor.fetchall()
    print(f"{'Symbol':<12} {'Trades':<8} {'Win Rate':<12} {'Total P&L'}")
    print("─" * 60)
    
    for symbol, trades, wins, pnl in symbol_stats:
        sym_win_rate = (wins / trades * 100) if trades > 0 else 0
        pnl = pnl or 0
        print(f"{symbol:<12} {trades:<8} {format_percentage(sym_win_rate):<12} {format_currency(pnl)}")
    
    # Daily statistics (last 7 days)
    print("\n📅 RECENT PERFORMANCE (Last 7 Days)")
    print("─" * 60)
    cursor.execute("""
        SELECT 
            DATE(entry_timestamp) as date,
            COUNT(*) as trades,
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
            SUM(pnl) as daily_pnl
        FROM trades
        WHERE exit_timestamp IS NOT NULL
        AND DATE(entry_timestamp) >= DATE('now', '-7 days')
        GROUP BY DATE(entry_timestamp)
        ORDER BY date DESC
    """)
    
    daily_stats = cursor.fetchall()
    if daily_stats:
        print(f"{'Date':<12} {'Trades':<8} {'Win Rate':<12} {'P&L'}")
        print("─" * 60)
        for date, trades, wins, pnl in daily_stats:
            daily_win_rate = (wins / trades * 100) if trades > 0 else 0
            pnl = pnl or 0
            print(f"{date:<12} {trades:<8} {format_percentage(daily_win_rate):<12} {format_currency(pnl)}")
    else:
        print("No trades in last 7 days")
    
    print("\n" + "="*60)
    print("📋 NEXT STEPS:")
    print("─" * 60)
    
    if baseline_trades >= 100 and 55 <= win_rate <= 70:
        print("✅ Your baseline is verified and ready!")
        print("✅ You can now proceed with optimization testing")
        print("\nRecommended actions:")
        print("  1. Run evolution tests (scripts/evolution_tester.py)")
        print("  2. Test one variable at a time")
        print("  3. Compare results against this baseline")
    elif baseline_trades < 100:
        print("⚠️  Continue collecting baseline data")
        print(f"   Need {100 - baseline_trades} more trades")
        print("   Let bot run for 1-2 more days")
    else:
        print("⚠️  Win rate outside normal range")
        print("   Review strategy configuration")
        print("   May need to adjust parameters")
    
    print("="*60 + "\n")
    
    conn.close()
    
    # Return status code
    if baseline_trades >= 100 and 55 <= win_rate <= 70:
        return 0  # Success
    else:
        return 1  # Not ready

if __name__ == "__main__":
    try:
        exit_code = verify_baseline()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\033[91m❌ ERROR: {str(e)}\033[0m")
        import traceback
        traceback.print_exc()
        sys.exit(1)
