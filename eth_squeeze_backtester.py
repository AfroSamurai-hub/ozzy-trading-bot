#!/usr/bin/env python3
"""
Optimized ETH Volatility Squeeze Backtester (1H)
Pro-level: trend filter, confirmation candle, time exit, volume filter, tighter stops.
"""

import json
import math
from datetime import datetime
from binance.client import Client
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET

# ── Config ──
SYMBOL = "ETHUSDT"
INITIAL_CAPITAL = 5000.0
LEVERAGE = 10
RISK_PER_TRADE = 250.0  # Fixed $ risk per trade
FEE_TAKER = 0.0004
SLIPPAGE_PCT = 0.0003
TESTNET = True

client = Client(BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET, testnet=TESTNET)

def fetch_ohlcv(symbol, interval, days=180):
    # Binance limit max is 1000, so we fetch in chunks
    all_candles = []
    end = int(datetime.now().timestamp() * 1000)
    
    while True:
        start = end - (min(days, 30) * 24 * 60 * 60 * 1000)  # Fetch 30 days at a time
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
        
        if len(all_candles) >= days * 24 * (60 // int(interval.replace('h', '').replace('m', '') or 60)):
            break
        
        days -= 30
        end = start
        if days <= 0:
            break
    
    # Sort by time and remove duplicates
    all_candles.sort(key=lambda x: x['time'])
    seen = set()
    unique = []
    for c in all_candles:
        if c['time'] not in seen:
            seen.add(c['time'])
            unique.append(c)
    
    return unique

def calc_ema(data, period):
    ema = []
    multiplier = 2 / (period + 1)
    for i in range(len(data)):
        if i < period - 1:
            ema.append(None)
        elif i == period - 1:
            ema.append(sum(data[:period]) / period)
        else:
            ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
    return ema

def calc_atr(candles, period=14):
    atr = []
    for i in range(len(candles)):
        if i == 0:
            atr.append(candles[i]['high'] - candles[i]['low'])
            continue
        tr = max(
            candles[i]['high'] - candles[i]['low'],
            abs(candles[i]['high'] - candles[i-1]['close']),
            abs(candles[i]['low'] - candles[i-1]['close'])
        )
        if i < period:
            atr.append(tr)
        else:
            atr.append((atr[-1] * (period-1) + tr) / period)
    return atr

def calc_bb(closes, period=20, mult=2.0):
    upper, lower = [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
            continue
        sma = sum(closes[i-period+1:i+1]) / period
        std = math.sqrt(sum((c - sma)**2 for c in closes[i-period+1:i+1]) / period)
        upper.append(sma + mult * std)
        lower.append(sma - mult * std)
    return upper, lower

def calc_kc(closes, atr_vals, period=20, mult=1.5):
    upper, lower = [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
            continue
        ema = sum(closes[i-period+1:i+1]) / period
        upper.append(ema + mult * atr_vals[i])
        lower.append(ema - mult * atr_vals[i])
    return upper, lower

def calc_sma(data, period):
    sma = []
    for i in range(len(data)):
        if i < period - 1:
            sma.append(None)
        else:
            sma.append(sum(data[i-period+1:i+1]) / period)
    return sma

def strategy_eth_squeeze_optimized(candles_1h, candles_4h):
    """
    Optimized ETH Squeeze:
    1. BB inside KC = squeeze condition
    2. 4H trend filter (EMA21 > EMA55 for longs, reverse for shorts)
    3. Confirmation candle close outside squeeze zone
    4. Volume > 1.2x 20-period average
    5. Entry on next candle open
    """
    closes_1h = [c['close'] for c in candles_1h]
    atr_1h = calc_atr(candles_1h, 14)
    bb_up, bb_lo = calc_bb(closes_1h, 20, 2.0)
    kc_up, kc_lo = calc_kc(closes_1h, atr_1h, 20, 1.5)
    vol_1h = [c['volume'] for c in candles_1h]
    vol_avg = calc_sma(vol_1h, 20)
    
    # 4H trend filter
    closes_4h = [c['close'] for c in candles_4h]
    ema21_4h = calc_ema(closes_4h, 21)
    ema55_4h = calc_ema(closes_4h, 55)
    
    signals = []
    
    # Map 4h trend to 1h candles (approximate)
    # Each 4h candle covers 4 1h candles
    trend_map = []
    idx_4h = 0
    for i in range(len(candles_1h)):
        if i > 0 and i % 4 == 0:
            idx_4h += 1
        if idx_4h < len(ema21_4h) and ema21_4h[idx_4h] is not None and ema55_4h[idx_4h] is not None:
            trend_up = ema21_4h[idx_4h] > ema55_4h[idx_4h]
        else:
            trend_up = None
        trend_map.append(trend_up)
    
    for i in range(100, len(candles_1h)):
        if bb_up[i] is None or kc_up[i] is None:
            continue
        
        # Squeeze condition: BB inside KC
        squeeze = bb_up[i] < kc_up[i] and bb_lo[i] > kc_lo[i]
        
        if not squeeze:
            continue
        
        # Volume filter
        if vol_avg[i] is not None and vol_1h[i] < vol_avg[i] * 1.2:
            continue
        
        # Trend filter
        if trend_map[i] is None:
            continue
        
        # Bullish breakout: close above KC upper + trend up
        if closes_1h[i] > kc_up[i] and trend_map[i]:
            signals.append({'idx': i, 'side': 'BUY', 'entry': candles_1h[i+1]['open'] if i+1 < len(candles_1h) else None})
        
        # Bearish breakout: close below KC lower + trend down
        elif closes_1h[i] < kc_lo[i] and not trend_map[i]:
            signals.append({'idx': i, 'side': 'SELL', 'entry': candles_1h[i+1]['open'] if i+1 < len(candles_1h) else None})
    
    return signals

def run_backtest(signals, candles, symbol):
    capital = INITIAL_CAPITAL
    trades = []
    equity_curve = [capital]
    
    for sig in signals:
        i = sig['idx']
        if i >= len(candles) - 2 or sig['entry'] is None:
            break
        
        entry_price = sig['entry'] * (1 + SLIPPAGE_PCT if sig['side'] == 'BUY' else 1 - SLIPPAGE_PCT)
        atr = calc_atr(candles, 14)
        atr_val = atr[i] if i < len(atr) else entry_price * 0.015
        if atr_val == 0:
            atr_val = entry_price * 0.015
        
        # Tighter stop: 1.0x ATR
        sl_distance = atr_val * 1.0
        rr = 2.5
        
        if sig['side'] == 'BUY':
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * rr
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * rr
        
        # Position size: fixed $ risk
        qty = RISK_PER_TRADE / sl_distance
        
        # Check margin
        margin_needed = (qty * entry_price) / LEVERAGE
        if margin_needed > capital * 0.85:
            continue
        
        # Simulate trade
        entry_time = candles[i]['time']
        exit_price = None
        exit_reason = None
        exit_time = None
        pnl = 0
        fees = 0
        
        # Max trade duration: 6 hours (6 candles on 1H)
        max_candles = 6
        
        for j in range(i+1, min(i+1+max_candles, len(candles))):
            c = candles[j]
            
            if sig['side'] == 'BUY':
                if c['low'] <= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif c['high'] >= tp:
                    exit_price = tp
                    exit_reason = 'TP'
                elif j == i + max_candles:
                    exit_price = c['close']
                    exit_reason = 'TIME'
            else:
                if c['high'] >= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif c['low'] <= tp:
                    exit_price = tp
                    exit_reason = 'TP'
                elif j == i + max_candles:
                    exit_price = c['close']
                    exit_reason = 'TIME'
            
            if exit_price:
                exit_time = c['time']
                
                if sig['side'] == 'BUY':
                    pnl = qty * (exit_price - entry_price)
                else:
                    pnl = qty * (entry_price - exit_price)
                
                fees = qty * entry_price * FEE_TAKER + qty * exit_price * FEE_TAKER
                capital += pnl - fees
                break
        
        if exit_reason:
            trade = {
                'symbol': symbol,
                'side': sig['side'],
                'entry': entry_price,
                'exit': exit_price,
                'qty': round(qty, 3),
                'pnl': pnl,
                'fees': fees,
                'net': pnl - fees,
                'exit_reason': exit_reason,
                'entry_time': datetime.fromtimestamp(entry_time/1000).strftime('%Y-%m-%d %H:%M'),
                'exit_time': datetime.fromtimestamp(exit_time/1000).strftime('%Y-%m-%d %H:%M'),
            }
            trades.append(trade)
            equity_curve.append(capital)
    
    return {
        'capital': capital,
        'trades': trades,
        'equity_curve': equity_curve,
        'initial_capital': INITIAL_CAPITAL,
    }

def analyze_results(result, strategy_name, symbol):
    trades = result['trades']
    if not trades:
        return {'strategy': strategy_name, 'symbol': symbol, 'trades': 0}
    
    wins = [t for t in trades if t['net'] > 0]
    losses = [t for t in trades if t['net'] <= 0]
    win_rate = len(wins) / len(trades) * 100
    
    total_pnl = sum(t['net'] for t in trades)
    total_fees = sum(t['fees'] for t in trades)
    
    avg_win = sum(t['net'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['net'] for t in losses) / len(losses) if losses else 0
    
    gross_wins = sum(t['net'] for t in wins)
    gross_losses = abs(sum(t['net'] for t in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')
    
    max_drawdown = 0
    peak = result['initial_capital']
    for eq in result['equity_curve']:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_drawdown:
            max_drawdown = dd
    
    return {
        'strategy': strategy_name,
        'symbol': symbol,
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(win_rate, 1),
        'net_pnl': round(total_pnl, 2),
        'total_fees': round(total_fees, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
        'max_drawdown': round(max_drawdown, 1),
        'final_capital': round(result['capital'], 2),
        'return_pct': round((result['capital'] - result['initial_capital']) / result['initial_capital'] * 100, 1),
    }

if __name__ == '__main__':
    print("🚀 Optimized ETH Volatility Squeeze Backtester (1H)\n")
    print("Fetching 180 days of data...")
    
    candles_1h = fetch_ohlcv(SYMBOL, '1h', days=180)
    candles_4h = fetch_ohlcv(SYMBOL, '4h', days=180)
    
    print(f"1H candles: {len(candles_1h)}")
    print(f"4H candles: {len(candles_4h)}")
    
    print("\nRunning strategy...")
    signals = strategy_eth_squeeze_optimized(candles_1h, candles_4h)
    print(f"Signals generated: {len(signals)}")
    
    result = run_backtest(signals, candles_1h, SYMBOL)
    analysis = analyze_results(result, 'ETH Squeeze Optimized', SYMBOL)
    
    print("\n" + "="*60)
    print("📈 OPTIMIZED BACKTEST RESULTS")
    print("="*60)
    print(f"Strategy: ETH Volatility Squeeze (1H) + 4H Trend Filter")
    print(f"Total Trades: {analysis['total_trades']}")
    print(f"Win Rate: {analysis['win_rate']}%")
    print(f"Net PnL: ${analysis['net_pnl']}")
    print(f"Return: {analysis['return_pct']}%")
    print(f"Profit Factor: {analysis['profit_factor']}")
    print(f"Max Drawdown: {analysis['max_drawdown']}%")
    print(f"Total Fees: ${analysis['total_fees']}")
    print(f"Avg Win: ${analysis['avg_win']}")
    print(f"Avg Loss: ${analysis['avg_loss']}")
    print(f"Final Capital: ${analysis['final_capital']}")
    
    # Show trade breakdown
    trades = result['trades']
    exits = {}
    for t in trades:
        exits[t['exit_reason']] = exits.get(t['exit_reason'], 0) + 1
    print(f"\nExit Breakdown: {exits}")
    
    # Save results
    with open('eth_squeeze_optimized_results.json', 'w') as f:
        json.dump({
            'analysis': analysis,
            'trades': trades[:20],  # First 20 trades
        }, f, indent=2)
    
    print(f"\n✅ Results saved to eth_squeeze_optimized_results.json")
