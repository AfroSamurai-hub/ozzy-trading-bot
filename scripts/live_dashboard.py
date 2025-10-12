#!/usr/bin/env python3
"""
Live A/B Test Dashboard
Shows real-time progress of the time filter A/B test
"""

import os
import sys
import time
import sqlite3
from datetime import datetime
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from rich.console import Console
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️  Rich library not available. Install with: pip install rich")
    print("Falling back to simple display...")


class ABTestDashboard:
    def __init__(self, db_path="ozzy_simple.db", test_name="time_filter_night"):
        self.db_path = db_path
        self.test_name = test_name
        self.console = Console() if RICH_AVAILABLE else None
        
    def get_test_data(self):
        """Get current test statistics from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get control group trades
            control_query = f"""
                SELECT COUNT(*), 
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(pnl) as total_pnl,
                       AVG(pnl) as avg_pnl
                FROM trades 
                WHERE entry_reason LIKE '%TEST_{self.test_name}_control_%'
                AND exit_timestamp IS NOT NULL
            """
            cursor.execute(control_query)
            control_data = cursor.fetchone()
            
            # Get test group trades
            test_query = f"""
                SELECT COUNT(*), 
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(pnl) as total_pnl,
                       AVG(pnl) as avg_pnl
                FROM trades 
                WHERE entry_reason LIKE '%TEST_{self.test_name}_test_%'
                AND exit_timestamp IS NOT NULL
            """
            cursor.execute(test_query)
            test_data = cursor.fetchone()
            
            # Get recent trades (last 10)
            recent_query = f"""
                SELECT symbol, side, pnl, exit_timestamp, entry_reason
                FROM trades
                WHERE entry_reason LIKE '%TEST_{self.test_name}_%'
                AND exit_timestamp IS NOT NULL
                ORDER BY id DESC
                LIMIT 10
            """
            cursor.execute(recent_query)
            recent_trades = cursor.fetchall()
            
            # Get open positions count
            open_query = """
                SELECT COUNT(*)
                FROM trades
                WHERE exit_timestamp IS NULL
            """
            cursor.execute(open_query)
            open_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'control': {
                    'count': control_data[0] or 0,
                    'wins': control_data[1] or 0,
                    'total_pnl': control_data[2] or 0,
                    'avg_pnl': control_data[3] or 0
                },
                'test': {
                    'count': test_data[0] or 0,
                    'wins': test_data[1] or 0,
                    'total_pnl': test_data[2] or 0,
                    'avg_pnl': test_data[3] or 0
                },
                'recent_trades': recent_trades,
                'open_positions': open_count
            }
        except Exception as e:
            return {
                'control': {'count': 0, 'wins': 0, 'total_pnl': 0, 'avg_pnl': 0},
                'test': {'count': 0, 'wins': 0, 'total_pnl': 0, 'avg_pnl': 0},
                'recent_trades': [],
                'open_positions': 0,
                'error': str(e)
            }
    
    def create_rich_layout(self, data):
        """Create rich display - using simple Group instead of complex Layout"""
        from rich.columns import Columns
        from rich import box
        
        control_count = data['control']['count']
        test_count = data['test']['count']
        total = control_count + test_count
        
        # Header
        header = Panel(
            Text("🧪 TIME FILTER A/B TEST - LIVE DASHBOARD 🧪", style="bold cyan", justify="center"),
            border_style="cyan"
        )
        
        # Progress panel
        progress_table = Table.grid(padding=(0, 2))
        progress_table.add_column(style="cyan", justify="left")
        progress_table.add_column(style="white", justify="left")
        
        progress_table.add_row("Target:", "50 trades per group (100 total)")
        progress_table.add_row("")
        progress_table.add_row("Control Group:", f"{control_count}/50 ({control_count*2}%)")
        progress_table.add_row("Test Group:", f"{test_count}/50 ({test_count*2}%)")
        progress_table.add_row("")
        progress_table.add_row("Total Completed:", f"{total}/100 ({total}%)")
        
        if total >= 100:
            progress_table.add_row("")
            progress_table.add_row("Status:", "✅ COMPLETE! Run --report", style="bold green")
        else:
            progress_table.add_row("")
            remaining = 100 - total
            progress_table.add_row("Remaining:", f"{remaining} trades")
        
        progress_panel = Panel(progress_table, title="📊 Progress", border_style="blue")
        
        # Stats comparison
        stats_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Control", justify="right", style="yellow")
        stats_table.add_column("Test", justify="right", style="green")
        stats_table.add_column("Diff", justify="right")
        
        control_wr = (data['control']['wins'] / data['control']['count'] * 100) if data['control']['count'] > 0 else 0
        test_wr = (data['test']['wins'] / data['test']['count'] * 100) if data['test']['count'] > 0 else 0
        wr_diff = test_wr - control_wr
        
        stats_table.add_row(
            "Win Rate",
            f"{control_wr:.1f}%",
            f"{test_wr:.1f}%",
            Text(f"{wr_diff:+.1f}%" if wr_diff != 0 else "-", style="green" if wr_diff > 0 else "red" if wr_diff < 0 else "white")
        )
        
        stats_table.add_row(
            "Avg P&L",
            f"R{data['control']['avg_pnl']:.2f}",
            f"R{data['test']['avg_pnl']:.2f}",
            Text(f"R{data['test']['avg_pnl'] - data['control']['avg_pnl']:+.2f}", 
                 style="green" if data['test']['avg_pnl'] > data['control']['avg_pnl'] else "red")
        )
        
        stats_table.add_row(
            "Total P&L",
            f"R{data['control']['total_pnl']:.2f}",
            f"R{data['test']['total_pnl']:.2f}",
            Text(f"R{data['test']['total_pnl'] - data['control']['total_pnl']:+.2f}",
                 style="green" if data['test']['total_pnl'] > data['control']['total_pnl'] else "red")
        )
        
        stats_panel = Panel(stats_table, title="📈 Performance", border_style="magenta")
        
        # Recent trades
        trades_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        trades_table.add_column("Time", style="dim", width=8)
        trades_table.add_column("Symbol", style="cyan", width=10)
        trades_table.add_column("Side", justify="center", width=10)
        trades_table.add_column("P&L", justify="right", width=10)
        trades_table.add_column("Group", justify="center", width=6)
        
        for trade in data['recent_trades'][:10]:
            symbol, side, pnl, exit_time, entry_reason = trade
            
            group = "CTRL" if "_control_" in entry_reason else "TEST"
            pnl_str = f"R{pnl:.2f}"
            pnl_style = "green" if pnl > 0 else "red" if pnl < 0 else "white"
            side_emoji = "🟢" if side == "LONG" else "🔴"
            
            try:
                time_obj = datetime.strptime(exit_time, "%Y-%m-%d %H:%M:%S")
                time_str = time_obj.strftime("%H:%M")
            except:
                time_str = exit_time[:5] if exit_time else "?"
            
            trades_table.add_row(
                time_str,
                symbol,
                f"{side_emoji} {side[:4]}",
                Text(pnl_str, style=pnl_style),
                Text(group, style="yellow" if group == "CTRL" else "green")
            )
        
        trades_panel = Panel(trades_table, title="📋 Recent Trades", border_style="green")
        
        # Footer
        footer_text = Text()
        footer_text.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC ", style="dim")
        footer_text.append(f"| Open: {data['open_positions']} ", style="cyan")
        footer_text.append("| Press Ctrl+C to exit", style="dim")
        footer = Panel(footer_text, border_style="dim")
        
        # Combine everything using Group
        from rich.console import Group
        left_column = Group(progress_panel, stats_panel)
        body = Columns([left_column, trades_panel], equal=False, expand=True)
        
        return Group(header, body, footer)
    
    def create_simple_display(self, data):
        """Create simple text display for terminals without rich"""
        output = []
        output.append("\n" + "=" * 70)
        output.append("🧪 TIME FILTER A/B TEST - LIVE DASHBOARD")
        output.append("=" * 70)
        output.append("")
        
        # Progress
        control_count = data['control']['count']
        test_count = data['test']['count']
        total = control_count + test_count
        
        output.append("📊 PROGRESS")
        output.append("-" * 70)
        output.append(f"Target: 50 trades per group (100 total)")
        output.append(f"Control Group: {control_count}/50 ({control_count*2}%)")
        output.append(f"Test Group:    {test_count}/50 ({test_count*2}%)")
        output.append(f"Total:         {total}/100 ({total}%)")
        output.append("")
        
        # Stats
        control_wr = (data['control']['wins'] / data['control']['count'] * 100) if data['control']['count'] > 0 else 0
        test_wr = (data['test']['wins'] / data['test']['count'] * 100) if data['test']['count'] > 0 else 0
        
        output.append("📈 PERFORMANCE")
        output.append("-" * 70)
        output.append(f"{'Metric':<20} {'Control':<15} {'Test':<15} {'Diff'}")
        output.append(f"{'Win Rate':<20} {control_wr:.1f}% {' '*9} {test_wr:.1f}% {' '*9} {test_wr - control_wr:+.1f}%")
        output.append(f"{'Avg P&L':<20} R{data['control']['avg_pnl']:.2f} {' '*8} R{data['test']['avg_pnl']:.2f} {' '*8} R{data['test']['avg_pnl'] - data['control']['avg_pnl']:+.2f}")
        output.append("")
        
        # Recent trades
        output.append("📋 RECENT TRADES")
        output.append("-" * 70)
        for trade in data['recent_trades'][:5]:
            symbol, side, pnl, exit_time, entry_reason = trade
            group = "CTRL" if "_control_" in entry_reason else "TEST"
            output.append(f"{symbol:8} {side:5} R{pnl:7.2f}  {group}")
        
        output.append("")
        output.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Open: {data['open_positions']} | Ctrl+C to exit")
        output.append("=" * 70)
        
        return "\n".join(output)
    
    def run(self, refresh_seconds=10):
        """Run the live dashboard"""
        if RICH_AVAILABLE:
            self._run_rich(refresh_seconds)
        else:
            self._run_simple(refresh_seconds)
    
    def _run_rich(self, refresh_seconds):
        """Run with rich display"""
        try:
            with Live(self.create_rich_layout(self.get_test_data()), 
                     refresh_per_second=1/refresh_seconds,
                     screen=True) as live:
                while True:
                    time.sleep(refresh_seconds)
                    data = self.get_test_data()
                    live.update(self.create_rich_layout(data))
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Dashboard stopped by user[/yellow]")
    
    def _run_simple(self, refresh_seconds):
        """Run with simple display"""
        try:
            while True:
                os.system('clear' if os.name != 'nt' else 'cls')
                data = self.get_test_data()
                print(self.create_simple_display(data))
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n\nDashboard stopped by user")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Live A/B Test Dashboard")
    parser.add_argument("--refresh", type=int, default=10, 
                       help="Refresh interval in seconds (default: 10)")
    parser.add_argument("--test-name", default="time_filter_night",
                       help="Test name to monitor")
    
    args = parser.parse_args()
    
    dashboard = ABTestDashboard(test_name=args.test_name)
    
    print(f"\n🚀 Starting live dashboard (refreshing every {args.refresh} seconds)...")
    print("Press Ctrl+C to exit\n")
    time.sleep(2)
    
    dashboard.run(refresh_seconds=args.refresh)
