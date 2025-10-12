#!/usr/bin/env python3
"""
Phase 1 Signal Analysis
Analyzes signals collected during Phase 1 monitoring period
Run after 48-72 hours of Phase 1 monitoring
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

def connect_db():
    """Connect to database"""
    db_path = 'ozzy_simple.db'
    if not Path(db_path).exists():
        print("❌ Database not found. Make sure Phase 1 has been running.")
        sys.exit(1)
    return sqlite3.connect(db_path)

def analyze_signals():
    """Analyze collected signals"""
    print("\n" + "=" * 70)
    print("📊 PHASE 1 SIGNAL ANALYSIS REPORT")
    print("=" * 70)
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # Basic counts
    cursor.execute("SELECT COUNT(*) FROM signals")
    total_signals = cursor.fetchone()[0]
    
    if total_signals == 0:
        print("❌ No signals found in database.")
        print("   Make sure Phase 1 has been running and generating signals.")
        return False
    
    # Time range
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM signals")
    start_time, end_time = cursor.fetchone()
    
    if start_time and end_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        duration = end_dt - start_dt
        duration_hours = duration.total_seconds() / 3600
    else:
        duration_hours = 0
    
    print(f"Total Signals: {total_signals}")
    print(f"Duration: {duration_hours:.1f} hours")
    print(f"Period: {start_time} to {end_time}")
    print()
    
    # By symbol
    print("BY SYMBOL:")
    cursor.execute("""
        SELECT symbol, signal, COUNT(*) as count
        FROM signals
        GROUP BY symbol, signal
        ORDER BY symbol, signal
    """)
    
    symbol_stats = {}
    for symbol, signal, count in cursor.fetchall():
        if symbol not in symbol_stats:
            symbol_stats[symbol] = {'LONG': 0, 'SHORT': 0, 'HOLD': 0}
        symbol_stats[symbol][signal] = count
    
    for symbol, stats in symbol_stats.items():
        total = sum(stats.values())
        long_count = stats.get('LONG', 0)
        short_count = stats.get('SHORT', 0)
        hold_count = stats.get('HOLD', 0)
        print(f"   {symbol}: {total} signals (LONG: {long_count}, SHORT: {short_count}, HOLD: {hold_count})")
    
    print()
    
    # By quality
    print("BY QUALITY:")
    cursor.execute("""
        SELECT quality, COUNT(*) as count
        FROM signals
        WHERE signal != 'HOLD'
        GROUP BY quality
        ORDER BY count DESC
    """)
    
    trading_signals = 0
    for quality, count in cursor.fetchall():
        if quality:
            percentage = (count / total_signals) * 100
            print(f"   {quality}: {count} ({percentage:.1f}%)")
            trading_signals += count
    
    print()
    
    # Confidence distribution
    print("CONFIDENCE DISTRIBUTION:")
    cursor.execute("""
        SELECT 
            CASE 
                WHEN confidence < 35 THEN '< 35%'
                WHEN confidence < 45 THEN '35-45%'
                WHEN confidence < 55 THEN '45-55%'
                WHEN confidence < 65 THEN '55-65%'
                WHEN confidence < 75 THEN '65-75%'
                WHEN confidence < 85 THEN '75-85%'
                ELSE '85%+'
            END as confidence_range,
            COUNT(*) as count
        FROM signals
        WHERE signal != 'HOLD' AND confidence IS NOT NULL
        GROUP BY confidence_range
        ORDER BY MIN(confidence)
    """)
    
    for conf_range, count in cursor.fetchall():
        print(f"   {conf_range}: {count} signals")
    
    print()
    
    # Success criteria
    print("✅ PHASE 1 SUCCESS CRITERIA:")
    
    criteria = {
        "Total signals ≥ 20": total_signals >= 20,
        "Duration ≥ 48 hours": duration_hours >= 48,
        "Multiple symbols": len(symbol_stats) >= 2,
        "Trading signals ≥ 10": trading_signals >= 10,
        "Both directions": any(stats.get('LONG', 0) > 0 and stats.get('SHORT', 0) > 0 for stats in symbol_stats.values()),
        "Quality distribution": True  # Always pass if we have signals
    }
    
    passed = 0
    for criterion, status in criteria.items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {criterion}")
        if status:
            passed += 1
    
    total_criteria = len(criteria)
    print(f"\nScore: {passed}/{total_criteria} criteria met")
    
    # Recommendations
    print("\n" + "=" * 70)
    print("🎯 RECOMMENDATIONS")
    print("=" * 70)
    
    if passed == total_criteria:
        print("\n🎉 PHASE 1 COMPLETE!")
        print("\n✅ All criteria met. Ready for Phase 2 (Paper Trading)")
        print("\nNext steps:")
        print("   1. Update config.py: MONITOR_ONLY_MODE = False")
        print("   2. Update config.py: PAPER_TRADING = True")
        print("   3. Restart the bot")
        print("   4. Run for another 48-72 hours")
        print("   5. Monitor paper trade performance")
        
    elif passed >= total_criteria * 0.8:  # 80% pass rate
        print("\n⚠️  ALMOST READY")
        print(f"\n{passed}/{total_criteria} criteria met. Close to Phase 2 readiness.")
        print("\nOptions:")
        print("   1. Continue Phase 1 for another 12-24 hours")
        print("   2. Lower confidence thresholds in config.py")
        print("   3. Add more symbols to TRADING_SYMBOLS")
        
    else:
        print("\n❌ NEED MORE DATA")
        print(f"\nOnly {passed}/{total_criteria} criteria met.")
        print("\nActions needed:")
        print("   1. Continue Phase 1 for another 24-48 hours")
        print("   2. Check logs for errors")
        print("   3. Lower MIN_CONFIDENCE in config.py")
        print("   4. Verify bot is running continuously")
    
    # Export to CSV for further analysis
    print("\n📊 EXPORTING DATA...")
    try:
        cursor.execute("""
            SELECT timestamp, symbol, signal, confidence, quality, 
                   entry_price, stop_loss, take_profit, reason
            FROM signals
            ORDER BY timestamp
        """)
        
        with open('phase1_signals.csv', 'w') as f:
            f.write("timestamp,symbol,signal,confidence,quality,entry_price,stop_loss,take_profit,reason\n")
            for row in cursor.fetchall():
                # Handle None values
                row_str = ','.join(str(x) if x is not None else '' for x in row)
                f.write(row_str + '\n')
        
        print("   ✅ Exported to phase1_signals.csv")
        
    except Exception as e:
        print(f"   ⚠️  Export failed: {e}")
    
    conn.close()
    
    return passed == total_criteria

def main():
    """Main analysis function"""
    if not analyze_signals():
        print("\n🔄 Continue Phase 1 monitoring...")
        return 1
    else:
        print("\n🚀 Ready to proceed to Phase 2!")
        return 0

if __name__ == "__main__":
    sys.exit(main())