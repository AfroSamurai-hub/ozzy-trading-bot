#!/usr/bin/env python3
"""
Real-Time Learning Analysis
Shows how your bot is adapting and learning from market data
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

def analyze_recent_learning():
    """Analyze recent bot behavior for learning patterns"""
    
    print("🧠 REAL-TIME LEARNING ANALYSIS")
    print("=" * 60)
    print()
    
    # Connect to database
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        
        # Get recent signals (last 2 hours)
        recent_signals = pd.read_sql_query("""
            SELECT timestamp, symbol, signal, confidence, quality, 
                   rsi, ema_short, ema_long, volume_ratio, momentum, reason
            FROM signals 
            WHERE datetime(timestamp) >= datetime('now', '-2 hours')
            ORDER BY timestamp DESC
        """, conn)
        
        if len(recent_signals) == 0:
            print("❌ No recent signals found")
            return
            
        print(f"📊 Analyzing {len(recent_signals)} signals from last 2 hours")
        print()
        
        # 1. CONFIDENCE ADAPTATION
        print("🎯 CONFIDENCE ADAPTATION:")
        print("-" * 30)
        
        # Group by symbol and show confidence trends
        for symbol in recent_signals['symbol'].unique():
            symbol_data = recent_signals[recent_signals['symbol'] == symbol]
            symbol_data = symbol_data.sort_values('timestamp')
            
            if len(symbol_data) > 3:
                early_conf = symbol_data.head(5)['confidence'].mean()
                recent_conf = symbol_data.tail(5)['confidence'].mean()
                trend = "📈 UP" if recent_conf > early_conf else "📉 DOWN" if recent_conf < early_conf else "➡️ STABLE"
                
                print(f"   {symbol}: {early_conf:.1f}% → {recent_conf:.1f}% {trend}")
        
        print()
        
        # 2. SIGNAL TYPE ADAPTATION
        print("🔄 SIGNAL TYPE LEARNING:")
        print("-" * 30)
        
        signal_counts = recent_signals['signal'].value_counts()
        for signal_type, count in signal_counts.items():
            percentage = (count / len(recent_signals)) * 100
            emoji = "🟢" if signal_type == "LONG" else "🔴" if signal_type == "SHORT" else "⚪"
            print(f"   {emoji} {signal_type}: {count} signals ({percentage:.1f}%)")
        
        print()
        
        # 3. TECHNICAL INDICATOR ADAPTATION
        print("📈 TECHNICAL INDICATOR LEARNING:")
        print("-" * 40)
        
        # RSI adaptation patterns
        rsi_data = recent_signals.dropna(subset=['rsi'])
        if len(rsi_data) > 0:
            avg_rsi = rsi_data['rsi'].mean()
            rsi_volatility = rsi_data['rsi'].std()
            
            print(f"   RSI Average: {avg_rsi:.1f} (volatility: {rsi_volatility:.1f})")
            
            # Show RSI vs signal type correlation
            long_rsi = rsi_data[rsi_data['signal'] == 'LONG']['rsi'].mean()
            short_rsi = rsi_data[rsi_data['signal'] == 'SHORT']['rsi'].mean() 
            hold_rsi = rsi_data[rsi_data['signal'] == 'HOLD']['rsi'].mean()
            
            print(f"   🟢 LONG signals avg RSI: {long_rsi:.1f}")
            if not np.isnan(short_rsi):
                print(f"   🔴 SHORT signals avg RSI: {short_rsi:.1f}")
            print(f"   ⚪ HOLD signals avg RSI: {hold_rsi:.1f}")
        
        print()
        
        # 4. QUALITY IMPROVEMENT TRACKING
        print("⭐ QUALITY LEARNING:")
        print("-" * 20)
        
        quality_counts = recent_signals['quality'].value_counts()
        for quality, count in quality_counts.items():
            percentage = (count / len(recent_signals)) * 100
            emoji = "🏆" if quality == "PREMIUM" else "✅" if quality == "GOOD" else "⚠️" if quality == "MODERATE" else "❌"
            print(f"   {emoji} {quality}: {count} ({percentage:.1f}%)")
        
        print()
        
        # 5. ADAPTATION PATTERNS
        print("🔧 ADAPTATION PATTERNS:")
        print("-" * 25)
        
        # Look for patterns in confidence vs RSI
        if len(rsi_data) > 10:
            correlation = np.corrcoef(rsi_data['confidence'], rsi_data['rsi'])[0, 1]
            print(f"   Confidence-RSI correlation: {correlation:.3f}")
            
            if abs(correlation) > 0.3:
                trend = "Strong positive" if correlation > 0.3 else "Strong negative"
                print(f"   📊 {trend} adaptation detected!")
            else:
                print(f"   📊 Weak correlation - exploring different patterns")
        
        # Check for time-based patterns
        recent_signals['hour'] = pd.to_datetime(recent_signals['timestamp']).dt.hour
        hourly_confidence = recent_signals.groupby('hour')['confidence'].mean()
        
        if len(hourly_confidence) > 1:
            max_hour = hourly_confidence.idxmax()
            min_hour = hourly_confidence.idxmin()
            print(f"   🕐 Best confidence at {max_hour}:00 ({hourly_confidence[max_hour]:.1f}%)")
            print(f"   🕐 Lowest confidence at {min_hour}:00 ({hourly_confidence[min_hour]:.1f}%)")
        
        print()
        
        # 6. A/B TESTING STATUS
        print("🧪 A/B TESTING STATUS:")
        print("-" * 25)
        
        # Look for test group indicators in reasons
        test_reasons = recent_signals[recent_signals['reason'].str.contains('TEST|test|A/B|group', na=False)]
        if len(test_reasons) > 0:
            print(f"   ✅ A/B test active: {len(test_reasons)} test signals")
            
            # Extract test groups if possible
            for reason in test_reasons['reason'].unique()[:3]:
                print(f"   📝 {reason}")
        else:
            print(f"   ⚪ No A/B testing detected in recent signals")
        
        # Check for time filter usage
        time_filter_signals = recent_signals[recent_signals['reason'].str.contains('time_filter|night|avoid', na=False, case=False)]
        if len(time_filter_signals) > 0:
            print(f"   🕐 Time filter active: {len(time_filter_signals)} filtered signals")
        
        print()
        
        # 7. LEARNING RECOMMENDATIONS
        print("💡 LEARNING INSIGHTS:")
        print("-" * 25)
        
        total_actionable = len(recent_signals[recent_signals['signal'] != 'HOLD'])
        actionable_rate = (total_actionable / len(recent_signals)) * 100
        
        print(f"   📊 Signal rate: {actionable_rate:.1f}% actionable signals")
        
        if actionable_rate > 50:
            print(f"   🚀 High activity - good learning environment!")
        elif actionable_rate > 25:
            print(f"   ✅ Moderate activity - steady learning pace")
        else:
            print(f"   ⚠️ Low activity - consider lowering thresholds")
        
        # Average confidence trend
        avg_confidence = recent_signals['confidence'].mean()
        if avg_confidence > 45:
            print(f"   🎯 High confidence ({avg_confidence:.1f}%) - strong signal quality")
        elif avg_confidence > 35:
            print(f"   ✅ Good confidence ({avg_confidence:.1f}%) - balanced approach")
        else:
            print(f"   📚 Learning mode ({avg_confidence:.1f}%) - exploring patterns")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analyzing learning: {e}")

def main():
    print()
    analyze_recent_learning()
    print()
    print("🔄 Learning Analysis Complete")
    print("Run again in 30 minutes to see adaptation progress!")
    print()

if __name__ == "__main__":
    main()