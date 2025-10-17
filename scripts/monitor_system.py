#!/usr/bin/env python3
"""
🔍 Real-Time System Monitor

Monitors the running overnight test and displays:
- Process status
- Pattern intelligence stats
- Recent market context
- System health
"""

import time
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from intelligence.pattern_intelligence import get_intelligence
from intelligence.market_context import get_session_detector
from agent.portfolio import PaperTradingPortfolio


def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')


def get_process_info(pid=6683):
    """Get process information"""
    try:
        import subprocess
        result = subprocess.run(
            ['ps', '-p', str(pid), '-o', 'pid,etime,%cpu,%mem,cmd'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return {
                    'running': True,
                    'info': lines[1]
                }
        return {'running': False, 'info': None}
    except Exception as e:
        return {'running': False, 'error': str(e)}


def format_time(seconds):
    """Format seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def monitor_system(refresh_interval=5):
    """Monitor system in real-time"""
    
    print("🔍 Starting Real-Time System Monitor...")
    print("   Press Ctrl+C to exit\n")
    time.sleep(2)
    
    try:
        while True:
            clear_screen()
            
            now = datetime.now(timezone.utc)
            
            # Header
            print("╔════════════════════════════════════════════════════════════╗")
            print("║                                                            ║")
            print("║           🔍 REAL-TIME SYSTEM MONITOR 🔍                  ║")
            print("║                                                            ║")
            print("╚════════════════════════════════════════════════════════════╝\n")
            
            print(f"⏰ Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            
            # Process status
            process = get_process_info(6683)
            
            print("=" * 60)
            print("📊 OVERNIGHT TEST STATUS (PID 6683)")
            print("=" * 60)
            
            if process['running']:
                print("✅ Status: RUNNING")
                print(f"📈 Process Info: {process['info']}")
                
                # Parse elapsed time
                parts = process['info'].split()
                if len(parts) >= 2:
                    elapsed = parts[1]  # ELAPSED column
                    print(f"⏱️  Runtime: {elapsed}")
            else:
                print("❌ Status: NOT RUNNING")
                if 'error' in process:
                    print(f"⚠️  Error: {process['error']}")
            
            print()
            
            # Pattern Intelligence Stats
            print("=" * 60)
            print("🧠 PATTERN INTELLIGENCE")
            print("=" * 60)
            
            try:
                intel = get_intelligence()
                health = intel.health_check()
                
                print(f"📊 Total Patterns: {health['total_patterns']}")
                print(f"📈 Patterns with Trades: {health['patterns_with_trades']}")
                print(f"✅ Average Win Rate: {health['average_win_rate']:.1%}")
                print(f"💰 Average Expectancy: {health['average_expectancy']:.2%}")
                
                if health.get('warnings'):
                    print(f"\n⚠️  Warnings:")
                    for warning in health['warnings']:
                        print(f"   • {warning}")
                
                # Top 3 patterns
                top_patterns = intel.get_top_patterns(n=3, min_trades=3)
                if top_patterns:
                    print(f"\n🏆 Top 3 Patterns:")
                    for i, p in enumerate(top_patterns, 1):
                        print(f"   {i}. {p['pattern_id'][:30]}...")
                        print(f"      Win Rate: {p['win_rate']:.1%} | "
                              f"Expectancy: {p['expectancy']:.2%} | "
                              f"Trades: {p['times_traded']}")
                
            except Exception as e:
                print(f"⚠️  Could not load pattern intelligence: {e}")
            
            print()
            
            # Market Context
            print("=" * 60)
            print("🌍 MARKET CONTEXT")
            print("=" * 60)
            
            try:
                session_detector = get_session_detector()
                current_session = session_detector.get_session()
                
                print(f"🕐 Trading Session: {current_session.upper()}")
                
                # Session info
                session_info = {
                    'asian_early': '🌏 Asian Early (00-07 UTC) - Low volume',
                    'asian_late': '🌏 Asian Late (07-13 UTC) - Building volume',
                    'european': '🌍 European (07-16 UTC) - High volume',
                    'overlap': '🔥 Overlap (13-16 UTC) - HIGHEST volume!',
                    'us': '🌎 US (16-22 UTC) - High volume'
                }
                
                if current_session in session_info:
                    print(f"ℹ️  {session_info[current_session]}")
                
            except Exception as e:
                print(f"⚠️  Could not load market context: {e}")
            
            print()
            
            # Portfolio (if available)
            print("=" * 60)
            print("💼 PORTFOLIO STATUS")
            print("=" * 60)
            
            try:
                portfolio = PaperTradingPortfolio(load_previous_state=True)
                
                print(f"💰 Balance: R{portfolio.balance:,.2f}")
                print(f"📊 Open Positions: {len(portfolio.positions)}")
                print(f"✅ Closed Positions: {len(portfolio.closed_positions)}")
                
                if portfolio.positions:
                    print(f"\n📍 Active Positions:")
                    for pos in portfolio.positions[:5]:  # Show first 5
                        pnl_pct = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100
                        pnl_symbol = "📈" if pnl_pct > 0 else "📉"
                        print(f"   {pnl_symbol} {pos.symbol}: "
                              f"Entry R{pos.entry_price:,.2f} → "
                              f"Current R{pos.current_price:,.2f} "
                              f"({pnl_pct:+.2f}%)")
                
            except Exception as e:
                print(f"⚠️  Could not load portfolio: {e}")
            
            print()
            
            # Log file status
            print("=" * 60)
            print("📝 LOG FILES")
            print("=" * 60)
            
            log_file = Path("logs/overnight_FIXED_20251016_1637.log")
            if log_file.exists():
                size = log_file.stat().st_size
                print(f"📄 Overnight Log: {size:,} bytes")
                if size <= 100:
                    print("   ⚠️  Log file very small (output may be buffered)")
                else:
                    print("   ✅ Log file growing")
            else:
                print("❌ Log file not found")
            
            print()
            print("=" * 60)
            print(f"🔄 Refreshing in {refresh_interval}s... (Ctrl+C to exit)")
            print("=" * 60)
            
            time.sleep(refresh_interval)
            
    except KeyboardInterrupt:
        print("\n\n✋ Monitor stopped by user")
        print("📊 Final snapshot saved above")
        sys.exit(0)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-Time System Monitor')
    parser.add_argument('--interval', type=int, default=5, 
                       help='Refresh interval in seconds (default: 5)')
    
    args = parser.parse_args()
    
    monitor_system(refresh_interval=args.interval)
