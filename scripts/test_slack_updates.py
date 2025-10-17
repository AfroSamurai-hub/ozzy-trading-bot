#!/usr/bin/env python3
"""
Test the new Slack position update notifications
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from notifications.slack_notifier import SlackNotifier
import os

# Load .env
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

def test_position_update():
    """Test position update with visual progress bars"""
    notifier = SlackNotifier()
    
    if not notifier.enabled:
        print("❌ Slack webhook not configured!")
        print("Set SLACK_WEBHOOK_URL in .env file")
        return False
    
    print("📊 Testing position update notification...")
    
    # Simulate a position near take profit
    position_near_tp = {
        "id": 1,
        "symbol": "BTCUSDT",
        "entry_price": 112000.00,
        "size": 250.00,
        "unrealized_pnl": 6.50,  # +2.6%
        "pnl_pct": 2.6,
        "status": "OPEN"
    }
    
    current_price = 112900.00
    tp_price = 112000.00 * 1.03  # +3%
    sl_price = 112000.00 * 0.985  # -1.5%
    
    success = notifier.notify_position_update(
        position=position_near_tp,
        current_price=current_price,
        tp_price=tp_price,
        sl_price=sl_price
    )
    
    if success:
        print("✅ Position update (near TP) sent!")
    else:
        print("❌ Failed to send position update")
        return False
    
    print("\n⏳ Waiting 2 seconds...\n")
    import time
    time.sleep(2)
    
    # Simulate a position near stop loss
    position_near_sl = {
        "id": 2,
        "symbol": "BTCUSDT",
        "entry_price": 113000.00,
        "size": 250.00,
        "unrealized_pnl": -3.25,  # -1.3%
        "pnl_pct": -1.3,
        "status": "OPEN"
    }
    
    current_price = 111530.00
    tp_price = 113000.00 * 1.03
    sl_price = 113000.00 * 0.985
    
    success = notifier.notify_position_update(
        position=position_near_sl,
        current_price=current_price,
        tp_price=tp_price,
        sl_price=sl_price
    )
    
    if success:
        print("✅ Position update (near SL) sent!")
    else:
        print("❌ Failed to send position update")
        return False
    
    return True


def test_positions_summary():
    """Test positions summary notification"""
    notifier = SlackNotifier()
    
    if not notifier.enabled:
        print("❌ Slack webhook not configured!")
        return False
    
    print("\n📊 Testing positions summary notification...")
    
    # Simulate multiple positions
    positions = [
        {
            "id": 1,
            "symbol": "BTCUSDT",
            "entry_price": 112000.00,
            "size": 250.00,
            "unrealized_pnl": 6.50,
            "status": "OPEN"
        },
        {
            "id": 2,
            "symbol": "BTCUSDT",
            "entry_price": 113000.00,
            "size": 250.00,
            "unrealized_pnl": -3.25,
            "status": "OPEN"
        },
        {
            "id": 3,
            "symbol": "BTCUSDT",
            "entry_price": 112500.00,
            "size": 250.00,
            "unrealized_pnl": 1.20,
            "status": "OPEN"
        },
        {
            "id": 4,
            "symbol": "BTCUSDT",
            "entry_price": 112700.00,
            "size": 250.00,
            "unrealized_pnl": -0.30,
            "status": "OPEN"
        },
        {
            "id": 5,
            "symbol": "BTCUSDT",
            "entry_price": 111800.00,
            "size": 250.00,
            "unrealized_pnl": 7.80,
            "status": "OPEN"
        }
    ]
    
    current_prices = {"BTCUSDT": 112650.00}
    total_pnl = sum(p["unrealized_pnl"] for p in positions)
    capital = 5000 - (len(positions) * 250)
    
    success = notifier.notify_positions_summary(
        positions=positions,
        current_prices=current_prices,
        total_pnl=total_pnl,
        capital=capital
    )
    
    if success:
        print("✅ Positions summary sent!")
    else:
        print("❌ Failed to send positions summary")
        return False
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING NEW SLACK POSITION UPDATES")
    print("=" * 60)
    print()
    
    # Test individual position updates
    if test_position_update():
        print("\n✅ Position update tests passed!")
    else:
        print("\n❌ Position update tests failed!")
        sys.exit(1)
    
    # Test positions summary
    if test_positions_summary():
        print("\n✅ Positions summary test passed!")
    else:
        print("\n❌ Positions summary test failed!")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Check your Slack channel for the notifications!")
    print()
    print("You should see:")
    print("  1. Position near Take Profit (with green progress bar)")
    print("  2. Position near Stop Loss (with red progress bar)")
    print("  3. Summary of 5 positions with status breakdown")
    print()
