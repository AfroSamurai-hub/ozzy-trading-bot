#!/usr/bin/env python3
"""
Phase 1 Monitor Script
Quick status check for your Phase 1 bot
"""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta

def check_bot_running():
    """Check if the bot is running"""
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        if 'main.py' in result.stdout and 'python' in result.stdout:
            return True
        return False
    except:
        return False

def get_signal_count():
    """Get signal counts from database"""
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        cursor = conn.cursor()
        
        # Total signals today
        cursor.execute("""
            SELECT COUNT(*) FROM signals 
            WHERE DATE(timestamp) = DATE('now')
        """)
        today_count = cursor.fetchone()[0]
        
        # Total signals this hour
        cursor.execute("""
            SELECT COUNT(*) FROM signals 
            WHERE datetime(timestamp) >= datetime('now', '-1 hour')
        """)
        hour_count = cursor.fetchone()[0]
        
        # Recent signals by type
        cursor.execute("""
            SELECT signal, COUNT(*) FROM signals 
            WHERE DATE(timestamp) = DATE('now')
            GROUP BY signal
        """)
        signal_types = cursor.fetchall()
        
        # Recent signals by symbol
        cursor.execute("""
            SELECT symbol, signal, COUNT(*) FROM signals 
            WHERE DATE(timestamp) = DATE('now')
            GROUP BY symbol, signal
        """)
        symbol_signals = cursor.fetchall()
        
        conn.close()
        return today_count, hour_count, signal_types, symbol_signals
    except:
        return 0, 0, [], []

def get_recent_signals():
    """Get last 10 signals"""
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, symbol, signal, confidence, reason
            FROM signals 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        signals = cursor.fetchall()
        conn.close()
        return signals
    except:
        return []

def main():
    print("=" * 70)
    print("🔍 PHASE 1 MONITOR - QUICK STATUS CHECK")
    print("=" * 70)
    print()
    
    # Bot status
    bot_running = check_bot_running()
    if bot_running:
        print("✅ Bot Status: RUNNING")
    else:
        print("❌ Bot Status: NOT RUNNING")
        print("   To restart: cd /home/rick/ozzy-simple && nohup bash -c 'echo \"yes\" | venv/bin/python main.py' > logs/phase1_monitor.log 2>&1 &")
    
    print()
    
    # Signal counts
    today_count, hour_count, signal_types, symbol_signals = get_signal_count()
    
    print("📊 SIGNAL ACTIVITY")
    print("-" * 30)
    print(f"Today: {today_count} signals")
    print(f"Last hour: {hour_count} signals")
    print()
    
    if signal_types:
        print("By Type:")
        for signal_type, count in signal_types:
            emoji = "🟢" if signal_type == "LONG" else "🔴" if signal_type == "SHORT" else "⚪"
            print(f"   {emoji} {signal_type}: {count}")
        print()
    
    if symbol_signals:
        print("By Symbol:")
        for symbol, signal_type, count in symbol_signals:
            emoji = "🟢" if signal_type == "LONG" else "🔴" if signal_type == "SHORT" else "⚪"
            print(f"   {symbol}: {emoji} {signal_type} ({count})")
        print()
    
    # Recent signals
    recent = get_recent_signals()
    if recent:
        print("🕒 RECENT SIGNALS (Last 10)")
        print("-" * 50)
        for timestamp, symbol, signal, confidence, reason in recent:
            emoji = "🟢" if signal == "LONG" else "🔴" if signal == "SHORT" else "⚪"
            # Parse timestamp and show time only
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M')
            except:
                time_str = timestamp[-8:-3] if len(timestamp) > 8 else timestamp
            
            print(f"   {time_str} | {symbol:8} | {emoji} {signal:5} | {confidence:5.1f}%")
        print()
    
    # Log check
    if os.path.exists('logs/phase1_monitor.log'):
        # Get file size
        size = os.path.getsize('logs/phase1_monitor.log')
        size_mb = size / (1024 * 1024)
        print(f"📝 Log Size: {size_mb:.1f} MB")
        
        # Check for recent errors
        try:
            with open('logs/phase1_monitor.log', 'r') as f:
                lines = f.readlines()
                error_lines = [line for line in lines[-100:] if 'ERROR' in line and 'Failed to fetch balance' not in line]
                if error_lines:
                    print(f"⚠️  Recent Errors: {len(error_lines)}")
                    for error in error_lines[-3:]:  # Last 3 errors
                        print(f"   {error.strip()}")
                else:
                    print("✅ No critical errors in recent log")
        except:
            print("⚠️  Could not read log file")
    else:
        print("⚠️  Log file not found")
    
    print()
    print("=" * 70)
    print("🎯 COMMANDS")
    print("=" * 70)
    print()
    print("Monitor live:")
    print("   tail -f logs/phase1_monitor.log")
    print()
    print("Check signals:")
    print("   python monitor_phase1.py")
    print()
    print("Stop bot:")
    print("   pkill -f main.py")
    print()
    print("Restart bot:")
    print("   cd /home/rick/ozzy-simple")
    print("   nohup bash -c 'echo \"yes\" | venv/bin/python main.py' > logs/phase1_monitor.log 2>&1 &")
    print()
    print("Phase 1 analysis (after 3 days):")
    print("   python phase1_analysis.py")
    print()

if __name__ == "__main__":
    main()