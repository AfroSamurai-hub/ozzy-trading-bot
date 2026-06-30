#!/usr/bin/env python3
"""
Multi-Timeframe Backtester: 4H Trend → 1H Entry for XAUUSD Gold
Tests the strategy Rick wants: faster Gold signals without losing edge.
"""

import json
import math
from datetime import datetime
from binance.client import Client
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET

# ── Config ──
SYMBOL = "XAUUSDT"  # Binance Gold perpetual
INITIAL_CAPITAL = 5000.0
LEVERAGE = 10
RISK_PER_TRADE = 250.0
FEE_TAKER = 0.0004
SLIPPAGE_PCT = 0.0002
TESTNET = True

client = Client(BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET, testnet=TESTNET)

def fetch_ohlcv(symbol, interval, days=90):
    all_candles = []
    end = int(datetime.now().timestamp() * 1000)
    while True:
        start = end - (min(days, 30) * 24 * 60 * 60 * 1000)
        klines = client.futures_klines(symbol=symbol, interval=interval, startTime=start, endTime=end, limit=1000)
        for k in klines:
            all_candles.append({
                'time': k[0], 'open': float(k[1]), 'high': float(k[2]),
                'low': float(k[3]), 'close': float(k[4]), 'volume': float(k[5]),
            })
        days -= 30
        end = start
        if days <= 0 or len(klines) < 1000: break
    all_candles.sort(key=lambda x: x['time'])
    seen = set()
    return [c for c in all_candles if c['time'] not in seen and not seen.add(c['time'])]

def calc_rsi(closes, period=14):
    rsi = []
    gains, losses = [], []
    for i in range(len(closes)):
        if i == 0: gains.append(0); losses.append(0); rsi.append(50); continue
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0)); losses.append(max(-change, 0))
        if i < period: rsi.append(50); continue
        ag = sum(gains[i-period+1:i+1]) / period
        al = sum(losses[i-period+1:i+1]) / period
        rsi.append(100 if al == 0 else 100 - (100 / (1 + ag/al)))
    return rsi

def calc_atr(candles, period=14):
    atr = []
    for i in range(len(candles)):
        if i == 0: atr.append(candles[i]['high'] - candles[i]['low']); continue
        tr = max(candles[i]['high'] - candles[i]['low'], abs(candles[i]['high'] - candles[i-1]['close']), abs(candles[i]['low'] - candles[i-1]['close']))
        atr.append(tr if i < period else (atr[-1] * (period-1) + tr) / period)
    return atr

def calc_ema(data, period):
    ema = []
    mult = 2 / (period + 1)
    for i in range(len(data)):
        if i < period - 1: ema.append(None)
        elif i == period - 1: ema.append(sum(data[:period]) / period)
        else: ema.append((data[i] - ema[-1]) * mult + ema[-1])
    return ema

def calc_supertrend(candles, atr, period=10, mult=3):
    st = []
    for i in range(len(candles)):
        if atr[i] == 0: atr[i] = candles[i]['close'] * 0.001
        basic_upper = (candles[i]['high'] + candles[i]['low']) / 2 + mult * atr[i]
        basic_lower = (candles[i]['high'] + candles[i]['low']) / 2 - mult * atr[i]
        if i == 0:
            st.append({'upper': basic_upper, 'lower': basic_lower, 'dir': 1})
            continue
        prev = st[-1]
        final_upper = basic_upper if basic_upper < prev['upper'] or candles[i-1]['close'] > prev['upper'] else prev['upper']
        final_lower = basic_lower if basic_lower > prev['lower'] or candles[i-1]['close'] < prev['lower'] else prev['lower']
        direction = 1 if candles[i]['close'] > final_upper else (-1 if candles[i]['close'] < final_lower else prev['dir'])
        st.append({'upper': final_upper, 'lower': final_lower, 'dir': direction})
    return st

def strategy_gold_multiframe(candles_1h, candles_4h):
    """
    4H Trend → 1H Entry for XAUUSD:
    1. 4H SuperTrend defines trend direction
    2. 1H RSI + EMA pullback in trend direction
    3. 1H ATR-based SL (1.5x) and TP (2.5x)
    4. Max hold: 12h
    """
    signals = []
    closes_1h = [c['close'] for c in candles_1h]
    rsi_1h = calc_rsi(closes_1h, 14)
    atr_1h = calc_atr(candles_1h, 14)
    ema200_1h = calc_ema(closes_1h, 200)
    
    # 4H SuperTrend
    closes_4h = [c['close'] for c in candles_4h]
    atr_4h = calc_atr(candles_4h, 14)
    st_4h = calc_supertrend(candles_4h, atr_4h, 10, 3)
    
    # Map 4h trend to 1h candles (4 per 4h)
    trend_map = []
    idx_4h = 0
    for i in range(len(candles_1h)):
        if i > 0 and i % 4 == 0: idx_4h += 1
        if idx_4h < len(st_4h):
            trend_map.append(1 if st_4h[idx_4h]['dir'] == 1 else -1)
        else:
            trend_map.append(0)
    
    for i in range(200, len(candles_1h)):
        if ema200_1h[i] is None or rsi_1h[i] is None or trend_map[i] == 0:
            continue
        
        trend = trend_map[i]
        price = closes_1h[i]
        ema = ema200_1h[i]
        rsi = rsi_1h[i]
        
        # Buy: uptrend + price above EMA + RSI cooling (40-65)
        if trend == 1 and price > ema and 40 < rsi < 65:
            if candles_1h[i-1]['close'] > ema and candles_1h[i]['low'] <= ema * 1.002 and candles_1h[i]['close'] > ema:
                signals.append({'idx': i+1, 'side': 'BUY', 'entry': candles_1h[i+1]['open'] if i+1 < len(candles_1h) else None})
        
        # Sell: downtrend + price below EMA + RSI warming (35-60)
        elif trend == -1 and price < ema and 35 < rsi < 60:
            if candles_1h[i-1]['close'] < ema and candles_1h[i]['high'] >= ema * 0.998 and candles_1h[i]['close'] < ema:
                signals.append({'idx': i+1, 'side': 'SELL', 'entry': candles_1h[i+1]['open'] if i+1 < len(candles_1h) else None})
    
    return signals

def run_backtest(signals, candles, symbol):
    capital = INITIAL_CAPITAL
    trades = []
    equity_curve = [capital]
    
    for sig in signals:
        i = sig['idx']
        if i >= len(candles) - 2 or sig['entry'] is None: break
        
        entry_price = sig['entry'] * (1 + SLIPPAGE_PCT if sig['side'] == 'BUY' else 1 - SLIPPAGE_PCT)
        atr = calc_atr(candles, 14)
        atr_val = atr[i] if i < len(atr) else entry_price * 0.005
        if atr_val == 0: atr_val = entry_price * 0.005
        
        sl_distance = atr_val * 1.5
        rr = 2.5
        
        if sig['side'] == 'BUY':
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * rr
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * rr
        
        qty = RISK_PER_TRADE / sl_distance
        if (qty * entry_price) / LEVERAGE > capital * 0.85: continue
        
        entry_time = candles[i]['time']
        exit_price, exit_reason, exit_time = None, None, None
        
        for j in range(i+1, min(i+13, len(candles))):  # 12h max
            c = candles[j]
            if sig['side'] == 'BUY':
                if c['low'] <= sl: exit_price, exit_reason = sl, 'SL'
                elif c['high'] >= tp: exit_price, exit_reason = tp, 'TP'
                elif j == i + 12: exit_price, exit_reason = c['close'], 'TIME'
            else:
                if c['high'] >= sl: exit_price, exit_reason = sl, 'SL'
                elif c['low'] <= tp: exit_price, exit_reason = tp, 'TP'
                elif j == i + 12: exit_price, exit_reason = c['close'], 'TIME'
            
            if exit_reason:
                exit_time = c['time']
                pnl = qty * (exit_price - entry_price) if sig['side'] == 'BUY' else qty * (entry_price - exit_price)
                fees = qty * entry_price * FEE_TAKER + qty * exit_price * FEE_TAKER
                capital += pnl - fees
                break
        
        if exit_reason:
            trades.append({
                'symbol': symbol, 'side': sig['side'], 'entry': entry_price, 'exit': exit_price,
                'qty': round(qty, 3), 'pnl': pnl, 'fees': fees, 'net': pnl - fees,
                'exit_reason': exit_reason, 'entry_time': datetime.fromtimestamp(entry_time/1000).strftime('%H:%M'),
                'exit_time': datetime.fromtimestamp(exit_time/1000).strftime('%H:%M'),
            })
            equity_curve.append(capital)
    
    return {'capital': capital, 'trades': trades, 'equity_curve': equity_curve}

def analyze(result, name, sym):
    trades = result['trades']
    if not trades: return {'strategy': name, 'symbol': sym, 'trades': 0}
    wins = [t for t in trades if t['net'] > 0]
    losses = [t for t in trades if t['net'] <= 0]
    wr = len(wins) / len(trades) * 100
    net = sum(t['net'] for t in trades)
    pf = abs(sum(t['net'] for t in wins) / sum(t['net'] for t in losses)) if losses else float('inf')
    dd = 0; peak = 5000
    for eq in result['equity_curve']:
        if eq > peak: peak = eq
        d = (peak - eq) / peak * 100
        if d > dd: dd = d
    
    exits = {}
    for t in trades: exits[t['exit_reason']] = exits.get(t['exit_reason'], 0) + 1
    
    return {'strategy': name, 'symbol': sym, 'trades': len(trades), 'win_rate': round(wr, 1), 
            'net_pnl': round(net, 2), 'return_pct': round((result['capital']-5000)/5000*100, 1), 
            'profit_factor': round(pf, 2) if pf != float('inf') else 'inf', 
            'max_drawdown': round(dd, 1), 'total_fees': round(sum(t['fees'] for t in trades), 2),
            'exits': exits}

if __name__ == '__main__':
    print("🥇 Multi-Timeframe Gold Backtester (4H Trend → 1H Entry)\n")
    
    c_1h = fetch_ohlcv(SYMBOL, '1h', days=90)
    c_4h = fetch_ohlcv(SYMBOL, '4h', days=90)
    print(f"1H: {len(c_1h)} | 4H: {len(c_4h)}")
    
    signals = strategy_gold_multiframe(c_1h, c_4h)
    print(f"Signals: {len(signals)}")
    
    res = run_backtest(signals, c_1h, SYMBOL)
    result = analyze(res, 'Gold MTF (4H→1H)', SYMBOL)
    
    print("\n" + "="*60)
    print(f"Strategy: {result['strategy']} | {result['symbol']}")
    print(f"Trades: {result['trades']} | Win Rate: {result['win_rate']}%")
    print(f"Net PnL: ${result['net_pnl']} | Return: {result['return_pct']}%")
    print(f"Profit Factor: {result['profit_factor']} | Max DD: {result['max_drawdown']}%")
    print(f"Fees: ${result['total_fees']}")
    print(f"Exit Breakdown: {result['exits']}")
