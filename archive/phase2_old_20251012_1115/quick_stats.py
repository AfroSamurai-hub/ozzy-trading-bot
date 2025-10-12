#!/usr/bin/env python3
"""Quick trading stats dashboard - instant snapshot of your progress"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'ozzy_simple.db'

def get_quick_stats():
    conn = sqlite3.connect(DB_PATH)
    
    try:
        trades = pd.read_sql("SELECT * FROM trades", conn)
        
        if len(trades) == 0:
            print("No trades yet!")
            return
        
        # Basic counts
        total = len(trades)
        longs = len(trades[trades['side'] == 'LONG'])
        shorts = len(trades[trades['side'] == 'SHORT'])
        
        # Performance
        wins = (trades['pnl'] > 0).sum()
        losses = (trades['pnl'] <= 0).sum()
        win_rate = (wins / total) * 100 if total > 0 else 0
        
        total_pnl = trades['pnl'].sum()
        avg_pnl = trades['pnl'].mean()
        avg_win = trades[trades['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
        avg_loss = trades[trades['pnl'] <= 0]['pnl'].mean() if losses > 0 else 0
        
        # Progress to goals
        trades_needed = max(0, 200 - total)
        longs_needed = max(0, 50 - longs)
        shorts_needed = max(0, 50 - shorts)
        
        # Display
        print("\n" + "="*60)
        print(f"📊 OZZY QUICK STATS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        print(f"\n📈 PROGRESS TO 200 TRADES:")
        print(f"  Current: {total}/200 ({total/200*100:.1f}%)")
        print(f"  Remaining: {trades_needed} trades")
        
        print(f"\n⚖️  TRADE BALANCE:")
        print(f"  LONGs:  {longs:3d} {'✅' if longs >= 50 else f'❌ (need {longs_needed} more)'}")
        print(f"  SHORTs: {shorts:3d} {'✅' if shorts >= 50 else f'❌ (need {shorts_needed} more)'}")
        balance_ratio = (shorts / longs * 100) if longs > 0 else 0
        print(f"  Ratio:  {balance_ratio:.1f}% (target: 40-60%)")
        
        print(f"\n💰 PERFORMANCE:")
        print(f"  Win Rate:   {win_rate:.1f}% ({wins}W/{losses}L)")
        print(f"  Total P&L:  R{total_pnl:,.2f}")
        print(f"  Avg P&L:    R{avg_pnl:.2f}")
        print(f"  Avg Win:    R{avg_win:.2f}")
        print(f"  Avg Loss:   R{avg_loss:.2f}")
        
        if avg_loss != 0:
            risk_reward = abs(avg_win / avg_loss)
            print(f"  Risk/Reward: {risk_reward:.2f}")
        
        # Readiness score
        print(f"\n🎯 READINESS CHECKLIST:")
        checks = []
        checks.append(("200+ trades", total >= 200))
        checks.append(("55%+ win rate", win_rate >= 55))
        checks.append(("50+ LONGs", longs >= 50))
        checks.append(("50+ SHORTs", shorts >= 50))
        
        for check, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check}")
        
        ready_count = sum(1 for _, p in checks if p)
        print(f"\n🚦 Status: {ready_count}/4 checks passed")
        
        if ready_count == 4:
            print("🎉 READY FOR LIVE TRADING!")
        elif ready_count >= 3:
            print("⚠️  ALMOST READY - Keep collecting data")
        else:
            print("🔄 KEEP TRADING - More data needed")
        
        # Recent activity
        trades['datetime'] = pd.to_datetime(trades['entry_timestamp'], errors='coerce')
        recent = trades.sort_values('datetime', ascending=False).head(5)
        
        print(f"\n📋 LAST 5 TRADES:")
        for _, trade in recent.iterrows():
            side_emoji = "🟢" if trade['side'] == 'LONG' else "🔴"
            pnl = trade.get('pnl', 0)
            if pd.isna(pnl):
                pnl = 0
            pnl_emoji = "💚" if pnl > 0 else "💔"
            symbol = trade.get('symbol', 'UNKNOWN')
            print(f"  {side_emoji} {symbol:8s} {pnl_emoji} R{pnl:7.2f}")
        
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    get_quick_stats()
