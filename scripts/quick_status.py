#!/usr/bin/env python3
"""Quick status check for fresh test"""
import sqlite3
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel

console = Console()

def quick_status():
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        cursor = conn.cursor()
        
        # Get trades from last 24 hours
        yesterday = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(pnl) as total_pnl
            FROM trades
            WHERE entry_timestamp >= ?
        """, (yesterday,))
        
        today = cursor.fetchone()
        
        # Get all-time test stats (new trades only)
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(pnl) as total_pnl
            FROM trades
            WHERE entry_reason NOT LIKE 'BASELINE_%'
            OR entry_reason IS NULL
        """)
        
        test = cursor.fetchone()
        conn.close()
        
        today_trades = today[0] if today[0] else 0
        today_wins = today[1] if today[1] else 0
        today_pnl = today[2] if today[2] else 0
        today_wr = (today_wins / today_trades * 100) if today_trades > 0 else 0
        
        test_trades = test[0] if test[0] else 0
        test_wins = test[1] if test[1] else 0
        test_pnl = test[2] if test[2] else 0
        test_wr = (test_wins / test_trades * 100) if test_trades > 0 else 0
        
        # Status message
        if test_trades == 0:
            status = "[yellow]⏳ No test trades yet - Start your bot![/yellow]"
            progress = 0
        elif test_trades < 50:
            status = f"[cyan]📊 Collecting data: {test_trades}/50 trades[/cyan]"
            progress = (test_trades / 50) * 100
        else:
            status = f"[green]✅ Ready for analysis: {test_trades} trades[/green]"
            progress = 100
        
        # Progress bar
        bar_width = 30
        filled = int(bar_width * progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        console.print(Panel(
            f"{status}\n\n"
            f"Progress: [{bar}] {progress:.0f}%\n\n"
            f"[bold]Last 24 Hours:[/bold]\n"
            f"  Trades: {today_trades} | Win Rate: {today_wr:.1f}% | P&L: R{today_pnl:.0f}\n\n"
            f"[bold]Total Test Period:[/bold]\n"
            f"  Trades: {test_trades} | Win Rate: {test_wr:.1f}% | P&L: R{test_pnl:.0f}\n\n"
            f"[dim]Target: 60% win rate, R32+ avg per trade[/dim]",
            title="🎯 Fresh Test Status",
            border_style="cyan"
        ))
        
        if test_trades >= 50:
            console.print("\n[green]✅ Ready for full analysis![/green]")
            console.print("[green]Run: python scripts/test_tracker.py[/green]\n")
        elif test_trades > 0:
            console.print(f"\n[yellow]Keep running to reach 50 trades ({50 - test_trades} more needed)[/yellow]\n")
        else:
            console.print("\n[yellow]Start your bot to begin collecting data[/yellow]")
            console.print("[yellow]Command: python main.py[/yellow]\n")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

if __name__ == '__main__':
    quick_status()
