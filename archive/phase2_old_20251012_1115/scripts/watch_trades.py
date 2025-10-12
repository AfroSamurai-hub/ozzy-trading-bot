#!/usr/bin/env python3
"""
Real-time trade monitoring script
Watches for new trades and displays them as they happen
"""

import sqlite3
import time
import os
from datetime import datetime
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

console = Console()

def get_latest_trades(limit=10):
    """Get the most recent trades from database"""
    conn = sqlite3.connect('ozzy_simple.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT entry_timestamp, exit_timestamp, symbol, side, 
               entry_price, exit_price, pnl, position_size, duration_seconds
        FROM trades 
        WHERE pnl IS NOT NULL
        ORDER BY entry_timestamp DESC 
        LIMIT ?
    ''', (limit,))
    
    trades = cursor.fetchall()
    conn.close()
    return trades

def create_trade_table():
    """Create a rich table with recent trades"""
    table = Table(title="🔥 LIVE TRADE MONITOR", show_header=True, header_style="bold magenta")
    table.add_column("Time", style="cyan", width=8)
    table.add_column("Symbol", style="white", width=10)
    table.add_column("Side", style="yellow", width=6)
    table.add_column("Entry", style="green", width=8)
    table.add_column("Exit", style="red", width=8)
    table.add_column("P&L", style="bold", width=10)
    table.add_column("Duration", style="blue", width=8)
    
    trades = get_latest_trades(15)
    
    for trade in trades:
        entry_time, exit_time, symbol, side, entry_price, exit_price, pnl, size, duration = trade
        
        # Format time (just HH:MM)
        if entry_time:
            time_str = entry_time[-8:-3]  # Extract HH:MM from timestamp
        else:
            time_str = "N/A"
            
        # Format P&L with color
        if pnl > 0:
            pnl_str = f"[green]+R{pnl:.2f}[/green]"
            pnl_icon = "✅"
        else:
            pnl_str = f"[red]R{pnl:.2f}[/red]"
            pnl_icon = "❌"
            
        # Format duration
        if duration:
            if duration < 60:
                dur_str = f"{duration}s"
            elif duration < 3600:
                dur_str = f"{duration//60}m"
            else:
                dur_str = f"{duration//3600}h"
        else:
            dur_str = "N/A"
            
        # Side with icon
        side_icon = "🟢" if side == "LONG" else "🔴"
        side_str = f"{side_icon} {side}"
        
        table.add_row(
            time_str,
            symbol,
            side_str,
            f"R{entry_price:.2f}" if entry_price else "N/A",
            f"R{exit_price:.2f}" if exit_price else "N/A",
            f"{pnl_icon} {pnl_str}",
            dur_str
        )
    
    return table

def get_trading_stats():
    """Get current trading statistics"""
    conn = sqlite3.connect('ozzy_simple.db')
    cursor = conn.cursor()
    
    # Get total trades and win rate
    cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl IS NOT NULL')
    total_trades = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl > 0')
    winning_trades = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(pnl) FROM trades WHERE pnl IS NOT NULL')
    total_pnl = cursor.fetchone()[0] or 0
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Get trades in last hour
    cursor.execute('''
        SELECT COUNT(*) FROM trades 
        WHERE entry_timestamp > datetime('now', '-1 hour')
        AND pnl IS NOT NULL
    ''')
    last_hour = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'last_hour': last_hour,
        'progress_to_500': (total_trades / 500 * 100) if total_trades < 500 else 100
    }

def create_stats_panel():
    """Create stats panel"""
    stats = get_trading_stats()
    
    stats_text = f"""
[bold cyan]📊 CURRENT SESSION STATS[/bold cyan]

🎯 Progress to 500: [yellow]{stats['total_trades']}/500[/yellow] ([green]{stats['progress_to_500']:.1f}%[/green])
🏆 Win Rate: [green]{stats['win_rate']:.1f}%[/green]
💰 Total P&L: [green]+R{stats['total_pnl']:.2f}[/green]
⚡ Last Hour: [yellow]{stats['last_hour']} trades[/yellow]

[dim]Press Ctrl+C to stop monitoring[/dim]
    """
    
    return Panel(stats_text, title="📈 Trading Dashboard", border_style="green")

def monitor_trades():
    """Main monitoring function with live updates"""
    with Live(console=console, refresh_per_second=2) as live:
        while True:
            try:
                # Create layout
                stats_panel = create_stats_panel()
                trade_table = create_trade_table()
                
                # Combine in a layout
                from rich.layout import Layout
                layout = Layout()
                layout.split_column(
                    Layout(stats_panel, size=8),
                    Layout(trade_table)
                )
                
                live.update(layout)
                time.sleep(5)  # Update every 5 seconds
                
            except KeyboardInterrupt:
                console.print("\n[yellow]👋 Monitoring stopped![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                time.sleep(2)

if __name__ == "__main__":
    console.print("[bold green]🚀 Starting Live Trade Monitor...[/bold green]")
    console.print("[dim]Updates every 5 seconds. Press Ctrl+C to stop.[/dim]\n")
    monitor_trades()