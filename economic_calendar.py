#!/usr/bin/env python3
"""
Hermes Economic Calendar Gate
==============================
Protects the bot from high-volatility macro events (FOMC, CPI, NFP, etc.)
by adjusting risk parameters or halting new trades during event windows.

Actions:
    no_new_trades  → block all new signals within the window
    reduce_risk    → cut risk per trade to 25% of normal
    widen_sl       → increase SL multiplier from 5x to 8x ATR
    no_action      → trade normally
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

CALENDAR_PATH = os.path.join(os.path.dirname(__file__), "economic_calendar.json")

# Default multipliers
DEFAULT_SL_MULT = 1.0   # 1.0 means "use asset default"; >1.0 is absolute override
DEFAULT_RISK_MULT = 1.0

# Action-specific overrides
# sl_mult: 1.0 = use asset default; 8.0 = override to 8x ATR
ACTION_OVERRIDES = {
    "no_new_trades": {"sl_mult": 1.0, "risk_mult": 0.0,  "allows_trading": False},
    "reduce_risk":   {"sl_mult": 1.0, "risk_mult": 0.25, "allows_trading": True},
    "widen_sl":      {"sl_mult": 8.0, "risk_mult": 1.0,  "allows_trading": True},
    "no_action":     {"sl_mult": 1.0, "risk_mult": 1.0,  "allows_trading": True},
}


def load_calendar() -> dict:
    """Load economic calendar from JSON."""
    if not os.path.exists(CALENDAR_PATH):
        return {"events": [], "default_actions": {}}
    try:
        with open(CALENDAR_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"events": [], "default_actions": {}}


def _parse_event_dt(event: dict) -> datetime:
    """Parse event date+time into a timezone-aware UTC datetime."""
    dt_str = f"{event['date']} {event['time']}"
    # Calendar times are US Eastern (ET) for macro events
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    # ET is UTC-4 or UTC-5; we approximate with UTC-4 (EDT) for simplicity
    # since the window is wide enough that 1 hour offset doesn't matter
    dt = dt.replace(tzinfo=timezone(timedelta(hours=-4)))
    return dt.astimezone(timezone.utc)


def check_upcoming_events(hours_ahead: float = 4.0, hours_behind: float = 2.0) -> list[dict]:
    """Return events whose window overlaps with the current time."""
    calendar = load_calendar()
    events = calendar.get("events", [])
    now = datetime.now(timezone.utc)
    active = []
    for ev in events:
        ev_dt = _parse_event_dt(ev)
        window = timedelta(hours=ev.get("window_hours", 2))
        # Window: X hours BEFORE event + X hours AFTER event
        start = ev_dt - window
        end = ev_dt + window
        if start <= now <= end:
            active.append(ev)
    return active


def get_current_action() -> str:
    """Return the most restrictive action currently in effect."""
    active = check_upcoming_events()
    if not active:
        return "no_action"
    # Priority: no_new_trades > reduce_risk > widen_sl > no_action
    priority = {"no_new_trades": 3, "reduce_risk": 2, "widen_sl": 1, "no_action": 0}
    best = max(active, key=lambda e: priority.get(e.get("action", "no_action"), 0))
    return best.get("action", "no_action")


def get_active_event() -> dict | None:
    """Return the event causing the most restrictive action currently in effect."""
    active = check_upcoming_events()
    if not active:
        return None
    priority = {"no_new_trades": 3, "reduce_risk": 2, "widen_sl": 1, "no_action": 0}
    best = max(active, key=lambda e: priority.get(e.get("action", "no_action"), 0))
    return best


def is_trading_allowed() -> bool:
    """True if no 'no_new_trades' action is active."""
    action = get_current_action()
    return ACTION_OVERRIDES.get(action, {}).get("allows_trading", True)


def get_sl_multiplier() -> float:
    """Return SL multiplier.
    1.0  → use asset default (e.g. 1.5x ATR)
    8.0  → absolute override to 8x ATR (widen_sl)
    """
    action = get_current_action()
    return ACTION_OVERRIDES.get(action, {}).get("sl_mult", DEFAULT_SL_MULT)


def get_risk_multiplier() -> float:
    """Return risk multiplier adjustment (1.0 = normal, 0.25 = reduced, 0.0 = halted)."""
    action = get_current_action()
    return ACTION_OVERRIDES.get(action, {}).get("risk_mult", DEFAULT_RISK_MULT)


def get_next_event() -> dict | None:
    """Return the nearest upcoming event (even if outside current window)."""
    calendar = load_calendar()
    events = calendar.get("events", [])
    now = datetime.now(timezone.utc)
    future = []
    for ev in events:
        ev_dt = _parse_event_dt(ev)
        if ev_dt >= now:
            future.append((ev_dt, ev))
    if not future:
        return None
    future.sort(key=lambda x: x[0])
    return future[0][1]


def format_event_for_telegram(event: dict | None) -> str:
    """Human-readable event description for Telegram."""
    if event is None:
        return "No upcoming events"
    ev_dt = _parse_event_dt(event)
    time_str = ev_dt.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"<b>{event.get('event', 'Unknown')}</b> ({event.get('impact', 'MEDIUM')})\n"
        f"Time: {time_str}\n"
        f"Action: {event.get('action', 'no_action')}"
    )
