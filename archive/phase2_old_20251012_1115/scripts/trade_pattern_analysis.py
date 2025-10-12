#!/usr/bin/env python3
"""
Trade Pattern Analysis - Analyze existing trades to find optimal parameters
Works with backfilled trades to find patterns and recommendations
"""

import sqlite3
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys

console = Console()

def load_trades():
    """Load all completed trades from database"""
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        query = """
        SELECT 
            id, symbol, side, entry_price, exit_price,
            pnl, duration_seconds, quality, confidence,
            entry_timestamp, exit_timestamp
        FROM trades
        WHERE exit_timestamp IS NOT NULL
        ORDER BY entry_timestamp
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Calculate win/loss
        df['is_win'] = df['pnl'] > 0
        df['is_loss'] = df['pnl'] < 0
        df['is_breakeven'] = df['pnl'] == 0
        
        return df
    except Exception as e:
        console.print(f"[red]Error loading trades: {e}[/red]")
        return None

def analyze_by_confidence(df):
    """Analyze performance by confidence levels"""
    console.print("\n[bold cyan]═══ CONFIDENCE LEVEL ANALYSIS ═══[/bold cyan]\n")
    
    # Group by confidence ranges
    bins = [0, 20, 30, 40, 50, 60, 70, 100]
    labels = ['0-20%', '20-30%', '30-40%', '40-50%', '50-60%', '60-70%', '70-100%']
    df['confidence_range'] = pd.cut(df['confidence'], bins=bins, labels=labels, include_lowest=True)
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Confidence", style="dim", width=12)
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Avg P&L", justify="right")
    table.add_column("Total P&L", justify="right")
    table.add_column("Best Range", justify="center")
    
    results = []
    for conf_range in labels:
        subset = df[df['confidence_range'] == conf_range]
        if len(subset) > 0:
            win_rate = (subset['is_win'].sum() / len(subset) * 100)
            avg_pnl = subset['pnl'].mean()
            total_pnl = subset['pnl'].sum()
            results.append({
                'range': conf_range,
                'count': len(subset),
                'win_rate': win_rate,
                'avg_pnl': avg_pnl,
                'total_pnl': total_pnl
            })
    
    # Find best range
    if results:
        best = max(results, key=lambda x: x['win_rate'])
        
        for r in results:
            is_best = "⭐" if r['range'] == best['range'] else ""
            table.add_row(
                r['range'],
                str(r['count']),
                f"{r['win_rate']:.1f}%",
                f"R{r['avg_pnl']:.0f}",
                f"R{r['total_pnl']:.0f}",
                is_best
            )
        
        console.print(table)
        console.print(f"\n[green]✓ Best performing range: {best['range']} ({best['win_rate']:.1f}% win rate)[/green]")

def analyze_by_symbol(df):
    """Analyze performance by trading symbol"""
    console.print("\n[bold cyan]═══ SYMBOL PERFORMANCE ANALYSIS ═══[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Symbol", style="dim", width=10)
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Avg P&L", justify="right")
    table.add_column("Total P&L", justify="right")
    table.add_column("Best", justify="center")
    
    results = []
    for symbol in df['symbol'].unique():
        subset = df[df['symbol'] == symbol]
        win_rate = (subset['is_win'].sum() / len(subset) * 100)
        avg_pnl = subset['pnl'].mean()
        total_pnl = subset['pnl'].sum()
        results.append({
            'symbol': symbol,
            'count': len(subset),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'total_pnl': total_pnl
        })
    
    # Find best symbol
    best = max(results, key=lambda x: x['win_rate'])
    
    for r in sorted(results, key=lambda x: x['win_rate'], reverse=True):
        is_best = "⭐" if r['symbol'] == best['symbol'] else ""
        table.add_row(
            r['symbol'],
            str(r['count']),
            f"{r['win_rate']:.1f}%",
            f"R{r['avg_pnl']:.0f}",
            f"R{r['total_pnl']:.0f}",
            is_best
        )
    
    console.print(table)
    console.print(f"\n[green]✓ Best performing symbol: {best['symbol']} ({best['win_rate']:.1f}% win rate)[/green]")

def analyze_by_side(df):
    """Analyze LONG vs SHORT performance"""
    console.print("\n[bold cyan]═══ LONG vs SHORT ANALYSIS ═══[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Side", style="dim", width=10)
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Avg P&L", justify="right")
    table.add_column("Total P&L", justify="right")
    table.add_column("Better", justify="center")
    
    for side in ['LONG', 'SHORT']:
        subset = df[df['side'] == side]
        if len(subset) > 0:
            win_rate = (subset['is_win'].sum() / len(subset) * 100)
            avg_pnl = subset['pnl'].mean()
            total_pnl = subset['pnl'].sum()
            
            table.add_row(
                side,
                str(len(subset)),
                f"{win_rate:.1f}%",
                f"R{avg_pnl:.0f}",
                f"R{total_pnl:.0f}",
                "⭐" if avg_pnl > 0 and len(subset) > 10 else ""
            )
    
    console.print(table)
    
    # Check for imbalance
    long_count = len(df[df['side'] == 'LONG'])
    short_count = len(df[df['side'] == 'SHORT'])
    
    if long_count > short_count * 5:
        console.print(f"\n[yellow]⚠️  Imbalance detected: {long_count} LONGs vs {short_count} SHORTs[/yellow]")
        console.print("[yellow]   Consider adjusting RSI thresholds to balance trades[/yellow]")

def analyze_trade_duration(df):
    """Analyze optimal trade duration"""
    console.print("\n[bold cyan]═══ TRADE DURATION ANALYSIS ═══[/bold cyan]\n")
    
    # Convert seconds to minutes
    df['duration_minutes'] = df['duration_seconds'] / 60
    
    # Group by duration ranges
    bins = [0, 5, 15, 30, 60, 120, 300, float('inf')]
    labels = ['0-5m', '5-15m', '15-30m', '30-60m', '1-2h', '2-5h', '5h+']
    df['duration_range'] = pd.cut(df['duration_minutes'], bins=bins, labels=labels)
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Duration", style="dim", width=10)
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Avg P&L", justify="right")
    table.add_column("Best", justify="center")
    
    results = []
    for dur_range in labels:
        subset = df[df['duration_range'] == dur_range]
        if len(subset) > 0:
            win_rate = (subset['is_win'].sum() / len(subset) * 100)
            avg_pnl = subset['pnl'].mean()
            results.append({
                'range': dur_range,
                'count': len(subset),
                'win_rate': win_rate,
                'avg_pnl': avg_pnl
            })
    
    # Find best range
    if results:
        best = max(results, key=lambda x: x['win_rate'])
        
        for r in results:
            is_best = "⭐" if r['range'] == best['range'] else ""
            table.add_row(
                r['range'],
                str(r['count']),
                f"{r['win_rate']:.1f}%",
                f"R{r['avg_pnl']:.0f}",
                is_best
            )
        
        console.print(table)
        console.print(f"\n[green]✓ Best performing duration: {best['range']} ({best['win_rate']:.1f}% win rate)[/green]")

def generate_recommendations(df):
    """Generate actionable recommendations based on analysis"""
    console.print("\n[bold cyan]═══ RECOMMENDATIONS ═══[/bold cyan]\n")
    
    recommendations = []
    
    # 1. Confidence filtering
    for conf_min in [30, 35, 40, 45]:
        subset = df[df['confidence'] >= conf_min]
        if len(subset) >= 50:  # Minimum sample size
            win_rate = (subset['is_win'].sum() / len(subset) * 100)
            if win_rate > 60:
                recommendations.append({
                    'type': '🎯 Confidence Filter',
                    'action': f'Set MIN_CONFIDENCE = {conf_min}',
                    'impact': f'{win_rate:.1f}% win rate on {len(subset)} trades',
                    'priority': 'HIGH'
                })
                break
    
    # 2. Symbol focus
    symbol_perf = []
    for symbol in df['symbol'].unique():
        subset = df[df['symbol'] == symbol]
        if len(subset) >= 20:
            win_rate = (subset['is_win'].sum() / len(subset) * 100)
            symbol_perf.append({'symbol': symbol, 'win_rate': win_rate, 'count': len(subset)})
    
    if symbol_perf:
        best_symbols = [s for s in symbol_perf if s['win_rate'] > 62]
        if len(best_symbols) > 0 and len(best_symbols) < len(symbol_perf):
            symbols_list = [s['symbol'] for s in best_symbols]
            recommendations.append({
                'type': '🎲 Symbol Selection',
                'action': f'Focus on: {", ".join(symbols_list)}',
                'impact': f'Best performing symbols (>62% win rate)',
                'priority': 'MEDIUM'
            })
    
    # 3. RSI adjustment based on LONG/SHORT balance
    long_count = len(df[df['side'] == 'LONG'])
    short_count = len(df[df['side'] == 'SHORT'])
    
    if long_count > short_count * 5:
        recommendations.append({
            'type': '⚖️  Balance Trades',
            'action': 'Adjust RSI: OVERSOLD=35→30, OVERBOUGHT=65→70',
            'impact': f'More conservative to balance {long_count}L/{short_count}S',
            'priority': 'LOW'
        })
    
    # 4. Current performance assessment
    overall_win_rate = (df['is_win'].sum() / len(df) * 100)
    if overall_win_rate > 58:
        recommendations.append({
            'type': '✅ Status',
            'action': 'Current parameters are performing well',
            'impact': f'{overall_win_rate:.1f}% win rate is solid',
            'priority': 'INFO'
        })
    
    # Display recommendations
    for rec in recommendations:
        color = {
            'HIGH': 'green',
            'MEDIUM': 'yellow',
            'LOW': 'blue',
            'INFO': 'cyan'
        }.get(rec['priority'], 'white')
        
        console.print(Panel(
            f"[bold]{rec['action']}[/bold]\n\n"
            f"Impact: {rec['impact']}\n"
            f"Priority: [{color}]{rec['priority']}[/{color}]",
            title=rec['type'],
            border_style=color
        ))

def main():
    console.print("[bold magenta]" + "="*60 + "[/bold magenta]")
    console.print("[bold magenta]     TRADE PATTERN ANALYSIS - Ozzy Simple Bot[/bold magenta]")
    console.print("[bold magenta]" + "="*60 + "[/bold magenta]")
    
    # Load trades
    console.print("\n[yellow]Loading trades from database...[/yellow]")
    df = load_trades()
    
    if df is None or len(df) == 0:
        console.print("[red]No trades found in database![/red]")
        sys.exit(1)
    
    console.print(f"[green]✓ Loaded {len(df)} completed trades[/green]")
    
    # Overall stats
    win_rate = (df['is_win'].sum() / len(df) * 100)
    total_pnl = df['pnl'].sum()
    avg_pnl = df['pnl'].mean()
    
    console.print(Panel(
        f"Total Trades: {len(df)}\n"
        f"Win Rate: {win_rate:.1f}%\n"
        f"Total P&L: R{total_pnl:,.0f}\n"
        f"Avg P&L per Trade: R{avg_pnl:.0f}",
        title="📊 Overall Performance",
        border_style="cyan"
    ))
    
    # Run analyses
    analyze_by_confidence(df)
    analyze_by_symbol(df)
    analyze_by_side(df)
    analyze_trade_duration(df)
    
    # Generate recommendations
    generate_recommendations(df)
    
    console.print("\n[bold green]Analysis complete![/bold green]")
    console.print("[dim]Tip: Use these insights to adjust config.py parameters[/dim]\n")

if __name__ == "__main__":
    main()
