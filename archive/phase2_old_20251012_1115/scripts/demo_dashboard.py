#!/usr/bin/env python3
"""
Demo Dashboard - Real-time monitoring of R10,000 demo trading progress
"""

import sqlite3
import time
import os
import sys
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo_utils import ensure_demo_database, get_demo_db_path

DEMO_DB_PATH = get_demo_db_path()

class DemoDashboard:
    def __init__(self):
        self.console = Console()
        self.last_update = None
        
        try:
            self.db_path = ensure_demo_database(DEMO_DB_PATH)
        except Exception as exc:
            self.console.print(f"❌ Demo database error: {exc}", style="red")
            sys.exit(1)
    
    def get_demo_stats(self):
        """Get current demo statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get config
        cursor.execute('SELECT * FROM demo_config ORDER BY id DESC LIMIT 1')
        config = cursor.fetchone()
        
        if not config:
            conn.close()
            return None
        
        starting_capital = config[1]
        current_balance = config[2]
        start_date = datetime.fromisoformat(config[3])
        total_trades = config[4]
        total_pnl = config[5]
        
        # Calculate days running
        days_running = (datetime.now() - start_date.replace(tzinfo=None)).days
        if days_running == 0:
            days_running = (datetime.now() - start_date.replace(tzinfo=None)).seconds / 86400
        
        # Get trade statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade,
                AVG(pnl) as avg_trade,
                MAX(entry_time) as last_trade_time
            FROM demo_trades 
            WHERE status = 'closed' AND pnl IS NOT NULL
        ''')
        trade_stats = cursor.fetchone()
        
        total_closed_trades = trade_stats[0] or 0
        winning_trades = trade_stats[1] or 0
        losing_trades = trade_stats[2] or 0
        best_trade = trade_stats[3] or 0
        worst_trade = trade_stats[4] or 0
        avg_trade = trade_stats[5] or 0
        last_trade_time = trade_stats[6]
        
        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
        
        # Calculate max drawdown
        cursor.execute('SELECT MIN(balance_after) FROM demo_trades WHERE balance_after IS NOT NULL')
        min_balance_result = cursor.fetchone()
        min_balance = min_balance_result[0] if min_balance_result[0] else starting_capital
        max_drawdown = ((starting_capital - min_balance) / starting_capital * 100) if min_balance < starting_capital else 0
        
        # Current drawdown
        current_drawdown = ((starting_capital - current_balance) / starting_capital * 100) if current_balance < starting_capital else 0
        
        # Get daily breakdown (last 7 days)
        cursor.execute('''
            SELECT date, starting_balance, ending_balance, daily_pnl_percent, trades_count
            FROM demo_daily_summary
            ORDER BY date DESC
            LIMIT 7
        ''')
        daily_data = cursor.fetchall()
        
        # Calculate current streak
        cursor.execute('''
            SELECT pnl FROM demo_trades 
            WHERE status = 'closed' AND pnl IS NOT NULL
            ORDER BY exit_time DESC
            LIMIT 10
        ''')
        recent_trades = cursor.fetchall()
        
        current_streak = 0
        streak_type = "unknown"
        if recent_trades:
            last_pnl = recent_trades[0][0]
            streak_type = "wins" if last_pnl > 0 else "losses"
            for trade in recent_trades:
                if (trade[0] > 0 and last_pnl > 0) or (trade[0] <= 0 and last_pnl <= 0):
                    current_streak += 1
                else:
                    break
        
        conn.close()
        
        return {
            'starting_capital': starting_capital,
            'current_balance': current_balance,
            'total_gain_loss': current_balance - starting_capital,
            'gain_loss_percent': ((current_balance - starting_capital) / starting_capital * 100),
            'days_running': days_running,
            'total_closed_trades': total_closed_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_trade': avg_trade,
            'max_drawdown': max_drawdown,
            'current_drawdown': current_drawdown,
            'current_streak': current_streak,
            'streak_type': streak_type,
            'last_trade_time': last_trade_time,
            'daily_data': daily_data
        }
    
    def create_dashboard(self):
        """Create the dashboard layout"""
        stats = self.get_demo_stats()
        
        if not stats:
            return Panel("❌ No demo data found", style="red")
        
        # Create main layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        # Split main into left and right
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Header
        header_text = Text("💰 FRESH DEMO TEST - LIVE PERFORMANCE", style="bold blue")
        layout["header"].update(Panel(header_text, style="blue"))
        
        # Left panel - Capital and Trading Stats
        capital_info = []
        
        # Capital tracking
        capital_info.append("📊 CAPITAL TRACKING:")
        capital_info.append(f"    Starting Capital:  R{stats['starting_capital']:,.2f}")
        capital_info.append(f"    Current Balance:   R{stats['current_balance']:,.2f}")
        
        gain_loss = stats['total_gain_loss']
        gain_loss_pct = stats['gain_loss_percent']
        if gain_loss >= 0:
            capital_info.append(f"    Total Gain:        R{gain_loss:,.2f} (+{gain_loss_pct:.2f}%) 🔥")
        else:
            capital_info.append(f"    Total Loss:        R{gain_loss:,.2f} ({gain_loss_pct:.2f}%) 📉")
        
        if stats['days_running'] < 1:
            capital_info.append(f"    Days Running:      {stats['days_running']:.1f} days")
        else:
            capital_info.append(f"    Days Running:      {int(stats['days_running'])} days")
        
        # Trading stats
        capital_info.append("")
        capital_info.append("📈 TRADING STATS:")
        capital_info.append(f"    Total Trades:      {stats['total_closed_trades']}")
        
        if stats['total_closed_trades'] > 0:
            capital_info.append(f"    Winning Trades:    {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
            capital_info.append(f"    Losing Trades:     {stats['losing_trades']} ({100-stats['win_rate']:.1f}%)")
            capital_info.append(f"    Average per Trade: R{stats['avg_trade']:.2f}")
        else:
            capital_info.append("    No trades completed yet")
        
        left_content = "\n".join(capital_info)
        layout["left"].update(Panel(left_content, title="Capital & Performance", style="green"))
        
        # Right panel - Risk and Progress
        right_info = []
        
        # Best/Worst trades
        if stats['total_closed_trades'] > 0:
            right_info.append("💎 BEST/WORST:")
            right_info.append(f"    Best Trade:   +R{stats['best_trade']:.2f}")
            right_info.append(f"    Worst Trade:  R{stats['worst_trade']:.2f}")
            right_info.append("")
        
        # Risk metrics
        right_info.append("⚠️  RISK METRICS:")
        right_info.append(f"    Max Drawdown:      {stats['max_drawdown']:.1f}%")
        right_info.append(f"    Current Drawdown:  {stats['current_drawdown']:.1f}%")
        
        if stats['current_streak'] > 0:
            streak_emoji = "🔥" if stats['streak_type'] == "wins" else "❄️"
            right_info.append(f"    Current Streak:    {stats['current_streak']} {stats['streak_type']} {streak_emoji}")
        
        # Milestones
        right_info.append("")
        right_info.append("🎯 MILESTONES:")
        current = stats['current_balance']
        
        milestones = [
            (10000, "✅ R10,000 (Start)"),
            (10250, "✅ R10,250" if current >= 10250 else "⏳ R10,250"),
            (11000, "✅ R11,000" if current >= 11000 else "⏳ R11,000"),
            (12000, "✅ R12,000" if current >= 12000 else "⏳ R12,000"),
            (15000, "✅ R15,000 (Target)" if current >= 15000 else "⏳ R15,000 (Target)")
        ]
        
        for milestone_val, milestone_text in milestones:
            if current >= milestone_val:
                right_info.append(f"    {milestone_text}")
            else:
                # Show progress to next milestone (with zero division protection)
                if milestone_val - 10000 != 0:
                    progress_pct = ((current - 10000) / (milestone_val - 10000)) * 100
                    right_info.append(f"    {milestone_text} ({progress_pct:.0f}% progress)")
                else:
                    right_info.append(f"    {milestone_text} (0% progress)")
                break
        
        right_content = "\n".join(right_info)
        layout["right"].update(Panel(right_content, title="Risk & Milestones", style="yellow"))
        
        # Footer - Status and daily breakdown
        footer_info = []
        
        # Daily breakdown (last 3 days)
        if stats['daily_data']:
            footer_info.append("📅 RECENT DAYS:")
            for day_data in stats['daily_data'][:3]:  # Last 3 days
                date = day_data[0]
                start_bal = day_data[1]
                end_bal = day_data[2]
                daily_pnl_pct = day_data[3]
                trades = day_data[4]
                
                icon = "🔥" if daily_pnl_pct > 0 else "📉" if daily_pnl_pct < 0 else "⚪"
                footer_info.append(f"    {date}: R{start_bal:,.0f} → R{end_bal:,.0f} ({daily_pnl_pct:+.2f}%) [{trades} trades] {icon}")
        
        # Status
        footer_info.append("")
        
        # Last trade info
        if stats['last_trade_time']:
            try:
                last_trade_dt = datetime.strptime(stats['last_trade_time'], "%Y-%m-%d %H:%M:%S")
                time_since = datetime.now() - last_trade_dt
                if time_since.total_seconds() < 3600:  # Less than 1 hour
                    time_ago = f"{int(time_since.total_seconds() / 60)} minutes ago"
                else:
                    time_ago = f"{int(time_since.total_seconds() / 3600)} hours ago"
                footer_info.append(f"Status: 🟢 RUNNING | Last Trade: {time_ago}")
            except:
                footer_info.append("Status: 🟢 RUNNING")
        else:
            footer_info.append("Status: 🟢 RUNNING | No trades yet")
        
        footer_info.append(f"Next Update: {10 - (int(time.time()) % 10)} seconds")
        footer_info.append("Press Ctrl+C to exit")
        
        footer_content = "\n".join(footer_info)
        layout["footer"].update(Panel(footer_content, style="blue"))
        
        return layout
    
    def run(self):
        """Run the live dashboard"""
        try:
            with Live(self.create_dashboard(), refresh_per_second=1, screen=True) as live:
                while True:
                    time.sleep(10)  # Update every 10 seconds
                    live.update(self.create_dashboard())
                    
        except KeyboardInterrupt:
            self.console.print("\n👋 Dashboard stopped", style="yellow")

def main():
    try:
        dashboard = DemoDashboard()
        dashboard.run()
    except ZeroDivisionError as e:
        print(f"❌ Math error: {e}")
        print("💡 Tip: Make sure bot has completed at least 1 trade")
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        print("💡 Try restarting the bot with: ./demo start")

if __name__ == "__main__":
    main()
