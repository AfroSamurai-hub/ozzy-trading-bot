#!/usr/bin/env python3
"""
Test the outcome tracker by feeding it the 24 decisions from our stability test.
This will simulate the capture → label → analyze flow.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.track_trade_outcomes import TradeOutcomeTracker


def load_test_decisions():
    """Load the 24 decisions from our test"""
    test_file = Path("scripts/logs/test_detailed_20251017_134454.json")
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return []
    
    with open(test_file) as f:
        data = json.load(f)
    
    return data['decisions']


def main():
    print("="*70)
    print("🧪 TESTING OUTCOME TRACKER WITH REAL TEST DATA")
    print("="*70)
    
    # Initialize tracker
    tracker = TradeOutcomeTracker()
    
    # Load test decisions
    decisions = load_test_decisions()
    print(f"\n📊 Loaded {len(decisions)} decisions from stability test")
    
    # Filter BUY decisions only
    buy_decisions = [d for d in decisions if d['action'] == 'BUY']
    print(f"📈 Found {len(buy_decisions)} BUY decisions to track\n")
    
    # Stage 1: Capture trades
    print("📸 STAGE 1: Capturing trades...")
    print("-" * 70)
    captured_ids = []
    for decision in buy_decisions:
        trade_id = tracker.capture_trade(decision)
        if trade_id:
            captured_ids.append(trade_id)
    
    print(f"\n✅ Captured {len(captured_ids)} trades")
    print(f"📂 Pending trades: {len(tracker.pending_trades)}")
    
    # Show pending trades
    print("\n📋 PENDING TRADES:")
    print("-" * 70)
    for i, trade in enumerate(tracker.pending_trades, 1):
        print(f"{i}. {trade['id']}")
        print(f"   Pattern: {trade['pattern']} | Confidence: {trade['confidence']*100:.0f}%")
        print(f"   Entry: R{trade['entry_price']:.2f} | Regime: {trade['regime']}")
    
    # Stage 2: Simulate outcomes (force them to complete)
    print("\n\n⏰ STAGE 2: Simulating outcomes (forcing completion)...")
    print("-" * 70)
    
    # Manually age the trades so they get labeled
    from datetime import datetime, timedelta
    for trade in tracker.pending_trades:
        # Set timestamp to 2 hours ago so they're old enough to label
        old_time = datetime.now() - timedelta(hours=2)
        trade['timestamp'] = old_time.isoformat()
    tracker._save_pending()
    
    # Now monitor and label
    labeled = tracker.monitor_outcomes()
    print(f"\n✅ Labeled {labeled} trades")
    
    # Show statistics
    print("\n\n📊 FINAL STATISTICS:")
    print("="*70)
    stats = tracker.get_stats()
    
    print(f"Total Labeled: {stats['total_labeled']}")
    print(f"Pending: {stats['pending_trades']}")
    print(f"\nWins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Breakevens: {stats['breakevens']}")
    print(f"\nWin Rate: {stats['win_rate']}")
    print(f"Avg P&L: {stats['avg_pnl']}")
    
    print(f"\nOutcome Breakdown:")
    for outcome, count in stats['outcome_breakdown'].items():
        print(f"  {outcome}: {count}")
    
    print("\n" + "="*70)
    print("✅ TEST COMPLETE!")
    print("="*70)
    
    print("\n💡 NEXT STEPS:")
    print("1. Integrate with actual position tracking (replace simulation)")
    print("2. Build pattern performance analyzer (Day 3)")
    print("3. Build volume impact analyzer (Day 3)")
    print("4. Start generating quality reports")
    
    print(f"\n📂 Data stored in: data/trade_labels/")
    print(f"   ChromaDB collection: 'trade_outcomes' ({stats['total_labeled']} trades)")


if __name__ == '__main__':
    main()
