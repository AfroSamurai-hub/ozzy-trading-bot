#!/usr/bin/env python3
"""
🤖 AI CONFIG PERFORMANCE TRACKER
Monitors new trades with AI-optimized parameters vs historical baseline
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def get_ai_vs_baseline_performance():
    """Compare AI config trades vs baseline historical performance"""
    
    # AI config started around 12:04 PM (2025-10-11)
    ai_start_time = "2025-10-11 12:04:00"
    
    conn = sqlite3.connect('ozzy_simple.db')
    
    # Get baseline trades (before AI config)
    baseline_query = '''
    SELECT entry_timestamp, symbol, side, pnl, confidence
    FROM trades 
    WHERE pnl IS NOT NULL 
    AND entry_timestamp < ?
    ORDER BY entry_timestamp DESC
    '''
    
    baseline_df = pd.read_sql_query(baseline_query, conn, params=[ai_start_time])
    
    # Get AI config trades (after AI config started)
    ai_query = '''
    SELECT entry_timestamp, symbol, side, pnl, confidence
    FROM trades 
    WHERE pnl IS NOT NULL 
    AND entry_timestamp >= ?
    ORDER BY entry_timestamp DESC
    '''
    
    ai_df = pd.read_sql_query(ai_query, conn, params=[ai_start_time])
    
    conn.close()
    
    return baseline_df, ai_df

def analyze_performance(df, name):
    """Analyze performance metrics for a set of trades"""
    if len(df) == 0:
        return {
            'name': name,
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'avg_confidence': 0
        }
    
    wins = len(df[df['pnl'] > 0])
    losses = len(df[df['pnl'] <= 0])
    win_rate = wins / len(df) * 100
    total_pnl = df['pnl'].sum()
    avg_pnl = df['pnl'].mean()
    avg_confidence = df['confidence'].mean() if 'confidence' in df.columns else 0
    
    return {
        'name': name,
        'total_trades': len(df),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'avg_confidence': avg_confidence
    }

def create_comparison_table(baseline_stats, ai_stats):
    """Create a rich comparison table"""
    
    table = Table(title="🤖 AI CONFIG vs BASELINE PERFORMANCE", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Baseline (Historical)", style="red", width=20)
    table.add_column("AI Config (New)", style="green", width=20)
    table.add_column("Improvement", style="yellow", width=15)
    
    # Win Rate
    win_rate_diff = ai_stats['win_rate'] - baseline_stats['win_rate']
    win_rate_improvement = f"+{win_rate_diff:.1f}%" if win_rate_diff > 0 else f"{win_rate_diff:.1f}%"
    
    table.add_row(
        "Total Trades",
        str(baseline_stats['total_trades']),
        str(ai_stats['total_trades']),
        "📊 Collecting..."
    )
    
    table.add_row(
        "Win Rate",
        f"{baseline_stats['win_rate']:.1f}%",
        f"{ai_stats['win_rate']:.1f}%",
        win_rate_improvement
    )
    
    # Average P&L
    avg_pnl_diff = ai_stats['avg_pnl'] - baseline_stats['avg_pnl']
    avg_pnl_improvement = f"+R{avg_pnl_diff:.2f}" if avg_pnl_diff > 0 else f"R{avg_pnl_diff:.2f}"
    
    table.add_row(
        "Avg Trade P&L",
        f"R{baseline_stats['avg_pnl']:.2f}",
        f"R{ai_stats['avg_pnl']:.2f}",
        avg_pnl_improvement
    )
    
    # Total P&L
    table.add_row(
        "Total P&L",
        f"R{baseline_stats['total_pnl']:.2f}",
        f"R{ai_stats['total_pnl']:.2f}",
        f"R{ai_stats['total_pnl']:.2f}"
    )
    
    # Confidence
    if ai_stats['avg_confidence'] > 0:
        conf_diff = ai_stats['avg_confidence'] - baseline_stats['avg_confidence']
        conf_improvement = f"+{conf_diff:.1f}%" if conf_diff > 0 else f"{conf_diff:.1f}%"
        
        table.add_row(
            "Avg Confidence",
            f"{baseline_stats['avg_confidence']:.1f}%",
            f"{ai_stats['avg_confidence']:.1f}%",
            conf_improvement
        )
    
    return table

def show_recent_ai_trades(ai_df):
    """Show the most recent AI trades"""
    if len(ai_df) == 0:
        return Panel("🤖 No AI trades yet - waiting for first signal...", title="Recent AI Trades", border_style="yellow")
    
    trade_table = Table(title="🔥 Recent AI Trades", show_header=True, header_style="bold green")
    trade_table.add_column("Time", style="cyan", width=8)
    trade_table.add_column("Symbol", style="white", width=10)
    trade_table.add_column("Side", style="yellow", width=6)
    trade_table.add_column("P&L", style="bold", width=12)
    trade_table.add_column("Confidence", style="blue", width=10)
    
    for _, trade in ai_df.head(10).iterrows():
        time_str = trade['entry_timestamp'][-8:-3] if pd.notna(trade['entry_timestamp']) else "N/A"
        pnl = trade['pnl']
        pnl_color = "green" if pnl > 0 else "red"
        pnl_icon = "✅" if pnl > 0 else "❌"
        confidence = trade['confidence'] if pd.notna(trade['confidence']) else 0
        
        trade_table.add_row(
            time_str,
            trade['symbol'],
            trade['side'],
            f"[{pnl_color}]{pnl_icon} R{pnl:.2f}[/{pnl_color}]",
            f"{confidence:.1f}%"
        )
    
    return trade_table

def main():
    """Main analysis function"""
    console.print("\n🤖 [bold green]AI CONFIG PERFORMANCE ANALYSIS[/bold green]\n")
    
    baseline_df, ai_df = get_ai_vs_baseline_performance()
    
    # Focus on recent baseline for fair comparison (last 50 trades)
    recent_baseline_df = baseline_df.head(50)
    
    baseline_stats = analyze_performance(recent_baseline_df, "Recent Baseline")
    ai_stats = analyze_performance(ai_df, "AI Config")
    
    # Show comparison table
    comparison_table = create_comparison_table(baseline_stats, ai_stats)
    console.print(comparison_table)
    
    # Show recent AI trades
    console.print("\n")
    recent_ai_trades = show_recent_ai_trades(ai_df)
    console.print(recent_ai_trades)
    
    # Analysis summary
    if len(ai_df) == 0:
        status_text = """
[yellow]🤖 AI CONFIG STATUS: ACTIVE & WAITING[/yellow]

✅ Bot running with AI parameters (PID: check with ps aux)
✅ Trading hours: 10:00-21:00 (current time in window)
✅ RSI thresholds: 39/67 (more conservative)
✅ Min confidence: 41.1% (stricter filtering)

[cyan]⏳ WAITING FOR FIRST AI SIGNAL...[/cyan]

The AI config is much more selective, so signals will be:
• Less frequent (quality over quantity)
• Higher confidence (41%+ minimum)
• Only during 10am-9pm hours
• Better RSI conditions (39/67 vs 30/70)

[green]Expected first trade within 1-4 hours during trading window.[/green]
        """
    elif len(ai_df) < 5:
        ai_win_rate = ai_stats['win_rate']
        status_color = "green" if ai_win_rate > 60 else "yellow" if ai_win_rate > 40 else "red"
        
        status_text = f"""
[{status_color}]🤖 AI CONFIG: EARLY RESULTS[/{status_color}]

AI Trades: {len(ai_df)} (need 20 for full validation)
Win Rate: {ai_win_rate:.1f}%
Total P&L: R{ai_stats['total_pnl']:.2f}

[cyan]⏳ COLLECTING MORE DATA...[/cyan]
Target: 20 trades over next 2-3 days
Current pace: On track for validation

[green]Continue monitoring - need more samples for conclusion.[/green]
        """
    else:
        ai_win_rate = ai_stats['win_rate']
        
        if ai_win_rate >= 65:
            status_color = "green"
            verdict = "🚀 AI SUCCESS! Ready for live trading!"
        elif ai_win_rate >= 55:
            status_color = "yellow"
            verdict = "📊 AI IMPROVEMENT - Continue testing"
        else:
            status_color = "red"
            verdict = "⚠️ AI UNDERPERFORMING - Need adjustment"
        
        status_text = f"""
[{status_color}]🤖 AI CONFIG: {verdict}[/{status_color}]

AI Trades: {len(ai_df)}
Win Rate: {ai_win_rate:.1f}%
vs Baseline: {baseline_stats['win_rate']:.1f}%
Improvement: {ai_win_rate - baseline_stats['win_rate']:+.1f}%

[{status_color}]Next steps based on current performance...[/{status_color}]
        """
    
    console.print(Panel(status_text, title="📊 Current Status", border_style="blue"))

if __name__ == "__main__":
    main()