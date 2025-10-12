#!/usr/bin/env python3
"""
Track fresh test progress and compare to baseline
Monitors optimized config performance vs original 427 trades
"""
import sqlite3
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys

console = Console()

# Baseline (from 427 trades with original config)
BASELINE = {
    'trades': 427,
    'win_rate': 60.0,
    'avg_pnl': 32.44,
    'total_pnl': 13850,
    'long_trades': 397,
    'short_trades': 30,
    'long_short_ratio': 13.2,
    'best_confidence': '30-40%',
    'best_symbol': 'SOLUSDT'
}

def get_test_stats(days=7):
    """Get stats for trades from the last N days"""
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        cursor = conn.cursor()
        
        # Get trades from last N days
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                AVG(pnl) as avg_pnl,
                SUM(pnl) as total_pnl,
                MIN(pnl) as worst_trade,
                MAX(pnl) as best_trade,
                SUM(CASE WHEN side = 'LONG' THEN 1 ELSE 0 END) as long_trades,
                SUM(CASE WHEN side = 'SHORT' THEN 1 ELSE 0 END) as short_trades,
                AVG(confidence) as avg_confidence
            FROM trades
            WHERE entry_timestamp >= ?
            AND exit_timestamp IS NOT NULL
        """, (cutoff_date,))
        
        result = cursor.fetchone()
        
        if result[0] == 0:
            conn.close()
            return None
        
        # Get symbol breakdown
        cursor.execute("""
            SELECT 
                symbol,
                COUNT(*) as count,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(pnl) as avg_pnl
            FROM trades
            WHERE entry_timestamp >= ?
            AND exit_timestamp IS NOT NULL
            GROUP BY symbol
            ORDER BY count DESC
        """, (cutoff_date,))
        
        symbol_stats = cursor.fetchall()
        conn.close()
        
        total = result[0]
        wins = result[1]
        long_trades = result[8]
        short_trades = result[9]
        
        return {
            'total': total,
            'wins': wins,
            'losses': result[2],
            'breakeven': result[3],
            'win_rate': (wins / total * 100) if total > 0 else 0,
            'avg_pnl': result[4] if result[4] else 0,
            'total_pnl': result[5] if result[5] else 0,
            'worst_trade': result[6] if result[6] else 0,
            'best_trade': result[7] if result[7] else 0,
            'long_trades': long_trades,
            'short_trades': short_trades,
            'long_short_ratio': (long_trades / short_trades) if short_trades > 0 else 0,
            'avg_confidence': result[10] if result[10] else 0,
            'symbol_stats': symbol_stats
        }
    except Exception as e:
        console.print(f"[red]Error fetching test stats: {e}[/red]")
        return None

def compare_to_baseline(stats, days=7):
    """Compare test stats to baseline"""
    if not stats:
        console.print(Panel(
            "[yellow]❌ No test data yet![/yellow]\n\n"
            f"Keep your bot running for {days} days to collect data.\n"
            "Then run this script again to see the comparison.",
            title="⏳ Waiting for Test Data",
            border_style="yellow"
        ))
        return
    
    console.print(f"\n[bold cyan]{'='*70}[/bold cyan]")
    console.print(f"[bold cyan]  FRESH TEST RESULTS - Last {days} Days[/bold cyan]")
    console.print(f"[bold cyan]{'='*70}[/bold cyan]\n")
    
    # Main comparison table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="dim", width=20)
    table.add_column("Baseline\n(427 trades)", justify="right", style="yellow")
    table.add_column(f"Test\n({stats['total']} trades)", justify="right", style="green")
    table.add_column("Difference", justify="right", style="cyan")
    table.add_column("Status", justify="center")
    
    # Win Rate
    wr_diff = stats['win_rate'] - BASELINE['win_rate']
    wr_status = "✅" if wr_diff >= 2 else ("⚠️" if wr_diff >= 0 else "❌")
    table.add_row(
        "Win Rate",
        f"{BASELINE['win_rate']:.1f}%",
        f"{stats['win_rate']:.1f}%",
        f"{wr_diff:+.1f}%",
        wr_status
    )
    
    # Avg P&L per Trade
    pnl_diff = stats['avg_pnl'] - BASELINE['avg_pnl']
    pnl_status = "✅" if pnl_diff >= 5 else ("⚠️" if pnl_diff >= 0 else "❌")
    table.add_row(
        "Avg P&L per Trade",
        f"R{BASELINE['avg_pnl']:.2f}",
        f"R{stats['avg_pnl']:.2f}",
        f"R{pnl_diff:+.2f}",
        pnl_status
    )
    
    # Total P&L
    table.add_row(
        "Total P&L",
        f"R{BASELINE['total_pnl']:,.0f}",
        f"R{stats['total_pnl']:,.0f}",
        f"R{stats['total_pnl'] - BASELINE['total_pnl']:+,.0f}",
        ""
    )
    
    # LONG/SHORT Balance
    ls_ratio_diff = BASELINE['long_short_ratio'] - stats['long_short_ratio']
    ls_status = "✅" if ls_ratio_diff >= 3 else ("⚠️" if ls_ratio_diff >= 0 else "❌")
    table.add_row(
        "LONG/SHORT Ratio",
        f"{BASELINE['long_short_ratio']:.1f}:1",
        f"{stats['long_short_ratio']:.1f}:1" if stats['short_trades'] > 0 else "N/A",
        f"{ls_ratio_diff:+.1f}" if stats['short_trades'] > 0 else "N/A",
        ls_status
    )
    
    # Confidence Level
    table.add_row(
        "Avg Confidence",
        "~35%",
        f"{stats['avg_confidence']:.1f}%",
        f"{stats['avg_confidence'] - 35:+.1f}%",
        "✅" if stats['avg_confidence'] >= 30 else "⚠️"
    )
    
    console.print(table)
    
    # Symbol Performance
    if stats['symbol_stats']:
        console.print(f"\n[bold cyan]Symbol Breakdown:[/bold cyan]")
        symbol_table = Table(show_header=True, header_style="bold magenta")
        symbol_table.add_column("Symbol", style="dim")
        symbol_table.add_column("Trades", justify="right")
        symbol_table.add_column("Win Rate", justify="right")
        symbol_table.add_column("Avg P&L", justify="right")
        
        for symbol, count, wins, avg_pnl in stats['symbol_stats']:
            win_rate = (wins / count * 100) if count > 0 else 0
            symbol_table.add_row(
                symbol,
                str(count),
                f"{win_rate:.1f}%",
                f"R{avg_pnl:.2f}"
            )
        
        console.print(symbol_table)
    
    # Trade Details
    console.print(f"\n[bold cyan]Trade Details:[/bold cyan]")
    details_table = Table(show_header=True, header_style="bold magenta")
    details_table.add_column("Metric", style="dim")
    details_table.add_column("Value", justify="right")
    
    details_table.add_row("Total Trades", str(stats['total']))
    details_table.add_row("Wins", f"{stats['wins']} ({stats['win_rate']:.1f}%)")
    details_table.add_row("Losses", f"{stats['losses']}")
    details_table.add_row("Breakeven", f"{stats['breakeven']}")
    details_table.add_row("LONG Trades", f"{stats['long_trades']}")
    details_table.add_row("SHORT Trades", f"{stats['short_trades']}")
    details_table.add_row("Best Trade", f"R{stats['best_trade']:.2f}")
    details_table.add_row("Worst Trade", f"R{stats['worst_trade']:.2f}")
    
    console.print(details_table)
    
    # Final Verdict
    console.print("\n" + "="*70)
    
    improvements = 0
    if wr_diff >= 2: improvements += 1
    if pnl_diff >= 5: improvements += 1
    if ls_ratio_diff >= 3: improvements += 1
    if stats['avg_confidence'] >= 30: improvements += 1
    
    if stats['total'] < 50:
        console.print(Panel(
            f"[yellow]⏳ INSUFFICIENT DATA ({stats['total']} trades)[/yellow]\n\n"
            f"Keep running for at least 50 trades to validate.\n"
            f"Current sample size is too small for statistical significance.",
            title="📊 Status: Collecting Data",
            border_style="yellow"
        ))
    elif improvements >= 3:
        console.print(Panel(
            "[green]✅ OPTIMIZATION CONFIRMED![/green]\n\n"
            f"• Win rate improved by {wr_diff:+.1f}%\n"
            f"• Avg P&L improved by R{pnl_diff:+.2f}\n"
            f"• LONG/SHORT balance improved\n\n"
            "[bold green]RECOMMENDATION: Ready for live trading![/bold green]\n"
            "Start with small capital (R1,000-R2,000) and scale up gradually.",
            title="🎉 Test Result: SUCCESS",
            border_style="green"
        ))
    elif improvements >= 2:
        console.print(Panel(
            "[yellow]⚠️ PARTIAL IMPROVEMENT[/yellow]\n\n"
            f"• Win rate: {wr_diff:+.1f}% change\n"
            f"• Avg P&L: R{pnl_diff:+.2f} change\n\n"
            "[bold yellow]RECOMMENDATION: Run longer (2 weeks) to confirm[/bold yellow]\n"
            "Results are promising but need more data for validation.",
            title="📊 Test Result: PROMISING",
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            "[red]❌ NO IMPROVEMENT DETECTED[/red]\n\n"
            f"• Win rate: {wr_diff:+.1f}% change\n"
            f"• Avg P&L: R{pnl_diff:+.2f} change\n\n"
            "[bold red]RECOMMENDATION: Review configuration[/bold red]\n"
            "Consider reverting to baseline settings or adjusting parameters.",
            title="⚠️ Test Result: NEEDS REVIEW",
            border_style="red"
        ))
    
    console.print("="*70 + "\n")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Track optimized config test progress')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze (default: 7)')
    args = parser.parse_args()
    
    console.print("[bold magenta]" + "="*70 + "[/bold magenta]")
    console.print("[bold magenta]     OPTIMIZED CONFIG TEST TRACKER[/bold magenta]")
    console.print("[bold magenta]" + "="*70 + "[/bold magenta]")
    
    stats = get_test_stats(days=args.days)
    compare_to_baseline(stats, days=args.days)
    
    if stats and stats['total'] > 0:
        console.print("\n[dim]Tip: Run this script daily to monitor progress[/dim]")
        console.print(f"[dim]Usage: python scripts/test_tracker.py --days {args.days}[/dim]\n")

if __name__ == '__main__':
    main()
