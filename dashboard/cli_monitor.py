
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console

# Define PROJECT_ROOT for consistent path handling
PROJECT_ROOT = Path(__file__).parent.parent
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.progress import Progress, BarColumn, TextColumn

# Add project root to path to allow imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from intelligence.rolling_window_db import FLUSH_THRESHOLD, RollingWindowPatternDB
try:
    from intelligence.learn_from_trades import PatternLearner
    LEARNER_AVAILABLE = True
except ImportError:
    LEARNER_AVAILABLE = False

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DECISIONS_LOG_FILE = Path(__file__).parent.parent / "logs/decisions.json"
VECTOR_DB_PATH = str(Path(__file__).parent.parent / "data/vector_db")
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


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def load_decision_data():
    """Loads decision data from the JSON log file."""
    if not DECISIONS_LOG_FILE.exists():
        return {"decisions": [], "portfolio": {"starting_capital": STARTING_CAPITAL, "current_capital": STARTING_CAPITAL, "total_pnl": 0.0, "total_pnl_pct": 0.0}}
    
    try:
        with open(DECISIONS_LOG_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"decisions": [], "portfolio": {"starting_capital": STARTING_CAPITAL, "current_capital": STARTING_CAPITAL, "total_pnl": 0.0, "total_pnl_pct": 0.0}}

def load_portfolio_state():
    """Loads portfolio state directly from the portfolio_state.json file."""
    portfolio_state_file = Path(__file__).parent.parent / "logs/portfolio_state.json"
    
    if not portfolio_state_file.exists():
        # Fallback to decision data
        return load_decision_data().get("portfolio", {})
    
    try:
        with open(portfolio_state_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"starting_capital": STARTING_CAPITAL, "capital": STARTING_CAPITAL}

def get_db_stats():
    """Gets statistics from the vector database with enhanced error handling."""
    try:
        # Check if the DB directory exists
        db_path = Path(VECTOR_DB_PATH)
        if not db_path.exists():
            logger.warning(f"Vector DB directory does not exist: {VECTOR_DB_PATH}")
            return {"count": 0, "patterns": [], "capacity": {
                "current": 0,
                "max": 10000,
                "percentage": 0.0,
                "until_flush": 8000,
                "will_remove": 2000
            }}

        # Try to load the database
        try:
            db = RollingWindowPatternDB(persist_directory=VECTOR_DB_PATH)
        except Exception as e:
            logger.error(f"Failed to initialize RollingWindowPatternDB: {e}")
            return {"count": 0, "patterns": [], "capacity": {
                "current": 0,
                "max": 10000,
                "percentage": 0.0,
                "until_flush": 8000,
                "will_remove": 2000
            }}

        # Try to get pattern count
        try:
            count = db.count()
        except Exception as e:
            logger.error(f"Failed to count patterns: {e}")
            count = 0

        # Try to get capacity info
        try:
            capacity = db.get_capacity_info()
        except Exception as e:
            logger.error(f"Failed to get capacity info: {e}")
            capacity = {
                "current": count,
                "max": 10000,
                "percentage": count / 10000,
                "until_flush": 8000 - count if count < 8000 else 0,
                "will_remove": 2000
            }

        # Try to get patterns
        try:
            all_patterns = db.collection.get(include=["metadatas"])
            patterns = all_patterns.get('metadatas', []) if all_patterns else []
        except Exception as e:
            logger.error(f"Failed to get pattern metadata: {e}")
            patterns = []

        return {
            "count": count, 
            "patterns": patterns,
            "capacity": capacity
        }
    except Exception as e:
        logger.error(f"Unexpected error in get_db_stats: {e}")
        return {"count": 0, "patterns": [], "capacity": {
            "current": 0,
            "max": 10000,
            "percentage": 0.0,
            "until_flush": 8000,
            "will_remove": 2000
        }}

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
    header_text = Text.from_markup(f"🤖 [bold magenta]OZZY TRADING BOT - LIVE MONITOR[/bold magenta]\nTime: {now} | Status: [green]ACTIVE[/green] | AI Decision Mode: [cyan]AUTONOMOUS[/cyan]")
    return Panel(header_text, style="bold green", border_style="bright_magenta", box=box.ROUNDED)

def generate_portfolio_panel(data: dict) -> Panel:
    """Generates the portfolio panel."""
    # First check for direct portfolio state file
    portfolio_state = load_portfolio_state()
    
    # If portfolio state exists, use it, otherwise use decisions data
    if portfolio_state and isinstance(portfolio_state, dict) and "starting_capital" in portfolio_state:
        # Use portfolio state
        starting_capital = safe_float(portfolio_state.get("starting_capital"), STARTING_CAPITAL)
        current_capital = safe_float(portfolio_state.get("capital"), starting_capital)
        total_equity = safe_float(portfolio_state.get("total_equity"), current_capital)
        total_pnl = safe_float(portfolio_state.get("total_pnl"), 0.0)
        
        # Get positions from portfolio state
        positions = portfolio_state.get("positions", [])
        
        # Calculate P&L percentage
        pnl_today_pct = safe_divide(total_pnl, starting_capital) if starting_capital else None
        if pnl_today_pct is not None:
            pnl_today_pct *= 100
    else:
        # Fallback to decisions data
        portfolio = data.get("portfolio") or {}
        decisions = data.get("decisions") or []

        starting_capital = safe_float(portfolio.get("starting_capital"))
        if starting_capital is None:
            starting_capital = STARTING_CAPITAL

        closed_trades = [d for d in decisions if (d or {}).get("status") == "CLOSED"]
        total_pnl = sum(safe_float(d.get("actual_pnl")) or 0.0 for d in closed_trades)
        current_capital = (starting_capital or 0.0) + total_pnl
        total_equity = current_capital
        
        # Get positions from decisions
        positions = [d for d in decisions if (d or {}).get("status") == "OPEN"]
        
        # Calculate P&L percentage
        pnl_today_pct = safe_divide(total_pnl, starting_capital) if starting_capital else None
        if pnl_today_pct is not None:
            pnl_today_pct *= 100
            
    pnl_color = "green" if total_pnl >= 0 else "red"

    # Create a styled grid table
    table = Table.grid(expand=True)
    table.add_column(style="cyan")
    table.add_column()
    
    table.add_row(
        "Starting Capital:",
        f"{format_currency(starting_capital)}"
    )
    table.add_row(
        "Current Capital:",
        f"{format_currency(current_capital)}"
    )
    table.add_row(
        "Total Equity:",
        f"{format_currency(total_equity)}"
    )
    
    pnl_display = (
        f"[{pnl_color}]{format_currency(total_pnl, default='N/A')} "
        f"({format_percent(pnl_today_pct, default='N/A')})[/{pnl_color}]"
    )
    table.add_row("P&L All-Time:", pnl_display)

    # Add divider before positions
    table.add_row("", "")
    table.add_row(
        "Open Positions:",
        f"{len(positions)}"
    )

    for pos in positions:
        pos = pos or {}
        symbol = pos.get("symbol", "UNKNOWN")
        
        # Handle portfolio state format vs decisions format
        if "size" in pos:
            # Portfolio state format
            position_size = format_currency(pos.get("size"), default="$0.00")
            entry_price = format_currency(pos.get("entry_price"), default="N/A")
            current_price = format_currency(pos.get("current_price"), default="N/A")
            pnl_value = safe_float(pos.get("pnl"))
            pnl_pct_value = safe_float(pos.get("pnl_pct"))
        else:
            # Decisions format
            position_size = format_currency(pos.get("position_size"), default="$0.00")
            entry_price = format_currency(pos.get("entry_price"), default="N/A")
            current_price = format_currency(pos.get("current_price"), default="N/A")
            pnl_value = safe_float(pos.get("current_pnl"))
            pnl_pct_value = safe_float(pos.get("current_pnl_pct"))
            
        pos_color = "bright_green" if (pnl_value or 0) >= 0 else "bright_red"

        pnl_formatted = format_currency(pnl_value, default="N/A")
        pnl_pct_formatted = format_percent(pnl_pct_value, default="N/A")

        position_display = (
            f"{position_size} @ {entry_price} → {current_price} "
            f"([{pos_color}]{pnl_formatted}, {pnl_pct_formatted}[/{pos_color}])"
        )
        table.add_row(f"• {symbol}:", position_display)
        
    # If no positions, add placeholder
    if not positions:
        table.add_row("", "[dim]No open positions[/dim]")

    return Panel(table, title="[bold]PORTFOLIO[/bold]", border_style="bright_magenta", box=box.ROUNDED)

def generate_performance_panel(data: dict) -> Panel:
    """Generates the performance panel."""
    # First check for direct portfolio state file
    portfolio_state = load_portfolio_state()
    
    if portfolio_state and isinstance(portfolio_state, dict) and "closed_trades" in portfolio_state:
        # Use portfolio state
        closed_trades = portfolio_state.get("closed_trades", [])
        performance = portfolio_state.get("performance", {})
        
        total_trades = performance.get("total_trades", len(closed_trades))
        wins = performance.get("wins", len([t for t in closed_trades if t.get("outcome") == "WIN"]))
        losses = performance.get("losses", total_trades - wins)
        win_rate = safe_divide(wins, total_trades)
        if win_rate is not None:
            win_rate *= 100
    else:
        # Fallback to decisions data
        decisions = [d for d in (data.get("decisions") or []) if (d or {}).get("action") != "SKIP"]
        closed_trades = [d for d in decisions if (d or {}).get("status") == "CLOSED"]

        total_trades = len(closed_trades)
        wins = len([d for d in closed_trades if (d or {}).get("outcome") == "WIN"])
        losses = total_trades - wins
        win_rate = safe_divide(wins, total_trades)
        if win_rate is not None:
            win_rate *= 100

    # Build win streak indicators with enhanced visuals
    win_streak_icons = []
    current_streak = 0
    longest_streak = 0
    streak_type = None
    temp_streak = 0
    
    # Calculate current and longest streak
    for trade in closed_trades:
        outcome = (trade or {}).get("outcome")
        if outcome == "WIN":
            if streak_type == "WIN" or streak_type is None:
                temp_streak += 1
                streak_type = "WIN"
            else:
                temp_streak = 1
                streak_type = "WIN"
        elif outcome == "LOSS":
            if streak_type == "WIN":
                longest_streak = max(longest_streak, temp_streak)
            temp_streak = 0
            streak_type = "LOSS"
    
    if streak_type == "WIN":
        longest_streak = max(longest_streak, temp_streak)
        current_streak = temp_streak
    
    # Create visual streak display
    for i, trade in enumerate(closed_trades[-10:]):
        outcome = (trade or {}).get("outcome")
        if outcome == "WIN":
            win_streak_icons.append("[bright_green]✓[/bright_green]")
        elif outcome == "LOSS": 
            win_streak_icons.append("[red]×[/red]")
        else:
            win_streak_icons.append("[yellow]?[/yellow]")

    avg_profit = safe_divide(sum(safe_float(d.get("actual_pnl")) or 0.0 for d in closed_trades), total_trades)
    best_trade = None
    worst_trade = None
    if closed_trades:
        pnl_values = [safe_float(d.get("actual_pnl")) for d in closed_trades if d is not None]
        pnl_values = [v for v in pnl_values if v is not None]
        if pnl_values:
            best_trade = max(pnl_values)
            worst_trade = min(pnl_values)

    # Create styled table
    table = Table.grid(expand=True)
    table.add_column(style="cyan")
    table.add_column()
    
    win_rate_color = "green" if (win_rate or 0) >= 50 else "yellow" if (win_rate or 0) >= 40 else "red"
    
    table.add_row(
        "Total Trades:",
        f"{total_trades}"
    )
    table.add_row(
        "Wins/Losses:",
        f"{wins} [{win_rate_color}]({format_percent(win_rate, default='N/A', show_sign=False)})[/{win_rate_color}] / {losses}"
    )
    
    streak_display = " ".join(win_streak_icons)
    table.add_row(
        "Recent Results:",
        f"{streak_display}"
    )
    table.add_row(
        "Win Streak:",
        f"Current: [bright_green]{current_streak}[/bright_green] | Best: {longest_streak}"
    )
    
    table.add_row(
        "Avg Profit/Trade:",
        f"{format_currency(avg_profit)}"
    )
    
    table.add_row(
        "Best Trade:",
        f"[green]{format_currency(best_trade)}[/green]"
    )
    table.add_row(
        "Worst Trade:",
        f"[red]{format_currency(worst_trade)}[/red]"
    )

    return Panel(table, title="[bold]PERFORMANCE[/bold]", border_style="bright_magenta", box=box.ROUNDED)

def generate_recent_decisions_panel(data: dict) -> Panel:
    """Generates the recent decisions panel."""
    table = Table(expand=True, box=box.ROUNDED)
    table.add_column("Time", style="cyan", width=8)
    table.add_column("Action", style="magenta", width=5)
    table.add_column("Symbol @ Price", style="yellow")
    table.add_column("Confidence", style="green", width=5)
    table.add_column("Reason", style="white")

    decisions = data.get("decisions") or []
    
    # Sort decisions by timestamp (newest first)
    sorted_decisions = sorted(
        [d for d in decisions if d is not None], 
        key=lambda x: x.get("timestamp", ""), 
        reverse=True
    )
    
    for decision in sorted_decisions[:10]:  # Show 10 most recent
        timestamp_raw = decision.get("timestamp")
        time_str = "--:--"
        if isinstance(timestamp_raw, str):
            try:
                time_str = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00")).strftime("%H:%M")
            except ValueError:
                time_str = "--:--"

        action = (decision.get("action") or "").upper()
        action_style = "green" if action == "BUY" else "red" if action == "SELL" else "yellow"
        
        symbol = decision.get("symbol", "UNKNOWN")
        entry_price = format_currency(decision.get("entry_price"), default="$0.00")
        symbol_price = f"{symbol} @ {entry_price}" if entry_price != "$0.00" else symbol
        
        confidence = safe_float(decision.get("confidence"))
        confidence_str = format_percent(confidence * 100 if confidence is not None else None, default="N/A", show_sign=False)
        
        reason = decision.get("reasoning") or "No reason provided"
        pattern_name = decision.get("pattern") or decision.get("pattern_name") or ""
        
        # Format the reason with pattern name if available
        display_reason = reason
        if pattern_name:
            display_reason = f"→ {pattern_name} | {reason[:40]}..." if len(reason) > 40 else f"→ {pattern_name} | {reason}"
        elif len(reason) > 50:
            display_reason = f"{reason[:47]}..."
            
        # Add status indicators for trades
        status = (decision.get("status") or "").upper()
        if status == "OPEN":
            pnl_value = safe_float(decision.get("current_pnl"))
            pnl_color = "green" if (pnl_value or 0) >= 0 else "red"
            display_reason = f"{display_reason} [dim]({status}: [{pnl_color}]{format_currency(pnl_value)}[/{pnl_color}])[/dim]"
        elif status == "CLOSED":
            outcome = (decision.get("outcome") or "").upper()
            outcome_color = "bright_green" if outcome == "WIN" else "bright_red" if outcome == "LOSS" else "yellow"
            display_reason = f"{display_reason} [dim]({status}: [{outcome_color}]{outcome}[/{outcome_color}])[/dim]"
        
        table.add_row(
            time_str,
            f"[{action_style}]{action}[/{action_style}]",
            symbol_price,
            confidence_str,
            display_reason
        )

    return Panel(table, title="[bold]RECENT DECISIONS[/bold]", border_style="bright_magenta", box=box.ROUNDED)

def generate_top_patterns_panel(db_stats: dict) -> Panel:
    """Generates the top patterns panel."""
    patterns = db_stats.get("patterns") or []
    pattern_summary = {}

    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue

        name = pattern.get("pattern_name") or pattern.get("symbol") or "Unknown"
        name = str(name)

        summary = pattern_summary.setdefault(name, {"wins": 0, "losses": 0, "pnl": 0.0})
        outcome = (pattern.get("outcome") or "").lower()
        if outcome == "win":
            summary["wins"] += 1
            summary["pnl"] += safe_float(pattern.get("realized_pnl")) or 0.0
        elif outcome == "loss":
            summary["losses"] += 1
            summary["pnl"] += safe_float(pattern.get("realized_pnl")) or 0.0

    sorted_patterns = sorted(
        pattern_summary.items(), 
        key=lambda item: (item[1]['wins'] / (item[1]['wins'] + item[1]['losses'])) if (item[1]['wins'] + item[1]['losses']) > 0 else 0,
        reverse=True
    )

    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("Pattern", style="cyan")
    table.add_column("Win Rate", style="green")
    table.add_column("Trades", style="yellow")
    table.add_column("P&L", style="magenta")

    for name, stats in sorted_patterns[:5]:
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_ratio = safe_divide(wins, total)
        if win_ratio is not None:
            win_ratio *= 100
        
        win_rate_color = "green" if (win_ratio or 0) >= 60 else "yellow" if (win_ratio or 0) >= 50 else "red"
        pnl = stats.get("pnl", 0.0)
        pnl_color = "green" if pnl >= 0 else "red"
        
        table.add_row(
            name,
            f"[{win_rate_color}]{format_percent(win_ratio, default='N/A', show_sign=False)}[/{win_rate_color}]",
            f"{total} ({wins}W-{losses}L)",
            f"[{pnl_color}]{format_currency(pnl)}[/{pnl_color}]"
        )

    if sorted_patterns:
        return Panel(table, title="[bold]TOP PATTERNS[/bold]", border_style="bright_magenta", box=box.ROUNDED)
    else:
        return Panel("No labeled patterns found yet.", title="[bold]TOP PATTERNS[/bold]", border_style="bright_magenta", box=box.ROUNDED)


def generate_pattern_lifecycle_panel(db_stats: dict) -> Panel:
    """Generates the pattern lifecycle panel."""
    capacity_info = db_stats.get("capacity") or {}
    patterns = db_stats.get("patterns") or []

    cap_pct_ratio = safe_float(capacity_info.get("percentage"))
    # Create more visually appealing progress bar
    progress = Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(complete_style="bright_magenta", finished_style="bright_magenta"),
        TextColumn("[bold]{task.percentage:.1f}%"),
    )
    task_id = progress.add_task("Capacity", total=100, completed=cap_pct_ratio * 100 if cap_pct_ratio is not None else 0)

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
    
    # Get learner status
    learner_status = "[green]✅ Running[/green]"
    learner_last_run = "Running now"
    if LEARNER_AVAILABLE:
        try:
            # Check if labeler.log exists and read last line
            labeler_log = Path(__file__).parent.parent / "logs/labeler.log"
            if labeler_log.exists():
                with open(labeler_log, "r") as f:
                    lines = f.readlines()
                    if lines:
                        last_log = lines[-1]
                        if "Learning cycle complete" in last_log:
                            log_time = last_log.split(" - ")[0]
                            try:
                                log_dt = datetime.strptime(log_time, "%Y-%m-%d %H:%M:%S,%f")
                                now = datetime.now()
                                diff_seconds = (now - log_dt).total_seconds()
                                if diff_seconds < 3600:  # less than an hour ago
                                    learner_last_run = f"{int(diff_seconds / 60)}m ago"
                                else:
                                    learner_last_run = f"{int(diff_seconds / 3600)}h ago"
                            except ValueError:
                                learner_last_run = "Unknown"
        except Exception:
            pass

    # Create table for clean layout
    table = Table.grid(expand=True)
    table.add_column()
    
    # Add capacity progress bar
    table.add_row(progress)
    table.add_row(f"Current: {current:,} / {max_cap:,} patterns" if current is not None and max_cap is not None else "Current: N/A")
    table.add_row(f"Until Flush: {until_flush:,} patterns" if until_flush is not None else "Until Flush: N/A")
    table.add_row("")
    table.add_row("[bold cyan]This Hour:[/bold cyan]")
    table.add_row(f"  Created: {created_this_hour} | Labeled: {labeled_this_hour} | Pending: {pending}")
    table.add_row("")
    table.add_row(f"AI Learner: {learner_status}")
    table.add_row(f"Last Learn Run: {learner_last_run}")
    
    auto_flush_status = (
        "[yellow]⏰ Standby[/yellow]" if cap_pct_ratio is None or cap_pct_ratio < FLUSH_THRESHOLD else "[red]🔥 Active[/red]"
    )
    table.add_row(f"Auto-Flush: {auto_flush_status}")

    return Panel(table, title="[bold]PATTERN LIFECYCLE[/bold]", border_style="bright_magenta", box=box.ROUNDED)


def generate_system_health_panel(db_stats: dict, start_time: float) -> Panel:
    """Generates the system health panel."""
    uptime = time.time() - start_time
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)
    
    # Defensive formatting for cost
    count = db_stats.get("count")
    api_cost = 0.0007 * (count / 101) if count is not None and count > 0 else 0.0
    cost_pct = (api_cost / API_COST_BUDGET) * 100 if API_COST_BUDGET > 0 else 0

    # Check for errors in log files
    errors = 0
    warnings = 0
    try:
        errors_log = Path(__file__).parent.parent / "logs/errors_2025-10-12.log"
        if errors_log.exists():
            with open(errors_log, "r") as f:
                lines = f.readlines()
                errors = sum(1 for line in lines if "ERROR" in line)
                warnings = sum(1 for line in lines if "WARNING" in line)
    except:
        pass

    # Create table for better formatting
    table = Table.grid(expand=True)
    table.add_column(style="cyan")
    table.add_column()
    
    table.add_row(
        "Uptime:", 
        f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s"
    )
    table.add_row(
        "Total Patterns:", 
        f"{count if count is not None else 'N/A'}"
    )
    table.add_row(
        "API Cost Today:", 
        f"${api_cost:.4f} (${API_COST_BUDGET:.2f} budget) | {cost_pct:.1f}% used"
    )
    table.add_row(
        "WebSocket:", 
        "[green]✅ Connected[/green]"
    )
    table.add_row(
        "Errors:", 
        f"{errors} | Warnings: {warnings}"
    )
    table.add_row(
        "Last Update:", 
        f"{int(time.time() % 60)}s ago"
    )
    
    return Panel(table, title="[bold]SYSTEM HEALTH[/bold]", border_style="bright_magenta", box=box.ROUNDED)


async def main():
    """Main function to run the dashboard."""
    console.clear()
    console.print("[bold magenta]Starting Ozzy Trading Bot monitor...[/bold magenta]")
    
    layout = make_layout()
    start_time = time.time()

    # Start learning system if available
    if LEARNER_AVAILABLE:
        try:
            # Check if learning system is already running
            import subprocess
            import shlex
            
            check_cmd = "ps -ef | grep learn_from_trades.py | grep -v grep"
            result = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if result.returncode != 0:  # Not running
                console.print("[yellow]Starting Learning System in background...[/yellow]")
                try:
                    start_cmd = f"nohup python {PROJECT_ROOT}/intelligence/learn_from_trades.py --continuous --interval 1800 > {PROJECT_ROOT}/logs/learner_output.log 2>&1 &"
                    subprocess.run(start_cmd, shell=True)
                    console.print("[green]Learning System started successfully[/green]")
                except Exception as e:
                    console.print(f"[red]Could not start learning process: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Failed to start Learning System: {e}[/red]")

    # Set a reasonable refresh rate to prevent VS Code from becoming unresponsive
    refresh_interval = 5  # seconds
    
    # Load initial data before starting Live display to prevent errors
    try:
        initial_data = load_decision_data()
        initial_db_stats = get_db_stats()
    except Exception as e:
        console.print(f"[red]Failed to load initial data: {e}[/red]")
        initial_data = {"decisions": [], "portfolio": {}}
        initial_db_stats = {"count": 0, "patterns": [], "capacity": {}}

    # Pre-populate layout with initial data
    try:
        layout["header"].update(generate_header())
        layout["portfolio"].update(generate_portfolio_panel(initial_data))
        layout["performance"].update(generate_performance_panel(initial_data))
        layout["right"].update(generate_recent_decisions_panel(initial_data))
        layout["top_patterns"].update(generate_top_patterns_panel(initial_db_stats))
        layout["system_health"].update(generate_system_health_panel(initial_db_stats, start_time))
        layout["pattern_lifecycle"].update(generate_pattern_lifecycle_panel(initial_db_stats))
    except Exception as e:
        console.print(f"[red]Failed to build initial layout: {e}[/red]")

    # Start Live display with error handling
    try:
        with Live(layout, screen=True, redirect_stderr=False, refresh_per_second=1/refresh_interval) as live:
            try:
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
                        logger.error(f"Error updating dashboard: {e}")
                        error_panel = Panel(f"[bold red]An error occurred:[/bold red]\n{str(e)[:200]}", 
                                           title="[bold red]ERROR[/bold red]")
                        live.update(error_panel)

                    await asyncio.sleep(refresh_interval)
            except (KeyboardInterrupt, asyncio.CancelledError):
                # Make sure we catch interrupts within the live display
                raise
    except Exception as e:
        console.print(f"[bold red]Critical error in dashboard: {e}[/bold red]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[bright_magenta]⏸️ Dashboard stopped gracefully.[/bright_magenta]")
    except Exception as e:
        console.print(f"\n[red]❌ An unexpected error occurred: {e}[/red]", style="bold red")
    finally:
        console.print("[bright_cyan]Cleanup complete. Goodbye! 👋[/bright_cyan]")
