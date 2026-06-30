#!/usr/bin/env python3
"""Generate a daily edge and bottleneck report from the unified OzzyBot DB."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "trades.db"
DEFAULT_LOGS = [ROOT / "trades.log", ROOT / "live_micro" / "trades_live.log"]
DEFAULT_REPORT_DIR = ROOT / "reports"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (
        lambda item: datetime.fromisoformat(item),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parser(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except Exception:
            continue
    return None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _is_shadow_trade(row: dict) -> bool:
    """Return True for simulated rows that must not affect executed results."""
    execution_state = str(row.get("execution_state") or "").strip().lower()
    mode = str(row.get("mode") or "").strip().lower()
    return execution_state.startswith("shadow") or mode == "paper"


def _rows_since(conn: sqlite3.Connection, table: str, since: datetime) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            f"SELECT * FROM {table} WHERE datetime(ts) >= datetime(?) ORDER BY datetime(ts) ASC",
            (_iso(since),),
        ).fetchall()
    ]


def _all_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY ts ASC").fetchall()]


def _bucket_count(rows: list[dict], *keys: str, limit: int = 12) -> list[dict]:
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        counts[tuple(str(row.get(key) or "UNKNOWN") for key in keys)] += 1
    result = []
    for key_tuple, count in counts.most_common(limit):
        item = {"count": count}
        for idx, key in enumerate(keys):
            item[key] = key_tuple[idx]
        result.append(item)
    return result


def _closed_trade_stats(trades: list[dict]) -> dict:
    closed = [row for row in trades if row.get("exit_price") is not None]
    winners = [row for row in closed if _num(row.get("pnl")) > 0]
    losers = [row for row in closed if _num(row.get("pnl")) < 0]
    total_pnl = sum(_num(row.get("pnl")) for row in closed)
    r_values = [_num(row.get("r_multiple")) for row in closed if row.get("r_multiple") is not None]
    return {
        "closed": len(closed),
        "wins": len(winners),
        "losses": len(losers),
        "win_rate": round((len(winners) / len(closed)) * 100, 2) if closed else 0.0,
        "total_pnl": round(total_pnl, 4),
        "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else None,
    }


def _trade_quality(trades: list[dict]) -> dict:
    closed = [row for row in trades if row.get("exit_price") is not None]
    no_peak_losers = []
    green_to_red = []
    by_symbol: dict[str, dict[str, Any]] = defaultdict(lambda: {"closed": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    by_strategy: dict[str, dict[str, Any]] = defaultdict(lambda: {"closed": 0, "wins": 0, "losses": 0, "pnl": 0.0})

    for row in closed:
        pnl = _num(row.get("pnl"))
        peak = _num(row.get("peak_pnl"))
        risk = _num(row.get("risk_dollars"))
        peak_r = round(peak / risk, 4) if risk > 0 else None
        summary = {
            "trade_id": row.get("id"),
            "symbol": row.get("symbol"),
            "direction": row.get("direction"),
            "pnl": round(pnl, 4),
            "r_multiple": row.get("r_multiple"),
            "peak_pnl": round(peak, 4),
            "peak_r": peak_r,
            "exit_reason": row.get("exit_reason") or "UNKNOWN",
            "strategy_label": row.get("strategy_label") or row.get("strategy") or "UNKNOWN",
            "lane": row.get("lane") or "UNKNOWN",
        }
        if pnl < 0 and peak <= 0:
            no_peak_losers.append(summary)
        if pnl < 0 and peak > 0:
            green_to_red.append(summary)

        for bucket, key in ((by_symbol, row.get("symbol") or "UNKNOWN"), (by_strategy, row.get("strategy_label") or row.get("strategy") or "UNKNOWN")):
            bucket[key]["closed"] += 1
            bucket[key]["wins"] += 1 if pnl > 0 else 0
            bucket[key]["losses"] += 1 if pnl < 0 else 0
            bucket[key]["pnl"] += pnl

    def finalize(bucket: dict[str, dict[str, Any]]) -> list[dict]:
        rows = []
        for name, data in bucket.items():
            closed_count = data["closed"]
            rows.append(
                {
                    "bucket": name,
                    "closed": closed_count,
                    "wins": data["wins"],
                    "losses": data["losses"],
                    "win_rate": round((data["wins"] / closed_count) * 100, 2) if closed_count else 0.0,
                    "pnl": round(data["pnl"], 4),
                }
            )
        return sorted(rows, key=lambda item: (item["pnl"], -item["closed"]))

    return {
        "no_peak_losers": no_peak_losers[:20],
        "green_to_red": green_to_red[:20],
        "by_symbol": finalize(by_symbol),
        "by_strategy": finalize(by_strategy),
    }


def _open_position_summaries(trades: list[dict], now: datetime) -> list[dict]:
    summaries = []
    for row in trades:
        if row.get("exit_price") is not None:
            continue
        opened_at = _parse_dt(row.get("ts"))
        age_hours = round((now - opened_at).total_seconds() / 3600, 2) if opened_at else None
        risk = _num(row.get("risk_dollars"))
        peak = _num(row.get("peak_pnl"))
        summaries.append(
            {
                "trade_id": row.get("id"),
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "opened_at": row.get("ts"),
                "age_hours": age_hours,
                "entry_price": row.get("entry_price"),
                "qty": row.get("qty"),
                "risk_dollars": round(risk, 4),
                "peak_pnl": round(peak, 4),
                "peak_r": round(peak / risk, 4) if risk > 0 else None,
                "strategy_label": row.get("strategy_label") or row.get("strategy") or "UNKNOWN",
                "lane": row.get("lane") or "UNKNOWN",
            }
        )
    return sorted(summaries, key=lambda item: item["age_hours"] if item["age_hours"] is not None else -1, reverse=True)


def _position_pressure(gate_summary: dict, open_positions: list[dict]) -> dict:
    max_positions = _env_int("HERMES_MAX_POSITIONS", 3)
    max_blocks = 0
    for item in gate_summary["top_rejected_gates"]:
        if item.get("gate_name") == "max_positions":
            max_blocks = int(item.get("count") or 0)
            break
    open_count = len(open_positions)
    utilization = round((open_count / max_positions) * 100, 2) if max_positions > 0 else None
    if max_positions > 0 and open_count >= max_positions:
        state = "currently_at_cap"
    elif max_blocks > 0:
        state = "historical_cap_pressure"
    else:
        state = "no_cap_pressure"
    return {
        "configured_max_positions": max_positions,
        "open_positions": open_count,
        "cap_utilization_pct": utilization,
        "max_position_blocks": max_blocks,
        "state": state,
        "open_position_details": open_positions,
    }


def _trade_close_time(row: dict, now: datetime) -> datetime | None:
    opened_at = _parse_dt(row.get("ts"))
    if not opened_at:
        return None
    if row.get("exit_price") is None:
        return now
    duration = row.get("duration_min")
    try:
        return opened_at + timedelta(minutes=float(duration or 0))
    except Exception:
        return opened_at


def _cap_occupancy_report(gates: list[dict], signals: list[dict], trades: list[dict], now: datetime) -> dict:
    signal_lookup = {row.get("id"): row for row in signals}
    occupier_counts: Counter[tuple[Any, str, str]] = Counter()
    occupier_rows: dict[tuple[Any, str, str], dict] = {}
    blocked_symbols: Counter[str] = Counter()
    blocked_rows = []

    for gate in gates:
        if gate.get("gate_name") != "max_positions" or str(gate.get("decision") or "").lower() != "rejected":
            continue
        gate_ts = _parse_dt(gate.get("ts"))
        if not gate_ts:
            continue
        signal = signal_lookup.get(gate.get("signal_id")) or {}
        blocked_symbol = str(signal.get("symbol") or "UNKNOWN")
        blocked_symbols[blocked_symbol] += 1
        occupiers = []
        for trade in trades:
            opened_at = _parse_dt(trade.get("ts"))
            closed_at = _trade_close_time(trade, now)
            if not opened_at or not closed_at:
                continue
            if opened_at <= gate_ts < closed_at:
                key = (trade.get("id"), str(trade.get("symbol") or "UNKNOWN"), str(trade.get("direction") or "UNKNOWN"))
                occupier_counts[key] += 1
                occupier_rows[key] = trade
                occupiers.append(
                    {
                        "trade_id": trade.get("id"),
                        "symbol": trade.get("symbol"),
                        "direction": trade.get("direction"),
                        "opened_at": trade.get("ts"),
                        "exit_reason": trade.get("exit_reason"),
                        "strategy_label": trade.get("strategy_label") or trade.get("strategy") or "UNKNOWN",
                        "lane": trade.get("lane") or "UNKNOWN",
                    }
                )
        blocked_rows.append(
            {
                "ts": gate.get("ts"),
                "blocked_symbol": blocked_symbol,
                "blocked_direction": signal.get("direction"),
                "blocked_lane": signal.get("lane") or "UNKNOWN",
                "occupiers": occupiers,
            }
        )

    top_occupiers = [
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "blocked_count": count,
            "pnl": round(_num((occupier_rows.get((trade_id, symbol, direction)) or {}).get("pnl")), 4),
            "r_multiple": (occupier_rows.get((trade_id, symbol, direction)) or {}).get("r_multiple"),
            "duration_min": (occupier_rows.get((trade_id, symbol, direction)) or {}).get("duration_min"),
            "exit_reason": (occupier_rows.get((trade_id, symbol, direction)) or {}).get("exit_reason") or "OPEN",
            "strategy_label": (
                (occupier_rows.get((trade_id, symbol, direction)) or {}).get("strategy_label")
                or (occupier_rows.get((trade_id, symbol, direction)) or {}).get("strategy")
                or "UNKNOWN"
            ),
        }
        for (trade_id, symbol, direction), count in occupier_counts.most_common(12)
    ]
    return {
        "max_position_blocks": len(blocked_rows),
        "blocked_symbols": [
            {"symbol": symbol, "blocked_count": count} for symbol, count in blocked_symbols.most_common(12)
        ],
        "top_occupiers": top_occupiers,
        "blocked_events": blocked_rows[:30],
    }


def _gate_summary(gates: list[dict], signals: list[dict]) -> dict:
    rejected = [row for row in gates if str(row.get("decision") or "").lower() == "rejected"]
    passed = [row for row in gates if str(row.get("decision") or "").lower() == "passed"]
    signal_lookup = {row.get("id"): row for row in signals}
    enriched_rejects = []
    for gate in rejected:
        signal = signal_lookup.get(gate.get("signal_id")) or {}
        enriched_rejects.append({**gate, **{f"signal_{key}": value for key, value in signal.items()}})
    return {
        "passed_count": len(passed),
        "rejected_count": len(rejected),
        "top_rejected_gates": _bucket_count(rejected, "gate_name", limit=15),
        "top_rejected_reasons": _bucket_count(rejected, "reason", limit=15),
        "rejected_by_symbol": _bucket_count(enriched_rejects, "signal_symbol", limit=15),
        "rejected_by_lane": _bucket_count(enriched_rejects, "signal_lane", limit=15),
    }


def _read_log_events(paths: list[Path], since: datetime) -> dict:
    counts: Counter[str] = Counter()
    by_symbol: Counter[tuple[str, str]] = Counter()
    warnings = []
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    ts = _parse_dt(event.get("ts"))
                    if ts and ts < since:
                        continue
                    name = str(event.get("event") or "UNKNOWN")
                    counts[name] += 1
                    symbol = event.get("symbol")
                    if symbol:
                        by_symbol[(name, str(symbol))] += 1
        except Exception as exc:
            warnings.append(f"failed reading {path}: {exc}")
    return {
        "event_counts": [{"event": event, "count": count} for event, count in counts.most_common(20)],
        "event_symbol_counts": [
            {"event": event, "symbol": symbol, "count": count}
            for (event, symbol), count in by_symbol.most_common(20)
        ],
        "warnings": warnings,
    }


def _recommendations(report: dict) -> list[dict]:
    recommendations = []
    gates = report["gates"]["top_rejected_gates"]
    gate_counts = {item["gate_name"]: item["count"] for item in gates}
    total_rejected = report["gates"]["rejected_count"]
    position_state = report.get("position_pressure", {}).get("state")

    if position_state == "currently_at_cap":
        recommendations.append(
            {
                "priority": "high",
                "area": "throughput",
                "finding": "position cap is currently full",
                "action": "Do not raise caps blindly; inspect open trade age/peak R and exit responsiveness first.",
            }
        )
    elif gate_counts.get("max_positions", 0) >= 3:
        top_occupiers = report.get("cap_occupancy", {}).get("top_occupiers", [])
        profitable_occupiers = [item for item in top_occupiers if _num(item.get("pnl")) > 0]
        long_low_capture = [
            item
            for item in top_occupiers
            if _num(item.get("duration_min")) >= 240 and item.get("r_multiple") is not None and _num(item.get("r_multiple")) < 0.5
        ]
        if long_low_capture:
            action = "Investigate faster partials/trailing for long low-R occupiers before raising caps."
        elif profitable_occupiers and len(profitable_occupiers) == len(top_occupiers):
            action = "Do not raise caps from this alone; occupied slots were profitable, so compare missed-signal counterfactuals first."
        else:
            action = "Review whether earlier open trades stayed too long before changing entry filters."
        recommendations.append(
            {
                "priority": "medium",
                "area": "throughput",
                "finding": "max_positions was a historical bottleneck",
                "action": action,
            }
        )
    if gate_counts.get("local_regime_filter_adx_low", 0) >= 2:
        recommendations.append(
            {
                "priority": "medium",
                "area": "entry_filter",
                "finding": "ADX/choppy regime filter is blocking repeated signals",
                "action": "Run counterfactual review by symbol before lowering ADX globally.",
            }
        )
    if report["trade_quality"]["no_peak_losers"]:
        recommendations.append(
            {
                "priority": "high",
                "area": "entry_quality",
                "finding": "Some losers never went green",
                "action": "Tighten candle/location confirmation for the affected lane-symbol pairs.",
            }
        )
    if report["trade_quality"]["green_to_red"]:
        recommendations.append(
            {
                "priority": "medium",
                "area": "exit_quality",
                "finding": "Some trades gave back positive excursion and closed red",
                "action": "Review earlier partial/ratchet thresholds for those profiles.",
            }
        )
    if report["summary"]["signals"] < 5 and total_rejected == 0:
        recommendations.append(
            {
                "priority": "medium",
                "area": "signal_generation",
                "finding": "Low signal count with few explicit rejections",
                "action": "Check lane timers and scanner coverage before changing filters.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "info",
                "area": "sample_size",
                "finding": "No dominant bottleneck detected in this window",
                "action": "Collect more trades/signals before tuning.",
            }
        )
    return recommendations


def build_report(db_path: Path = DEFAULT_DB, log_paths: list[Path] | None = None, hours: int = 24, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    since = now - timedelta(hours=hours)
    log_paths = log_paths if log_paths is not None else DEFAULT_LOGS

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with _connect_readonly(db_path) as conn:
        signals = _rows_since(conn, "signals", since)
        gates = _rows_since(conn, "trade_gates", since)
        trades = _rows_since(conn, "trades", since)
        all_trades = _all_rows(conn, "trades")

    executed_trades = [row for row in trades if not _is_shadow_trade(row)]
    shadow_trades = [row for row in trades if _is_shadow_trade(row)]
    executed_all_trades = [row for row in all_trades if not _is_shadow_trade(row)]
    closed_stats = _closed_trade_stats(executed_trades)
    shadow_stats = _closed_trade_stats(shadow_trades)
    trade_quality = _trade_quality(executed_trades)
    gate_summary = _gate_summary(gates, signals)
    log_summary = _read_log_events(log_paths, since)
    open_trades = [row for row in executed_trades if row.get("exit_price") is None]
    open_position_details = _open_position_summaries(executed_all_trades, now)
    position_pressure = _position_pressure(gate_summary, open_position_details)
    cap_occupancy = _cap_occupancy_report(gates, signals, executed_all_trades, now)

    report = {
        "generated_at": _iso(now),
        "window": {"hours": hours, "since": _iso(since), "until": _iso(now)},
        "db_path": str(db_path),
        "sources": {
            "database": str(db_path),
            "logs": [str(path) for path in log_paths],
            "scope": "unified system view across STANDARD_TESTNET and LIVE_MICRO",
        },
        "summary": {
            "signals": len(signals),
            "trades_opened": len(executed_trades),
            "open_trades": len(open_trades),
            **closed_stats,
            "signal_to_trade_rate": round((len(executed_trades) / len(signals)) * 100, 2) if signals else 0.0,
        },
        "shadow_summary": {
            "trades_opened": len(shadow_trades),
            "open_trades": len([row for row in shadow_trades if row.get("exit_price") is None]),
            **shadow_stats,
        },
        "signals": {
            "by_source": _bucket_count(signals, "source", limit=12),
            "by_lane": _bucket_count(signals, "lane", limit=12),
            "by_symbol": _bucket_count(signals, "symbol", limit=20),
            "by_symbol_direction": _bucket_count(signals, "symbol", "direction", limit=20),
        },
        "gates": gate_summary,
        "position_pressure": position_pressure,
        "cap_occupancy": cap_occupancy,
        "trade_quality": trade_quality,
        "logs": log_summary,
    }
    report["recommendations"] = _recommendations(report)
    return report


def write_reports(report: dict, report_dir: Path = DEFAULT_REPORT_DIR) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(report["generated_at"]).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"daily_edge_{stamp}.json"
    md_path = report_dir / f"daily_edge_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    sources = report.get("sources", {})
    log_sources = sources.get("logs", [])
    lines = [
        "# OzzyBot Daily Edge Report",
        "",
        f"- Window: {report['window']['hours']}h since `{report['window']['since']}`",
        f"- DB: `{report['db_path']}`",
        f"- Scope: {sources.get('scope', 'unified system view')}",
        f"- Signals: {summary['signals']}",
        f"- Trades opened: {summary['trades_opened']} ({summary['signal_to_trade_rate']}% signal→trade)",
        f"- Closed: {summary['closed']} | Wins: {summary['wins']} | Losses: {summary['losses']} | WR: {summary['win_rate']}%",
        f"- Total PnL: ${summary['total_pnl']} | Avg R: {summary['avg_r']}",
    ]
    if log_sources:
        lines.extend(["", "## Data Sources"])
        lines.append(f"- Database: `{sources.get('database', report['db_path'])}`")
        for path in log_sources:
            lines.append(f"- Log: `{path}`")

    shadow = report.get("shadow_summary", {})
    lines.extend(["", "## Shadow Simulation — Excluded From Executed Results"])
    lines.append(
        f"- Closed: {shadow.get('closed', 0)} | Wins: {shadow.get('wins', 0)} | "
        f"Losses: {shadow.get('losses', 0)} | PnL: ${shadow.get('total_pnl', 0)} | Avg R: {shadow.get('avg_r')}"
    )

    lines.extend(["", "## Top Rejection Gates"])
    for item in report["gates"]["top_rejected_gates"][:10]:
        lines.append(f"- {item['gate_name']}: {item['count']}")
    if not report["gates"]["top_rejected_gates"]:
        lines.append("- None")

    lines.extend(["", "## Trade Quality Flags"])
    lines.append(f"- No-peak losers: {len(report['trade_quality']['no_peak_losers'])}")
    lines.append(f"- Green-to-red trades: {len(report['trade_quality']['green_to_red'])}")

    pressure = report.get("position_pressure", {})
    lines.extend(["", "## Position Pressure"])
    lines.append(
        f"- State: {pressure.get('state')} | Open: {pressure.get('open_positions')}/{pressure.get('configured_max_positions')} | "
        f"Cap usage: {pressure.get('cap_utilization_pct')}% | Max-position blocks: {pressure.get('max_position_blocks')}"
    )
    for item in pressure.get("open_position_details", [])[:10]:
        lines.append(
            f"- {item['symbol']} {item['direction']}: age={item['age_hours']}h peak_r={item['peak_r']} "
            f"risk=${item['risk_dollars']} lane={item['lane']}"
        )

    cap_occupancy = report.get("cap_occupancy", {})
    lines.extend(["", "## Cap Occupancy Attribution"])
    lines.append(f"- Max-position blocks analyzed: {cap_occupancy.get('max_position_blocks', 0)}")
    lines.append("- Top blocked symbols:")
    for item in cap_occupancy.get("blocked_symbols", [])[:8]:
        lines.append(f"  - {item['symbol']}: {item['blocked_count']}")
    if not cap_occupancy.get("blocked_symbols"):
        lines.append("  - None")
    lines.append("- Top slot occupiers during blocks:")
    for item in cap_occupancy.get("top_occupiers", [])[:8]:
        lines.append(
            f"  - trade {item['trade_id']} {item['symbol']} {item['direction']}: {item['blocked_count']} blocks, "
            f"pnl=${item['pnl']}, r={item['r_multiple']}, duration={item['duration_min']}m, exit={item['exit_reason']}"
        )
    if not cap_occupancy.get("top_occupiers"):
        lines.append("  - None")

    lines.extend(["", "## Recommendations"])
    for item in report["recommendations"]:
        lines.append(f"- [{item['priority']}] {item['area']}: {item['finding']} — {item['action']}")

    lines.extend(["", "## Worst Symbol Buckets"])
    for item in report["trade_quality"]["by_symbol"][:10]:
        lines.append(
            f"- {item['bucket']}: closed={item['closed']} wins={item['wins']} losses={item['losses']} pnl=${item['pnl']}"
        )
    if not report["trade_quality"]["by_symbol"]:
        lines.append("- No closed trades in window")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    report = build_report(db_path=args.db, hours=args.hours)
    json_path, md_path = write_reports(report, args.report_dir)
    print(json.dumps(report["summary"], indent=2))
    print(f"json={json_path}")
    if not args.json_only:
        print(f"markdown={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
