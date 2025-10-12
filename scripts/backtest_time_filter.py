#!/usr/bin/env python3
"""
Backtest Time Filter on Historical Trades
Tests what would have happened if we avoided certain hours
"""

import pandas as pd
import argparse
from datetime import datetime
import sqlite3
from pathlib import Path

def load_historical_trades(db_path="ozzy_simple.db"):
    """Load completed trades from database"""
    try:
        conn = sqlite3.connect(db_path)
        query = """
        SELECT entry_timestamp, exit_timestamp, symbol, side, 
               entry_price, exit_price, pnl, quality, confidence
        FROM trades 
        WHERE exit_timestamp IS NOT NULL
        AND entry_reason NOT LIKE '%TEST_%'
        ORDER BY entry_timestamp
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if len(df) == 0:
            print("❌ No historical trades found in database")
            return None
            
        # Convert timestamps
        df['entry_timestamp'] = pd.to_datetime(df['entry_timestamp'])
        df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'])
        
        # Extract entry hour (UTC)
        df['entry_hour'] = df['entry_timestamp'].dt.hour
        
        print(f"✅ Loaded {len(df)} historical trades from database")
        return df
        
    except Exception as e:
        print(f"❌ Error loading trades: {e}")
        return None

def is_in_avoid_window(hour, avoid_start=22, avoid_end=2):
    """Check if hour is in avoid window"""
    if avoid_start > avoid_end:  # Crosses midnight (e.g., 22-02)
        return hour >= avoid_start or hour < avoid_end
    else:  # Same day (e.g., 08-16)
        return avoid_start <= hour < avoid_end

def backtest_time_filter(df, avoid_start=22, avoid_end=2):
    """Backtest time filter strategy"""
    
    # Control: All trades
    control = df.copy()
    
    # Test: Exclude trades in avoid window
    test = df[~df['entry_hour'].apply(lambda h: is_in_avoid_window(h, avoid_start, avoid_end))]
    
    # Calculate metrics for both groups
    def calculate_metrics(trades, name):
        if len(trades) == 0:
            return {
                'name': name,
                'count': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'total_pnl': 0, 'avg_pnl': 0, 'win_pnl': 0, 'loss_pnl': 0
            }
        
        wins = trades[trades['pnl'] > 0]
        losses = trades[trades['pnl'] <= 0]
        
        return {
            'name': name,
            'count': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(trades) * 100,
            'total_pnl': trades['pnl'].sum(),
            'avg_pnl': trades['pnl'].mean(),
            'win_pnl': wins['pnl'].sum() if len(wins) > 0 else 0,
            'loss_pnl': losses['pnl'].sum() if len(losses) > 0 else 0
        }
    
    control_metrics = calculate_metrics(control, "Control (24/7)")
    test_metrics = calculate_metrics(test, "Test (Filtered)")
    
    # Skipped trades analysis
    skipped = df[df['entry_hour'].apply(lambda h: is_in_avoid_window(h, avoid_start, avoid_end))]
    skipped_metrics = calculate_metrics(skipped, "Skipped Trades")
    
    return control_metrics, test_metrics, skipped_metrics

def display_results(control, test, skipped, avoid_start, avoid_end):
    """Display backtest results"""
    
    print(f"\n{'='*70}")
    print(f"🧪 BACKTEST RESULTS: Time Filter ({avoid_start:02d}:00-{avoid_end:02d}:00 UTC)")
    print(f"{'='*70}")
    
    # Format avoid hours display
    if avoid_start > avoid_end:
        avoid_desc = f"{avoid_start:02d}:00-23:59 & 00:00-{avoid_end:02d}:00"
    else:
        avoid_desc = f"{avoid_start:02d}:00-{avoid_end:02d}:00"
    
    print(f"\n📊 STRATEGY COMPARISON")
    print(f"─" * 70)
    print(f"{'Metric':<20} {'Control (24/7)':<20} {'Test (Filtered)':<20} {'Difference'}")
    print(f"─" * 70)
    
    # Trades count
    print(f"{'Trades':<20} {control['count']:<20} {test['count']:<20} {test['count'] - control['count']:+d}")
    
    # Win rate
    win_diff = test['win_rate'] - control['win_rate']
    win_symbol = "🔥" if win_diff > 2 else "❄️" if win_diff < -2 else "➖"
    print(f"{'Win Rate':<20} {control['win_rate']:.1f}%{'':<15} {test['win_rate']:.1f}%{'':<15} {win_diff:+.1f}% {win_symbol}")
    
    # Total P&L
    pnl_diff = test['total_pnl'] - control['total_pnl']
    pnl_symbol = "💰" if pnl_diff > 100 else "💸" if pnl_diff < -100 else "➖"
    print(f"{'Total P&L':<20} R{control['total_pnl']:.2f}{'':<12} R{test['total_pnl']:.2f}{'':<12} R{pnl_diff:+.2f} {pnl_symbol}")
    
    # Avg P&L
    avg_diff = test['avg_pnl'] - control['avg_pnl']
    avg_symbol = "📈" if avg_diff > 2 else "📉" if avg_diff < -2 else "➖"
    print(f"{'Avg P&L':<20} R{control['avg_pnl']:.2f}{'':<12} R{test['avg_pnl']:.2f}{'':<12} R{avg_diff:+.2f} {avg_symbol}")
    
    print(f"\n📋 SKIPPED TRADES ANALYSIS")
    print(f"─" * 70)
    print(f"Time Window:     {avoid_desc}")
    print(f"Trades Skipped:  {skipped['count']} ({skipped['count']/control['count']*100:.1f}% of total)")
    
    if skipped['count'] > 0:
        print(f"Skipped Win Rate: {skipped['win_rate']:.1f}%")
        print(f"Skipped Total P&L: R{skipped['total_pnl']:.2f}")
        print(f"Skipped Avg P&L:   R{skipped['avg_pnl']:.2f}")
    
    print(f"\n🎯 VERDICT")
    print(f"─" * 70)
    
    # Decision logic
    if win_diff >= 2 and pnl_diff >= 100:
        verdict = "✅ STRONG WIN"
        action = "APPLY TIME FILTER IMMEDIATELY!"
        emoji = "🚀"
    elif win_diff >= 1 and pnl_diff >= 50:
        verdict = "✅ MODERATE WIN"
        action = "Apply time filter"
        emoji = "👍"
    elif win_diff <= -2 or pnl_diff <= -100:
        verdict = "❌ CLEAR LOSS"
        action = "DON'T apply filter - keep 24/7 trading"
        emoji = "🚫"
    else:
        verdict = "➖ NO SIGNIFICANT DIFFERENCE"
        action = "Keep 24/7 trading, test other variables"
        emoji = "🤷"
    
    print(f"{verdict} {emoji}")
    print(f"Recommendation: {action}")
    
    if verdict.startswith("✅"):
        annual_extra = pnl_diff * 4  # Rough estimate (quarterly)
        print(f"💡 Potential annual impact: ~R{annual_extra:,.0f} extra profit!")
    
    print(f"\n{'='*70}")
    
    return verdict.startswith("✅")

def main():
    parser = argparse.ArgumentParser(description="Backtest time filter on historical trades")
    parser.add_argument("--avoid-start", type=int, default=22, 
                       help="Start hour to avoid (0-23, default: 22)")
    parser.add_argument("--avoid-end", type=int, default=2,
                       help="End hour to avoid (0-23, default: 2)")
    parser.add_argument("--db", default="ozzy_simple.db",
                       help="Database file path")
    
    args = parser.parse_args()
    
    print(f"🧪 BACKTESTING TIME FILTER")
    print(f"Avoid hours: {args.avoid_start:02d}:00-{args.avoid_end:02d}:00 UTC")
    print(f"Database: {args.db}")
    print(f"Loading historical trades...")
    
    # Load data
    df = load_historical_trades(args.db)
    if df is None:
        return
    
    # Run backtest
    control, test, skipped = backtest_time_filter(df, args.avoid_start, args.avoid_end)
    
    # Display results
    should_apply = display_results(control, test, skipped, args.avoid_start, args.avoid_end)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"backtest_time_filter_{timestamp}.txt"
    
    with open(results_file, 'w') as f:
        f.write(f"Backtest Results: Time Filter {args.avoid_start:02d}:00-{args.avoid_end:02d}:00\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Control (24/7): {control['count']} trades, {control['win_rate']:.1f}% win rate, R{control['total_pnl']:.2f} total\n")
        f.write(f"Test (Filtered): {test['count']} trades, {test['win_rate']:.1f}% win rate, R{test['total_pnl']:.2f} total\n")
        f.write(f"Difference: {test['win_rate'] - control['win_rate']:+.1f}% win rate, R{test['total_pnl'] - control['total_pnl']:+.2f} P&L\n")
        f.write(f"Recommendation: {'Apply filter' if should_apply else 'Keep 24/7 trading'}\n")
    
    print(f"\n💾 Results saved to: {results_file}")

if __name__ == "__main__":
    main()