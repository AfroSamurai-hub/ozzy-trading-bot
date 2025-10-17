#!/usr/bin/env python3
"""CLI Trading Dashboard for Ozzy Simple."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Constants
DECISIONS_LOG_FILE = PROJECT_ROOT / "logs/decisions.json"
REFRESH_INTERVAL = 5  # seconds

console = Console()

def load_decisions() -> Dict[str, Any]:
    """Load all trading decisions from the log file."""
    try:
        if not DECISIONS_LOG_FILE.exists():
            # Create an empty decisions file
            os.makedirs(DECISIONS_LOG_FILE.parent, exist_ok=True)
            with open(DECISIONS_LOG_FILE, "w") as f:
                json.dump({"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}, f, indent=2)
            return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}
        
        with open(DECISIONS_LOG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}

def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to a readable format."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "Unknown"

def get_win_rate_by_pattern(decisions: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate win rates by pattern type."""
    patterns = {}
    for decision in decisions:
        pattern = decision.get("pattern", "Unknown")
        if not pattern:
            pattern = "Unknown"
        
        if pattern not in patterns:
            patterns[pattern] = {"wins": 0, "total": 0}
        
        outcome = decision.get("outcome")
        if outcome == "WIN":
            patterns[pattern]["wins"] += 1
        if outcome is not None:  # Only count completed trades
            patterns[pattern]["total"] += 1
    
    # Calculate win rates
    return {
        pattern: stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
        for pattern, stats in patterns.items()
    }

def display_dashboard():
    """Display the CLI dashboard."""
    console.clear()
    console.rule("🤖 [bold green]OZZY TRADING DASHBOARD[/bold green] 🤖")
    
    # Load trading decisions
    data = load_decisions()
    decisions = data.get("decisions", [])
    portfolio = data.get("portfolio", {"starting_capital": 5000, "current_capital": 5000})
    
    # If no decisions yet, show a message
    if not decisions:
        console.print("[yellow]No trading decisions found yet. Run the bot to start collecting data.[/yellow]")
        return
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(decisions)
    
    # Calculate key metrics
    total_decisions = len(decisions)
    buy_decisions = len([d for d in decisions if d.get("action") == "BUY"])
    sell_decisions = len([d for d in decisions if d.get("action") == "SELL"])
    skip_decisions = len([d for d in decisions if d.get("action") == "SKIP"])
    
    completed_trades = len([d for d in decisions if d.get("outcome") is not None])
    winning_trades = len([d for d in decisions if d.get("outcome") == "WIN"])
    losing_trades = len([d for d in decisions if d.get("outcome") == "LOSS"])
    
    win_rate = winning_trades / completed_trades * 100 if completed_trades > 0 else 0
    
    # Portfolio metrics
    starting_capital = portfolio.get('starting_capital', 5000)
    current_capital = portfolio.get('current_capital', 5000)
    pnl = current_capital - starting_capital
    
    # Display portfolio metrics
    portfolio_table = Table(title="Portfolio", box=box.ROUNDED)
    portfolio_table.add_column("Metric", style="cyan")
    portfolio_table.add_column("Value", style="white")
    
    portfolio_table.add_row("Starting Capital", f"${starting_capital:,.2f}")
    portfolio_table.add_row("Current Capital", f"${current_capital:,.2f}")
    
    if pnl > 0:
        portfolio_table.add_row("Total P&L", f"[green]${pnl:+,.2f}[/green]")
    elif pnl < 0:
        portfolio_table.add_row("Total P&L", f"[red]${pnl:,.2f}[/red]")
    else:
        portfolio_table.add_row("Total P&L", f"${pnl:,.2f}")
    
    # Display decision metrics
    decision_table = Table(title="Trading Summary", box=box.ROUNDED)
    decision_table.add_column("Metric", style="cyan")
    decision_table.add_column("Value", style="white")
    
    decision_table.add_row("Total Decisions", f"{total_decisions}")
    decision_table.add_row("Actions", f"Buy: {buy_decisions}, Sell: {sell_decisions}, Skip: {skip_decisions}")
    decision_table.add_row("Completed Trades", f"{completed_trades}")
    decision_table.add_row("Win/Loss", f"{winning_trades}/{losing_trades}")
    decision_table.add_row("Win Rate", f"{win_rate:.1f}%")
    
    if len(df) > 0:
        decision_table.add_row("Average Confidence", f"{df['confidence'].mean():.2f}")
    
    # Layout for the top section
    layout = Layout()
    layout.split_row(
        Layout(portfolio_table, name="portfolio"),
        Layout(decision_table, name="decisions"),
    )
    console.print(layout)
    
    # Recent decisions
    console.rule("Recent Decisions")
    
    if decisions:
        # Sort decisions by timestamp (newest first)
        sorted_decisions = sorted(
            decisions, 
            key=lambda x: x.get('timestamp', ''), 
            reverse=True
        )
        
        # Display the 5 most recent decisions
        recent = sorted_decisions[:5]
        
        # Create a table for recent decisions
        recent_table = Table(box=box.ROUNDED)
        recent_table.add_column("Time", style="cyan")
        recent_table.add_column("Action", style="green")
        recent_table.add_column("Symbol", style="white")
        recent_table.add_column("Price", style="yellow")
        recent_table.add_column("Conf", style="magenta")
        recent_table.add_column("Status", style="blue")
        recent_table.add_column("Outcome", style="cyan")
        
        for decision in recent:
            action = decision.get("action", "UNKNOWN")
            action_style = "green" if action == "BUY" else "red" if action == "SELL" else "white"
            
            outcome = decision.get("outcome", "PENDING")
            outcome_style = "green" if outcome == "WIN" else "red" if outcome == "LOSS" else "yellow"
            
            # Handle None values safely for formatting
            entry_price = decision.get('entry_price')
            entry_price_str = f"${entry_price:,.2f}" if entry_price is not None else "N/A"
            
            confidence = decision.get('confidence')
            confidence_str = f"{confidence:.2f}" if confidence is not None else "N/A"
            
            recent_table.add_row(
                format_timestamp(decision.get('timestamp', '')),
                f"[{action_style}]{action}[/{action_style}]",
                decision.get('symbol', 'UNKNOWN'),
                entry_price_str,
                confidence_str,
                decision.get('status', 'UNKNOWN'),
                f"[{outcome_style}]{outcome}[/{outcome_style}]",
            )
        
        console.print(recent_table)
    else:
        console.print("[yellow]No decisions recorded yet.[/yellow]")
    
    # Win rate by pattern
    console.rule("Win Rate by Pattern")
    win_rates_by_pattern = get_win_rate_by_pattern(decisions)
    
    if win_rates_by_pattern:
        pattern_table = Table(box=box.ROUNDED)
        pattern_table.add_column("Pattern", style="cyan")
        pattern_table.add_column("Win Rate", style="green")
        
        for pattern, win_rate in win_rates_by_pattern.items():
            pattern_table.add_row(pattern, f"{win_rate:.1f}%")
        
        console.print(pattern_table)
    else:
        console.print("[yellow]No pattern data available yet.[/yellow]")
    
    # Footer
    console.rule(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Refreshes every {REFRESH_INTERVAL}s)")

def main():
    try:
        while True:
            display_dashboard()
            time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        console.print("[yellow]Dashboard stopped.[/yellow]")

if __name__ == "__main__":
    main()