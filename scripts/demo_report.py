#!/usr/bin/env python3
"""
Demo Report Generator - Comprehensive analysis of demo trading performance
"""

import sqlite3
import argparse
import os
import sys
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo_utils import ensure_demo_database, get_demo_db_path

DEMO_DB_PATH = get_demo_db_path()

class DemoReportGenerator:
    def __init__(self):
        self.console = Console()
        
        try:
            self.db_path = ensure_demo_database(DEMO_DB_PATH)
        except Exception as exc:
            self.console.print(f"❌ Demo database error: {exc}", style="red")
            sys.exit(1)
    
    def get_demo_stats(self):
        """Get comprehensive demo statistics"""
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
        
        # Get detailed trade statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade,
                AVG(pnl) as avg_trade,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as total_wins,
                SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as total_losses,
                MAX(entry_time) as last_trade_time,
                MIN(entry_time) as first_trade_time
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
        avg_win = trade_stats[6] or 0
        avg_loss = trade_stats[7] or 0
        total_wins = trade_stats[8] or 0
        total_losses = trade_stats[9] or 0
        last_trade_time = trade_stats[10]
        first_trade_time = trade_stats[11]
        
        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
        
        # Calculate profit factor and win/loss ratio
        profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')
        win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss < 0 else float('inf')
        
        # Calculate max drawdown and recovery stats
        cursor.execute('SELECT balance_after, entry_time FROM demo_trades WHERE balance_after IS NOT NULL ORDER BY entry_time')
        balance_history = cursor.fetchall()
        
        max_balance = starting_capital
        max_drawdown = 0
        drawdown_periods = []
        current_drawdown_start = None
        
        for balance, timestamp in balance_history:
            if balance > max_balance:
                max_balance = balance
                if current_drawdown_start:
                    # End of drawdown period
                    drawdown_periods.append({
                        'start': current_drawdown_start,
                        'end': timestamp,
                        'peak': max_balance,
                        'trough': balance
                    })
                    current_drawdown_start = None
            else:
                drawdown_pct = ((max_balance - balance) / max_balance) * 100
                if drawdown_pct > max_drawdown:
                    max_drawdown = drawdown_pct
                
                if not current_drawdown_start and drawdown_pct > 1:  # Start tracking significant drawdowns
                    current_drawdown_start = timestamp
        
        # Calculate average recovery time
        avg_recovery_days = 0
        if drawdown_periods:
            total_recovery_time = 0
            for period in drawdown_periods:
                try:
                    start_dt = datetime.strptime(period['start'], "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(period['end'], "%Y-%m-%d %H:%M:%S")
                    recovery_time = (end_dt - start_dt).days
                    total_recovery_time += recovery_time
                except:
                    pass
            avg_recovery_days = total_recovery_time / len(drawdown_periods) if drawdown_periods else 0
        
        # Get weekly breakdown
        cursor.execute('''
            SELECT 
                strftime('%Y-W%W', date) as week,
                MIN(date) as week_start,
                MIN(starting_balance) as week_start_balance,
                MAX(ending_balance) as week_end_balance,
                SUM(trades_count) as week_trades,
                SUM(daily_pnl) as week_pnl
            FROM demo_daily_summary
            GROUP BY strftime('%Y-W%W', date)
            ORDER BY week
        ''')
        weekly_data = cursor.fetchall()
        
        # Calculate Sharpe and Sortino ratios (simplified)
        cursor.execute('SELECT daily_pnl_percent FROM demo_daily_summary WHERE daily_pnl_percent IS NOT NULL')
        daily_returns = [row[0] for row in cursor.fetchall()]
        
        sharpe_ratio = 0
        sortino_ratio = 0
        if daily_returns and len(daily_returns) > 1:
            import statistics
            avg_return = statistics.mean(daily_returns)
            std_return = statistics.stdev(daily_returns)
            
            # Simplified Sharpe (assuming risk-free rate = 0)
            sharpe_ratio = (avg_return / std_return) if std_return > 0 else 0
            
            # Sortino ratio (only downside deviation)
            negative_returns = [r for r in daily_returns if r < 0]
            if negative_returns:
                downside_deviation = statistics.stdev(negative_returns)
                sortino_ratio = (avg_return / downside_deviation) if downside_deviation > 0 else 0
        
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
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'win_loss_ratio': win_loss_ratio,
            'max_drawdown': max_drawdown,
            'avg_recovery_days': avg_recovery_days,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'weekly_data': weekly_data,
            'daily_returns': daily_returns,
            'first_trade_time': first_trade_time,
            'last_trade_time': last_trade_time
        }
    
    def generate_full_report(self):
        """Generate comprehensive demo report"""
        stats = self.get_demo_stats()
        
        if not stats:
            self.console.print("❌ No demo data found", style="red")
            return
        
        # Calculate period info
        if stats['first_trade_time'] and stats['last_trade_time']:
            start_date = datetime.strptime(stats['first_trade_time'], "%Y-%m-%d %H:%M:%S")
            end_date = datetime.strptime(stats['last_trade_time'], "%Y-%m-%d %H:%M:%S")
            period_text = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')} ({int(stats['days_running'])} days)"
        else:
            period_text = f"Demo Period ({int(stats['days_running'])} days)"
        
        # Header
        self.console.print()
        self.console.print("╔══════════════════════════════════════════════════════════════╗", style="blue")
        self.console.print("║  📊 DEMO TEST - COMPREHENSIVE REPORT                        ║", style="blue")
        self.console.print(f"║  Period: {period_text:<47} ║", style="blue")
        self.console.print("╠══════════════════════════════════════════════════════════════╣", style="blue")
        
        # Capital Performance
        self.console.print("║  💰 CAPITAL PERFORMANCE:                                     ║", style="blue")
        self.console.print(f"║     Starting Capital:  R{stats['starting_capital']:,.2f}{'':>25} ║", style="blue")
        self.console.print(f"║     Ending Balance:    R{stats['current_balance']:,.2f}{'':>25} ║", style="blue")
        self.console.print(f"║     Total Gain:        R{stats['total_gain_loss']:,.2f}{'':>25} ║", style="blue")
        
        gain_pct = stats['gain_loss_percent']
        if gain_pct >= 0:
            icon = "🚀" if gain_pct > 20 else "🔥"
            self.console.print(f"║     Return:            +{gain_pct:.2f}% {icon}{'':>25} ║", style="blue")
        else:
            self.console.print(f"║     Return:            {gain_pct:.2f}% 📉{'':>25} ║", style="blue")
        
        if stats['days_running'] > 0:
            avg_daily_gain = gain_pct / stats['days_running']
            self.console.print(f"║     Avg Daily Gain:    +{avg_daily_gain:.2f}%{'':>25} ║", style="blue")
        
        self.console.print("║                                                              ║", style="blue")
        
        # Trading Performance
        self.console.print("║  📈 TRADING PERFORMANCE:                                     ║", style="blue")
        self.console.print(f"║     Total Trades:       {stats['total_closed_trades']:<10}{'':>35} ║", style="blue")
        
        if stats['total_closed_trades'] > 0:
            self.console.print(f"║     Winning Trades:     {stats['winning_trades']} ({stats['win_rate']:.1f}%){'':>25} ║", style="blue")
            self.console.print(f"║     Losing Trades:      {stats['losing_trades']} ({100-stats['win_rate']:.1f}%){'':>25} ║", style="blue")
            self.console.print(f"║     Avg Win:            +R{stats['avg_win']:.2f}{'':>25} ║", style="blue")
            self.console.print(f"║     Avg Loss:           R{stats['avg_loss']:.2f}{'':>25} ║", style="blue")
            
            if stats['profit_factor'] != float('inf'):
                self.console.print(f"║     Profit Factor:      {stats['profit_factor']:.2f}{'':>25} ║", style="blue")
            
            if stats['win_loss_ratio'] != float('inf'):
                self.console.print(f"║     Win/Loss Ratio:     {stats['win_loss_ratio']:.2f}{'':>25} ║", style="blue")
        else:
            self.console.print("║     No trades completed yet                                  ║", style="blue")
        
        self.console.print("║                                                              ║", style="blue")
        
        # Risk Analysis
        if stats['total_closed_trades'] > 0:
            self.console.print("║  📊 RISK ANALYSIS:                                           ║", style="blue")
            self.console.print(f"║     Max Drawdown:       {stats['max_drawdown']:.1f}%{'':>25} ║", style="blue")
            
            if stats['sharpe_ratio'] > 0:
                self.console.print(f"║     Sharpe Ratio:       {stats['sharpe_ratio']:.1f}{'':>25} ║", style="blue")
            
            if stats['sortino_ratio'] > 0:
                self.console.print(f"║     Sortino Ratio:      {stats['sortino_ratio']:.1f}{'':>25} ║", style="blue")
            
            if stats['avg_recovery_days'] > 0:
                self.console.print(f"║     Recovery Time:      {stats['avg_recovery_days']:.1f} days avg{'':>20} ║", style="blue")
            
            self.console.print("║                                                              ║", style="blue")
        
        # Weekly Breakdown
        if stats['weekly_data']:
            self.console.print("║  📅 WEEKLY BREAKDOWN:                                        ║", style="blue")
            for i, week_data in enumerate(stats['weekly_data'], 1):
                week_start_bal = week_data[2]
                week_end_bal = week_data[3]
                week_pnl_pct = ((week_end_bal - week_start_bal) / week_start_bal * 100) if week_start_bal > 0 else 0
                
                self.console.print(f"║     Week {i}: R{week_start_bal:,.0f} → R{week_end_bal:,.0f} ({week_pnl_pct:+.2f}%){'':>15} ║", style="blue")
            
            self.console.print("║                                                              ║", style="blue")
        
        # Verdict
        self.console.print("║  🎯 VERDICT:                                                 ║", style="blue")
        
        # Assessment criteria
        is_profitable = stats['gain_loss_percent'] > 0
        good_win_rate = stats['win_rate'] >= 55
        acceptable_drawdown = stats['max_drawdown'] < 15
        good_sharpe = stats['sharpe_ratio'] > 1.5
        enough_trades = stats['total_closed_trades'] >= 10
        
        if is_profitable:
            self.console.print("║     ✅ System is PROFITABLE                                  ║", style="blue")
        else:
            self.console.print("║     ❌ System is LOSING MONEY                                ║", style="blue")
        
        if good_win_rate:
            self.console.print(f"║     ✅ Win rate is good ({stats['win_rate']:.1f}% > 55%){'':>15} ║", style="blue")
        else:
            self.console.print(f"║     ⚠️  Win rate needs improvement ({stats['win_rate']:.1f}% < 55%){'':>10} ║", style="blue")
        
        if acceptable_drawdown:
            self.console.print(f"║     ✅ Drawdown within limits ({stats['max_drawdown']:.1f}% < 15%){'':>15} ║", style="blue")
        else:
            self.console.print(f"║     ❌ High drawdown risk ({stats['max_drawdown']:.1f}% > 15%){'':>15} ║", style="blue")
        
        if enough_trades:
            self.console.print(f"║     ✅ Sufficient trade sample ({stats['total_closed_trades']} trades){'':>15} ║", style="blue")
        else:
            self.console.print(f"║     ⚠️  Need more trades ({stats['total_closed_trades']} < 10){'':>20} ║", style="blue")
        
        if good_sharpe and stats['sharpe_ratio'] > 0:
            self.console.print(f"║     ✅ Good risk-adjusted returns (Sharpe > 1.5)             ║", style="blue")
        
        self.console.print("║                                                              ║", style="blue")
        
        # Final recommendation
        if is_profitable and good_win_rate and acceptable_drawdown and enough_trades:
            self.console.print("║     🚀 RECOMMENDATION: READY FOR LIVE TRADING!               ║", style="green")
        elif is_profitable and enough_trades:
            self.console.print("║     ⚠️  RECOMMENDATION: PROMISING, MONITOR CLOSELY            ║", style="yellow")
        else:
            self.console.print("║     ❌ RECOMMENDATION: NEEDS IMPROVEMENT BEFORE LIVE         ║", style="red")
        
        self.console.print("║                                                              ║", style="blue")
        
        # Projected Live Performance
        if is_profitable and stats['total_closed_trades'] >= 5:
            monthly_return = gain_pct * (30 / max(stats['days_running'], 1))
            live_capital = 50000  # Assumed live capital
            
            self.console.print("║  💎 PROJECTED LIVE PERFORMANCE (R50,000 capital):            ║", style="blue")
            
            month1_expected = live_capital * (1 + monthly_return / 100)
            month1_gain = month1_expected - live_capital
            self.console.print(f"║     Month 1 Expected: R{live_capital:,.0f} → R{month1_expected:,.0f} (+R{month1_gain:,.0f}){'':>10} ║", style="blue")
            
            month3_expected = live_capital * (1 + monthly_return / 100) ** 3
            month3_gain = month3_expected - live_capital
            self.console.print(f"║     Month 3 Expected: R{live_capital:,.0f} → R{month3_expected:,.0f} (+R{month3_gain:,.0f}){'':>10} ║", style="blue")
            
            year1_expected = live_capital * (1 + monthly_return / 100) ** 12
            year1_gain = year1_expected - live_capital
            self.console.print(f"║     Year 1 Target:    R{live_capital:,.0f} → R{year1_expected:,.0f} (+R{year1_gain:,.0f}){'':>5} ║", style="blue")
        
        self.console.print("╚══════════════════════════════════════════════════════════════╝", style="blue")
        self.console.print()
    
    def generate_weekly_report(self):
        """Generate weekly summary report"""
        stats = self.get_demo_stats()
        
        if not stats:
            self.console.print("❌ No demo data found", style="red")
            return
        
        # Simple weekly summary
        self.console.print("\n📊 Weekly Demo Report", style="bold blue")
        self.console.print(f"Current Balance: R{stats['current_balance']:,.2f}")
        self.console.print(f"Total Gain: R{stats['total_gain_loss']:,.2f} ({stats['gain_loss_percent']:+.2f}%)")
        self.console.print(f"Win Rate: {stats['win_rate']:.1f}%")
        self.console.print(f"Total Trades: {stats['total_closed_trades']}")
        
        if stats['weekly_data']:
            self.console.print("\nWeekly Breakdown:")
            for i, week_data in enumerate(stats['weekly_data'], 1):
                week_start_bal = week_data[2]
                week_end_bal = week_data[3]
                week_pnl_pct = ((week_end_bal - week_start_bal) / week_start_bal * 100) if week_start_bal > 0 else 0
                print(f"  Week {i}: R{week_start_bal:,.0f} → R{week_end_bal:,.0f} ({week_pnl_pct:+.2f}%)")
    
    def generate_monthly_report(self):
        """Generate monthly summary report"""
        stats = self.get_demo_stats()
        
        if not stats:
            self.console.print("❌ No demo data found", style="red")
            return
        
        self.console.print("\n📊 Monthly Demo Report", style="bold blue")
        self.console.print(f"Period: {stats['days_running']:.1f} days")
        self.console.print(f"Starting: R{stats['starting_capital']:,.2f}")
        self.console.print(f"Current: R{stats['current_balance']:,.2f}")
        self.console.print(f"Gain: R{stats['total_gain_loss']:,.2f} ({stats['gain_loss_percent']:+.2f}%)")
        self.console.print(f"Total Trades: {stats['total_closed_trades']}")
        self.console.print(f"Win Rate: {stats['win_rate']:.1f}%")
        self.console.print(f"Max Drawdown: {stats['max_drawdown']:.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Demo Report Generator')
    parser.add_argument('--weekly', action='store_true', help='Generate weekly report')
    parser.add_argument('--monthly', action='store_true', help='Generate monthly report')
    parser.add_argument('--full', action='store_true', help='Generate comprehensive report')
    
    args = parser.parse_args()
    
    generator = DemoReportGenerator()
    
    if args.weekly:
        generator.generate_weekly_report()
    elif args.monthly:
        generator.generate_monthly_report()
    elif args.full:
        generator.generate_full_report()
    else:
        print("Usage: python demo_report.py [--weekly|--monthly|--full]")

if __name__ == "__main__":
    main()
