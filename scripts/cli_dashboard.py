#!/usr/bin/env python3
"""Rich-powered live CLI dashboard for ozzy-simple.

Run with:
  PYTHONPATH=. /path/to/venv/bin/python scripts/cli_dashboard.py [--live]

Features:
- Live updating stats using Rich Live
- Clear screen on each refresh
- Pretty tables and panels
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich.layout import Layout
from rich import box
import sqlite3
import time
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, '.')
try:
    import config
except Exception:
    class config:
        STARTING_CAPITAL = 10000.0


DB = 'ozzy_simple.db'
console = Console()


def color_pnl(v):
    if v is None:
        return "NULL"
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v > 0:
        return f"[green]+R{v:,.2f}[/green]"
    if v < 0:
        return f"[red]-R{abs(v):,.2f}[/red]"
    return f"R{v:,.2f}"


def get_metrics():
    if not os.path.exists(DB):
        return None
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute('SELECT COUNT(*) FROM signals')
    signals_count = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM trades')
    trades_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trades WHERE exit_timestamp IS NULL")
    open_trades = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM positions')
    positions_count = cur.fetchone()[0]
    cur.execute('SELECT COALESCE(SUM(pnl),0) FROM trades WHERE pnl IS NOT NULL')
    total_pnl = cur.fetchone()[0] or 0.0

    # Win rate and stats
    cur.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0")
    wins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trades WHERE pnl < 0")
    losses = cur.fetchone()[0]
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0

    # Recent completed trades - be schema resilient (exit_reason may not exist)
    cur.execute("PRAGMA table_info('trades')")
    trades_cols = [r[1] for r in cur.fetchall()]
    trades_select_cols = ['entry_timestamp', 'exit_timestamp', 'symbol', 'side', 'pnl']
    if 'exit_reason' in trades_cols:
        trades_select_cols.append('exit_reason')
    # duration computed separately using julianday
    trades_cols_sql = ', '.join(trades_select_cols)
    q = f"SELECT {trades_cols_sql}, (julianday(exit_timestamp) - julianday(entry_timestamp))*24*60 as duration_min FROM trades WHERE exit_timestamp IS NOT NULL ORDER BY id DESC LIMIT 5"
    cur.execute(q)
    recent = cur.fetchall()

    # Open positions: be schema resilient (current_price/target may not exist)
    cur.execute("PRAGMA table_info('positions')")
    pos_cols = [r[1] for r in cur.fetchall()]
    pos_select = ['symbol', 'side', 'entry_price', 'qty', 'unrealized_pnl']
    if 'current_price' in pos_cols:
        pos_select.insert(3, 'current_price')
    else:
        # keep positional order consistent by inserting None later
        pass
    if 'target' in pos_cols:
        pos_select.append('target')
    pos_sql = ', '.join(pos_select)
    q2 = f"SELECT {pos_sql} FROM positions ORDER BY id DESC"
    try:
        cur.execute(q2)
        positions = cur.fetchall()
    except Exception:
        # Fallback: select minimal columns
        cur.execute('SELECT symbol, side, entry_price, qty, unrealized_pnl FROM positions ORDER BY id DESC')
        positions = cur.fetchall()

    # Performance summary
    cur.execute('SELECT COALESCE(MAX(pnl),0) FROM trades')
    best = cur.fetchone()[0] or 0.0
    cur.execute('SELECT COALESCE(MIN(pnl),0) FROM trades')
    worst = cur.fetchone()[0] or 0.0
    cur.execute('SELECT AVG(CASE WHEN pnl>0 THEN pnl END) FROM trades')
    avg_win = cur.fetchone()[0] or 0.0
    cur.execute('SELECT AVG(CASE WHEN pnl<0 THEN pnl END) FROM trades')
    avg_loss = cur.fetchone()[0] or 0.0

    conn.close()

    metrics = {
        'signals_count': signals_count,
        'trades_count': trades_count,
        'open_trades': open_trades,
        'positions_count': positions_count,
        'total_pnl': total_pnl,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'recent': recent,
        'positions': positions,
        'best': best,
        'worst': worst,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }
    return metrics


def make_header(balance, mode='Paper Trading'):
    now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    title = f"🔥 OZZY TRADING BOT - LIVE CLI DASHBOARD\nTime: {now} | Mode: {mode} | Balance: [bold yellow]R{balance:,.2f}[/bold yellow]"
    return Panel(Align.center(title), style='cyan', padding=(1, 2))


def make_top_metrics(metrics):
    bal = config.STARTING_CAPITAL + metrics['total_pnl']
    total_pnl = metrics['total_pnl']
    win_rate = metrics['win_rate']
    open_trades = metrics['open_trades']

    table = Table.grid(expand=True)
    table.add_column()
    table.add_column()
    table.add_column()
    table.add_column()

    def pnl_delta_text(v):
        # For now use absolute change vs starting capital (simple)
        delta = v
        arrow = '↑' if delta >= 0 else '↓'
        col = 'green' if delta >= 0 else 'red'
        return f"[{col}]{arrow} R{delta:+,.2f}[/{col}]"

    table.add_row(
        Panel(f"[bold]Balance[/bold]\n[bold yellow]R{bal:,.2f}[/bold yellow]\n{pnl_delta_text(metrics['total_pnl'])}", style='white on black'),
        Panel(f"[bold]Total P&L[/bold]\n{color_pnl(total_pnl)}\n", style='white on black'),
        Panel(f"[bold]Win Rate[/bold]\n{win_rate:.1f}%\n", style='white on black'),
        Panel(f"[bold]Open Trades[/bold]\n{open_trades}\n", style='white on black'),
    )
    return table


def make_positions_table(positions):
    t = Table(show_header=True, header_style='bold green', box=box.SIMPLE_HEAVY)
    t.add_column('Symbol', style='cyan')
    t.add_column('Side')
    t.add_column('Entry')
    t.add_column('Current')
    t.add_column('P&L')
    t.add_column('Target')

    if not positions:
        t.add_row('No open positions', '', '', '', '', '')
        return t

    for row in positions:
        symbol, side, entry_price, current_price, qty, unrealized_pnl, target = row
        entry_s = f"{entry_price:,.6f}" if isinstance(entry_price, (int, float)) else str(entry_price)
        cur_s = f"{current_price:,.6f}" if isinstance(current_price, (int, float)) else str(current_price)
        pnl_s = color_pnl(unrealized_pnl)
        target_s = str(target) if target is not None else ''
        t.add_row(symbol, side, entry_s, cur_s, pnl_s, target_s)
    return t


def make_recent_trades_table(recent):
    t = Table(show_header=True, header_style='bold magenta')
    t.add_column('Time')
    t.add_column('Symbol')
    t.add_column('Side')
    t.add_column('P&L')
    t.add_column('Duration')
    t.add_column('Exit Reason')

    if not recent:
        t.add_row('No trades yet', '', '', '', '', '')
        return t

    for r in recent:
        # r may have different shapes depending on schema (exit_reason optional)
        # We expect at least: entry_timestamp, exit_timestamp, symbol, side, pnl
        entry_ts = r[0] if len(r) > 0 else None
        exit_ts = r[1] if len(r) > 1 else None
        symbol = r[2] if len(r) > 2 else ''
        side = r[3] if len(r) > 3 else ''
        pnl = r[4] if len(r) > 4 else None
        # duration may be last or second-last depending on whether exit_reason present
        duration_min = None
        exit_reason = ''
        if len(r) == 6:
            # (entry, exit, symbol, side, pnl, duration)
            duration_min = r[5]
        elif len(r) >= 7:
            # (entry, exit, symbol, side, pnl, exit_reason, duration) OR with duration last
            # We attempted to select exit_reason then duration_min; fallback parse
            exit_reason = r[5] or ''
            duration_min = r[6]
        # Format
        try:
            t_exit = datetime.fromisoformat(exit_ts).strftime('%H:%M:%S') if exit_ts else 'NULL'
        except Exception:
            t_exit = str(exit_ts) if exit_ts else 'NULL'
        dur = ''
        try:
            if duration_min is not None:
                m = float(duration_min)
                if m >= 60:
                    dur = f"{int(m//60)}h {int(m%60)}m"
                else:
                    dur = f"{int(m)} min"
        except Exception:
            dur = ''

    t.add_row(str(t_exit), str(symbol), str(side), str(color_pnl(pnl)), str(dur), str(exit_reason or ''))
    return t


def create_layout(metrics):
    layout = Layout()
    layout.split_column(
        Layout(name='header', size=3),
        Layout(name='top', size=6),
        Layout(name='middle'),
        Layout(name='perf', size=6),
        Layout(name='footer', size=1),
    )

    balance = config.STARTING_CAPITAL + metrics['total_pnl']
    layout['header'].update(make_header(balance))
    layout['top'].update(make_top_metrics(metrics))

    middle = Layout()
    middle.split_row(Layout(name='positions'), Layout(name='recent'))
    middle['positions'].update(Panel(make_positions_table(metrics['positions']), title='Open Positions', padding=(1,)))
    middle['recent'].update(Panel(make_recent_trades_table(metrics['recent']), title='Recent Trades'))
    layout['middle'].update(middle)

    perf = Table.grid(expand=True)
    perf.add_column()
    perf.add_column()
    perf.add_row(
        Panel(f"Total Trades: {metrics['trades_count']}\nWins: {metrics['wins']} ({metrics['win_rate']:.1f}%)\nLosses: {metrics['losses']}", title='Performance'),
        Panel(f"Best Trade: [green]R{metrics['best']:+.2f}[/green]\nWorst Trade: [red]R{metrics['worst']:+.2f}[/red]\nAvg Win: [green]R{metrics['avg_win']:+.2f}[/green]\nAvg Loss: [red]R{metrics['avg_loss']:+.2f}[/red]", title='Stats'),
    )
    layout['perf'].update(perf)

    now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    layout['footer'].update(Panel(f"Last Update: {now} | Press Ctrl+C to stop", style='dim'))

    return layout


def run_once():
    metrics = get_metrics()
    if metrics is None:
        console.print('[red]No database found. Run from project root where ozzy_simple.db exists.[/red]')
        return
    layout = create_layout(metrics)
    console.clear()
    console.print(layout)


def run_live(refresh=5):
    with Live(console=console, refresh_per_second=4) as live:
        try:
            while True:
                metrics = get_metrics()
                if metrics is None:
                    console.clear()
                    console.print('[red]No database found. Run from project root where ozzy_simple.db exists.[/red]')
                    return
                layout = create_layout(metrics)
                console.clear()
                live.update(layout)
                time.sleep(refresh)
        except KeyboardInterrupt:
            console.print('\n[bold]Stopping live dashboard...[/bold]')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Ozzy live CLI dashboard')
    parser.add_argument('--live', action='store_true', help='Run in live updating mode')
    parser.add_argument('--refresh', type=int, default=5, help='Refresh interval in seconds')
    args = parser.parse_args()

    if args.live:
        run_live(refresh=args.refresh)
    else:
        run_once()
