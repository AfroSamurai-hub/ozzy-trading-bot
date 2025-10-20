#!/usr/bin/env python3
"""
4H Strategy Validation Backtest

Uses the downloaded 4H historical data to validate:
1. Pattern detection at 4H scale
2. Trade frequency (should be 10-15/month)
3. Win rate on 4H timeframe
4. Fee impact with new parameters
5. Risk/reward ratio

This is a simplified backtest focused on validating the timeframe pivot.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SimplePattern:
    """Simple pattern detection for validation"""
    
    @staticmethod
    def detect_engulfing_bullish(curr, prev):
        """Detect bullish engulfing pattern"""
        return (
            prev['close'] < prev['open'] and  # Prev red
            curr['close'] > curr['open'] and  # Curr green
            curr['open'] < prev['close'] and  # Curr opens below prev close
            curr['close'] > prev['open']      # Curr closes above prev open
        )
    
    @staticmethod
    def detect_engulfing_bearish(curr, prev):
        """Detect bearish engulfing pattern"""
        return (
            prev['close'] > prev['open'] and  # Prev green
            curr['close'] < curr['open'] and  # Curr red
            curr['open'] > prev['close'] and  # Curr opens above prev close
            curr['close'] < prev['open']      # Curr closes below prev open
        )
    
    @staticmethod
    def detect_hammer(candle):
        """Detect hammer pattern (bullish reversal)"""
        body = abs(candle['close'] - candle['open'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        
        return (
            lower_wick > body * 2 and  # Long lower wick
            upper_wick < body * 0.5 and  # Small upper wick
            candle['close'] > candle['open']  # Bullish close
        )
    
    @staticmethod
    def detect_shooting_star(candle):
        """Detect shooting star pattern (bearish reversal)"""
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        return (
            upper_wick > body * 2 and  # Long upper wick
            lower_wick < body * 0.5 and  # Small lower wick
            candle['close'] < candle['open']  # Bearish close
        )


class FourHourBacktest:
    """Backtest the 4H trading strategy"""
    
    def __init__(self, data_file: str, initial_capital: float = 10000.0):
        self.data_file = data_file
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = []
        self.closed_trades = []
        
        # Risk parameters (from .env calibration)
        self.tp_pct = 0.06  # 6% take profit
        self.sl_pct = 0.03  # 3% stop loss
        self.position_size_pct = 0.02  # 2% per trade
        self.maker_fee = 0.001  # 0.1% maker fee
        self.taker_fee = 0.001  # 0.1% taker fee
        
        # Optimization parameters (Week 2) - ITERATION 3C: More relaxed
        self.min_candles_between_trades = 1  # Cooldown: 4 hours @ 4H (minimal)
        self.last_trade_idx = -999  # Track last trade for cooldown
        self.rsi_oversold = 50  # Buy when RSI < 50 (neutral point)
        self.rsi_overbought = 50  # Sell when RSI > 50 (neutral point)
        self.min_atr_pct = 0.3  # Only trade when ATR > 0.3% (very relaxed)
        
        # Load data
        self.df = pd.read_csv(data_file)
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        print(f"✅ Loaded {len(self.df)} 4H candles")
        print(f"📅 Period: {self.df['timestamp'].iloc[0]} to {self.df['timestamp'].iloc[-1]}")
    
    def calculate_indicators(self):
        """Calculate technical indicators"""
        # Simple Moving Averages
        self.df['sma_10'] = self.df['close'].rolling(10).mean()
        self.df['sma_20'] = self.df['close'].rolling(20).mean()
        
        # Volume moving average
        self.df['volume_ma'] = self.df['volume'].rolling(20).mean()
        
        # RSI (14-period) for momentum confirmation
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR (14-period) for volatility filtering
        high_low = self.df['high'] - self.df['low']
        high_close = (self.df['high'] - self.df['close'].shift()).abs()
        low_close = (self.df['low'] - self.df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        self.df['atr'] = true_range.rolling(14).mean()
        self.df['atr_pct'] = (self.df['atr'] / self.df['close']) * 100
        
        # Trend detection (1 = uptrend, -1 = downtrend, 0 = neutral)
        self.df['trend'] = 0
        self.df.loc[self.df['sma_10'] > self.df['sma_20'], 'trend'] = 1
        self.df.loc[self.df['sma_10'] < self.df['sma_20'], 'trend'] = -1
        
    def check_entry_signal(self, i: int) -> tuple[str, str]:
        """Check for entry signals - returns (action, reason)"""
        if i < 20:  # Need enough data for indicators
            return None, None
        
        # OPTIMIZATION 1: Cooldown filter (prevent overtrading)
        if (i - self.last_trade_idx) < self.min_candles_between_trades:
            return None, None  # Too soon since last trade
        
        curr = self.df.iloc[i]
        prev = self.df.iloc[i-1]
        
        # OPTIMIZATION 2: Volatility filter (avoid choppy markets)
        atr_pct = self.df.loc[curr.name, 'atr_pct']
        if pd.notna(atr_pct) and atr_pct < self.min_atr_pct:
            return None, None  # Market too quiet, skip
        
        # OPTIMIZATION 3: RSI momentum confirmation
        rsi = self.df.loc[curr.name, 'rsi']
        if pd.isna(rsi):
            return None, None
        
        # Bullish signals - REQUIRE RSI oversold for better entry
        if SimplePattern.detect_engulfing_bullish(curr, prev):
            if curr['trend'] >= 0 and rsi < self.rsi_oversold:
                return 'BUY', 'Bullish engulfing + RSI oversold'
        
        if SimplePattern.detect_hammer(curr):
            if curr['trend'] >= 0 and rsi < self.rsi_oversold:
                return 'BUY', 'Hammer + RSI oversold'
        
        # Trend following entries - REQUIRE RSI confirmation
        if curr['trend'] == 1:
            # Enter on pullback to SMA ONLY if RSI oversold
            if (curr['low'] <= curr['sma_10'] and 
                curr['close'] > curr['sma_10'] and 
                rsi < self.rsi_oversold):
                return 'BUY', 'Pullback to SMA10 + RSI oversold'
        
        # Bearish signals - REQUIRE RSI overbought for better entry
        if SimplePattern.detect_engulfing_bearish(curr, prev):
            if curr['trend'] <= 0 and rsi > self.rsi_overbought:
                return 'SELL', 'Bearish engulfing + RSI overbought'
        
        if SimplePattern.detect_shooting_star(curr):
            if curr['trend'] <= 0 and rsi > self.rsi_overbought:
                return 'SELL', 'Shooting star + RSI overbought'
        
        # Trend following short entries - REQUIRE RSI confirmation
        if curr['trend'] == -1:
            # Enter on bounce to SMA ONLY if RSI overbought
            if (curr['high'] >= curr['sma_10'] and 
                curr['close'] < curr['sma_10'] and 
                rsi > self.rsi_overbought):
                return 'SELL', 'Bounce to SMA10 + RSI overbought'
        
        return None, None
    
    def open_position(self, i: int, action: str, reason: str):
        """Open a new position"""
        candle = self.df.iloc[i]
        entry_price = candle['close']
        
        # OPTIMIZATION 4: Fixed position sizing (use initial capital, not compounded)
        size = self.initial_capital * self.position_size_pct
        
        # Calculate fees
        entry_fee = size * self.taker_fee
        size -= entry_fee
        
        # Update cooldown tracker
        self.last_trade_idx = i
    
    def open_position(self, i: int, action: str, reason: str):
        """Open a new position"""
        candle = self.df.iloc[i]
        entry_price = candle['close']
        size = self.capital * self.position_size_pct
        
        # Calculate fees
        entry_fee = size * self.taker_fee
        size -= entry_fee
        
        if action == 'BUY':
            tp_price = entry_price * (1 + self.tp_pct)
            sl_price = entry_price * (1 - self.sl_pct)
        else:  # SELL (short)
            tp_price = entry_price * (1 - self.tp_pct)
            sl_price = entry_price * (1 + self.sl_pct)
        
        position = {
            'entry_idx': i,
            'entry_time': candle['timestamp'],
            'entry_price': entry_price,
            'action': action,
            'size': size,
            'tp': tp_price,
            'sl': sl_price,
            'entry_fee': entry_fee,
            'reason': reason
        }
        
        self.positions.append(position)
        self.capital -= entry_fee
    
    def check_exits(self, i: int):
        """Check if any positions should be closed"""
        candle = self.df.iloc[i]
        
        for pos in list(self.positions):
            exit_reason = None
            exit_price = None
            
            if pos['action'] == 'BUY':
                # Check TP
                if candle['high'] >= pos['tp']:
                    exit_reason = 'TP'
                    exit_price = pos['tp']
                # Check SL
                elif candle['low'] <= pos['sl']:
                    exit_reason = 'SL'
                    exit_price = pos['sl']
                # Timeout (24H = 6 candles @ 4H)
                elif (i - pos['entry_idx']) >= 6:
                    exit_reason = 'TIMEOUT'
                    exit_price = candle['close']
            
            else:  # SELL (short)
                # Check TP
                if candle['low'] <= pos['tp']:
                    exit_reason = 'TP'
                    exit_price = pos['tp']
                # Check SL
                elif candle['high'] >= pos['sl']:
                    exit_reason = 'SL'
                    exit_price = pos['sl']
                # Timeout
                elif (i - pos['entry_idx']) >= 6:
                    exit_reason = 'TIMEOUT'
                    exit_price = candle['close']
            
            if exit_reason:
                self.close_position(pos, i, candle['timestamp'], exit_price, exit_reason)
                self.positions.remove(pos)
    
    def close_position(self, pos: dict, exit_idx: int, exit_time, exit_price: float, reason: str):
        """Close a position and record the trade"""
        # Calculate P&L
        if pos['action'] == 'BUY':
            pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        else:  # SELL (short)
            pnl_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
        
        pnl_dollars = pos['size'] * pnl_pct
        exit_fee = pos['size'] * self.taker_fee
        net_pnl = pnl_dollars - exit_fee
        
        self.capital += pos['size'] + net_pnl
        
        trade = {
            **pos,
            'exit_idx': exit_idx,
            'exit_time': exit_time,
            'exit_price': exit_price,
            'exit_reason': reason,
            'exit_fee': exit_fee,
            'pnl_pct': pnl_pct * 100,
            'pnl_dollars': pnl_dollars,
            'net_pnl': net_pnl,
            'total_fees': pos['entry_fee'] + exit_fee,
            'win': net_pnl > 0
        }
        
        self.closed_trades.append(trade)
    
    def run(self):
        """Run the backtest"""
        print(f"\n{'='*80}")
        print("🚀 STARTING 4H BACKTEST")
        print(f"{'='*80}\n")
        
        print(f"💰 Initial capital: ${self.initial_capital:,.2f}")
        print(f"🎯 Take Profit: {self.tp_pct*100:.1f}%")
        print(f"🛡️  Stop Loss: {self.sl_pct*100:.1f}%")
        print(f"📊 Position size: {self.position_size_pct*100:.1f}% per trade")
        print(f"💸 Fees: {self.maker_fee*100:.2f}% maker, {self.taker_fee*100:.2f}% taker\n")
        
        # Calculate indicators
        print("📈 Calculating indicators...")
        self.calculate_indicators()
        
        # Run simulation
        print(f"🔄 Simulating {len(self.df)} 4H candles...\n")
        
        for i in range(len(self.df)):
            # Check exits first
            self.check_exits(i)
            
            # Check for new entry (max 3 concurrent positions)
            if len(self.positions) < 3:
                action, reason = self.check_entry_signal(i)
                if action:
                    self.open_position(i, action, reason)
                    candle = self.df.iloc[i]
                    print(f"📍 [{candle['timestamp']}] {action} @ ${candle['close']:,.2f} - {reason}")
        
        # Close any remaining positions at market price
        if self.positions:
            final_candle = self.df.iloc[-1]
            for pos in list(self.positions):
                self.close_position(pos, len(self.df)-1, final_candle['timestamp'], 
                                  final_candle['close'], 'END_OF_TEST')
        
        self.print_results()
    
    def print_results(self):
        """Print backtest results"""
        print(f"\n{'='*80}")
        print("📊 BACKTEST RESULTS")
        print(f"{'='*80}\n")
        
        # Overall performance
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        print(f"💰 Final Capital: ${self.capital:,.2f}")
        print(f"📈 Total Return: {total_return:+.2f}%")
        print(f"💵 P&L: ${self.capital - self.initial_capital:+,.2f}\n")
        
        if not self.closed_trades:
            print("⚠️  No trades executed!")
            return
        
        # Trade statistics
        total_trades = len(self.closed_trades)
        wins = sum(1 for t in self.closed_trades if t['win'])
        losses = total_trades - wins
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        print(f"📊 Trade Statistics:")
        print(f"   Total trades: {total_trades}")
        print(f"   Wins: {wins}")
        print(f"   Losses: {losses}")
        print(f"   Win rate: {win_rate:.1f}%\n")
        
        # Calculate monthly trade frequency
        days = (self.df['timestamp'].iloc[-1] - self.df['timestamp'].iloc[0]).days
        months = days / 30
        trades_per_month = total_trades / months if months > 0 else 0
        
        print(f"📅 Trading Frequency:")
        print(f"   Test period: {days} days ({months:.1f} months)")
        print(f"   Trades per month: {trades_per_month:.1f}\n")
        
        # P&L breakdown
        total_pnl = sum(t['net_pnl'] for t in self.closed_trades)
        total_fees = sum(t['total_fees'] for t in self.closed_trades)
        avg_win = np.mean([t['net_pnl'] for t in self.closed_trades if t['win']]) if wins > 0 else 0
        avg_loss = np.mean([t['net_pnl'] for t in self.closed_trades if not t['win']]) if losses > 0 else 0
        
        print(f"💵 P&L Breakdown:")
        print(f"   Total P&L: ${total_pnl:+,.2f}")
        print(f"   Total Fees: ${total_fees:,.2f}")
        print(f"   Avg Win: ${avg_win:+,.2f}")
        print(f"   Avg Loss: ${avg_loss:+,.2f}")
        if avg_loss != 0:
            print(f"   Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}:1\n")
        
        # Fee analysis
        fee_pct = (total_fees / self.initial_capital) * 100
        monthly_fees = total_fees / months if months > 0 else 0
        
        print(f"💸 Fee Analysis:")
        print(f"   Total fees: ${total_fees:,.2f} ({fee_pct:.2f}% of capital)")
        print(f"   Monthly fees: ${monthly_fees:,.2f}\n")
        
        # Exit reasons
        exit_counts = {}
        for t in self.closed_trades:
            reason = t['exit_reason']
            exit_counts[reason] = exit_counts.get(reason, 0) + 1
        
        print(f"🚪 Exit Reasons:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_trades) * 100
            print(f"   {reason}: {count} ({pct:.1f}%)")
        
        print(f"\n{'='*80}")
        print("🎯 VALIDATION SUMMARY")
        print(f"{'='*80}\n")
        
        # Validation checks
        checks = []
        
        # 1. Trading frequency (should be 10-15/month)
        freq_ok = 10 <= trades_per_month <= 15
        checks.append(('Trading frequency', f'{trades_per_month:.1f}/month', '10-15/month', freq_ok))
        
        # 2. Win rate (should be >50% for profitability)
        wr_ok = win_rate >= 50
        checks.append(('Win rate', f'{win_rate:.1f}%', '≥50%', wr_ok))
        
        # 3. Monthly fees (should be <$400 on $10K)
        fees_ok = monthly_fees < 400
        checks.append(('Monthly fees', f'${monthly_fees:.2f}', '<$400', fees_ok))
        
        # 4. Positive return
        return_ok = total_return > 0
        checks.append(('Total return', f'{total_return:+.2f}%', '>0%', return_ok))
        
        for metric, actual, target, passed in checks:
            status = '✅' if passed else '❌'
            print(f"{status} {metric:20s}: {actual:15s} (target: {target})")
        
        passed_checks = sum(1 for _, _, _, ok in checks if ok)
        print(f"\n{'='*80}")
        print(f"Validation: {passed_checks}/{len(checks)} checks passed")
        print(f"{'='*80}\n")
        
        if passed_checks == len(checks):
            print("✅ 4H STRATEGY VALIDATED - ALL CHECKS PASSED!")
        elif passed_checks >= len(checks) * 0.75:
            print("⚠️  4H STRATEGY PARTIALLY VALIDATED - NEEDS TUNING")
        else:
            print("❌ 4H STRATEGY FAILED VALIDATION - MAJOR ISSUES")


if __name__ == "__main__":
    # Path to the downloaded 4H data
    data_file = "data/historical/BTCUSDT_240m_bootstrap.csv"
    
    if not Path(data_file).exists():
        print(f"❌ Data file not found: {data_file}")
        print("Run: python3 scripts/download_historical.py --symbol BTCUSDT --interval 240 --days 365")
        sys.exit(1)
    
    backtest = FourHourBacktest(data_file)
    backtest.run()
