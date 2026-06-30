#!/usr/bin/env python3
"""
15m Liquidation Wick + RSI Divergence Backtester
High-frequency scalp strategy for daily/weekly returns.
Targets: ETHUSDT, BTCUSDT
Timeframe: 15m
Max Hold: 4h (16 candles)
"""

import json
import math
from datetime import datetime
from binance.client import Client
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET

# ── Config ──
SYMBOLS = ["ETHUSDT", "BTCUSDT"]
INITIAL_CAPITAL = 5000.0
LEVERAGE = 10
RISK_PER_TRADE = 250.0
FEE_TAKER = 0.0004
SLIPPAGE_PCT = 0.0002
TESTNET = True

client = Client(BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET, testnet=TESTNET)

def fetch_ohlcv(symbol, interval, days=90):
    """Fetch OHLCV with chunking for 15m data."""
    all_candles = []
    end = int(datetime.now().timestamp() * 1000)
    
    while True:
        start = end - (min(days, 30) * 24 * 60 * 60 * 1000)
        klines = client.futures_klines(symbol=symbol, interval=interval, startTime=start, endTime=end, limit=1000)
        for k in klines:
            all_candles.append({
                'time': k[0],
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })
        
        days -= 30
        end = start
        if days <= 0 or len(klines) < 1000:
            break
    
    all_candles.sort(key=lambda x: x['time'])
    seen = set()
    return [c for c in all_candles if c['time'] not in seen and not seen.add(c['time'])]

def calc_rsi(closes, period=14):
    rsi = []
    gains, losses = [], []
    for i in range(len(closes)):
        if i == 0:
            gains.append(0); losses.append(0); rsi.append(50); continue
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0)); losses.append(max(-change, 0))
        if i < period: rsi.append(50); continue
        avg_gain = sum(gains[i-period+1:i+1]) / period
        avg_loss = sum(losses[i-period+1:i+1]) / period
        rsi.append(100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss)))
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

def detect_liquidation_zones(candles, lookback=20):
    """Find recent swing highs/lows that likely hold stops/liquidations."""
    zones = []
    for i in range(lookback, len(candles)):
        swing_high = max(c['high'] for c in candles[i-lookback:i])
        swing_low = min(c['low'] for c in candles[i-lookback:i])
        zones.append({'high': swing_high, 'low': swing_low, 'idx': i})
    return zones

def strategy_liq_wick_rsi(candles_15m, candles_1h):
    """
    15m Liquidation Wick + RSI Divergence:
    1. 1H trend filter (EMA21 > EMA55 for longs)
    2. 15m price wicks below recent swing low (long) or above swing high (short)
    3. RSI divergence: Price makes lower low, RSI makes higher low (bullish)
    4. Entry on next candle close in direction
    5. Tight stop: 0.75x ATR
    6. Take profit: 1.5x ATR (RR 2.0)
    7. Time exit: 4h (16 candles)
    """
    signals = []
    closes_15m = [c['close'] for c in candles_15m]
    rsi_15m = calc_rsi(closes_15m, 14)
    atr_15m = calc_atr(candles_15m, 14)
    
    # 1H trend
    closes_1h = [c['close'] for c in candles_1h]
    ema21_1h = calc_ema(closes_1h, 21)
    ema55_1h = calc_ema(closes_1h, 55)
    
    # Map 1h trend to 15m (4 candles per 1h)
    trend_map = []
    idx_1h = 0
    for i in range(len(candles_15m)):
        if i > 0 and i % 4 == 0: idx_1h += 1
        if idx_1h < len(ema21_1h) and ema21_1h[idx_1h] is not None and ema55_1h[idx_1h] is not None:
            trend_map.append(ema21_1h[idx_1h] > ema55_1h[idx_1h])
        else:
            trend_map.append(None)
    
    for i in range(100, len(candles_15m)):
        if rsi_15m[i] is None or trend_map[i] is None:
            continue
        
        # Recent swing low/high
        swing_low = min(c['low'] for c in candles_15m[i-20:i])
        swing_high = max(c['high'] for c in candles_15m[i-20:i])
        
        # Bullish setup: wick below swing low + RSI higher low + uptrend
        if candles_15m[i]['low'] < swing_low and candles_15m[i]['close'] > swing_low:
            if rsi_15m[i] > rsi_15m[i-1] and rsi_15m[i] < 40 and trend_map[i]:
                signals.append({'idx': i+1, 'side': 'BUY', 'entry': candles_15m[i+1]['close'] if i+1 < len(candles_15m) else None})
        
        # Bearish setup: wick above swing high + RSI lower high + downtrend
        elif candles_15m[i]['high'] > swing_high and candles_15m[i]['close'] < swing_high:
            if rsi_15m[i] < rsi_15m[i-1] and rsi_15m[i] > 60 and not trend_map[i]:
                signals.append({'idx': i+1, 'side': 'SELL', 'entry': candles_15m[i+1]['close'] if i+1 < len(candles_15m) else None})
    
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
        atr_val = atr[i] if i < len(atr) else entry_price * 0.01
        if atr_val == 0: atr_val = entry_price * 0.01
        
        # Tight stop: 0.75x ATR
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
        
        # Max 4h hold (16 candles)
        for j in range(i+1, min(i+17, len(candles))):
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
    return {'strategy': name, 'symbol': sym, 'trades': len(trades), 'win_rate': round(wr, 1), 'net_pnl': round(net, 2), 'return_pct': round((result['capital']-5000)/5000*100, 1), 'profit_factor': round(pf, 2) if pf != float('inf') else 'inf', 'max_drawdown': round(dd, 1), 'total_fees': round(sum(t['fees'] for t in trades), 2)}

if __name__ == '__main__':
    print("🚀 15m Liquidation Wick + RSI Divergence Backtester\n")
    results = []
    
    for sym in SYMBOLS:
        print(f"📊 Processing {sym}...")
        c_15m = fetch_ohlcv(sym, '15m', days=90)
        c_1h = fetch_ohlcv(sym, '1h', days=90)
        print(f"  15m: {len(c_15m)} | 1h: {len(c_1h)}")
        
        signals = strategy_liq_wick_rsi(c_15m, c_1h)
        print(f"  Signals: {len(signals)}")
        
        res = run_backtest(signals, c_15m, sym)
        results.append(analyze(res, 'Liq Wick + RSI 15m', sym))
    
    print("\n" + "="*60)
    for r in results:
        print(f"\n{r['strategy']} | {r['symbol']}")
        print(f"  Trades: {r['trades']} | WR: {r['win_rate']}% | PnL: ${r['net_pnl']}")
        print(f"  PF: {r['profit_factor']} | DD: {r['max_drawdown']}% | Fees: ${r['total_fees']}")
    
    with open('liq_wick_rsi_results.json', 'w') as f: json.dump(results, f, indent=2)
