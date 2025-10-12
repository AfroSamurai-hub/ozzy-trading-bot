#!/usr/bin/env python3
"""
Backtest Confidence Threshold on Historical Trades
Tests what would have happened with different minimum confidence levels
"""

import pandas as pd
import argparse
import sqlite3

def backtest_confidence(df, min_confidence=10):
    """Backtest minimum confidence threshold"""
    
    # Control: All trades
    control = df.copy()
    
    # Test: Only trades above confidence threshold
    test = df[df['confidence'] >= min_confidence]
    
    def calculate_metrics(trades, name):
        if len(trades) == 0:
            return {'name': name, 'count': 0, 'wins': 0, 'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0}
        
        wins = trades[trades['pnl'] > 0]
        return {
            'name': name, 'count': len(trades), 'wins': len(wins),
            'win_rate': len(wins) / len(trades) * 100,
            'total_pnl': trades['pnl'].sum(), 'avg_pnl': trades['pnl'].mean()
        }
    
    control_metrics = calculate_metrics(control, f"Control (All trades)")
    test_metrics = calculate_metrics(test, f"Test (Min {min_confidence}% confidence)")
    
    # Skipped trades
    skipped = df[df['confidence'] < min_confidence]
    skipped_metrics = calculate_metrics(skipped, "Skipped (Low confidence)")
    
    return control_metrics, test_metrics, skipped_metrics

def main():
    parser = argparse.ArgumentParser(description="Backtest confidence threshold")
    parser.add_argument("--min-confidence", type=float, default=15,
                       help="Minimum confidence threshold (default: 15)")
    args = parser.parse_args()
    
    # Load data
    conn = sqlite3.connect('ozzy_simple.db')
    df = pd.read_sql_query("""
        SELECT confidence, pnl FROM trades 
        WHERE exit_timestamp IS NOT NULL 
        AND entry_reason NOT LIKE '%TEST_%'
        AND confidence IS NOT NULL
    """, conn)
    conn.close()
    
    if len(df) == 0:
        print("❌ No trades with confidence data found")
        return
    
    print(f"🧪 BACKTESTING CONFIDENCE THRESHOLD: {args.min_confidence}%")
    print(f"✅ Loaded {len(df)} trades")
    
    control, test, skipped = backtest_confidence(df, args.min_confidence)
    
    print(f"\n📊 RESULTS")
    print(f"─" * 60)
    print(f"{'Strategy':<25} {'Trades':<8} {'Win Rate':<10} {'Total P&L':<12} {'Avg P&L'}")
    print(f"─" * 60)
    print(f"{control['name']:<25} {control['count']:<8} {control['win_rate']:6.1f}%{'':<3} R{control['total_pnl']:8.2f}{'':<2} R{control['avg_pnl']:6.2f}")
    print(f"{test['name']:<25} {test['count']:<8} {test['win_rate']:6.1f}%{'':<3} R{test['total_pnl']:8.2f}{'':<2} R{test['avg_pnl']:6.2f}")
    
    if skipped['count'] > 0:
        print(f"\n📋 SKIPPED TRADES ({skipped['count']} trades, {skipped['count']/control['count']*100:.1f}%)")
        print(f"Win Rate: {skipped['win_rate']:.1f}%")
        print(f"P&L Lost: R{skipped['total_pnl']:.2f}")
    
    # Verdict
    win_diff = test['win_rate'] - control['win_rate']
    pnl_diff = test['total_pnl'] - control['total_pnl']
    
    print(f"\n🎯 VERDICT")
    if win_diff >= 3 and pnl_diff >= 200:
        print(f"✅ STRONG WIN! Use {args.min_confidence}% minimum confidence")
    elif win_diff >= 1 and pnl_diff >= 100:
        print(f"✅ WIN! Consider {args.min_confidence}% minimum confidence")
    elif win_diff <= -2 or pnl_diff <= -200:
        print(f"❌ LOSS! Keep current threshold")
    else:
        print(f"➖ No significant difference")
    
    print(f"Win rate change: {win_diff:+.1f}%")
    print(f"P&L change: R{pnl_diff:+.2f}")

if __name__ == "__main__":
    main()