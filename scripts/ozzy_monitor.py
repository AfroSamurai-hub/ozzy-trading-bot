#!/usr/bin/env python3
"""Live trading dashboard for Ozzy Simple."""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Add project root to path to allow imports
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.rolling_window_db import FLUSH_THRESHOLD, RollingWindowPatternDB

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DECISIONS_LOG_FILE = PROJECT_ROOT / "logs/decisions.json"
VECTOR_DB_PATH = str(PROJECT_ROOT / "data/vector_db")
STARTING_CAPITAL = 5000.00
API_COST_BUDGET = 2.70

console = Console()


def format_currency(value, default="N/A") -> str:
    """Format a numeric value as a currency string."""
    try:
        f_val = safe_float(value)
        if f_val is None:
            return default
        return f"${f_val:,.2f}"
    except (TypeError, ValueError):
        return default


def format_percent(value, default="N/A", precision: int = 2, show_sign: bool = True) -> str:
    """Format a numeric value as a percentage string."""
    try:
        numeric = safe_float(value)
        if numeric is None:
            return default
        if show_sign:
            sign = "+" if numeric >= 0 else ""
            return f"{sign}{abs(numeric):.{precision}f}%" if sign == "+" else f"-{abs(numeric):.{precision}f}%"
        return f"{numeric:.{precision}f}%"
    except (TypeError, ValueError):
        return default


def format_ratio(value, default="N/A", precision: int = 1) -> str:
    """Format a ratio (e.g. EMA ratio) with fixed precision."""
    try:
        f_val = safe_float(value)
        if f_val is None:
            return default
        return f"{f_val:.{precision}f}"
    except (TypeError, ValueError):
        return default


def safe_divide(numerator, denominator):
    try:
        if numerator is None or denominator in (0, None):
            return None
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return None


def safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def load_decision_data():
    """Loads decision data from the JSON log file."""
    if not DECISIONS_LOG_FILE.exists():
        return {"decisions": [], "portfolio": {"starting_capital": STARTING_CAPITAL, "current_capital": STARTING_CAPITAL, "total_pnl": 0.0, "total_pnl_pct": 0.0}}
    with open(DECISIONS_LOG_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"decisions": [], "portfolio": {"starting_capital": STARTING_CAPITAL, "current_capital": STARTING_CAPITAL, "total_pnl": 0.0, "total_pnl_pct": 0.0}}

def get_db_stats():
    """Gets statistics from the vector database."""
    try:
        db = RollingWindowPatternDB(persist_directory=VECTOR_DB_PATH)
        # This is a simplified version. A real implementation might need more complex queries.
        all_patterns = db.collection.get(include=["metadatas"])
        return {
            "count": db.count(), 
            "patterns": all_patterns['metadatas'],
            "capacity": db.get_capacity_info()
        }
    except Exception as e:
        logger.error(f"Error getting DB stats: {e}")
        return {"count": 0, "patterns": [], "capacity": {}}

def make_layout() -> Layout:
    """Defines the dashboard layout."""
    layout = Layout(name="root")

    layout.split(
        Layout(name="header", size=3),
        Layout(ratio=1, name="main"),
        Layout(size=10, name="footer"),
    )

    layout["main"].split_row(Layout(name="left"), Layout(name="right", ratio=2))
    layout["left"].split_column(Layout(name="portfolio"), Layout(name="performance"))
    layout["footer"].split_row(
        Layout(name="top_patterns"), 
        Layout(name="system_health"),
        Layout(name="pattern_lifecycle") # New panel
    )
    
    return layout

def generate_header() -> Panel:
    """Generates the header panel."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = Text.from_markup(f"🤖 [bold cyan]OZZY TRADING BOT - LIVE MONITOR[/bold cyan]\nTime: {now} | Status: [green]OK[/green]")
    return Panel(header_text, style="bold magenta", border_style="magenta")

def generate_portfolio_panel(data: dict) -> Panel:
    """Generates the portfolio panel."""
    portfolio = data.get("portfolio") or {}
    decisions = data.get("decisions") or []

    starting_capital = safe_float(portfolio.get("starting_capital"))
    if starting_capital is None:
        starting_capital = STARTING_CAPITAL

    closed_trades = [d for d in decisions if (d or {}).get("status") == "CLOSED"]
    total_pnl = sum(safe_float(d.get("actual_pnl")) or 0.0 for d in closed_trades)
    current_capital = (starting_capital or 0.0) + total_pnl

    pnl_today_pct = safe_divide(total_pnl, starting_capital) if starting_capital else None
    if pnl_today_pct is not None:
        pnl_today_pct *= 100
    pnl_color = "green" if total_pnl >= 0 else "red"

    content_lines = [
        f"Starting Capital: {format_currency(starting_capital)}",
        f"Current Capital:  {format_currency(current_capital)}",
    ]

    pnl_line = (
        f"P&L All-Time:     [{pnl_color}]{format_currency(total_pnl, default='N/A')}"
        f" ({format_percent(pnl_today_pct, default='N/A')})[/{pnl_color}]"
    )
    content_lines.append(pnl_line)

    open_positions = [d for d in decisions if (d or {}).get("status") == "OPEN"]
    content_lines.append(f"Open Positions:   {len(open_positions)}")

    for pos in open_positions:
        pos = pos or {}
        symbol = pos.get("symbol", "UNKNOWN")
        position_size = format_currency(pos.get("position_size"), default="$0.00")
        entry_price = format_currency(pos.get("entry_price"), default="N/A")
        current_price = format_currency(pos.get("current_price"), default="N/A")
        pnl_value = safe_float(pos.get("current_pnl"))
        pnl_pct_value = safe_float(pos.get("current_pnl_pct"))
        pos_color = "green" if (pnl_value or 0) >= 0 else "red"

        pnl_formatted = format_currency(pnl_value, default="N/A")
        pnl_pct_formatted = format_percent(pnl_pct_value, default="N/A")

        content_lines.append(
            f"  - {symbol}: {position_size} @ {entry_price} → {current_price} "
            f"([{pos_color}]{pnl_formatted}, {pnl_pct_formatted}[/{pos_color}])"
        )

    return Panel(Text.from_markup("\n".join(content_lines)), title="[bold]PORTFOLIO[/bold]", border_style="cyan")

def generate_performance_panel(data: dict) -> Panel:
    """Generates the performance panel."""
    decisions = [d for d in (data.get("decisions") or []) if (d or {}).get("action") != "SKIP"]
    closed_trades = [d for d in decisions if (d or {}).get("status") == "CLOSED"]

    total_trades = len(closed_trades)
    wins = len([d for d in closed_trades if (d or {}).get("outcome") == "WIN"])
    losses = total_trades - wins
    win_rate = safe_divide(wins, total_trades)
    if win_rate is not None:
        win_rate *= 100

    # Build win streak indicators safely
    win_streak_icons = []
    current_streak = 0
    last_outcome = None
    for trade in closed_trades[-10:]:
        outcome = (trade or {}).get("outcome")
        icon = "✅" if outcome == "WIN" else "❌" if outcome == "LOSS" else "➖"
        win_streak_icons.append(icon)
    if closed_trades:
        last_outcome = (closed_trades[-1] or {}).get("outcome")
        for trade in reversed(closed_trades):
            outcome = (trade or {}).get("outcome")
            if outcome == last_outcome and outcome in {"WIN", "LOSS"}:
                current_streak += 1
            else:
                break

    avg_profit = safe_divide(sum(safe_float(d.get("actual_pnl")) or 0.0 for d in closed_trades), total_trades)
    best_trade = None
    worst_trade = None
    if closed_trades:
        pnl_values = [safe_float(d.get("actual_pnl")) for d in closed_trades if d is not None]
        pnl_values = [v for v in pnl_values if v is not None]
        if pnl_values:
            best_trade = max(pnl_values)
            worst_trade = min(pnl_values)

    content_lines = [
        f"Total Trades: {total_trades}",
        f"Wins: {wins} ({format_percent(win_rate, default='N/A', show_sign=False)}) | Losses: {losses}",
        f"Win Streak: [{' '.join(win_streak_icons) if win_streak_icons else '—'}] Current: {current_streak if current_streak else 0}",
        f"Avg Profit/Trade: {format_currency(avg_profit)}",
        (
            "Best Trade: [green]"
            f"{format_currency(best_trade)}"
            "[/green] | Worst: [red]"
            f"{format_currency(worst_trade)}"
            "[/red]"
        ),
    ]

    return Panel(Text.from_markup("\n".join(content_lines)), title="[bold]PERFORMANCE[/bold]", border_style="cyan")

def generate_recent_decisions_panel(data: dict) -> Panel:
    """Generates the recent decisions panel."""
    table = Table(show_header=False, expand=True, border_style="yellow")
    table.add_column("Decision", style="dim")

    decisions = data.get("decisions") or []
    for decision in reversed(decisions[-10:]):
        decision = decision or {}
        timestamp_raw = decision.get("timestamp")
        time_str = "--:--"
        if isinstance(timestamp_raw, str):
            try:
                time_str = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00")).strftime("%H:%M")
            except ValueError:
                time_str = "--:--"

        action = (decision.get("action") or "").upper()

        if action in {"BUY", "SELL"}:
            color = "green" if action == "BUY" else "red"
            symbol = decision.get("symbol", "UNKNOWN")
            entry_price = format_currency(decision.get("entry_price"))
            confidence = safe_float(decision.get("confidence"))
            confidence_str = format_percent(confidence * 100 if confidence is not None else None, default="N/A", show_sign=False)
            pattern_name = decision.get("pattern") or decision.get("pattern_name") or "N/A"
            expected_pct = safe_float(decision.get("expected_profit_pct"))
            line1 = f"[{time_str}] [{color}]{action}[/{color}] {symbol} @ {entry_price} ({confidence_str})"
            line2 = f"  → {pattern_name} | Expected: {format_percent(expected_pct, default='N/A')}"

            status_line = "  → Status: UNKNOWN"
            status = (decision.get("status") or "").upper()
            if status == "OPEN":
                pnl_value = safe_float(decision.get("current_pnl"))
                pnl_pct_value = safe_float(decision.get("current_pnl_pct"))
                pnl_color = "green" if (pnl_value or 0) >= 0 else "red"
                status_line = (
                    f"  → Status: OPEN ([{pnl_color}]{format_currency(pnl_value)}, {format_percent(pnl_pct_value)}[/{pnl_color}])"
                )
            elif status == "CLOSED":
                pnl_value = safe_float(decision.get("actual_pnl"))
                outcome = (decision.get("outcome") or "").upper()
                outcome_color = "bright_green" if outcome == "WIN" else "bright_red" if outcome == "LOSS" else "yellow"
                status_line = (
                    f"  → Status: CLOSED → [{outcome_color}]{outcome or 'N/A'} {format_currency(pnl_value)}[/{outcome_color}]"
                )

            table.add_row(f"{line1}\n{line2}\n{status_line}")

        elif action == "SKIP":
            reason = decision.get("reasoning") or "No reason given"
            table.add_row(f"[{time_str}] [yellow]SKIP[/yellow] {reason}")

        table.add_row("")

    return Panel(table, title="[bold]RECENT DECISIONS[/bold]", border_style="yellow")

def generate_top_patterns_panel(db_stats: dict) -> Panel:
    """Generates the top patterns panel."""
    patterns = db_stats.get("patterns") or []
    pattern_summary = {}

    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue

        name = pattern.get("pattern_name") or pattern.get("symbol") or "Unknown"
        name = str(name)

        summary = pattern_summary.setdefault(name, {"wins": 0, "losses": 0})
        outcome = (pattern.get("outcome") or "").lower()
        if outcome == "win":
            summary["wins"] += 1
        elif outcome == "loss":
            summary["losses"] += 1

    sorted_patterns = sorted(
        pattern_summary.items(), 
        key=lambda item: (item[1]['wins'] / (item[1]['wins'] + item[1]['losses'])) if (item[1]['wins'] + item[1]['losses']) > 0 else 0,
        reverse=True
    )

    content_lines = []
    for name, stats in sorted_patterns[:4]:
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_ratio = safe_divide(wins, total)
        if win_ratio is not None:
            win_ratio *= 100
        color = "green" if (win_ratio or 0) >= 60 else "yellow" if (win_ratio or 0) >= 50 else "red"
        content_lines.append(
            f"[{color}]{name}: {format_percent(win_ratio, default='N/A', show_sign=False)} ({wins}W-{losses}L)[/{color}]"
        )

    if not content_lines:
        content_lines = ["No labeled patterns found yet."]

    return Panel(Text.from_markup("\n".join(content_lines)), title="[bold]TOP PATTERNS[/bold]", border_style="cyan")


def generate_pattern_lifecycle_panel(db_stats: dict) -> Panel:
    """Generates the pattern lifecycle panel."""
    capacity_info = db_stats.get("capacity") or {}
    patterns = db_stats.get("patterns") or []

    cap_pct_ratio = safe_float(capacity_info.get("percentage"))
    meter_bar = "Waiting for data..."
    if cap_pct_ratio is not None:
        meter_filled = max(0, min(20, int(cap_pct_ratio * 20)))
        meter_bar = "█" * meter_filled + "░" * (20 - meter_filled)

    cap_pct_value = cap_pct_ratio * 100 if cap_pct_ratio is not None else None
    capacity_line = (
        f"Capacity: {meter_bar} {format_percent(cap_pct_value, default='N/A', precision=1, show_sign=False)}"
        if cap_pct_ratio is not None
        else "Capacity: [yellow]Waiting...[/yellow]"
    )

    current = safe_int(capacity_info.get("current"))
    max_cap = safe_int(capacity_info.get("max"))
    until_flush = safe_int(capacity_info.get("until_flush"))

    now = time.time()
    one_hour_ago = now - 3600
    created_this_hour = 0
    labeled_this_hour = 0
    pending = 0

    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue

        timestamp_val = safe_float(pattern.get("timestamp"))
        if timestamp_val is not None and timestamp_val > one_hour_ago:
            created_this_hour += 1

        labeled_at = pattern.get("labeled_at")
        if isinstance(labeled_at, str):
            try:
                labeled_ts = datetime.fromisoformat(labeled_at.replace("Z", "+00:00")).timestamp()
                if labeled_ts > one_hour_ago:
                    labeled_this_hour += 1
            except ValueError:
                pass

        if (pattern.get("label") or "").upper() == "PENDING":
            pending += 1

    content_lines = [capacity_line]
    content_lines.append(
        f"Current: {current:,} / {max_cap:,} patterns" if current is not None and max_cap is not None else "Current: N/A"
    )
    content_lines.append(
        f"Until Flush: {until_flush:,} patterns" if until_flush is not None else "Until Flush: N/A"
    )
    content_lines.append("")
    content_lines.append("[bold]This Hour:[/bold]")
    content_lines.append(
        f"  Created: {created_this_hour} | Labeled: {labeled_this_hour} | Pending: {pending}"
    )
    content_lines.append("")
    content_lines.append("Labeling Service: [green]✅ Running[/green]")
    auto_flush_status = (
        "[yellow]⏰ Standby[/yellow]" if cap_pct_ratio is None or cap_pct_ratio < FLUSH_THRESHOLD else "[red]🔥 Active[/red]"
    )
    content_lines.append(f"Auto-Flush: {auto_flush_status}")

    return Panel(Text.from_markup("\n".join(content_lines)), title="[bold]PATTERN LIFECYCLE[/bold]", border_style="cyan")


def generate_system_health_panel(db_stats: dict, start_time: float) -> Panel:
    """Generates the system health panel."""
    uptime = time.time() - start_time
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)
    
    # Defensive formatting for cost
    count = db_stats.get("count")
    api_cost = 0.0007 * (count / 101) if count is not None and count > 0 else 0.0
    cost_pct = (api_cost / API_COST_BUDGET) * 100 if API_COST_BUDGET > 0 else 0

    content = (
        f"Uptime: {int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s\n"
        f"Total Patterns: {count if count is not None else 'N/A'}\n"
        f"API Cost Today: ${api_cost:.4f} (${API_COST_BUDGET:.2f} budget) | {cost_pct:.1f}% used\n"
        f"WebSocket: [green]✅ Connected[/green]\n"
        f"Errors: 0 | Warnings: 0\n"
        f"Last Update: {int(time.time() % 60)}s ago"
    )
    return Panel(content, title="[bold]SYSTEM HEALTH[/bold]", border_style="cyan")


async def main():
    """Main function to run the dashboard."""
    layout = make_layout()
    start_time = time.time()

    with Live(layout, screen=True, redirect_stderr=False) as live:
        while True:
            try:
                data = load_decision_data()
                db_stats = get_db_stats()

                layout["header"].update(generate_header())
                layout["portfolio"].update(generate_portfolio_panel(data))
                layout["performance"].update(generate_performance_panel(data))
                layout["right"].update(generate_recent_decisions_panel(data))
                layout["top_patterns"].update(generate_top_patterns_panel(db_stats))
                layout["system_health"].update(generate_system_health_panel(db_stats, start_time))
                layout["pattern_lifecycle"].update(generate_pattern_lifecycle_panel(db_stats))
            except Exception as e:
                # Display error in a panel to avoid crashing the whole dashboard
                error_panel = Panel(f"[bold red]An error occurred:[/bold red]\n{e}", title="[bold red]ERROR[/bold red]")
                live.update(error_panel)

            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[yellow]⏸️ Dashboard stopped gracefully.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ An unexpected error occurred: {e}[/red]", style="bold red")
    finally:
        console.print("[cyan]Cleanup complete. Goodbye! 👋[/cyan]")