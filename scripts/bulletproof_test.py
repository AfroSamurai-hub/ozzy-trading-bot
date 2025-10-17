#!/usr/bin/env python3
"""
🔥 BULLETPROOF LIVE STREAM TEST - NO MORE HANGING! 🔥

This version is:
- SYNCHRONOUS (no async complexity)
- VERBOSE (prints everything)
- UNBUFFERED (see output immediately)
- TIMEOUT-PROTECTED (cannot hang)
- SIMPLE (obvious what it's doing)
"""

import sys
import os
import time
import signal
import json
from datetime import datetime, timezone
from pathlib import Path

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

print(f"\n{'='*60}")
print(f"🔥 BULLETPROOF TEST STARTING")
print(f"{'='*60}")
print(f"⏰ Start Time: {datetime.now()}")
print(f"📁 Project Root: {PROJECT_ROOT}")
sys.stdout.flush()

# Load environment
print(f"\n[{datetime.now()}] Loading environment...")
sys.stdout.flush()
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")
    print(f"✅ Environment loaded")
else:
    print(f"⚠️  No .env file found")
sys.stdout.flush()

# Import components
print(f"\n[{datetime.now()}] Importing components...")
sys.stdout.flush()

try:
    from agent.portfolio import PaperTradingPortfolio
    print(f"✅ Portfolio imported")
    sys.stdout.flush()
    
    from agent.trader import TradingAgent
    print(f"✅ TradingAgent imported")
    sys.stdout.flush()
    
    from mcp.trading_server import TradingMCPServer
    print(f"✅ MCP Server imported")
    sys.stdout.flush()
    
    from intelligence.realistic_mock_feed import RealisticMockFeed
    print(f"✅ RealisticMockFeed imported")
    sys.stdout.flush()
    
except Exception as e:
    print(f"❌ IMPORT FAILED: {e}")
    sys.stdout.flush()
    sys.exit(1)


class TimeoutException(Exception):
    """Raised when operation times out"""
    pass


def timeout_handler(signum, frame):
    """Handle timeout signal"""
    print(f"\n❌ TIMEOUT! Operation took too long!")
    sys.stdout.flush()
    raise TimeoutException("Operation exceeded timeout")


def safe_call(func, *args, timeout_seconds=120, **kwargs):
    """
    Call a function with timeout protection.
    
    Args:
        func: Function to call
        timeout_seconds: Max seconds to wait
        *args, **kwargs: Function arguments
    
    Returns:
        Function result or None if timeout
    """
    print(f"[{datetime.now()}] Calling {func.__name__} (timeout: {timeout_seconds}s)...")
    sys.stdout.flush()
    
    # Set timeout alarm
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)
    
    try:
        result = func(*args, **kwargs)
        signal.alarm(0)  # Cancel alarm
        print(f"✅ {func.__name__} completed")
        sys.stdout.flush()
        return result
    except TimeoutException:
        print(f"❌ {func.__name__} TIMED OUT after {timeout_seconds}s!")
        sys.stdout.flush()
        signal.alarm(0)
        return None
    except Exception as e:
        print(f"❌ {func.__name__} FAILED: {e}")
        sys.stdout.flush()
        signal.alarm(0)
        return None


def write_progress(message, progress_file="logs/test_progress.txt"):
    """Write progress to file (immediate flush)"""
    try:
        with open(progress_file, 'a') as f:
            f.write(f"[{datetime.now()}] {message}\n")
            f.flush()
            os.fsync(f.fileno())  # Force OS to write to disk
    except Exception as e:
        print(f"⚠️  Could not write progress: {e}")
        sys.stdout.flush()


def run_test(
    symbol: str = "BTCUSDT",
    duration_seconds: int = 600,
    decision_interval: int = 60,
    capital: float = 10000.0
):
    """
    Run the bulletproof test.
    
    Args:
        symbol: Trading symbol
        duration_seconds: Total test duration
        decision_interval: Seconds between decisions
        capital: Starting capital
    """
    
    print(f"\n{'='*60}")
    print(f"📋 TEST CONFIGURATION")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Duration: {duration_seconds}s ({duration_seconds/60:.1f} minutes)")
    print(f"Decision Interval: {decision_interval}s")
    print(f"Capital: R{capital:,.2f}")
    
    max_decisions = int(duration_seconds / decision_interval)
    print(f"Expected Decisions: {max_decisions}")
    sys.stdout.flush()
    
    write_progress(f"Test starting: {symbol}, {max_decisions} decisions")
    
    # Initialize portfolio
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] INITIALIZING PORTFOLIO")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    try:
        portfolio = PaperTradingPortfolio(
            starting_capital=capital,
            max_positions=20,
            max_exposure_pct=0.80
        )
        print(f"✅ Portfolio initialized")
        print(f"   Capital: R{portfolio.capital:,.2f}")
        print(f"   Max Positions: 20")
        sys.stdout.flush()
        write_progress(f"Portfolio initialized: R{portfolio.capital:,.2f}")
    except Exception as e:
        print(f"❌ Portfolio initialization FAILED: {e}")
        sys.stdout.flush()
        return
    
    # Initialize MCP server
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] INITIALIZING MCP SERVER")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    try:
        from intelligence.rolling_window_db import RollingWindowPatternDB
        pattern_db = RollingWindowPatternDB()
        # 🔥 FIX: Pass actual portfolio to MCP so it sees real capital!
        mcp_server = TradingMCPServer(pattern_db=pattern_db, portfolio=portfolio)
        print(f"✅ MCP Server initialized (connected to portfolio)")
        sys.stdout.flush()
        write_progress("MCP Server initialized")
    except Exception as e:
        print(f"❌ MCP Server initialization FAILED: {e}")
        sys.stdout.flush()
        return
    
    # Initialize trading agent
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] INITIALIZING TRADING AGENT")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    try:
        agent = TradingAgent(
            mcp_server=mcp_server,
            capital=capital,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        print(f"✅ Trading Agent initialized")
        sys.stdout.flush()
        write_progress("Trading Agent initialized")
    except Exception as e:
        print(f"❌ Agent initialization FAILED: {e}")
        sys.stdout.flush()
        return
    
    # Initialize mock feed
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] INITIALIZING MOCK FEED")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    try:
        mock_feed = RealisticMockFeed(symbol=symbol, base_price=67000.0)
        print(f"✅ Mock feed initialized")
        sys.stdout.flush()
        write_progress("Mock feed initialized")
    except Exception as e:
        print(f"❌ Mock feed initialization FAILED: {e}")
        sys.stdout.flush()
        return
    
    # MAIN DECISION LOOP
    print(f"\n{'='*60}")
    print(f"{'='*60}")
    print(f"🚀 STARTING DECISION LOOP")
    print(f"{'='*60}")
    print(f"{'='*60}\n")
    sys.stdout.flush()
    
    write_progress("Decision loop starting")
    
    decisions_made = 0
    decisions_log = []
    start_time = time.time()
    
    for i in range(max_decisions):
        decision_start = time.time()
        
        print(f"\n{'='*60}")
        print(f"🎯 DECISION #{i+1}/{max_decisions}")
        print(f"{'='*60}")
        print(f"⏰ Time: {datetime.now()}")
        elapsed = time.time() - start_time
        print(f"⏱️  Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
        sys.stdout.flush()
        
        write_progress(f"Decision #{i+1}/{max_decisions} starting")
        
        # Get market data
        print(f"\n[{datetime.now()}] Getting market tick...")
        sys.stdout.flush()
        
        try:
            # Need to run async method synchronously
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ticker = loop.run_until_complete(mock_feed.get_ticker())
            loop.close()
            
            price = float(ticker.get('last_price', 0))
            print(f"✅ Market data received")
            print(f"   Price: R{price:,.2f}")
            print(f"   Symbol: {ticker.get('symbol', 'N/A')}")
            sys.stdout.flush()
        except Exception as e:
            print(f"❌ Failed to get market data: {e}")
            sys.stdout.flush()
            continue
        
        # Make decision (with timeout)
        print(f"\n[{datetime.now()}] Analyzing and making decision with AI...")
        sys.stdout.flush()
        
        def make_decision():
            """Call AI to make decision"""
            try:
                # Run async method synchronously
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                print(f"   Calling agent.analyze_and_decide({symbol})...")
                sys.stdout.flush()
                
                decision = loop.run_until_complete(agent.analyze_and_decide(symbol))
                loop.close()
                
                print(f"   AI responded with: {decision.get('action', 'UNKNOWN')}")
                sys.stdout.flush()
                
                return decision
            except Exception as e:
                print(f"   ⚠️  AI decision failed: {e}")
                sys.stdout.flush()
                # Return safe default on error
                return {
                    'action': 'SKIP',
                    'confidence': 0.0,
                    'reasoning': f'Error in AI decision: {str(e)}'
                }
        
        decision = safe_call(make_decision, timeout_seconds=90)
        
        if decision is None:
            print(f"❌ Decision timed out or failed!")
            sys.stdout.flush()
            write_progress(f"Decision #{i+1} FAILED (timeout)")
            continue
        
        decisions_made += 1
        
        # Log decision
        action = decision.get('action', 'UNKNOWN')
        confidence = decision.get('confidence', 0)
        reasoning = decision.get('reasoning', 'N/A')
        
        print(f"\n✅ DECISION COMPLETE:")
        print(f"   Action: {action}")
        print(f"   Confidence: {confidence:.1%}")
        print(f"   Reasoning: {reasoning[:80]}...")
        
        decision_time = time.time() - decision_start
        print(f"   Decision Time: {decision_time:.2f}s")
        sys.stdout.flush()
        
        # Save decision
        decisions_log.append({
            'index': i + 1,
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'confidence': confidence,
            'reasoning': reasoning,
            'price': price,
            'duration_seconds': decision_time
        })
        
        write_progress(f"Decision #{i+1} complete: {action} ({confidence:.1%})")
        
        # 🔥 EXECUTE TRADE if BUY/SELL (was missing!)
        if action == "BUY" and price > 0:
            print(f"\n💰 EXECUTING BUY...")
            sys.stdout.flush()
            
            position_size = decision.get('position_size', capital * 0.05)
            try:
                position = portfolio.open_position(
                    symbol=symbol,
                    side="LONG",
                    entry_price=price,
                    size=position_size,
                    confidence=confidence,
                    reason=reasoning
                )
                
                if position:
                    print(f"   ✅ Position #{position['id']} opened @ R{price:,.2f}")
                    write_progress(f"Position #{position['id']} opened: {symbol} @ R{price:,.2f}")
                else:
                    print(f"   ⏭️  Position rejected by risk management")
                    write_progress(f"Position rejected (risk limits)")
                    
            except Exception as e:
                print(f"   ❌ Error opening position: {e}")
                write_progress(f"Error opening position: {e}")
            
            sys.stdout.flush()
        
        elif action == "SELL" and price > 0:
            print(f"\n� EXECUTING SELL (closing positions)...")
            sys.stdout.flush()
            
            closed_count = 0
            for pos in portfolio.positions[:]:
                if pos['symbol'] == symbol and pos.get('status') == 'OPEN':
                    try:
                        closed = portfolio.close_position(
                            position_id=pos['id'],
                            exit_price=price,
                            reason=f"AI Decision: {reasoning[:50]}"
                        )
                        if closed:
                            closed_count += 1
                            print(f"   ✅ Position #{pos['id']} closed @ R{price:,.2f}")
                    except Exception as e:
                        print(f"   ❌ Error closing position #{pos['id']}: {e}")
            
            if closed_count > 0:
                write_progress(f"Closed {closed_count} positions")
            else:
                print(f"   ℹ️  No positions to close")
            
            sys.stdout.flush()
        
        # Update positions with current price
        if price > 0:
            portfolio.update_positions(symbol, price)
            
            # 🎯 CHECK TP/SL ON ALL OPEN POSITIONS
            print(f"\n🔍 Checking TP/SL conditions...")
            sys.stdout.flush()
            
            TP_PCT = 2.0  # 2% take profit
            SL_PCT = 1.0  # 1% stop loss
            
            for pos in portfolio.positions[:]:
                if pos.get('status') != 'OPEN' or pos['symbol'] != symbol:
                    continue
                
                pnl_pct = pos.get('pnl_pct', 0)
                
                # Check take profit
                if pnl_pct >= TP_PCT:
                    print(f"   🎯 TP HIT on Position #{pos['id']}: {pnl_pct:.2f}% >= {TP_PCT}%")
                    sys.stdout.flush()
                    
                    try:
                        closed = portfolio.close_position(
                            position_id=pos['id'],
                            exit_price=price,
                            reason=f"Take Profit ({pnl_pct:.2f}%)"
                        )
                        if closed:
                            print(f"      ✅ Position closed with profit: R{closed['realized_pnl']:,.2f}")
                            write_progress(f"TP: Position #{pos['id']} closed @ +{pnl_pct:.2f}%")
                    except Exception as e:
                        print(f"      ❌ Error closing position: {e}")
                    
                    sys.stdout.flush()
                
                # Check stop loss
                elif pnl_pct <= -SL_PCT:
                    print(f"   🛑 SL HIT on Position #{pos['id']}: {pnl_pct:.2f}% <= -{SL_PCT}%")
                    sys.stdout.flush()
                    
                    try:
                        closed = portfolio.close_position(
                            position_id=pos['id'],
                            exit_price=price,
                            reason=f"Stop Loss ({pnl_pct:.2f}%)"
                        )
                        if closed:
                            print(f"      ✅ Position closed with loss: R{closed['realized_pnl']:,.2f}")
                            write_progress(f"SL: Position #{pos['id']} closed @ {pnl_pct:.2f}%")
                    except Exception as e:
                        print(f"      ❌ Error closing position: {e}")
                    
                    sys.stdout.flush()
                
                else:
                    # Position still open - show current P&L
                    print(f"   📊 Position #{pos['id']}: {pnl_pct:+.2f}% (holding)")
            
            sys.stdout.flush()
        
        # Portfolio status
        print(f"\n�💼 Portfolio Status:")
        print(f"   Capital: R{portfolio.capital:,.2f}")
        print(f"   Open Positions: {len([p for p in portfolio.positions if p.get('status') == 'OPEN'])}")
        sys.stdout.flush()
        
        # Wait for next decision (unless last one)
        if i < max_decisions - 1:
            print(f"\n[{datetime.now()}] Waiting {decision_interval}s until next decision...")
            sys.stdout.flush()
            write_progress(f"Sleeping {decision_interval}s")
            
            # Simple sleep (no async complexity)
            time.sleep(decision_interval)
            
            print(f"[{datetime.now()}] Wait complete! Moving to next decision...")
            sys.stdout.flush()
            write_progress("Sleep complete")
    
    # FINAL SUMMARY
    total_time = time.time() - start_time
    
    print(f"\n\n{'='*60}")
    print(f"{'='*60}")
    print(f"🎉 TEST COMPLETE!")
    print(f"{'='*60}")
    print(f"{'='*60}\n")
    
    print(f"📊 RESULTS:")
    print(f"   Duration: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"   Expected Decisions: {max_decisions}")
    print(f"   Actual Decisions: {decisions_made}")
    print(f"   Success Rate: {decisions_made/max_decisions*100:.1f}%")
    
    if decisions_log:
        actions = {}
        for d in decisions_log:
            action = d['action']
            actions[action] = actions.get(action, 0) + 1
        
        print(f"\n   Decision Breakdown:")
        for action, count in actions.items():
            print(f"      {action}: {count}")
    
    print(f"\n💼 Final Portfolio:")
    print(f"   Capital: R{portfolio.capital:,.2f}")
    print(f"   Open Positions: {len(portfolio.positions)}")
    print(f"   Closed Trades: {len(portfolio.closed_trades)}")
    
    sys.stdout.flush()
    
    write_progress(f"Test complete! {decisions_made}/{max_decisions} decisions")
    
    # Save detailed log
    log_file = f"logs/test_detailed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(log_file, 'w') as f:
            json.dump({
                'config': {
                    'symbol': symbol,
                    'duration': duration_seconds,
                    'interval': decision_interval,
                    'capital': capital
                },
                'results': {
                    'total_time': total_time,
                    'decisions_made': decisions_made,
                    'decisions_expected': max_decisions
                },
                'decisions': decisions_log,
                'portfolio': {
                    'capital': portfolio.capital,
                    'open_positions': len(portfolio.positions),
                    'closed_trades': len(portfolio.closed_trades)
                }
            }, f, indent=2)
        print(f"\n📝 Detailed log saved: {log_file}")
    except Exception as e:
        print(f"\n⚠️  Could not save detailed log: {e}")
    
    sys.stdout.flush()
    
    print(f"\n✅ ALL DONE!")
    print(f"{'='*60}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Bulletproof Live Stream Test - Optimized for 15-min overnight runs')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--duration', type=int, default=21600, help='Test duration in seconds (default: 6 hours for overnight)')
    parser.add_argument('--interval', type=int, default=900, help='Decision interval in seconds (default: 900 = 15 minutes, less noisy)')
    parser.add_argument('--capital', type=float, default=10000.0, help='Starting capital')
    
    args = parser.parse_args()
    
    try:
        run_test(
            symbol=args.symbol,
            duration_seconds=args.duration,
            decision_interval=args.interval,
            capital=args.capital
        )
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Test interrupted by user!")
        sys.stdout.flush()
        write_progress("Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        write_progress(f"Fatal error: {e}")
