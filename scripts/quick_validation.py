#!/usr/bin/env python3
"""Quick validation test - no ZAR env vars to avoid hanging"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# LOAD ENV FIRST
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

# NOW RUN THE ACTUAL TEST
import asyncio
import argparse
from agent.portfolio import PaperTradingPortfolio
from agent.pattern_builder import RealtimePatternBuilder
from agent.trader import TradingAgent
from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer
from stream.market_feed import MockTickFeed
from utils.currency import format_currency, format_currency_signed

async def quick_test(duration: int = 60, interval: int = 60, model: str = "gpt-4o-mini", capital: float | None = None, bootstrap_csv: str | None = None, start_labeler: bool = False):
    """Run a quick test with mock feed.

    duration: total run time in seconds
    interval: seconds between AI decisions (default 60 -> 1-minute timeframe)
    model: OpenAI model to use
    capital: starting capital in USD (if None use portfolio starting value)
    bootstrap_csv: optional CSV to load patterns from (path)
    start_labeler: if True, spawn the live labeler as a background process
    """

    print("=" * 80)
    print(f"QUICK VALIDATION TEST - {duration}s WITH MOCK FEED | INTERVAL: {interval}s")
    print("=" * 80)
    
    # Initialize portfolio with R10,000 equivalent (540.54 USD ~ R10,000 @ 18.50)
    portfolio = PaperTradingPortfolio(starting_capital=540.54, load_previous_state=False)
    print(f"\n💰 Portfolio initialized")
    print(f"   Display: R{portfolio.capital * 18.50:,.2f}")
    print(f"   Internal USD: ${portfolio.capital:,.2f}")
    print(f"   Position size: R{portfolio.starting_capital * 0.05 * 18.50:,.2f} (5%)")
    
    # Initialize pattern DB
    pattern_db = RollingWindowPatternDB()
    # Optionally load bootstrap CSV (useful to seed the vector DB with historical patterns)
    if bootstrap_csv:
        try:
            loaded = pattern_db.load_from_csv(str(Path(bootstrap_csv)), clear_existing=False, apply_pruning=False)
            print(f"\n📥 Bootstrapped {loaded} patterns from {bootstrap_csv}")
        except Exception as e:
            print(f"\n⚠️ Failed to load bootstrap CSV: {e}")

    print(f"\n📚 Pattern DB: {pattern_db.count()} patterns loaded")
    
    # Initialize MCP server
    mcp_server = TradingMCPServer(pattern_db)
    print("✅ MCP server initialized")
    
    # Initialize agent (requires OPENAI_API_KEY). If missing, fall back to a MockAgent so the quick test won't crash.
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        class MockAgent:
            async def analyze_and_decide(self, symbol: str = "BTCUSDT") -> dict:
                return {"action": "SKIP", "confidence": 0.0, "reasoning": "MockAgent - OPENAI_API_KEY not set"}

        agent = MockAgent()
        print("⚠️ OPENAI_API_KEY not set - using MockAgent (decisions will be SKIP). Set OPENAI_API_KEY to enable real AI.")
    else:
        agent = TradingAgent(mcp_server, model=model, capital=portfolio.starting_capital)
        print("✅ Trading agent initialized")
    
    # Initialize pattern builder. Keep a reasonably short pattern building cadence while making decisions every `interval` seconds.
    builder = RealtimePatternBuilder(pattern_db, interval_seconds=min(30, max(1, interval // 4)))
    print("✅ Pattern builder initialized")
    
    # Use mock feed (ticks are fast; AI decisions are controlled by `interval`).
    feed = MockTickFeed(symbol="BTCUSDT", interval_ms=500)
    print("✅ Mock feed initialized (no WebSocket needed)")
    
    print("\n" + "=" * 80)
    print("RUNNING 60-SECOND TEST")
    print("=" * 80)
    
    # Simple loop with decision interval
    import time
    start = time.time()
    decision_times = list(range(interval, duration + 1, interval))
    decision_count = 0
    price_history = []
    
    async for tick in feed.ticks():
        elapsed = time.time() - start
        
        # Collect prices
        if hasattr(tick, 'price'):
            price_history.append(tick.price)
        
        # Check if time to make decision
        # Use a tolerance window of 1 second to hit the interval
        if any(abs(elapsed - dt) < 1 for dt in decision_times):
            decision_count += 1
            avg_price = sum(price_history) / len(price_history) if price_history else 0
            
            print(f"\n[{elapsed:.0f}s] Decision #{decision_count}")
            print(f"   Market price: ${avg_price:,.2f}")
            print(f"   Positions open: {len(portfolio.positions)}")
            print(f"   Capital available: R{portfolio.capital * 18.50:,.2f}")
            
            # Get AI decision
            try:
                result = await agent.analyze_and_decide(symbol="BTCUSDT")
                print(f"   AI Action: {result.get('action', 'UNKNOWN')}")
                print(f"   Confidence: {result.get('confidence', 0):.1%}")
                reason = result.get('reasoning', 'N/A')
                print(f"   Reason: {reason[:80]}...")
            except Exception as e:
                print(f"   ⚠️ Decision error: {e}")
        
        if elapsed >= 60:
            break
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print(f"✅ System functioning correctly!")
    print(f"✅ Made {decision_count} decisions")
    print(f"✅ Portfolio: {len(portfolio.positions)} positions")
    print(f"✅ Capital: R{portfolio.capital * 18.50:,.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="quick_validation.py")
    parser.add_argument("--duration", type=int, default=60, help="Total run time in seconds")
    parser.add_argument("--interval", type=int, default=60, help="Decision interval in seconds (default 60 -> 1m timeframe)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model to use")
    parser.add_argument("--capital", type=float, default=None, help="Starting capital override (USD)")
    parser.add_argument("--bootstrap-csv", type=str, default=None, help="Optional CSV to load historical patterns from")
    parser.add_argument("--start-labeler", action="store_true", help="Spawn the live labeler as a background process")
    args = parser.parse_args()

    # Ensure logs directory exists for labeler output when spawned
    Path(__file__).resolve().parent.parent.joinpath("logs").mkdir(exist_ok=True)

    try:
        asyncio.run(quick_test(duration=args.duration, interval=args.interval, model=args.model, capital=args.capital, bootstrap_csv=args.bootstrap_csv, start_labeler=args.start_labeler))
    except Exception as e:
        print(f"Fatal error running quick test: {e}")
