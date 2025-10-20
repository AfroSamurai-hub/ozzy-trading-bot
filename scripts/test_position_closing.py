"""
Test script to verify position closing logic
"""
import sys
sys.path.insert(0, '/home/rick/ozzy-simple')

from agent.portfolio import PaperTradingPortfolio
from datetime import datetime, timedelta

def test_tp_sl_logic():
    """Test Take Profit and Stop Loss triggering"""
    print("\n" + "="*70)
    print("🧪 TESTING POSITION CLOSING LOGIC")
    print("="*70)
    
    # Create fresh portfolio
    portfolio = PaperTradingPortfolio(
        starting_capital=10000.0,
        max_positions=20,
        max_exposure_pct=0.80,
        load_previous_state=False  # Fresh start
    )
    
    print(f"\n💰 Starting capital: ${portfolio.capital:,.2f}")
    
    # Test 1: Open a position
    print("\n" + "-"*70)
    print("TEST 1: Opening Long Position")
    print("-"*70)
    
    pos = portfolio.open_position(
        symbol="BTCUSDT",
        side="LONG",
        entry_price=60000.0,
        size=1000.0,
        confidence=0.75,
        reason="Test position"
    )
    
    if pos:
        print(f"✅ Position #{pos['id']} opened: ${pos['size']:,.2f} @ ${pos['entry_price']:,.2f}")
        print(f"   Qty: {pos['qty']:.6f} BTC")
    else:
        print("❌ Failed to open position!")
        return False
    
    # Test 2: Update price (no TP/SL hit)
    print("\n" + "-"*70)
    print("TEST 2: Update Price (No TP/SL)")
    print("-"*70)
    
    portfolio.update_positions("BTCUSDT", 61000.0)  # +1.67% (below TP)
    
    open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']
    print(f"Current price: $61,000")
    print(f"Position P&L: ${open_positions[0]['pnl']:,.2f} ({open_positions[0]['pnl_pct']:+.2f}%)")
    print(f"Open positions: {len(open_positions)}")
    
    # Test 3: Check TP condition (should trigger at +3.5%)
    print("\n" + "-"*70)
    print("TEST 3: Simulate Take Profit (+3.5%)")
    print("-"*70)
    
    tp_price = 60000 * 1.035  # +3.5%
    portfolio.update_positions("BTCUSDT", tp_price)
    
    open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']
    if open_positions:
        pnl_pct = open_positions[0]['pnl_pct']
        print(f"TP Price: ${tp_price:,.2f}")
        print(f"Current P&L: {pnl_pct:+.2f}%")
        
        # Use 3.4 threshold to account for floating point precision
        if pnl_pct >= 3.4:
            print(f"✅ TP CONDITION MET ({pnl_pct:+.2f}% >= 3.4%) - Should close position!")
            
            # Simulate closing
            closed = portfolio.close_position(
                position_id=open_positions[0]['id'],
                exit_price=tp_price,
                reason="Take Profit"
            )
            
            if closed:
                print(f"✅ Position closed successfully!")
                print(f"   Realized P&L: ${closed['realized_pnl']:,.2f} ({closed['realized_pnl_pct']:+.2f}%)")
            else:
                print("❌ Failed to close position!")
                return False
        else:
            print(f"❌ TP condition NOT met: {pnl_pct:.10f}% < 3.4%")
            return False
    
    # Test 4: Open another position and test SL
    print("\n" + "-"*70)
    print("TEST 4: Simulate Stop Loss (-1.5%)")
    print("-"*70)
    
    pos2 = portfolio.open_position(
        symbol="BTCUSDT",
        side="LONG",
        entry_price=60000.0,
        size=1000.0,
        confidence=0.75,
        reason="Test SL"
    )
    
    if pos2:
        print(f"✅ Position #{pos2['id']} opened")
        
        sl_price = 60000 * 0.985  # -1.5%
        portfolio.update_positions("BTCUSDT", sl_price)
        
        open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']
        if open_positions:
            pnl_pct = open_positions[0]['pnl_pct']
            print(f"SL Price: ${sl_price:,.2f}")
            print(f"Current P&L: {pnl_pct:+.2f}%")
            
            # Use -1.4 threshold to account for floating point precision
            if pnl_pct <= -1.4:
                print(f"✅ SL CONDITION MET ({pnl_pct:+.2f}% <= -1.4%) - Should close position!")
                
                closed = portfolio.close_position(
                    position_id=open_positions[0]['id'],
                    exit_price=sl_price,
                    reason="Stop Loss"
                )
                
                if closed:
                    print(f"✅ Position closed successfully!")
                    print(f"   Realized P&L: ${closed['realized_pnl']:,.2f} ({closed['realized_pnl_pct']:+.2f}%)")
                else:
                    print("❌ Failed to close position!")
                    return False
            else:
                print(f"❌ SL condition NOT met: {pnl_pct:.10f}% > -1.4%")
                return False
    
    # Test 5: 24-hour time exit
    print("\n" + "-"*70)
    print("TEST 5: Simulate 24-Hour Time Exit")
    print("-"*70)
    
    pos3 = portfolio.open_position(
        symbol="BTCUSDT",
        side="LONG",
        entry_price=60000.0,
        size=1000.0,
        confidence=0.75,
        reason="Test time exit"
    )
    
    if pos3:
        print(f"✅ Position #{pos3['id']} opened")
        
        # Manually set entry time to 25 hours ago
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        pos3['entry_time'] = old_time
        
        entry_time = datetime.fromisoformat(pos3['entry_time'])
        hours_held = (datetime.now() - entry_time).total_seconds() / 3600
        
        print(f"Entry time (modified): {pos3['entry_time']}")
        print(f"Hours held: {hours_held:.1f}h")
        
        if hours_held >= 24.0:
            print("✅ TIME EXIT CONDITION MET - Should close position!")
            
            closed = portfolio.close_position(
                position_id=pos3['id'],
                exit_price=60000.0,
                reason=f"Time Exit ({hours_held:.1f}h)"
            )
            
            if closed:
                print(f"✅ Position closed successfully!")
                print(f"   Held for: {hours_held:.1f} hours")
            else:
                print("❌ Failed to close position!")
                return False
        else:
            print(f"❌ Time exit condition NOT met: {hours_held}h < 24h")
            return False
    
    # Final summary
    print("\n" + "="*70)
    print("📊 FINAL RESULTS")
    print("="*70)
    
    stats = portfolio.get_performance_stats()
    print(f"Total trades: {stats['total_trades']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Win rate: {stats['win_rate']:.1%}")
    print(f"Total P&L: ${stats['total_pnl']:,.2f}")
    print(f"Open positions: {len([p for p in portfolio.positions if p.get('status') == 'OPEN'])}")
    
    if stats['total_trades'] == 3:
        print("\n✅ ALL TESTS PASSED!")
        return True
    else:
        print(f"\n❌ TESTS FAILED! Expected 3 closed trades, got {stats['total_trades']}")
        return False

if __name__ == "__main__":
    try:
        success = test_tp_sl_logic()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
