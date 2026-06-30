#!/usr/bin/env python3
"""Read-only OzzyBot ops log viewer.

This script reads systemd journal output and observer JSON files. It never
imports broker connectors and never calls exchange APIs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OBSERVER_DIR = ROOT / "observer"
DEFAULT_UNITS = (
    "ozzybot-live-micro-webhook.service",
    "ozzybot-live-micro-monitor.service",
)

TRADE_EVENTS = {
    "SIGNAL_IN",
    "APPROVED",
    "REJECTED",
    "TRADE_ROUTER",
    "MILESTONE_ORDER_PLACED",
    "EXIT_REASON_PROTECTIVE",
    "EXIT_REASON_PROTECTIVE_FINAL",
}

PROTECTION_TOKENS = (
    "PROTECTION",
    "FINALIZER",
    "VERIFY",
    "VERIFIED",
    "REPAIR",
    "SL_",
    "TP_",
    "ROUNDTRIP_GUARD",
)


def parse_json_log_line(line: str) -> dict[str, Any] | None:
    """Extract a JSON log object from a raw journal line."""
    start = line.find("{")
    if start < 0:
        return None
    candidate = line[start:].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _stringify(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return summarize_detail(value)
    return str(value)


def summarize_detail(value: Any, *, max_items: int = 5) -> str:
    """Return compact detail text for nested JSON values."""
    if value is None:
        return "-"
    if isinstance(value, dict):
        parts = []
        for idx, (key, val) in enumerate(value.items()):
            if idx >= max_items:
                parts.append("...")
                break
            if isinstance(val, (dict, list)):
                parts.append(f"{key}={type(val).__name__}")
            else:
                parts.append(f"{key}={_stringify(val)}")
        return ", ".join(parts) if parts else "-"
    if isinstance(value, list):
        return f"{len(value)} items"
    return _stringify(value)


def event_time(event: dict[str, Any]) -> str:
    return _stringify(event.get("ts") or event.get("created_at") or event.get("time"))


def compact_time(value: str) -> str:
    if value in ("", "-"):
        return "-"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%H:%M:%S")
    except ValueError:
        pass
    if " " in text:
        return text.split(" ")[-1][:8]
    if "T" in text:
        return text.split("T")[-1][:8]
    return text[:8]


def parse_since_cutoff(since: str | None) -> datetime | None:
    """Parse simple journal-style relative since strings for observer files."""
    if not since:
        return None
    raw = since.strip().lower()
    match = re.fullmatch(r"(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago", raw)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("minute"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("hour"):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        return datetime.now(timezone.utc) - delta
    try:
        parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def event_datetime(event: dict[str, Any]) -> datetime | None:
    raw = event.get("created_at") or event.get("ts") or event.get("time")
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_auto_action(action: dict[str, Any]) -> dict[str, Any]:
    row = dict(action)
    row.setdefault("event", "AUTO_PROTECT_ACTION")
    row.setdefault("ts", row.get("created_at"))
    row.setdefault("enabled", "-")
    row.setdefault("open_positions", "-")
    row.setdefault("candidates_created", "-")
    row.setdefault("live_auto_protect_enabled", row.get("live_auto_protect_enabled", "-"))
    return row


def read_observer_auto_actions(
    observer_dir: Path = OBSERVER_DIR, since_cutoff: datetime | None = None
) -> list[dict[str, Any]]:
    path = observer_dir / "auto_protect_actions.json"
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    rows = [normalize_auto_action(row) for row in payload if isinstance(row, dict)]
    if since_cutoff is None:
        return rows
    return [row for row in rows if (event_datetime(row) is None or event_datetime(row) >= since_cutoff)]


def journal_command(units: Iterable[str], since: str | None, follow: bool) -> list[str]:
    cmd = ["journalctl", "--user"]
    for unit in units:
        cmd.extend(["-u", unit])
    if since:
        cmd.extend(["--since", since])
    if follow:
        cmd.append("-f")
    else:
        cmd.append("--no-pager")
    return cmd


def iter_journal_events(units: Iterable[str], since: str | None, follow: bool) -> Iterator[dict[str, Any]]:
    proc = subprocess.Popen(
        journal_command(units, since, follow),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            event = parse_json_log_line(line)
            if event is not None:
                yield event
    finally:
        if not follow and proc.poll() is None:
            proc.terminate()


def _event_name(event: dict[str, Any]) -> str:
    return str(event.get("event") or "").upper()


def matches_view(event: dict[str, Any], view: str) -> bool:
    name = _event_name(event)
    if view == "auto-protect":
        return name in {"AUTO_PROTECT_HEARTBEAT", "AUTO_PROTECT_ACTION"} or name.startswith("AUTO_PROTECT_")
    if view == "trades":
        return name in TRADE_EVENTS
    if view == "protection":
        return any(token in name for token in PROTECTION_TOKENS) or "protection_detail" in event
    return False


def matches_symbol(event: dict[str, Any], symbol: str | None) -> bool:
    if not symbol:
        return True
    wanted = symbol.upper()
    if str(event.get("symbol") or "").upper() == wanted:
        return True
    nested = event.get("protection_detail")
    return isinstance(nested, dict) and str(nested.get("symbol") or "").upper() == wanted


def event_mode(event: dict[str, Any]) -> str:
    mode = str(event.get("mode") or event.get("execution_mode") or "").strip().upper()
    if mode in {"LIVE", "TESTNET"}:
        return mode
    if mode in {"LIVE_MICRO", "LIVE-MICRO"}:
        return "LIVE"
    if mode in {"STANDARD_TESTNET", "STANDARD-TESTNET"}:
        return "TESTNET"
    execution_mode = str(event.get("execution_mode") or "").strip().lower()
    if execution_mode in {"live", "live_micro"}:
        return "LIVE"
    if execution_mode in {"testnet", "standard_testnet"}:
        return "TESTNET"
    return "-"


def matches_mode(event: dict[str, Any], mode: str) -> bool:
    wanted = mode.upper()
    if wanted == "ALL":
        return True
    return event_mode(event) == wanted


def is_live_disabled_heartbeat(event: dict[str, Any]) -> bool:
    return (
        _event_name(event) == "AUTO_PROTECT_HEARTBEAT"
        and event_mode(event) == "LIVE"
        and event.get("enabled") is False
        and str(event.get("reason") or "") == "live_auto_protect_disabled"
    )


def is_unsafe_event(event: dict[str, Any]) -> bool:
    detail = event.get("protection_detail") if isinstance(event.get("protection_detail"), dict) else event
    return any(
        (
            detail.get("has_sl") is False,
            detail.get("protected") is False,
            event.get("executed") is True,
            event_mode(event) == "LIVE",
            event.get("dry_run") is False,
            event.get("live_auto_protect_enabled") is True,
        )
    )


def passes_display_filters(event: dict[str, Any], args: argparse.Namespace) -> bool:
    if not matches_view(event, args.view) or not matches_symbol(event, args.symbol):
        return False
    if not matches_mode(event, args.mode):
        return False
    if args.view == "auto-protect" and not args.show_live_disabled and is_live_disabled_heartbeat(event):
        return False
    if args.errors_only and not is_unsafe_event(event):
        return False
    return True


def row_for_event(event: dict[str, Any], view: str, *, wide: bool = False) -> list[str]:
    max_detail = 1000 if wide else 80
    if view == "auto-protect":
        return [
            compact_time(event_time(event)),
            _stringify(event.get("mode")),
            _stringify(event.get("enabled")),
            _stringify(event.get("dry_run")),
            _stringify(event.get("cash_ratchet_enabled")),
            _stringify(event.get("live_auto_protect_enabled")),
            _stringify(event.get("open_positions")),
            _stringify(event.get("candidates_created")),
            _stringify(event.get("reason")),
        ]
    if view == "trades":
        return [
            compact_time(event_time(event)),
            _stringify(event.get("event")),
            _stringify(event.get("symbol")),
            _stringify(event.get("signal")),
            _stringify(event.get("setup_grade")),
            _stringify(event.get("strategy_label")),
            _stringify(event.get("entry_setup_label")),
            _stringify(event.get("risk_dollars")),
            _stringify(event.get("reason")),
            _stringify(event.get("exit_reason")),
        ]
    detail = event.get("protection_detail") if isinstance(event.get("protection_detail"), dict) else event
    detail_text = summarize_detail(detail)
    if not wide and len(detail_text) > max_detail:
        detail_text = detail_text[: max_detail - 1] + "…"
    return [
        compact_time(event_time(event)),
        _stringify(event.get("event")),
        _stringify(event.get("symbol") or detail.get("symbol")),
        _stringify(event.get("trade_id") or detail.get("trade_id")),
        _stringify(event.get("has_sl") if "has_sl" in event else detail.get("has_sl")),
        _stringify(event.get("has_tp") if "has_tp" in event else detail.get("has_tp")),
        _stringify(event.get("protected") if "protected" in event else detail.get("protected")),
        _stringify(event.get("reason")),
        detail_text,
    ]


def headers_for_view(view: str) -> list[str]:
    if view == "auto-protect":
        return ["time", "mode", "enabled", "dry_run", "cash_ratchet", "live_ap", "positions", "candidates", "reason"]
    if view == "trades":
        return [
            "time",
            "event",
            "symbol",
            "signal",
            "setup_grade",
            "strategy_label",
            "entry_setup_label",
            "risk_dollars",
            "reason",
            "exit_reason",
        ]
    return ["time", "event", "symbol", "trade_id", "has_sl", "has_tp", "protected", "reason", "detail"]


def grouped_headers_for_view(view: str) -> list[str]:
    if view == "auto-protect":
        return [
            "first_seen",
            "last_seen",
            "count",
            "event",
            "mode",
            "enabled",
            "dry_run",
            "cash_ratchet",
            "live_ap",
            "positions",
            "candidates",
            "symbol",
            "trade_id",
            "rule",
            "intended_action",
            "executed",
            "reason",
        ]
    if view == "trades":
        return [
            "first_seen",
            "last_seen",
            "count",
            "event",
            "symbol",
            "signal",
            "setup_grade",
            "strategy_label",
            "entry_setup_label",
            "risk_dollars",
            "reason",
            "exit_reason",
        ]
    return [
        "first_seen",
        "last_seen",
        "count",
        "event",
        "symbol",
        "trade_id",
        "has_sl",
        "has_tp",
        "protected",
        "reason",
        "detail",
    ]


def protection_values(event: dict[str, Any]) -> dict[str, Any]:
    detail = event.get("protection_detail") if isinstance(event.get("protection_detail"), dict) else event
    return {
        "symbol": event.get("symbol") or detail.get("symbol"),
        "trade_id": event.get("trade_id") or detail.get("trade_id"),
        "has_sl": event.get("has_sl") if "has_sl" in event else detail.get("has_sl"),
        "has_tp": event.get("has_tp") if "has_tp" in event else detail.get("has_tp"),
        "protected": event.get("protected") if "protected" in event else detail.get("protected"),
        "detail": summarize_detail(detail),
    }


def group_key(event: dict[str, Any], view: str) -> tuple:
    name = _event_name(event)
    if view == "auto-protect":
        return (
            name,
            event_mode(event),
            event.get("enabled"),
            event.get("dry_run"),
            event.get("cash_ratchet_enabled"),
            event.get("live_auto_protect_enabled"),
            event.get("open_positions"),
            event.get("candidates_created"),
            event.get("symbol"),
            event.get("trade_id"),
            event.get("rule"),
            event.get("intended_action"),
            event.get("executed"),
            event.get("reason"),
        )
    if view == "trades":
        return (
            name,
            event.get("symbol"),
            event.get("signal"),
            event.get("setup_grade"),
            event.get("strategy_label"),
            event.get("entry_setup_label"),
            event.get("risk_dollars"),
            event.get("reason"),
            event.get("exit_reason"),
        )
    values = protection_values(event)
    return (
        name,
        values["symbol"],
        values["trade_id"],
        values["has_sl"],
        values["has_tp"],
        values["protected"],
        event.get("reason"),
    )


def group_events(events: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    groups: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    sorted_events = sorted(events, key=lambda event: event_datetime(event) or datetime.min.replace(tzinfo=timezone.utc))
    for event in sorted_events:
        key = group_key(event, view)
        if key not in groups:
            groups[key] = {"first": event, "last": event, "count": 0}
            order.append(key)
        groups[key]["last"] = event
        groups[key]["count"] += 1
    return [groups[key] for key in order]


def row_for_group(group: dict[str, Any], view: str, *, wide: bool = False) -> list[str]:
    first = group["first"]
    last = group["last"]
    first_seen = compact_time(event_time(first))
    last_seen = compact_time(event_time(last))
    count = _stringify(group["count"])
    if view == "auto-protect":
        return [
            first_seen,
            last_seen,
            count,
            _stringify(last.get("event")),
            event_mode(last),
            _stringify(last.get("enabled")),
            _stringify(last.get("dry_run")),
            _stringify(last.get("cash_ratchet_enabled")),
            _stringify(last.get("live_auto_protect_enabled")),
            _stringify(last.get("open_positions")),
            _stringify(last.get("candidates_created")),
            _stringify(last.get("symbol")),
            _stringify(last.get("trade_id")),
            _stringify(last.get("rule")),
            _stringify(last.get("intended_action")),
            _stringify(last.get("executed")),
            _stringify(last.get("reason")),
        ]
    if view == "trades":
        return [
            first_seen,
            last_seen,
            count,
            _stringify(last.get("event")),
            _stringify(last.get("symbol")),
            _stringify(last.get("signal")),
            _stringify(last.get("setup_grade")),
            _stringify(last.get("strategy_label")),
            _stringify(last.get("entry_setup_label")),
            _stringify(last.get("risk_dollars")),
            _stringify(last.get("reason")),
            _stringify(last.get("exit_reason")),
        ]
    values = protection_values(last)
    detail = _stringify(values["detail"])
    if not wide and len(detail) > 80:
        detail = detail[:79] + "…"
    return [
        first_seen,
        last_seen,
        count,
        _stringify(last.get("event")),
        _stringify(values["symbol"]),
        _stringify(values["trade_id"]),
        _stringify(values["has_sl"]),
        _stringify(values["has_tp"]),
        _stringify(values["protected"]),
        _stringify(last.get("reason")),
        detail,
    ]


def format_table(headers: list[str], rows: list[list[str]], *, max_width: int = 34) -> str:
    all_rows = [headers, *rows]
    widths = [0] * len(headers)
    for row in all_rows:
        for idx, cell in enumerate(row):
            widths[idx] = min(max(widths[idx], len(cell)), max_width)

    def trim(cell: str, width: int) -> str:
        if len(cell) <= width:
            return cell
        if width <= 1:
            return cell[:width]
        return cell[: width - 1] + "…"

    rendered = []
    for row_idx, row in enumerate(all_rows):
        rendered.append("  ".join(trim(cell, widths[idx]).ljust(widths[idx]) for idx, cell in enumerate(row)))
        if row_idx == 0:
            rendered.append("  ".join("-" * width for width in widths))
    return "\n".join(rendered)


def collect_events(args: argparse.Namespace) -> Iterator[dict[str, Any]]:
    units = args.unit or list(DEFAULT_UNITS)
    if args.view == "auto-protect":
        for event in read_observer_auto_actions(args.observer_dir, parse_since_cutoff(args.since)):
            yield event
    yield from iter_journal_events(units, args.since, args.follow)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only OzzyBot journal/observer log viewer")
    parser.add_argument("--view", choices=("auto-protect", "trades", "protection"), required=True)
    parser.add_argument("--since", default="4 hours ago", help='journalctl --since value, e.g. "12 hours ago"')
    parser.add_argument("--symbol", help="Filter by symbol, e.g. HYPEUSDT")
    parser.add_argument("--mode", choices=("TESTNET", "LIVE", "ALL"), default="ALL")
    parser.add_argument("--follow", action="store_true", help="Follow journal output")
    parser.add_argument("--raw-json", action="store_true", help="Print matching events as JSON lines")
    parser.add_argument("--limit", type=int, default=120, help="Max rows for non-follow table output")
    parser.add_argument("--latest", type=int, help="Show last N grouped rows")
    parser.add_argument("--show-live-disabled", action="store_true", help="Show disabled LIVE auto-protect heartbeats")
    parser.add_argument("--errors-only", action="store_true", help="Show only unsafe/error rows")
    parser.add_argument("--wide", action="store_true", help="Show full detail fields")
    parser.add_argument("--unit", action="append", help="systemd user unit to read; repeatable")
    parser.add_argument("--observer-dir", type=Path, default=OBSERVER_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows: list[list[str]] = []
    headers = headers_for_view(args.view)
    events: list[dict[str, Any]] = []
    raw_count = 0
    follow_header_printed = False

    for event in collect_events(args):
        if not passes_display_filters(event, args):
            continue
        if args.raw_json:
            print(json.dumps(event, default=str), flush=args.follow)
            raw_count += 1
            raw_limit = args.latest if args.latest is not None else args.limit
            if raw_limit and not args.follow and raw_count >= raw_limit:
                break
            continue
        row = row_for_event(event, args.view, wide=args.wide)
        if args.follow:
            if not follow_header_printed:
                print(format_table(headers, [], max_width=1000 if args.wide else 80), flush=True)
                follow_header_printed = True
            print("  ".join(row), flush=True)
        else:
            events.append(event)

    if not args.raw_json and not args.follow:
        grouped = group_events(events, args.view)
        latest = args.latest if args.latest is not None else args.limit
        if latest:
            grouped = grouped[-latest:]
        grouped_headers = grouped_headers_for_view(args.view)
        rows = [row_for_group(group, args.view, wide=args.wide) for group in grouped]
        print(format_table(grouped_headers, rows, max_width=1000 if args.wide else 80))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
