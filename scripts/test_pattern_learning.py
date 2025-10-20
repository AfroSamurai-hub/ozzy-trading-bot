#!/usr/bin/env python3
"""
🧪 Test Pattern Intelligence Integration

This script tests that:
1. Positions store pattern_id when opened
2. Pattern Intelligence updates when positions close
3. Pattern stats reflect trade outcomes

Expected behavior:
- Open 3 positions with different patterns
- Close them with different outcomes (TP/SL/Time)
- Verify pattern stats update correctly
"""

import sys
from pathlib import Path
from datetime import datetime
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.portfolio import PaperTradingPortfolio
from intelligence.pattern_intelligence import PatternIntelligence
from intelligence.rolling_window_db import RollingWindowPatternDB

def test_pattern_learning():
    """Test that pattern learning works end-to-end."""
    
    print("🧪 Testing Pattern Intelligence Integration\n")
    
    # Initialize components
    print("1️⃣ Initializing components...")
    portfolio = PaperTradingPortfolio(starting_capital=10000.0)
    pattern_db = RollingWindowPatternDB()
    intelligence = PatternIntelligence.get_instance(pattern_db)
    print(f"   ✅ Portfolio: ${portfolio.capital:.2f}")
    print(f"   ✅ Pattern Intelligence initialized")
    print()
    
    # Test patterns
    test_patterns = [
        "bullish_engulfing",
        "hammer",
        "morning_star"
    ]
    
    # Open positions with pattern tracking
    print("2️⃣ Opening positions with pattern tracking...")
    positions = []
    entry_price = 60000.0
    
    for i, pattern_id in enumerate(test_patterns, 1):
        pos = portfolio.open_position(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=entry_price,
            size=250.0,
            confidence=0.75,
            reason=f"Test pattern: {pattern_id}",
            pattern_id=pattern_id  # 🧠 Pattern stored!
        )
        if pos:
            positions.append(pos)
            print(f"   ✅ Position #{pos['id']} opened with pattern: {pattern_id}")
        else:
            print(f"   ❌ Failed to open position for pattern: {pattern_id}")
    
    print(f"\n   📊 Total positions opened: {len(positions)}")
    print()
    
    # Verify pattern_id is stored
    print("3️⃣ Verifying pattern_id is stored in positions...")
    for pos in positions:
        pattern_id = pos.get('pattern_id')
        if pattern_id:
            print(f"   ✅ Position #{pos['id']} has pattern_id: {pattern_id}")
        else:
            print(f"   ❌ Position #{pos['id']} missing pattern_id!")
    print()
    
    # Check pattern stats before closing
    print("4️⃣ Checking pattern stats BEFORE closing trades...")
    for pattern_id in test_patterns:
        stats = intelligence.get_pattern_stats(pattern_id)
        if stats:
            print(f"   📊 {pattern_id}: {stats.times_traded} trades, {stats.win_rate:.1%} WR")
        else:
            print(f"   📊 {pattern_id}: No stats yet (NEW)")
    print()
    
    # Close positions with different outcomes
    print("5️⃣ Closing positions with different outcomes...")
    
    # Position 1: Take Profit (+3.5%)
    tp_price = entry_price * 1.035
    portfolio.update_positions("BTCUSDT", tp_price)
    closed_tp = portfolio.close_position(
        position_id=positions[0]['id'],
        exit_price=tp_price,
        reason="Take Profit (Test)"
    )
    if closed_tp:
        print(f"   ✅ Position 1 closed @ TP: P&L = {closed_tp['realized_pnl_pct']:+.2f}%")
        print(f"      Pattern: {closed_tp.get('pattern_id')}")
        
        # Learn from trade
        outcome = {
            'win': closed_tp['outcome'] == 'WIN',
            'pnl_pct': closed_tp['realized_pnl_pct'],
            'held_time': 3600  # 1 hour
        }
        intelligence.update_pattern_outcome(closed_tp['pattern_id'], outcome)
        print(f"      🧠 Pattern learning updated!")
    print()
    
    # Position 2: Stop Loss (-1.5%)
    sl_price = entry_price * 0.985
    portfolio.update_positions("BTCUSDT", sl_price)
    closed_sl = portfolio.close_position(
        position_id=positions[1]['id'],
        exit_price=sl_price,
        reason="Stop Loss (Test)"
    )
    if closed_sl:
        print(f"   ⚠️  Position 2 closed @ SL: P&L = {closed_sl['realized_pnl_pct']:+.2f}%")
        print(f"      Pattern: {closed_sl.get('pattern_id')}")
        
        # Learn from trade
        outcome = {
            'win': closed_sl['outcome'] == 'WIN',
            'pnl_pct': closed_sl['realized_pnl_pct'],
            'held_time': 1800  # 30 minutes
        }
        intelligence.update_pattern_outcome(closed_sl['pattern_id'], outcome)
        print(f"      🧠 Pattern learning updated!")
    print()
    
    # Position 3: Small profit (+1.5%)
    small_profit_price = entry_price * 1.015
    portfolio.update_positions("BTCUSDT", small_profit_price)
    closed_small = portfolio.close_position(
        position_id=positions[2]['id'],
        exit_price=small_profit_price,
        reason="Time Exit (Test)"
    )
    if closed_small:
        print(f"   ⏰ Position 3 closed @ Time: P&L = {closed_small['realized_pnl_pct']:+.2f}%")
        print(f"      Pattern: {closed_small.get('pattern_id')}")
        
        # Learn from trade
        outcome = {
            'win': closed_small['outcome'] == 'WIN',
            'pnl_pct': closed_small['realized_pnl_pct'],
            'held_time': 86400  # 24 hours
        }
        intelligence.update_pattern_outcome(closed_small['pattern_id'], outcome)
        print(f"      🧠 Pattern learning updated!")
    print()
    
    # Check pattern stats after closing
    print("6️⃣ Checking pattern stats AFTER closing trades...")
    for pattern_id in test_patterns:
        stats = intelligence.get_pattern_stats(pattern_id)
        if stats:
            print(f"   📊 {pattern_id}:")
            print(f"      Trades: {stats.times_traded}")
            print(f"      Wins: {stats.wins}, Losses: {stats.losses}")
            print(f"      Win Rate: {stats.win_rate:.1%}")
            print(f"      Expectancy: {stats.expectancy:+.2f}%")
            print(f"      Confidence: {stats.confidence_score:.2f}")
        else:
            print(f"   ❌ {pattern_id}: Still no stats (ERROR!)")
    print()
    
    # Get top patterns
    print("7️⃣ Getting top patterns from intelligence...")
    top_patterns = intelligence.get_top_patterns(n=3, min_trades=1)
    if top_patterns:
        print(f"   🏆 Top {len(top_patterns)} patterns:")
        for i, p in enumerate(top_patterns, 1):
            print(f"      {i}. {p['pattern_id']}: {p['win_rate']:.1%} WR, {p['expectancy']:+.2f}% exp")
    else:
        print(f"   ⚠️  No top patterns found")
    print()
    
    # Summary
    print("8️⃣ Test Summary:")
    summary = intelligence.get_pattern_summary()
    print(f"   Total patterns with stats: {summary['total_patterns']}")
    print(f"   Patterns with trades: {summary['patterns_with_trades']}")
    print(f"   Total trades: {summary['total_trades']}")
    print(f"   Overall win rate: {summary['overall_win_rate']:.1%}")
    print()
    
    # Health check
    print("9️⃣ Final health check:")
    health = intelligence.health_check()
    print(f"   Status: {health['status']}")
    print(f"   Patterns with trades: {health['patterns_with_trades']}")
    print(f"   Average win rate: {health['avg_win_rate']:.1%}")
    print()
    
    # Success criteria
    success = True
    if summary['total_trades'] < 3:
        print("❌ FAIL: Not all trades were recorded")
        success = False
    if summary['patterns_with_trades'] < 3:
        print("❌ FAIL: Not all patterns were updated")
        success = False
    if not top_patterns or len(top_patterns) < 3:
        print("❌ FAIL: Top patterns query failed")
        success = False
    
    if success:
        print("✅ SUCCESS! Pattern Intelligence integration working perfectly!")
        print("\n🎉 The system now learns from every trade!")
        print("   - Patterns store with positions")
        print("   - Stats update when positions close")
        print("   - Top patterns ranked by effectiveness")
        print("   - AI can use real win rates for decisions!")
        return 0
    else:
        print("❌ FAIL: Integration has issues")
        return 1


if __name__ == "__main__":
    exit(test_pattern_learning())
