#!/usr/bin/env python3
"""Weekly shadow report for OpenClaw derivatives-positioning context.

Reads advisory-only derivatives context from OPENCLAW_BREAKOUT_* log events and
correlates it with later signal-review outcomes when available. This script does
not affect trading, sizing, gates, services, credentials, or execution state.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = ROOT / "trades.log"
DEFAULT_REPORT_DIR = ROOT / "reports"
OPENCLAW_EVENTS = {"OPENCLAW_BREAKOUT_CHECK", "OPENCLAW_BREAKOUT_FIRED"}

sys.path.insert(0, str(ROOT))
import trade_db  # noqa: E402


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def symbol_key(symbol: str | None) -> str:
    text = str(symbol or "").upper().strip()
    if text.endswith("USDT"):
        return text[:-4]
    if text.endswith("USD"):
        return text[:-3]
    return text


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _event_status(row: dict[str, Any], verdict: dict[str, Any]) -> str:
    if row.get("event") == "OPENCLAW_BREAKOUT_FIRED":
        return "FIRED"
    if verdict.get("passed") is True:
        return "CHECK_PASS"
    return "WAIT"


def extract_shadow_events(log_path: Path, since_days: int | None = None) -> list[dict[str, Any]]:
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=since_days)

    events: list[dict[str, Any]] = []
    for row in load_jsonl(log_path):
        if row.get("event") not in OPENCLAW_EVENTS:
            continue
        ts = parse_ts(row.get("ts"))
        if cutoff and (ts is None or ts < cutoff):
            continue

        verdict_raw = row.get("verdict")
        verdict: dict[str, Any] = verdict_raw if isinstance(verdict_raw, dict) else {}
        ctx_raw = verdict.get("derivatives_context")
        ctx: dict[str, Any] | None = ctx_raw if isinstance(ctx_raw, dict) else None
        if not ctx:
            continue

        blueprint_raw = row.get("blueprint")
        blueprint: dict[str, Any] = blueprint_raw if isinstance(blueprint_raw, dict) else {}
        symbol = verdict.get("symbol") or row.get("symbol") or blueprint.get("symbol")
        signal = verdict.get("signal") or blueprint.get("side")
        metrics_raw = ctx.get("metrics")
        metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
        events.append(
            {
                "ts": ts.isoformat() if ts else str(row.get("ts")),
                "event": row.get("event"),
                "status": _event_status(row, verdict),
                "symbol": str(symbol or "").upper(),
                "signal": str(signal or "").upper(),
                "passed": bool(verdict.get("passed")),
                "breakout_reason": verdict.get("reason"),
                "breakout_reasons": verdict.get("reasons") or [],
                "derivatives_verdict": ctx.get("verdict", "unavailable"),
                "score": ctx.get("score", 0),
                "derivatives_reasons": ctx.get("reasons") or [],
                "metrics": metrics,
                "strategy_label": verdict.get("strategy_label") or blueprint.get("strategy_label"),
                "entry_setup_label": verdict.get("entry_setup_label") or blueprint.get("entry_setup_label") or verdict.get("setup_label") or blueprint.get("setup_label"),
                "regime_label": verdict.get("regime_label") or blueprint.get("regime_label"),
                "configured_lane": verdict.get("configured_lane") or blueprint.get("configured_lane"),
                "outcome": "unresolved",
                "r_multiple": None,
            }
        )
    return events


def load_trade_outcomes() -> list[dict[str, Any]]:
    """Load executed trade outcomes from the unified trades DB."""
    candidates: list[dict[str, Any]] = []
    try:
        with trade_db._connect() as conn:
            rows = conn.execute(
                "SELECT id, ts, symbol, direction, exit_price, pnl, r_multiple FROM trades ORDER BY ts DESC"
            ).fetchall()
    except Exception:
        return candidates

    for row in rows:
        if not isinstance(row, dict):
            row = dict(row)
        ts = parse_ts(row["ts"])
        if ts is None:
            continue
        exit_price = row.get("exit_price")
        pnl = row.get("pnl")
        if exit_price is None or pnl is None:
            outcome = "unresolved"
        elif pnl > 0:
            outcome = "win"
        elif pnl < 0:
            outcome = "loss"
        else:
            outcome = "scratch"
        candidates.append(
            {
                "trade_id": row["id"],
                "symbol": str(row.get("symbol") or "").upper(),
                "signal": str(row.get("direction") or "").upper(),
                "_parsed_ts": ts,
                "_outcome": outcome,
                "r_multiple": row.get("r_multiple"),
            }
        )
    return candidates


def correlate_outcomes(
    events: list[dict[str, Any]],
    reviews: list[dict[str, Any]] | None = None,
    tolerance_minutes: int = 180,
    trade_outcomes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates = trade_outcomes if trade_outcomes is not None else load_trade_outcomes()
    correlated: list[dict[str, Any]] = []
    tolerance = timedelta(minutes=tolerance_minutes)
    for event in events:
        event_dt = parse_ts(event.get("ts"))
        best: tuple[timedelta, dict[str, Any]] | None = None
        if event_dt is not None:
            for trade in candidates:
                if symbol_key(trade.get("symbol")) != symbol_key(event.get("symbol")):
                    continue
                if str(trade.get("signal") or "").upper() != str(event.get("signal") or "").upper():
                    continue
                delta = abs(trade["_parsed_ts"] - event_dt)
                if delta <= tolerance and (best is None or delta < best[0]):
                    best = (delta, trade)
        enriched = dict(event)
        if best:
            trade = best[1]
            enriched["outcome"] = trade["_outcome"]
            enriched["r_multiple"] = trade.get("r_multiple")
            enriched["matched_trade_id"] = trade.get("trade_id")
        correlated.append(enriched)
    return correlated


def aggregate_by_verdict(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        buckets[str(event.get("derivatives_verdict") or "unavailable")].append(event)

    stats: dict[str, dict[str, Any]] = {}
    for verdict, rows in sorted(buckets.items()):
        scores = [float(row.get("score") or 0) for row in rows]
        r_values = [float(row["r_multiple"]) for row in rows if row.get("r_multiple") is not None]
        stats[verdict] = {
            "total": len(rows),
            "status_counts": dict(Counter(row.get("status", "UNKNOWN") for row in rows)),
            "outcome_counts": dict(Counter(row.get("outcome", "unresolved") for row in rows)),
            "avg_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "avg_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
        }
    return stats


def aggregate_by_dimension(events: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Group advisory derivatives rows by symbol/setup/etc. for reporting only."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        label = str(event.get(key) or "UNKNOWN").upper() if key == "symbol" else str(event.get(key) or "UNKNOWN")
        buckets[label].append(event)

    stats: dict[str, dict[str, Any]] = {}
    for label, rows in sorted(buckets.items()):
        resolved_rows = [row for row in rows if row.get("outcome") not in (None, "", "unresolved")]
        wins = sum(1 for row in resolved_rows if row.get("outcome") == "win")
        scores = [float(row.get("score") or 0) for row in rows]
        r_values = [float(row["r_multiple"]) for row in resolved_rows if row.get("r_multiple") is not None]
        stats[label] = {
            "total": len(rows),
            "resolved": len(resolved_rows),
            "wins": wins,
            "win_rate": round((wins / len(resolved_rows)) * 100, 1) if resolved_rows else None,
            "status_counts": dict(Counter(row.get("status", "UNKNOWN") for row in rows)),
            "verdict_counts": dict(Counter(row.get("derivatives_verdict", "unavailable") for row in rows)),
            "avg_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "avg_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
        }
    return stats


def _render_dimension_table(title: str, stats: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not stats:
        lines.extend(["_No rows yet._", ""])
        return lines
    lines.extend([
        "| Label | Rows | Resolved | Win rate | Verdict counts | Avg score | Avg R |",
        "|---|---:|---:|---:|---|---:|---:|",
    ])
    for label, row in stats.items():
        win_rate = "n/a" if row.get("win_rate") is None else f"{row['win_rate']}%"
        avg_r = "n/a" if row.get("avg_r_multiple") is None else row["avg_r_multiple"]
        lines.append(
            f"| {label} | {row['total']} | {row['resolved']} | {win_rate} | {row['verdict_counts']} | {row['avg_score']} | {avg_r} |"
        )
    lines.append("")
    return lines


def render_markdown_report(events: list[dict[str, Any]], stats: dict[str, dict[str, Any]]) -> str:
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    lines = [
        "# Derivatives Shadow Report",
        "",
        f"Generated: `{generated}`",
        "",
        "Scope: advisory-only OpenClaw derivatives context. No gates or sizing decisions are made here.",
        "",
    ]
    if not events:
        lines.extend([
            "## Summary",
            "",
            "No derivatives-context rows found yet. Let the OpenClaw breakout executor run after Phase 1 deployment, then rerun this report.",
            "",
        ])
        return "\n".join(lines)

    total = len(events)
    resolved = sum(1 for row in events if row.get("outcome") != "unresolved")
    lines.extend([
        "## Summary",
        "",
        f"- Shadow rows: **{total}**",
        f"- Outcome-resolved rows: **{resolved}**",
        f"- Unresolved rows: **{total - resolved}**",
        "",
        "## Verdict Breakdown",
        "",
        "| Verdict | Rows | Status counts | Outcome counts | Avg score | Avg R |",
        "|---|---:|---|---|---:|---:|",
    ])
    for verdict, row in stats.items():
        avg_r = "n/a" if row.get("avg_r_multiple") is None else row["avg_r_multiple"]
        lines.append(
            f"| {verdict} | {row['total']} | {row['status_counts']} | {row['outcome_counts']} | {row['avg_score']} | {avg_r} |"
        )

    lines.extend([""])
    lines.extend(_render_dimension_table("By Symbol", aggregate_by_dimension(events, "symbol")))
    lines.extend(_render_dimension_table("By Entry Setup", aggregate_by_dimension(events, "entry_setup_label")))

    lines.extend([
        "",
        "## Notes",
        "",
        "- `crowded` is currently a warning label, not a blocker.",
        "- `unresolved` means no matching completed outcome was found in `signal_reviews.json` yet.",
        "- Promote nothing to a gate until enough per-symbol resolved samples exist.",
        "",
    ])
    return "\n".join(lines)


def write_csv(events: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts",
        "event",
        "status",
        "symbol",
        "signal",
        "derivatives_verdict",
        "score",
        "outcome",
        "r_multiple",
        "derivatives_reasons",
        "strategy_label",
        "entry_setup_label",
        "regime_label",
        "configured_lane",
        "price_change_pct",
        "open_interest_delta_pct",
        "funding_rate",
        "taker_buy_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            metrics = event.get("metrics") or {}
            writer.writerow(
                {
                    "ts": event.get("ts"),
                    "event": event.get("event"),
                    "status": event.get("status"),
                    "symbol": event.get("symbol"),
                    "signal": event.get("signal"),
                    "derivatives_verdict": event.get("derivatives_verdict"),
                    "score": event.get("score"),
                    "outcome": event.get("outcome"),
                    "r_multiple": event.get("r_multiple"),
                    "derivatives_reasons": ";".join(map(str, event.get("derivatives_reasons") or [])),
                    "strategy_label": event.get("strategy_label"),
                    "entry_setup_label": event.get("entry_setup_label"),
                    "regime_label": event.get("regime_label"),
                    "configured_lane": event.get("configured_lane"),
                    "price_change_pct": metrics.get("price_change_pct"),
                    "open_interest_delta_pct": metrics.get("open_interest_delta_pct"),
                    "funding_rate": metrics.get("funding_rate"),
                    "taker_buy_ratio": metrics.get("taker_buy_ratio"),
                }
            )


def build_report(log_path: Path, since_days: int, tolerance_minutes: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], str]:
    events = extract_shadow_events(log_path, since_days=since_days)
    correlated = correlate_outcomes(events, tolerance_minutes=tolerance_minutes)
    stats = aggregate_by_verdict(correlated)
    markdown = render_markdown_report(correlated, stats)
    return correlated, stats, markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OpenClaw derivatives-context shadow report")
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH), help="Path to trades.log JSONL")
    parser.add_argument("--since-days", type=int, default=14, help="Lookback window")
    parser.add_argument("--tolerance-minutes", type=int, default=180, help="Trade outcome match tolerance")
    parser.add_argument("--out-dir", default=str(DEFAULT_REPORT_DIR), help="Report output directory")
    args = parser.parse_args()

    events, stats, markdown = build_report(
        Path(args.log),
        since_days=args.since_days,
        tolerance_minutes=args.tolerance_minutes,
    )
    date_key = datetime.now(UTC).strftime("%Y%m%d")
    out_dir = Path(args.out_dir)
    md_path = out_dir / f"derivatives_shadow_report_{date_key}.md"
    csv_path = out_dir / f"derivatives_shadow_report_{date_key}.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    write_csv(events, csv_path)
    print(markdown)
    print(f"\nWrote: {md_path}")
    print(f"Wrote: {csv_path}")
    print(json.dumps({"rows": len(events), "stats": stats}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
