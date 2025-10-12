#!/usr/bin/env python3
"""
Unified Dashboard - Demo + AI Trading Performance
"""
import sqlite3
import os
import sys
import time
from datetime import datetime
import json
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.table import Table

# Paths
DEMO_DB = os.path.expanduser("~/ozzy-simple/demo_trades.db")
AI_DB = os.path.expanduser("~/ozzy-simple/ozzy_simple.db")

console = Console()

def get_demo_stats():
    if not os.path.exists(DEMO_DB):
        return None
    conn = sqlite3.connect(DEMO_DB)
    cursor = conn.cursor()
    # Demo config
    cursor.execute('SELECT * FROM demo_config ORDER BY id DESC LIMIT 1')
    config = cursor.fetchone()
    if not config:
        conn.close()
        return None
    starting_capital = config[1]
    current_balance = config[2]
    total_trades = config[4]
    total_pnl = config[5]
    # Trades
    # Closed trades and win rate
    cursor.execute('SELECT COUNT(*) FROM demo_trades WHERE status="closed"')
    closed_trades = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM demo_trades WHERE status="closed"')
    wins = cursor.fetchone()[0] or 0
    win_rate = (wins / closed_trades * 100) if closed_trades else 0

    # Open positions count
    cursor.execute('SELECT COUNT(*) FROM demo_trades WHERE status="open"')
    open_trades = cursor.fetchone()[0]

    # Recent activity (last 3 trades any status)
    cursor.execute('''
        SELECT symbol, side, status, COALESCE(pnl, 0), COALESCE(exit_time, entry_time)
        FROM demo_trades
        ORDER BY COALESCE(exit_time, entry_time) DESC
        LIMIT 3
    ''')
    recent = cursor.fetchall()
    conn.close()
    return {
        'capital': starting_capital,
        'balance': current_balance,
        'trades': closed_trades,
        'open_trades': open_trades,
        'win_rate': win_rate,
        'pnl': total_pnl,
        'recent': recent
    }

def get_demo_open_positions():
    positions_file = os.path.join(os.path.dirname(DEMO_DB), "positions.json")
    if not os.path.exists(positions_file):
        return []
    try:
        with open(positions_file, "r") as f:
            data = json.load(f)
    except Exception:
        return []
    positions = data.get("positions", {})
    formatted = []
    for sym, info in positions.items():
        formatted.append({
            "symbol": sym,
            "side": info.get("side"),
            "qty": info.get("qty"),
            "entry": info.get("entry_price"),
            "current": info.get("current_price"),
            "stop": info.get("stop_loss"),
            "target": info.get("take_profit"),
            "pnl": info.get("unrealized_pnl")
        })
    return formatted

def get_ai_stats():
    if not os.path.exists(AI_DB):
        return None
    conn = sqlite3.connect(AI_DB)
    cursor = conn.cursor()
    # Paper trades
    cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status="CLOSED"')
    closed_trades = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM paper_trades WHERE status="CLOSED"')
    wins = cursor.fetchone()[0] or 0
    win_rate = (wins / closed_trades * 100) if closed_trades else 0
    cursor.execute('SELECT COALESCE(SUM(pnl),0) FROM paper_trades WHERE status="CLOSED"')
    total_pnl = cursor.fetchone()[0]

    # Open positions and exposure
    cursor.execute('SELECT COUNT(*), COALESCE(SUM(value),0) FROM paper_trades WHERE status="OPEN"')
    row = cursor.fetchone()
    open_trades = row[0]
    open_exposure = row[1]

    # Recent paper trades
    cursor.execute('''
        SELECT symbol, side, status, COALESCE(pnl,0), timestamp
        FROM paper_trades
        ORDER BY timestamp DESC
        LIMIT 5
    ''')
    recent = cursor.fetchall()
    conn.close()
    return {
        'trades': closed_trades,
        'open_trades': open_trades,
        'open_exposure': open_exposure,
        'win_rate': win_rate,
        'pnl': total_pnl,
        'recent': recent
    }

def get_ai_open_positions():
    if not os.path.exists(AI_DB):
        return []
    conn = sqlite3.connect(AI_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT symbol, side, entry, stop, target, size, value, timestamp
        FROM paper_trades
        WHERE status = 'OPEN'
        ORDER BY timestamp DESC
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    conn.close()
    positions = []
    for row in rows:
        positions.append({
            "symbol": row[0],
            "side": row[1],
            "entry": row[2],
            "stop": row[3],
            "target": row[4],
            "size": row[5],
            "value": row[6],
            "timestamp": row[7]
        })
    return positions

def create_dashboard():
    demo = get_demo_stats()
    demo_positions = get_demo_open_positions()
    ai = get_ai_stats()
    ai_positions = get_ai_open_positions()
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="demo"),
        Layout(name="ai")
    )
    # Header
    layout["header"].update(Panel(Text("🚀 Unified Trading Dashboard", style="bold blue"), style="blue"))
    # Demo panel
    if demo:
        demo_lines = [
            f"[bold green]Demo Bot[/bold green]",
            f"Capital: R{demo['capital']:.2f}",
            f"Balance: R{demo['balance']:.2f}",
            f"Closed Trades: {demo['trades']} | Open: {demo['open_trades']}",
            f"Win Rate: {demo['win_rate']:.1f}%",
            f"PnL (closed): R{demo['pnl']:.2f}",
            "",
            "Recent Activity:",
        ]
        if demo['recent']:
            for sym, side, status, pnl, t in demo['recent']:
                when = t or "-"
                demo_lines.append(f" • {sym} {side} {status} pnl={pnl:+.2f} @ {when}")
        else:
            demo_lines.append(" • (no trades yet)")
        if demo_positions:
            demo_lines.append("")
            demo_lines.append("Open Positions:")
            for pos in demo_positions:
                entry = pos.get('entry')
                entry_str = f"{entry:.2f}" if entry is not None else "-"
                stop = pos.get('stop')
                stop_str = f"{stop:.2f}" if isinstance(stop, (int, float)) else "-"
                target = pos.get('target')
                target_str = f"{target:.2f}" if isinstance(target, (int, float)) else "-"
                qty = pos.get('qty')
                qty_str = f"{qty:.6f}" if isinstance(qty, (int, float)) else "-"
                pnl = pos.get('pnl')
                pnl_str = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "+0.00"
                demo_lines.append(
                    f" • {pos['symbol']} {pos['side']} qty={qty_str} entry={entry_str}"
                )
                demo_lines.append(
                    f"   SL={stop_str} | TP={target_str} | PnL={pnl_str}"
                )
        demo_text = "\n".join(demo_lines)
    else:
        demo_text = "No demo data"
    layout["demo"].update(Panel(demo_text, title="Demo", style="green"))
    # AI panel
    if ai:
        ai_lines = [
            f"[bold yellow]AI Bot[/bold yellow]",
            f"Closed Trades: {ai['trades']} | Open: {ai['open_trades']}",
            f"Open Exposure: R{ai['open_exposure']:.2f}",
            f"Win Rate: {ai['win_rate']:.1f}%",
            f"PnL (closed): R{ai['pnl']:.2f}",
            "",
            "Recent Activity:",
        ]
        if ai['recent']:
            for sym, side, status, pnl, ts in ai['recent']:
                ai_lines.append(f" • {sym} {side} {status} pnl={pnl:+.2f} @ {ts}")
        else:
            ai_lines.append(" • (no trades yet)")
        if ai_positions:
            ai_lines.append("")
            ai_lines.append("Open Positions:")
            for pos in ai_positions:
                entry = pos.get('entry')
                entry_str = f"{entry:.2f}" if isinstance(entry, (int, float)) else "-"
                stop = pos.get('stop')
                stop_str = f"{stop:.2f}" if isinstance(stop, (int, float)) else "-"
                target = pos.get('target')
                target_str = f"{target:.2f}" if isinstance(target, (int, float)) else "-"
                size = pos.get('size')
                size_str = f"{size:.4f}" if isinstance(size, (int, float)) else "-"
                value = pos.get('value')
                value_str = f"{value:.2f}" if isinstance(value, (int, float)) else "-"
                opened = pos.get('timestamp') or "-"
                ai_lines.append(
                    f" • {pos['symbol']} {pos['side']} size={size_str} entry={entry_str}"
                )
                ai_lines.append(
                    f"   SL={stop_str} | TP={target_str} | Value=R{value_str} | Opened {opened}"
                )
        ai_text = "\n".join(ai_lines)
    else:
        ai_text = "No AI data"
    layout["ai"].update(Panel(ai_text, title="AI", style="yellow"))
    # Footer
    layout["footer"].update(Panel("Press Ctrl+C to exit | Updates every 10s", style="blue"))
    return layout

def main():
    try:
        with Live(create_dashboard(), refresh_per_second=1, screen=True) as live:
            while True:
                time.sleep(10)
                live.update(create_dashboard())
    except KeyboardInterrupt:
        console.print("\n👋 Unified dashboard stopped", style="yellow")

if __name__ == "__main__":
    main()
