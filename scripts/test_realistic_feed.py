#!/usr/bin/env python3
"""Test RealisticMockFeed with actual patterns from ChromaDB"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stream.realistic_mock_feed import RealisticMockFeed
from intelligence.rolling_window_db import RollingWindowPatternDB


async def main():
    print("🧪 Testing RealisticMockFeed with ChromaDB patterns...")
    print()
    
    # Initialize pattern database
    pattern_db = RollingWindowPatternDB(persist_directory="data/vector_db")
    pattern_count = pattern_db.count()
    print(f"📊 Pattern database has {pattern_count} patterns")
    
    # Create realistic feed with pattern DB
    feed = RealisticMockFeed(
        symbol="BTCUSDT",
        interval_ms=100,  # Fast for testing
        pattern_db=pattern_db,
        base_price=60000.0,
        win_rate_target=0.70,  # 70% winners
        regime_duration=30,  # Change regime every 30 ticks
    )
    
    print()
    print("🎲 Starting tick generation...")
    print()
    
    tick_count = 0
    regime_changes = []
    last_regime = feed.current_regime
    
    async for tick in feed.ticks():
        tick_count += 1
        
        # Track regime changes
        if feed.current_regime != last_regime:
            regime_changes.append((tick_count, feed.current_regime))
            last_regime = feed.current_regime
        
        # Print every 10th tick
        if tick_count % 10 == 0:
            print(f"📊 Tick {tick_count:3d}: {tick.symbol} @ ${tick.price:>10,.2f} | Regime: {feed.current_regime}")
        
        if tick_count >= 100:
            break
    
    await feed.close()
    
    print()
    print("=" * 70)
    print("📈 TEST SUMMARY")
    print()
    print(f"✅ Generated {tick_count} realistic ticks")
    print(f"   Price range: ${feed.base_price:,.2f} → ${feed.current_price:,.2f}")
    print(f"   Price change: {((feed.current_price - feed.base_price) / feed.base_price * 100):+.2f}%")
    print(f"   Patterns loaded: {len(feed.winning_patterns)} wins, {len(feed.losing_patterns)} losses")
    print(f"   Final regime: {feed.current_regime}")
    print()
    print(f"📊 Regime changes: {len(regime_changes)}")
    for tick, regime in regime_changes:
        print(f"   Tick {tick}: → {regime}")
    print()
    print("✅ RealisticMockFeed with ChromaDB patterns: WORKING!")


if __name__ == "__main__":
    asyncio.run(main())
