#!/usr/bin/env python3
"""
RSI Parameter Optimization Suite
Find optimal RSI_OVERSOLD and RSI_OVERBOUGHT thresholds
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


class RSIOptimizer:
    """Optimize RSI parameters based on historical trade performance"""
    
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
        
        console.print(f"[green]✅ Loaded {len(self.trades_df)} trades[/green]")
        return self.trades_df
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def fetch_historical_data(self, symbol: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
        """Fetch historical price data for a trade period"""
        try:
            # Add buffer for RSI calculation (need 50+ candles)
            buffered_start = start_time - timedelta(hours=2)
            
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
    
    def simulate_with_params(self, rsi_oversold: int, rsi_overbought: int, 
                            confidence_filter: Tuple[int, int] = None) -> Dict:
        """Simulate trades with given RSI parameters"""
        
        trades = self.trades_df.copy()
        
        # Apply confidence filter if specified
        if confidence_filter:
            trades = trades[
                (trades['confidence'] >= confidence_filter[0]) & 
                (trades['confidence'] <= confidence_filter[1])
            ]
        
        if len(trades) == 0:
            return {
                'rsi_oversold': rsi_oversold,
                'rsi_overbought': rsi_overbought,
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'score': 0
            }
        
        # For each trade, check if RSI would have signaled entry
        valid_trades = []
        
        for _, trade in trades.iterrows():
            # Fetch historical data
            hist_data = self.fetch_historical_data(
                trade['symbol'],
                trade['entry_timestamp'],
                trade['exit_timestamp']
            )
            
            if hist_data.empty:
                continue
            
            # Calculate RSI
            rsi = self.calculate_rsi(hist_data['close'])
            
            # Find RSI at entry time
            entry_idx = hist_data[hist_data['timestamp'] >= trade['entry_timestamp']].index
            if len(entry_idx) == 0:
                continue
            
            entry_rsi = rsi.iloc[entry_idx[0]]
            
            if pd.isna(entry_rsi):
                continue
            
            # Check if RSI signal matches trade direction
            if trade['side'] == 'LONG' and entry_rsi <= rsi_oversold:
                valid_trades.append(trade)
            elif trade['side'] == 'SHORT' and entry_rsi >= rsi_overbought:
                valid_trades.append(trade)
        
        if len(valid_trades) == 0:
            return {
                'rsi_oversold': rsi_oversold,
                'rsi_overbought': rsi_overbought,
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'score': 0
            }
        
        # Calculate metrics
        valid_df = pd.DataFrame(valid_trades)
        wins = len(valid_df[valid_df['pnl'] > 0])
        losses = len(valid_df[valid_df['pnl'] <= 0])
        win_rate = (wins / len(valid_df)) * 100 if len(valid_df) > 0 else 0
        
        total_wins = valid_df[valid_df['pnl'] > 0]['pnl'].sum()
        total_losses = abs(valid_df[valid_df['pnl'] <= 0]['pnl'].sum())
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        total_pnl = valid_df['pnl'].sum()
        avg_pnl = valid_df['pnl'].mean()
        
        # Calculate drawdown
        cumulative = valid_df['pnl'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max)
        max_drawdown = abs(drawdown.min()) / config.STARTING_CAPITAL * 100 if len(drawdown) > 0 else 0
        
        # Calculate Sharpe ratio (simplified)
        returns = valid_df['pnl'] / config.STARTING_CAPITAL
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        
        # Composite score
        score = (
            win_rate * 0.30 +
            min(profit_factor * 10, 100) * 0.25 +
            min(sharpe_ratio * 20, 100) * 0.25 +
            max(0, 100 - max_drawdown * 5) * 0.20
        )
        
        return {
            'rsi_oversold': rsi_oversold,
            'rsi_overbought': rsi_overbought,
            'trades': len(valid_df),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'score': score
        }
    
    def optimize(self, oversold_range: List[int] = None, 
                 overbought_range: List[int] = None,
                 confidence_filter: Tuple[int, int] = None,
                 symbol: str = None) -> List[Dict]:
        """Run optimization across parameter space"""
        
        if oversold_range is None:
            oversold_range = [20, 25, 30, 35, 40]
        if overbought_range is None:
            overbought_range = [60, 65, 70, 75, 80]
        
        console.print(f"\n[cyan]🔧 Optimizing RSI parameters...[/cyan]")
        console.print(f"[dim]Oversold range: {oversold_range}[/dim]")
        console.print(f"[dim]Overbought range: {overbought_range}[/dim]")
        
        if symbol:
            console.print(f"[dim]Symbol filter: {symbol}[/dim]")
            self.trades_df = self.trades_df[self.trades_df['symbol'] == symbol]
        
        if confidence_filter:
            console.print(f"[dim]Confidence filter: {confidence_filter[0]}-{confidence_filter[1]}%[/dim]")
        
        total_combinations = len(oversold_range) * len(overbought_range)
        console.print(f"[dim]Testing {total_combinations} combinations...[/dim]\n")
        
        self.results = []
        
        for os in track(oversold_range, description="Testing RSI parameters..."):
            for ob in overbought_range:
                if os >= ob:  # Skip invalid combinations
                    continue
                
                result = self.simulate_with_params(os, ob, confidence_filter)
                self.results.append(result)
        
        # Sort by score
        self.results = sorted(self.results, key=lambda x: x['score'], reverse=True)
        
        console.print(f"[green]✅ Optimization complete![/green]\n")
        
        return self.results
    
    def print_results(self, top_n: int = 10):
        """Print optimization results in a beautiful table"""
        
        current_config = {
            'rsi_oversold': config.RSI_OVERSOLD,
            'rsi_overbought': config.RSI_OVERBOUGHT
        }
        
        console.print("┌────────────────────────────────────────────────────────────┐")
        console.print("│  [bold cyan]RSI OPTIMIZATION RESULTS[/bold cyan]                                  │")
        console.print(f"│  Current Config: RSI({current_config['rsi_oversold']}/{current_config['rsi_overbought']})                                │")
        console.print(f"│  Trades Analyzed: {len(self.trades_df)}                                      │")
        console.print("└────────────────────────────────────────────────────────────┘\n")
        
        console.print(f"[bold]Top {top_n} Configurations (ranked by composite score):[/bold]\n")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Rank", style="dim", width=6)
        table.add_column("RSI(OS/OB)", justify="center")
        table.add_column("Win Rate", justify="right")
        table.add_column("P.Factor", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Drawdown", justify="right")
        table.add_column("Signals", justify="right")
        table.add_column("Score", justify="right")
        
        for i, result in enumerate(self.results[:top_n], 1):
            is_current = (
                result['rsi_oversold'] == current_config['rsi_oversold'] and
                result['rsi_overbought'] == current_config['rsi_overbought']
            )
            
            marker = " [CURRENT]" if is_current else ""
            rank_style = "bold green" if i == 1 else "dim"
            
            table.add_row(
                f"{i}",
                f"RSI({result['rsi_oversold']}/{result['rsi_overbought']}){marker}",
                f"{result['win_rate']:.1f}%",
                f"{result['profit_factor']:.2f}",
                f"R{result['total_pnl']:.0f}",
                f"{result['max_drawdown']:.1f}%",
                f"{result['trades']}",
                f"[{rank_style}]{result['score']:.0f}/100[/{rank_style}]"
            )
        
        console.print(table)
        console.print()
        
        # Print insights
        if len(self.results) > 0:
            best = self.results[0]
            current_result = None
            
            for r in self.results:
                if (r['rsi_oversold'] == current_config['rsi_oversold'] and
                    r['rsi_overbought'] == current_config['rsi_overbought']):
                    current_result = r
                    break
            
            console.print("[bold]INSIGHTS:[/bold]")
            
            # Analyze aggressive vs conservative
            aggressive = [r for r in self.results if r['rsi_oversold'] <= 25]
            conservative = [r for r in self.results if r['rsi_oversold'] >= 35]
            
            if aggressive:
                avg_aggressive_wr = np.mean([r['win_rate'] for r in aggressive])
                console.print(f"• More aggressive (OS ≤ 25) avg win rate: {avg_aggressive_wr:.1f}%")
            
            if conservative:
                avg_conservative_wr = np.mean([r['win_rate'] for r in conservative])
                console.print(f"• Conservative (OS ≥ 35) avg win rate: {avg_conservative_wr:.1f}%")
            
            console.print(f"• Sweet spot appears to be RSI({best['rsi_oversold']}/{best['rsi_overbought']})")
            console.print()
            
            # Recommendation
            if current_result and best['score'] > current_result['score'] + 5:
                console.print("[bold green]RECOMMENDATION:[/bold green]")
                console.print(f"⭐ Switch to RSI({best['rsi_oversold']}/{best['rsi_overbought']})")
                
                wr_improvement = best['win_rate'] - current_result['win_rate']
                pnl_improvement = best['total_pnl'] - current_result['total_pnl']
                
                console.print(f"   Expected improvement: +{wr_improvement:.1f}% win rate, +R{pnl_improvement:.0f} profit")
                console.print(f"   Apply to config.py:")
                console.print(f"   [cyan]RSI_OVERSOLD = {best['rsi_oversold']}[/cyan]")
                console.print(f"   [cyan]RSI_OVERBOUGHT = {best['rsi_overbought']}[/cyan]")
            else:
                console.print("[bold yellow]RECOMMENDATION:[/bold yellow]")
                console.print(f"✅ Current RSI({current_config['rsi_oversold']}/{current_config['rsi_overbought']}) is already optimal or near-optimal")
            
            console.print()
    
    def export_results(self, filename: str):
        """Export results to CSV"""
        df = pd.DataFrame(self.results)
        df.to_csv(filename, index=False)
        console.print(f"[green]✅ Results exported to {filename}[/green]")


def main():
    parser = argparse.ArgumentParser(description="RSI Parameter Optimization")
    parser.add_argument('--range', type=str, help='Custom range: "15-45 55-95"')
    parser.add_argument('--top', type=int, default=10, help='Show top N results')
    parser.add_argument('--confidence', type=str, help='Confidence filter: "40-45"')
    parser.add_argument('--symbol', type=str, help='Optimize for specific symbol')
    parser.add_argument('--export', type=str, help='Export results to CSV')
    
    args = parser.parse_args()
    
    # Parse custom ranges
    oversold_range = None
    overbought_range = None
    
    if args.range:
        parts = args.range.split()
        if len(parts) == 2:
            os_start, os_end = map(int, parts[0].split('-'))
            ob_start, ob_end = map(int, parts[1].split('-'))
            oversold_range = list(range(os_start, os_end + 1, 5))
            overbought_range = list(range(ob_start, ob_end + 1, 5))
    
    # Parse confidence filter
    confidence_filter = None
    if args.confidence:
        conf_start, conf_end = map(int, args.confidence.split('-'))
        confidence_filter = (conf_start, conf_end)
    
    # Run optimization
    optimizer = RSIOptimizer()
    optimizer.load_trades()
    optimizer.optimize(
        oversold_range=oversold_range,
        overbought_range=overbought_range,
        confidence_filter=confidence_filter,
        symbol=args.symbol
    )
    optimizer.print_results(top_n=args.top)
    
    if args.export:
        optimizer.export_results(args.export)


if __name__ == "__main__":
    main()
