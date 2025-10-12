#!/usr/bin/env python3
"""
EMA Parameter Optimization Suite
Find optimal EMA_SHORT and EMA_LONG periods for crossover signals
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import track

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bybit_client import BybitClient

console = Console()


class EMAOptimizer:
    """Optimize EMA parameters based on historical trade performance"""
    
    def __init__(self, db_path: str = "ozzy_simple.db"):
        self.db_path = db_path
        self.client = BybitClient()
        self.trades_df = None
        self.results = []
        
    def load_trades(self) -> pd.DataFrame:
        """Load historical trades from database"""
        console.print("\n[cyan]📊 Loading historical trades...[/cyan]")
        
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT 
                id, symbol, side, 
                entry_timestamp, exit_timestamp,
                entry_price, exit_price, 
                pnl, confidence
            FROM trades
            WHERE exit_timestamp IS NOT NULL
            ORDER BY entry_timestamp
        """
        
        self.trades_df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Convert timestamps
        self.trades_df['entry_timestamp'] = pd.to_datetime(self.trades_df['entry_timestamp'])
        self.trades_df['exit_timestamp'] = pd.to_datetime(self.trades_df['exit_timestamp'])
        
        # Calculate trade duration
        self.trades_df['duration'] = (
            self.trades_df['exit_timestamp'] - self.trades_df['entry_timestamp']
        ).dt.total_seconds() / 60  # minutes
        
        console.print(f"[green]✅ Loaded {len(self.trades_df)} trades[/green]")
        return self.trades_df
    
    def calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate EMA indicator"""
        return prices.ewm(span=period, adjust=False).mean()
    
    def fetch_historical_data(self, symbol: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
        """Fetch historical price data for a trade period"""
        try:
            # Add buffer for EMA calculation (need 100+ candles)
            buffered_start = start_time - timedelta(hours=3)
            
            # Fetch 1-minute candles
            candles = self.client.get_candles(
                symbol=symbol,
                interval="1",
                limit=200,
                start_time=int(buffered_start.timestamp() * 1000)
            )
            
            if not candles:
                return pd.DataFrame()
            
            df = pd.DataFrame(candles)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['close'] = df['close'].astype(float)
            
            return df
            
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not fetch data for {symbol}: {e}[/yellow]")
            return pd.DataFrame()
    
    def detect_crossover(self, ema_short: pd.Series, ema_long: pd.Series, idx: int) -> str:
        """Detect if golden cross or death cross occurred"""
        if idx < 1 or pd.isna(ema_short.iloc[idx]) or pd.isna(ema_long.iloc[idx]):
            return "NONE"
        
        # Current state
        short_above = ema_short.iloc[idx] > ema_long.iloc[idx]
        # Previous state
        short_above_prev = ema_short.iloc[idx-1] > ema_long.iloc[idx-1]
        
        if short_above and not short_above_prev:
            return "GOLDEN"  # Bullish crossover
        elif not short_above and short_above_prev:
            return "DEATH"   # Bearish crossover
        
        return "NONE"
    
    def simulate_with_params(self, ema_short: int, ema_long: int,
                            mode: str = "balanced") -> Dict:
        """Simulate trades with given EMA parameters"""
        
        trades = self.trades_df.copy()
        
        if len(trades) == 0:
            return self._empty_result(ema_short, ema_long)
        
        # For each trade, check if EMA would have signaled entry
        valid_trades = []
        whipsaw_count = 0
        lag_times = []
        
        for _, trade in trades.iterrows():
            # Fetch historical data
            hist_data = self.fetch_historical_data(
                trade['symbol'],
                trade['entry_timestamp'],
                trade['exit_timestamp']
            )
            
            if hist_data.empty or len(hist_data) < max(ema_short, ema_long) + 10:
                continue
            
            # Calculate EMAs
            ema_s = self.calculate_ema(hist_data['close'], ema_short)
            ema_l = self.calculate_ema(hist_data['close'], ema_long)
            
            # Find entry point
            entry_idx = hist_data[hist_data['timestamp'] >= trade['entry_timestamp']].index
            if len(entry_idx) == 0:
                continue
            
            entry_idx = entry_idx[0]
            
            # Check for crossover signal
            crossover = self.detect_crossover(ema_s, ema_l, entry_idx)
            
            # Look back window for recent crossover
            lookback = 10  # candles
            recent_cross = "NONE"
            
            for i in range(max(0, entry_idx - lookback), entry_idx + 1):
                cross = self.detect_crossover(ema_s, ema_l, i)
                if cross != "NONE":
                    recent_cross = cross
                    # Calculate lag (distance from crossover to entry)
                    lag = entry_idx - i
                    lag_times.append(lag)
                    break
            
            # Check if EMA signal matches trade direction
            signal_match = False
            
            if trade['side'] == 'LONG' and recent_cross == "GOLDEN":
                signal_match = True
            elif trade['side'] == 'SHORT' and recent_cross == "DEATH":
                signal_match = True
            
            if signal_match:
                valid_trades.append(trade)
                
                # Check for whipsaw (quick reversal)
                for i in range(entry_idx, min(entry_idx + 20, len(hist_data))):
                    reverse_cross = self.detect_crossover(ema_s, ema_l, i)
                    if (recent_cross == "GOLDEN" and reverse_cross == "DEATH") or \
                       (recent_cross == "DEATH" and reverse_cross == "GOLDEN"):
                        whipsaw_count += 1
                        break
        
        if len(valid_trades) == 0:
            return self._empty_result(ema_short, ema_long)
        
        # Calculate metrics
        valid_df = pd.DataFrame(valid_trades)
        wins = len(valid_df[valid_df['pnl'] > 0])
        losses = len(valid_df[valid_df['pnl'] <= 0])
        win_rate = (wins / len(valid_df)) * 100 if len(valid_df) > 0 else 0
        
        total_wins = valid_df[valid_df['pnl'] > 0]['pnl'].sum()
        total_losses = abs(valid_df[valid_df['pnl'] <= 0]['pnl'].sum())
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        total_pnl = valid_df['pnl'].sum()
        avg_duration = valid_df['duration'].mean()
        
        # Whipsaw rate
        whipsaw_rate = (whipsaw_count / len(valid_df)) * 100 if len(valid_df) > 0 else 0
        
        # Average lag
        avg_lag = np.mean(lag_times) if lag_times else 0
        
        # Composite score
        score = (
            win_rate * 0.35 +
            min(profit_factor * 10, 100) * 0.30 +
            max(0, 100 - whipsaw_rate * 2) * 0.20 +
            max(0, 100 - avg_lag * 5) * 0.15
        )
        
        return {
            'ema_short': ema_short,
            'ema_long': ema_long,
            'trades': len(valid_df),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'avg_duration': avg_duration,
            'whipsaw_rate': whipsaw_rate,
            'avg_lag': avg_lag,
            'score': score
        }
    
    def _empty_result(self, ema_short: int, ema_long: int) -> Dict:
        """Return empty result structure"""
        return {
            'ema_short': ema_short,
            'ema_long': ema_long,
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_pnl': 0,
            'avg_duration': 0,
            'whipsaw_rate': 0,
            'avg_lag': 0,
            'score': 0
        }
    
    def optimize(self, short_range: List[int] = None,
                 long_range: List[int] = None,
                 mode: str = "balanced") -> List[Dict]:
        """Run optimization across parameter space"""
        
        if mode == "fast":
            short_range = short_range or [5, 8, 9, 12]
            long_range = long_range or [15, 18, 21, 26, 30]
        elif mode == "slow":
            short_range = short_range or [15, 18, 20, 25]
            long_range = long_range or [30, 34, 40, 50, 60]
        elif mode == "scalping":
            short_range = short_range or [5, 8, 9, 12]
            long_range = long_range or [15, 18, 21, 26]
        elif mode == "swing":
            short_range = short_range or [12, 15, 20, 26]
            long_range = long_range or [26, 34, 50, 100]
        else:  # balanced
            short_range = short_range or [5, 8, 9, 12, 15, 20]
            long_range = long_range or [18, 21, 26, 30, 34, 50]
        
        console.print(f"\n[cyan]🔧 Optimizing EMA parameters ({mode} mode)...[/cyan]")
        console.print(f"[dim]Short EMA range: {short_range}[/dim]")
        console.print(f"[dim]Long EMA range: {long_range}[/dim]")
        
        total_combinations = len(short_range) * len(long_range)
        console.print(f"[dim]Testing {total_combinations} combinations...[/dim]\n")
        
        self.results = []
        
        for short in track(short_range, description="Testing EMA parameters..."):
            for long in long_range:
                if short >= long:  # Skip invalid combinations
                    continue
                
                result = self.simulate_with_params(short, long, mode)
                self.results.append(result)
        
        # Sort by score
        self.results = sorted(self.results, key=lambda x: x['score'], reverse=True)
        
        console.print(f"[green]✅ Optimization complete![/green]\n")
        
        return self.results
    
    def print_results(self, top_n: int = 10):
        """Print optimization results in a beautiful table"""
        
        current_config = {
            'ema_short': config.EMA_SHORT,
            'ema_long': config.EMA_LONG
        }
        
        console.print("┌────────────────────────────────────────────────────────────┐")
        console.print("│  [bold cyan]EMA OPTIMIZATION RESULTS[/bold cyan]                                  │")
        console.print(f"│  Current Config: EMA({current_config['ema_short']}/{current_config['ema_long']})                                │")
        console.print(f"│  Trades Analyzed: {len(self.trades_df)}                                      │")
        console.print("└────────────────────────────────────────────────────────────┘\n")
        
        console.print(f"[bold]Top {top_n} Configurations (ranked by composite score):[/bold]\n")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Rank", style="dim", width=6)
        table.add_column("EMA(S/L)", justify="center")
        table.add_column("Win Rate", justify="right")
        table.add_column("P.Factor", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Whipsaw", justify="right")
        table.add_column("Lag", justify="right")
        table.add_column("Score", justify="right")
        
        for i, result in enumerate(self.results[:top_n], 1):
            is_current = (
                result['ema_short'] == current_config['ema_short'] and
                result['ema_long'] == current_config['ema_long']
            )
            
            marker = " [CURRENT]" if is_current else ""
            rank_style = "bold green" if i == 1 else "dim"
            
            table.add_row(
                f"{i}",
                f"EMA({result['ema_short']}/{result['ema_long']}){marker}",
                f"{result['win_rate']:.1f}%",
                f"{result['profit_factor']:.2f}",
                f"{result['avg_duration']:.0f} min",
                f"{result['whipsaw_rate']:.0f}%",
                f"{result['avg_lag']:.0f} min",
                f"[{rank_style}]{result['score']:.0f}/100[/{rank_style}]"
            )
        
        console.print(table)
        console.print()
        
        # Print insights
        if len(self.results) > 0:
            best = self.results[0]
            current_result = None
            
            for r in self.results:
                if (r['ema_short'] == current_config['ema_short'] and
                    r['ema_long'] == current_config['ema_long']):
                    current_result = r
                    break
            
            console.print("[bold]INSIGHTS:[/bold]")
            
            # Analyze fast vs slow
            fast_emas = [r for r in self.results if r['ema_short'] <= 10]
            slow_emas = [r for r in self.results if r['ema_short'] >= 15]
            
            if fast_emas:
                avg_fast_whipsaw = np.mean([r['whipsaw_rate'] for r in fast_emas if r['trades'] > 0])
                console.print(f"• Shorter EMAs (≤10) avg whipsaw rate: {avg_fast_whipsaw:.1f}%")
            
            if slow_emas:
                avg_slow_lag = np.mean([r['avg_lag'] for r in slow_emas if r['trades'] > 0])
                console.print(f"• Longer EMAs (≥15) avg lag: {avg_slow_lag:.1f} minutes")
            
            console.print(f"• EMA({best['ema_short']}/{best['ema_long']}) = Goldilocks zone (fast + low whipsaws)")
            
            # Recommendations by trading style
            scalping = [r for r in self.results if r['avg_duration'] < 40]
            swing = [r for r in self.results if r['avg_duration'] > 60]
            
            if scalping:
                best_scalp = max(scalping, key=lambda x: x['score'])
                console.print(f"• Best for scalping: EMA({best_scalp['ema_short']}/{best_scalp['ema_long']}) - quick entries/exits")
            
            if swing:
                best_swing = max(swing, key=lambda x: x['score'])
                console.print(f"• Best for swing trades: EMA({best_swing['ema_short']}/{best_swing['ema_long']}) - longer holds")
            
            console.print()
            
            # Recommendation
            if current_result and best['score'] > current_result['score'] + 5:
                console.print("[bold green]RECOMMENDATION:[/bold green]")
                console.print(f"⭐ Switch to EMA({best['ema_short']}/{best['ema_long']}) for balanced performance")
                
                wr_improvement = best['win_rate'] - current_result['win_rate']
                whipsaw_improvement = current_result['whipsaw_rate'] - best['whipsaw_rate']
                
                console.print(f"   Expected improvement: +{wr_improvement:.1f}% win rate, -{whipsaw_improvement:.0f}% whipsaws")
                console.print(f"   Apply to config.py:")
                console.print(f"   [cyan]EMA_SHORT = {best['ema_short']}[/cyan]")
                console.print(f"   [cyan]EMA_LONG = {best['ema_long']}[/cyan]")
            else:
                console.print("[bold yellow]RECOMMENDATION:[/bold yellow]")
                console.print(f"✅ Current EMA({current_config['ema_short']}/{current_config['ema_long']}) is already optimal or near-optimal")
            
            console.print()
    
    def export_results(self, filename: str):
        """Export results to CSV"""
        df = pd.DataFrame(self.results)
        df.to_csv(filename, index=False)
        console.print(f"[green]✅ Results exported to {filename}[/green]")


def main():
    parser = argparse.ArgumentParser(description="EMA Parameter Optimization")
    parser.add_argument('--fast', action='store_true', help='Test fast EMA combinations')
    parser.add_argument('--slow', action='store_true', help='Test slow EMA combinations')
    parser.add_argument('--scalping', action='store_true', help='Optimize for quick trades')
    parser.add_argument('--swing', action='store_true', help='Optimize for longer holds')
    parser.add_argument('--top', type=int, default=10, help='Show top N results')
    parser.add_argument('--export', type=str, help='Export results to CSV')
    
    args = parser.parse_args()
    
    # Determine mode
    mode = "balanced"
    if args.fast:
        mode = "fast"
    elif args.slow:
        mode = "slow"
    elif args.scalping:
        mode = "scalping"
    elif args.swing:
        mode = "swing"
    
    # Run optimization
    optimizer = EMAOptimizer()
    optimizer.load_trades()
    optimizer.optimize(mode=mode)
    optimizer.print_results(top_n=args.top)
    
    if args.export:
        optimizer.export_results(args.export)


if __name__ == "__main__":
    main()
