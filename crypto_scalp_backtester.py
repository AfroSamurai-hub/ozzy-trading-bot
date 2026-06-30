#!/usr/bin/env python3
"""
Crypto 15m Scalper: 1H Trend → 15m Entry for BTC/ETH
High-frequency setup for daily returns.
"""

import json
import math
from datetime import datetime
from binance.client import Client
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
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
        days -= 30; end = start
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

def strategy_crypto_scalp(candles_15m, candles_1h):
    """
    1H Trend → 15m Scalp:
    1. 1H EMA21 > EMA55 = uptrend (longs only), reverse for shorts
    2. 15m RSI pullback to 40-60 zone in trend direction
    3. Entry on 15m candle close back above/below EMA20
    4. Tight stop: 0.75x ATR (15m)
    5. TP: 1.5x ATR (RR 2.0)
    6. Max hold: 4h (16 candles)
    """
    signals = []
    closes_15m = [c['close'] for c in candles_15m]
    rsi_15m = calc_rsi(closes_15m, 14)
    atr_15m = calc_atr(candles_15m, 14)
    ema20_15m = calc_ema(closes_15m, 20)
    
    # 1H trend
    closes_1h = [c['close'] for c in candles_1h]
    ema21_1h = calc_ema(closes_1h, 21)
    ema55_1h = calc_ema(closes_1h, 55)
    
    # Map 1h trend to 15m (4 per 1h)
    trend_map = []
    idx_1h = 0
    for i in range(len(candles_15m)):
        if i > 0 and i % 4 == 0: idx_1h += 1
        if idx_1h < len(ema21_1h) and ema21_1h[idx_1h] is not None and ema55_1h[idx_1h] is not None:
            trend_map.append(1 if ema21_1h[idx_1h] > ema55_1h[idx_1h] else -1)
        else: trend_map.append(0)
    
    for i in range(100, len(candles_15m)):
        if ema20_15m[i] is None or rsi_15m[i] is None or trend_map[i] == 0: continue
        
        trend = trend_map[i]
        price = closes_15m[i]
        ema20 = ema20_15m[i]
        rsi = rsi_15m[i]
        
        # Long: uptrend + price dipped below EMA20 + RSI 40-60 + close back above
        if trend == 1 and candles_15m[i]['low'] < ema20 and price > ema20 and 40 < rsi < 60:
            signals.append({'idx': i+1, 'side': 'BUY', 'entry': candles_15m[i+1]['open'] if i+1 < len(candles_15m) else None})
        
        # Short: downtrend + price spiked above EMA20 + RSI 40-60 + close back below
        elif trend == -1 and candles_15m[i]['high'] > ema20 and price < ema20 and 40 < rsi < 60:
            signals.append({'idx': i+1, 'side': 'SELL', 'entry': candles_15m[i+1]['open'] if i+1 < len(candles_15m) else None})
    
    return signals

def run_backtest(signals, candles, symbol):
    capital = INITIAL_CAPITAL
    trades = []
    equity_curve = [capital]
    
    for sig in signals:
        i = sig['idx']
        if i >= len(candles) - 2 or sig['entry'] is None: break
        
        entry_price = sig['entry'] * (1 + SLIPPAGE_PCT if sig['side'] == 'BUY' else 1 - SLIPPAGE_PCT)
        atr_val = calc_atr(candles, 14)[i] if i < len(calc_atr(candles, 14)) else entry_price * 0.005
        if atr_val == 0: atr_val = entry_price * 0.005
        
        sl_distance = atr_val * 0.75
        rr = 2.0
        
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
        
        for j in range(i+1, min(i+17, len(candles))):  # 4h max
            c = candles[j]
            if sig['side'] == 'BUY':
                if c['low'] <= sl: exit_price, exit_reason = sl, 'SL'
                elif c['high'] >= tp: exit_price, exit_reason = tp, 'TP'
                elif j == i + 16: exit_price, exit_reason = c['close'], 'TIME'
            else:
                if c['high'] >= sl: exit_price, exit_reason = sl, 'SL'
                elif c['low'] <= tp: exit_price, exit_reason = tp, 'TP'
                elif j == i + 16: exit_price, exit_reason = c['close'], 'TIME'
            
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
    print("⚡ Crypto 15m Scalper (1H Trend → 15m Entry)\n")
    results = []
    
    for sym in SYMBOLS:
        c_15m = fetch_ohlcv(sym, '15m', days=90)
        c_1h = fetch_ohlcv(sym, '1h', days=90)
        print(f"📊 {sym}: 15m={len(c_15m)} | 1h={len(c_1h)}")
        
        signals = strategy_crypto_scalp(c_15m, c_1h)
        print(f"  Signals: {len(signals)}")
        
        res = run_backtest(signals, c_15m, sym)
        r = analyze(res, 'Crypto Scalp 15m', sym)
        results.append(r)
        print(f"  Trades: {r['trades']} | WR: {r['win_rate']}% | PnL: ${r['net_pnl']} | PF: {r['profit_factor']} | DD: {r['max_drawdown']}%")
    
    print("\n" + "="*60)
    with open('crypto_scalp_results.json', 'w') as f: json.dump(results, f, indent=2)
