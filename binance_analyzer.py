#!/usr/bin/env python3
"""
Binance Futures Trade Analyzer
Pulls trade history from Binance testnet and generates a structured report.
"""
import sys
sys.path.insert(0, '/home/rick/ozzy-bot')

from binance.client import Client
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET
from datetime import datetime, timezone
import json

def get_trade_history():
    client = Client(BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET, testnet=True)
    
    # Get account balance
    account = client.futures_account()
    balance = float(account['totalWalletBalance'])
    equity = float(account['totalMarginBalance'])
    
    # Get income history (realized PnL)
    income = client.futures_income_history(limit=50)
    
    trades = []
    for item in income:
        if float(item['income']) != 0:
            trades.append({
                'symbol': item['symbol'],
                'income': float(item['income']),
                'asset': item['asset'],
                'income_type': item['incomeType'],
                'time': datetime.fromtimestamp(item['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'trade_id': item.get('tradeId', ''),
                'position_side': item.get('positionSide', ''),
            })
    
    # Get open orders (SL/TP)
    open_orders = client.futures_get_open_orders()
    
    # Get positions
    positions = client.futures_position_information()
    open_pos = []
    for p in positions:
        if float(p['positionAmt']) != 0:
            open_pos.append({
                'symbol': p['symbol'],
                'side': 'LONG' if float(p['positionAmt']) > 0 else 'SHORT',
                'amount': float(p['positionAmt']),
                'entry': float(p['entryPrice']),
                'mark': float(p['markPrice']),
                'pnl': float(p['unRealizedProfit']),
            })
    
    return {
        'account': {
            'balance': balance,
            'equity': equity,
        },
        'open_positions': open_pos,
        'open_orders': len(open_orders),
        'trades': trades,
    }

def print_report(data):
    print(f"{'='*60}")
    print(f"📊 BINANCE FUTURES TRADE REPORT")
    print(f"{'='*60}")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Balance: ${data['account']['balance']:,.2f}")
    print(f"Equity:  ${data['account']['equity']:,.2f}")
    print(f"Open Positions: {len(data['open_positions'])}")
    print(f"Open Orders (SL/TP): {data['open_orders']}")
    print(f"{'='*60}")
    
    if data['open_positions']:
        print(f"\n🔵 OPEN POSITIONS:")
        for p in data['open_positions']:
            print(f"  {p['symbol']} {p['side']}: {p['amount']} @ {p['entry']:,.2f}")
            print(f"    Mark: {p['mark']:,.2f} | PnL: ${p['pnl']:+.2f}")
    
    if data['trades']:
        print(f"\n📋 TRADE HISTORY (Realized PnL):")
        total_pnl = 0
        wins = 0
        losses = 0
        
        # Group by symbol
        by_symbol = {}
        for t in data['trades']:
            sym = t['symbol']
            if sym not in by_symbol:
                by_symbol[sym] = {'pnl': 0, 'count': 0, 'wins': 0, 'losses': 0}
            by_symbol[sym]['pnl'] += t['income']
            by_symbol[sym]['count'] += 1
            if t['income'] > 0:
                by_symbol[sym]['wins'] += 1
            else:
                by_symbol[sym]['losses'] += 1
        
        for sym, stats in sorted(by_symbol.items()):
            print(f"  {sym}:")
            print(f"    Trades: {stats['count']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
            print(f"    Net PnL: ${stats['pnl']:+.2f}")
            total_pnl += stats['pnl']
            wins += stats['wins']
            losses += stats['losses']
        
        print(f"\n  TOTAL: {wins + losses} trades | {wins}W / {losses}L | Net: ${total_pnl:+.2f}")
        
        # Show individual trades
        print(f"\n  Recent Trades:")
        for t in data['trades'][:20]:
            pnl_str = f"+${t['income']:.2f}" if t['income'] > 0 else f"-${abs(t['income']):.2f}"
            print(f"    [{t['time']}] {t['symbol']} {t['income_type']}: {pnl_str} {t['position_side']}")
    else:
        print(f"\n  No realized trades yet.")
    
    print(f"{'='*60}")

if __name__ == "__main__":
    data = get_trade_history()
    print_report(data)
    
    # Save to file for historical tracking
    with open('/home/rick/.hermes/trading-journal/binance_report.json', 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\n💾 Report saved to ~/.hermes/trading-journal/binance_report.json")
