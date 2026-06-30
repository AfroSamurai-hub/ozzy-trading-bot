#!/usr/bin/env python3
"""
OzzyBot Futures Strategy Backtester
Compares multiple strategies across timeframes with realistic fees/slippage/funding.
Pulls live data from Binance Futures API.
"""

import json
import time
import math
from datetime import datetime, timedelta
from binance.client import Client

# ── Config ──
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INITIAL_CAPITAL = 5000.0  # USDT
LEVERAGE = 10  # x
RISK_PER_TRADE = 0.05  # 5%
FEE_MAKER = 0.0002  # 0.02%
FEE_TAKER = 0.0004  # 0.04%
SLIPPAGE_PCT = 0.0005  # 0.05%
TESTNET = True

# ── Binance Client ──
from config import BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET
client = Client(BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET, testnet=TESTNET)

def fetch_ohlcv(symbol, interval, days=90):
    """Fetch OHLCV data from Binance Futures."""
    end = int(time.time() * 1000)
    start = end - (days * 24 * 60 * 60 * 1000)
    
    klines = client.futures_klines(
        symbol=symbol,
        interval=interval,
        startTime=start,
        endTime=end,
        limit=1000
    )
    
    candles = []
    for k in klines:
        candles.append({
            'time': k[0],
            'open': float(k[1]),
            'high': float(k[2]),
            'low': float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5]),
            'close_time': k[6],
        })
    return candles

def fetch_funding(symbol, days=90):
    """Fetch historical funding rates."""
    end = int(time.time() * 1000)
    start = end - (days * 24 * 60 * 60 * 1000)
    
    funding = client.futures_funding_rate(
        symbol=symbol,
        startTime=start,
        endTime=end,
        limit=1000
    )
    
    rates = []
    for f in funding:
        rates.append({
            'time': int(f['fundingTime']),
            'rate': float(f['fundingRate']),
        })
    return rates

# ── Strategy Implementations ──

def calc_sma(data, period):
    sma = []
    for i in range(len(data)):
        if i < period - 1:
            sma.append(None)
        else:
            sma.append(sum(data[i-period+1:i+1]) / period)
    return sma

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

def calc_rsi(data, period=14):
    rsi = []
    gains = []
    losses = []
    
    for i in range(len(data)):
        if i == 0:
            gains.append(0)
            losses.append(0)
            rsi.append(50)
            continue
        
        change = data[i] - data[i-1]
        gain = change if change > 0 else 0
        loss = -change if change < 0 else 0
        
        gains.append(gain)
        losses.append(loss)
        
        if i < period:
            rsi.append(50)
            continue
        
        avg_gain = sum(gains[i-period+1:i+1]) / period
        avg_loss = sum(losses[i-period+1:i+1]) / period
        
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    
    return rsi

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

def calc_vwap(candles):
    vwap = []
    cum_vol = 0
    cum_pv = 0
    
    for c in candles:
        typical = (c['high'] + c['low'] + c['close']) / 3
        cum_vol += c['volume']
        cum_pv += typical * c['volume']
        
        if cum_vol > 0:
            vwap.append(cum_pv / cum_vol)
        else:
            vwap.append(c['close'])
    
    return vwap

# ── Strategy 1: OzzyBot Current (SuperTrend + SMC) ──
def strategy_ozzybot(candles):
    signals = []
    closes = [c['close'] for c in candles]
    atr = calc_atr(candles, 14)
    
    # Simplified SuperTrend
    upper = []
    lower = []
    st = []
    
    for i in range(len(candles)):
        if atr[i] == 0:
            atr[i] = closes[i] * 0.01
        
        mid = (candles[i]['high'] + candles[i]['low']) / 2
        upper.append(mid + 3 * atr[i])
        lower.append(mid - 3 * atr[i])
        
        if i == 0:
            st.append({'dir': 1, 'val': lower[0]})
            continue
        
        prev_dir = st[-1]['dir']
        prev_val = st[-1]['val']
        
        if closes[i] > upper[i-1]:
            new_dir = 1
            new_val = lower[i]
        elif closes[i] < lower[i-1]:
            new_dir = -1
            new_val = upper[i]
        else:
            new_dir = prev_dir
            new_val = lower[i] if prev_dir == 1 else upper[i]
        
        st.append({'dir': new_dir, 'val': new_val})
    
    # Generate signals
    for i in range(100, len(candles)):
        if st[i]['dir'] == 1 and st[i-1]['dir'] == -1:
            signals.append({'idx': i, 'side': 'BUY', 'entry': closes[i]})
        elif st[i]['dir'] == -1 and st[i-1]['dir'] == 1:
            signals.append({'idx': i, 'side': 'SELL', 'entry': closes[i]})
    
    return signals

# ── Strategy 2: VWAP + EMA Ribbon (Mean Reversion + Trend) ──
def strategy_vwap_ema(candles):
    signals = []
    closes = [c['close'] for c in candles]
    ema8 = calc_ema(closes, 8)
    ema21 = calc_ema(closes, 21)
    ema55 = calc_ema(closes, 55)
    vwap = calc_vwap(candles)
    
    for i in range(100, len(candles)):
        if ema8[i] is None or ema21[i] is None or ema55[i] is None:
            continue
        
        # Trend confirmation: EMA 8 > 21 > 55
        trend_up = ema8[i] > ema21[i] > ema55[i]
        trend_down = ema8[i] < ema21[i] < ema55[i]
        
        # Pullback to VWAP in uptrend
        if trend_up and candles[i]['low'] <= vwap[i] * 1.002 and candles[i]['close'] > vwap[i]:
            signals.append({'idx': i, 'side': 'BUY', 'entry': closes[i]})
        
        # Pullback to VWAP in downtrend
        elif trend_down and candles[i]['high'] >= vwap[i] * 0.998 and candles[i]['close'] < vwap[i]:
            signals.append({'idx': i, 'side': 'SELL', 'entry': closes[i]})
    
    return signals

# ── Strategy 3: RSI Divergence + Liquidation Wick (Reversal) ──
def strategy_rsi_div(candles):
    signals = []
    closes = [c['close'] for c in candles]
    rsi = calc_rsi(closes, 14)
    atr = calc_atr(candles, 14)
    
    for i in range(100, len(candles)):
        if rsi[i] is None:
            continue
        
        # Oversold bounce
        if rsi[i] < 30 and rsi[i-1] < 35 and candles[i]['close'] > candles[i-1]['close']:
            # Wicked low below support
            if candles[i]['low'] < candles[i-1]['low'] and candles[i]['close'] > candles[i-1]['low']:
                signals.append({'idx': i, 'side': 'BUY', 'entry': closes[i]})
        
        # Overbought reversal
        elif rsi[i] > 70 and rsi[i-1] > 65 and candles[i]['close'] < candles[i-1]['close']:
            # Wicked high above resistance
            if candles[i]['high'] > candles[i-1]['high'] and candles[i]['close'] < candles[i-1]['high']:
                signals.append({'idx': i, 'side': 'SELL', 'entry': closes[i]})
    
    return signals

# ── Strategy 4: Volatility Squeeze (Bollinger/Keltner) ──
def strategy_squeeze(candles):
    signals = []
    closes = [c['close'] for c in candles]
    atr = calc_atr(candles, 20)
    
    # Bollinger Bands
    bb_upper = []
    bb_lower = []
    for i in range(len(candles)):
        if i < 19:
            bb_upper.append(None)
            bb_lower.append(None)
            continue
        sma = sum(closes[i-19:i+1]) / 20
        std = math.sqrt(sum((c - sma)**2 for c in closes[i-19:i+1]) / 20)
        bb_upper.append(sma + 2 * std)
        bb_lower.append(sma - 2 * std)
    
    # Keltner Channel
    kc_upper = []
    kc_lower = []
    for i in range(len(candles)):
        if i < 20:
            kc_upper.append(None)
            kc_lower.append(None)
            continue
        ema = sum(closes[i-19:i+1]) / 20
        kc_upper.append(ema + 1.5 * atr[i])
        kc_lower.append(ema - 1.5 * atr[i])
    
    for i in range(100, len(candles)):
        if bb_upper[i] is None:
            continue
        
        # Squeeze: BB inside KC
        squeeze = bb_upper[i] < kc_upper[i] and bb_lower[i] > kc_lower[i]
        
        # Breakout from squeeze
        if squeeze:
            # Bullish breakout
            if closes[i] > kc_upper[i]:
                signals.append({'idx': i, 'side': 'BUY', 'entry': closes[i]})
            # Bearish breakout
            elif closes[i] < kc_lower[i]:
                signals.append({'idx': i, 'side': 'SELL', 'entry': closes[i]})
    
    return signals

# ── Strategy 5: OI + Volume Breakout (Smart Money Flow) ──
def strategy_oi_volume(candles):
    signals = []
    closes = [c['close'] for c in candles]
    volumes = [c['volume'] for c in candles]
    ema20_vol = calc_ema(volumes, 20)
    
    for i in range(100, len(candles)):
        if ema20_vol[i] is None:
            continue
        
        # High volume breakout
        vol_surge = volumes[i] > ema20_vol[i] * 1.5
        
        # Price breaks recent high/low
        recent_high = max(c['high'] for c in candles[i-20:i])
        recent_low = min(c['low'] for c in candles[i-20:i])
        
        if vol_surge and closes[i] > recent_high:
            signals.append({'idx': i, 'side': 'BUY', 'entry': closes[i]})
        elif vol_surge and closes[i] < recent_low:
            signals.append({'idx': i, 'side': 'SELL', 'entry': closes[i]})
    
    return signals

# ── Backtest Engine ──
def run_backtest(signals, candles, symbol, funding_rates, fee_taker=FEE_TAKER):
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    equity_curve = [capital]
    
    for sig in signals:
        i = sig['idx']
        if i >= len(candles) - 2:
            break
        
        entry_price = sig['entry'] * (1 + SLIPPAGE_PCT if sig['side'] == 'BUY' else 1 - SLIPPAGE_PCT)
        atr = calc_atr(candles, 14)
        atr_val = atr[i] if i < len(atr) else entry_price * 0.01
        if atr_val == 0:
            atr_val = entry_price * 0.01
        
        sl_distance = atr_val * 1.5
        rr = 2.5
        
        if sig['side'] == 'BUY':
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * rr
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * rr
        
        # Position size
        risk = capital * RISK_PER_TRADE
        qty = risk / sl_distance
        
        # Check margin (leverage)
        margin_needed = (qty * entry_price) / LEVERAGE
        if margin_needed > capital * 0.9:  # Can't use more than 90% of capital
            continue
        
        # Simulate trade
        entry_time = candles[i]['time']
        exit_price = None
        exit_reason = None
        exit_time = None
        pnl = 0
        fees = 0
        funding_paid = 0
        
        # Check each subsequent candle for SL/TP hit
        for j in range(i+1, len(candles)):
            c = candles[j]
            
            if sig['side'] == 'BUY':
                if c['low'] <= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif c['high'] >= tp:
                    exit_price = tp
                    exit_reason = 'TP'
            else:
                if c['high'] >= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif c['low'] <= tp:
                    exit_price = tp
                    exit_reason = 'TP'
            
            if exit_price:
                exit_time = c['time']
                
                # Calculate PnL
                if sig['side'] == 'BUY':
                    pnl = qty * (exit_price - entry_price)
                else:
                    pnl = qty * (entry_price - exit_price)
                
                # Fees
                entry_fee = qty * entry_price * fee_taker
                exit_fee = qty * exit_price * fee_taker
                fees = entry_fee + exit_fee
                
                # Funding cost
                for fr in funding_rates:
                    if entry_time < fr['time'] <= exit_time:
                        funding_paid += abs(fr['rate'] * qty * entry_price)
                
                capital += pnl - fees - funding_paid
                break
        
        if exit_reason:
            trade = {
                'symbol': symbol,
                'side': sig['side'],
                'entry': entry_price,
                'exit': exit_price,
                'qty': qty,
                'pnl': pnl,
                'fees': fees,
                'funding': funding_paid,
                'net': pnl - fees - funding_paid,
                'exit_reason': exit_reason,
                'entry_time': datetime.fromtimestamp(entry_time/1000).strftime('%Y-%m-%d %H:%M'),
                'exit_time': datetime.fromtimestamp(exit_time/1000).strftime('%Y-%m-%d %H:%M'),
            }
            trades.append(trade)
            equity_curve.append(capital)
        
        # Update equity curve for open period
        if not position:
            for k in range(i, min(i+20, len(candles))):
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
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    
    total_pnl = sum(t['net'] for t in trades)
    total_fees = sum(t['fees'] for t in trades)
    total_funding = sum(t['funding'] for t in trades)
    
    avg_win = sum(t['net'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['net'] for t in losses) / len(losses) if losses else 0
    
    profit_factor = abs(sum(t['net'] for t in wins) / sum(t['net'] for t in losses)) if losses and sum(t['net'] for t in losses) != 0 else float('inf')
    
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
        'total_funding': round(total_funding, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'max_drawdown': round(max_drawdown, 1),
        'final_capital': round(result['capital'], 2),
        'return_pct': round((result['capital'] - result['initial_capital']) / result['initial_capital'] * 100, 1),
    }

# ── Main ──
if __name__ == '__main__':
    print("🚀 OzzyBot Futures Strategy Backtester\n")
    print("Fetching data from Binance Futures...")
    
    strategies = [
        ('OzzyBot ST/SMC (4H)', strategy_ozzybot, '4h'),
        ('VWAP + EMA Ribbon (1H)', strategy_vwap_ema, '1h'),
        ('RSI Divergence (15m)', strategy_rsi_div, '15m'),
        ('Volatility Squeeze (1H)', strategy_squeeze, '1h'),
        ('OI + Volume Breakout (1H)', strategy_oi_volume, '1h'),
    ]
    
    results = []
    
    for sym in SYMBOLS:
        print(f"\n📊 Processing {sym}...")
        
        # Fetch data for each timeframe needed
        timeframes = set(s[2] for s in strategies)
        data = {}
        for tf in timeframes:
            print(f"  Fetching {sym} {tf}...")
            data[tf] = fetch_ohlcv(sym, tf, days=90)
            print(f"  Got {len(data[tf])} candles")
        
        funding = fetch_funding(sym, days=90)
        
        for name, func, tf in strategies:
            candles = data[tf]
            if len(candles) < 100:
                continue
            
            print(f"  Running {name}...")
            signals = func(candles)
            result = run_backtest(signals, candles, sym, funding)
            analysis = analyze_results(result, name, sym)
            results.append(analysis)
    
    # Print results
    print("\n" + "="*80)
    print("📈 BACKTEST RESULTS")
    print("="*80)
    
    for r in results:
        print(f"\n--- {r['strategy']} | {r['symbol']} ---")
        print(f"Trades: {r['total_trades']} | Win Rate: {r['win_rate']}%")
        print(f"Net PnL: ${r['net_pnl']} | Return: {r['return_pct']}%")
        print(f"Profit Factor: {r['profit_factor']} | Max DD: {r['max_drawdown']}%")
        print(f"Fees: ${r['total_fees']} | Funding: ${r['total_funding']}")
        print(f"Avg Win: ${r['avg_win']} | Avg Loss: ${r['avg_loss']}")
    
    # Save to file
    with open('futures_backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to futures_backtest_results.json")
