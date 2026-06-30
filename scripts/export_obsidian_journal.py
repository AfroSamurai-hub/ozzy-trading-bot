#!/usr/bin/env python3
"""Export read-only OzzyBot journal snapshots to an existing Obsidian vault."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERRED_ROOT = Path.home() / "Obsidian" / "OzzyBot"
FALLBACK_ROOT = Path.home() / "Documents" / "OzzyBot_Obsidian"


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to a temp file and atomically rename it to the target path."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    tmp.replace(path)

sys.path.insert(0, str(ROOT))

from logger import plain_log  # noqa: E402
from scripts.report_cash_bleed import _exit_at, build_report, render_markdown, write_outputs  # noqa: E402
from scripts.report_derivatives_shadow import (  # noqa: E402
    DEFAULT_LOG_PATH as DERIVATIVES_LOG_PATH,
)
from scripts.report_derivatives_shadow import (
    aggregate_by_dimension,
    aggregate_by_verdict,
)
from scripts.report_derivatives_shadow import (
    build_report as build_derivatives_shadow_report,
)
from scripts.report_derivatives_shadow import (
    render_markdown_report as render_derivatives_markdown_report,
)

EXPORT_FOLDERS = (
    "Trades",
    "Alerts/LossMin",
    "Daily",
    "Weekly",
    "DangerBoard",
    "DangerBoard/Auto Protect Details",
    "ExecutionFailures",
    "Symbols",
    "Strategies",
    "Setups",
    "Regimes",
    "Lanes",
    "Derivatives_Shadow",
    "Derivatives_Shadow/Symbols",
    "Derivatives_Shadow/Setups",
    "System_Architecture",
    "Dashboards",
)

ACTIVE_SETUPS_NOTE = "Active OpenClaw Setups"
MARKET_REGIME_NOTE = "Market Regime Map"
DERIVATIVES_SHADOW_NOTE = "Derivatives Shadow Evidence"
GRAPHIFY_NOTE = "Graphify Pilot"
OPERATING_DASHBOARD_NOTE = "OzzyBot Operating Dashboard"
CASH_BLEED_INDEX_NOTE = "Cash Bleed Review Index"


def resolve_export_root(preferred: Path = PREFERRED_ROOT, fallback: Path = FALLBACK_ROOT) -> Path | None:
    if os.getenv("HERMES_OBSIDIAN_EXPORT_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        plain_log("OBSIDIAN_EXPORT_SKIPPED", {"reason": "export disabled by environment"})
        return None
    if preferred.exists():
        return preferred
    if fallback.exists():
        return fallback
    plain_log(
        "OBSIDIAN_EXPORT_SKIPPED",
        {
            "reason": "export root missing",
            "preferred": str(preferred),
            "fallback": str(fallback),
        },
    )
    return None


def _frontmatter(note_type: str, note_id: str, **extras: object) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "---",
        f"id: {note_id}",
        f"type: {note_type}",
        f"created_at: {now}",
        "source: ozzy-bot",
    ]
    for key, value in extras.items():
        lines.append(f"{key}: {value}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def _note_name(value: object) -> str:
    return str(value or "UNKNOWN").strip().replace("/", "_").replace("\\", "_") or "UNKNOWN"


def _wikilink(folder: str, name: object, alias: object | None = None) -> str:
    note = _note_name(name)
    label = str(alias or note)
    return f"[[{folder}/{note}|{label}]]"


def _symbol_link(symbol: object) -> str:
    symbol_text = str(symbol or "UNKNOWN").upper()
    return _wikilink("Symbols", symbol_text, symbol_text)


def _strategy_link(label: object) -> str:
    label_text = _note_name(label)
    return _wikilink("Strategies", label_text, label_text)


def _setup_link(label: object) -> str:
    label_text = _note_name(label)
    return _wikilink("Setups", label_text, label_text)


def _regime_link(label: object) -> str:
    label_text = _note_name(label)
    return _wikilink("Regimes", label_text, label_text)


def _lane_link(label: object) -> str:
    label_text = _note_name(label)
    return _wikilink("Lanes", label_text, label_text)


LABEL_TYPES = {
    "strategy": {"folder": "Strategies", "note_type": "strategy", "title": "strategy", "section_title": "Strategies", "link": _strategy_link},
    "setup": {"folder": "Setups", "note_type": "setup", "title": "entry setup", "section_title": "Entry Setups", "link": _setup_link},
    "regime": {"folder": "Regimes", "note_type": "regime", "title": "regime", "section_title": "Regimes", "link": _regime_link},
    "lane": {"folder": "Lanes", "note_type": "lane", "title": "lane", "section_title": "Lanes", "link": _lane_link},
}

TRADE_LABEL_FIELDS = (
    ("strategy", "strategy_label"),
    ("strategy", "strategy"),
    ("setup", "entry_setup_label"),
    ("regime", "regime_label"),
)


def _first_present(*values: object, default: str = "-") -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _as_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def summarize_trade_rows(rows: list[dict], key: str) -> dict[str, dict[str, object]]:
    """Group trade rows by key and compute count/win-rate/PnL.

    Reporting-only: this summarizes executed trade history for Obsidian. It does
    not feed strategy gates, sizing, or execution.
    """
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        label = row.get(key)
        if key == "strategy_label" and label in (None, ""):
            label = row.get("strategy")
        if label in (None, ""):
            continue
        pnl = _as_float(row.get("pnl"))
        if pnl is None:
            continue
        bucket = grouped.setdefault(str(label), {"count": 0, "wins": 0, "pnl": 0.0, "symbols": set()})
        bucket["count"] = int(bucket["count"]) + 1
        bucket["wins"] = int(bucket["wins"]) + (1 if pnl > 0 else 0)
        bucket["pnl"] = float(bucket["pnl"]) + pnl
        if row.get("symbol"):
            bucket["symbols"].add(str(row.get("symbol")).upper())

    for bucket in grouped.values():
        count = int(bucket["count"])
        wins = int(bucket["wins"])
        bucket["pnl"] = round(float(bucket["pnl"]), 4)
        bucket["win_rate"] = round((wins / count) * 100, 1) if count else 0.0
        bucket["symbols"] = sorted(bucket["symbols"])
    return grouped


def _performance_lines(stats: dict[str, object] | None) -> list[str]:
    if not stats:
        return ["_No executed trade stats available yet._"]
    return [
        f"- Trade count: {stats.get('count', 0)}",
        f"- Wins: {stats.get('wins', 0)}",
        f"- Win rate: {stats.get('win_rate', 0.0)}%",
        f"- Total PnL: {_fmt_money(_as_float(stats.get('pnl')))}",
    ]


def load_all_trade_rows() -> list[dict]:
    """Load unified trade rows for reporting summaries."""
    from scripts.report_cash_bleed import DEFAULT_TESTNET_DB, _read_trades

    db_rows, _warnings = _read_trades(DEFAULT_TESTNET_DB)
    return [{**row, "db_mode": row.get("mode") or "unified"} for row in db_rows]


def _regime_markdown(regimes: dict) -> str:
    """Render market regimes as a Markdown table with graph-friendly links."""
    lines = [
        "# Market Regime Map",
        "",
        "Updated: " + datetime.now().isoformat(timespec="seconds"),
        "",
        "Purpose: keep lane/risk context visible so we know which symbols can realistically contribute to profitability.",
        "",
        "| Symbol | Lane | Timeframe | Status | Strategy | Bias | ADX | EMA Distance |",
        "|--------|------|-----------|--------|----------|------|-----|--------------|",
    ]
    for symbol, data in sorted(regimes.items()):
        status = data.get("assigned_strategy", "UNKNOWN")
        strategy = data.get("signal_strategy", "-")
        lane = data.get("configured_lane", "-")
        lane_tf = data.get("lane_timeframe", "-")
        bias = data.get("directional_bias", "-")
        metrics = data.get("metrics", {})
        adx = metrics.get("adx", "-")
        close = metrics.get("close")
        ema200 = metrics.get("ema200")
        ema_dist = "-" if close is None or ema200 in (None, 0) else round(((float(close) - float(ema200)) / float(ema200)) * 100, 2)
        lines.append(
            f"| {_symbol_link(symbol)} | {lane} | {lane_tf} | {status} | {_strategy_link(strategy)} | {bias} | {adx} | {ema_dist}% |"
        )
    lines.append("")
    return "\n".join(lines)


def export_dangerboard_regimes(root: Path) -> Path | None:
    """Export market regimes from Macro Scout to DangerBoard/Market_Regimes.md."""
    regimes_path = ROOT / "shared" / "market_regimes.json"
    if not regimes_path.exists():
        plain_log("OBSIDIAN_REGIMES_SKIPPED", {"reason": "market_regimes.json not found", "path": str(regimes_path)})
        return None
    try:
        regimes = json.loads(regimes_path.read_text())
    except Exception as e:
        plain_log("OBSIDIAN_REGIMES_ERROR", {"error": str(e)})
        return None

    (root / "DangerBoard").mkdir(parents=True, exist_ok=True)
    note_id = "market-regime-map"
    path = root / "DangerBoard" / f"{MARKET_REGIME_NOTE}.md"
    atomic_write(path, _frontmatter("regime_map", note_id) + _regime_markdown(regimes))
    plain_log("OBSIDIAN_REGIMES_EXPORTED", {"path": str(path), "symbol_count": len(regimes)})
    return path


def _trade_link_line(row: dict) -> str:
    symbol = str(row.get("symbol") or "UNKNOWN").upper()
    tid = row.get("id")
    pnl = _fmt_money(_as_float(row.get("pnl")))
    strategy = _first_present(row.get("strategy_label"), row.get("strategy"), "UNKNOWN")
    return f"- {_wikilink('Trades', f'{symbol}-{tid}', f'{symbol} #{tid}')} | {_strategy_link(strategy)} | PnL {pnl}"


def _closed_rows_on_date(rows: list[dict], target_date: str) -> list[dict]:
    matching: list[dict] = []
    for row in rows:
        if not row.get("id") or not row.get("symbol"):
            continue
        closed_at = _exit_at(row)
        if closed_at and closed_at.date().isoformat() == target_date:
            matching.append(row)
    return matching


def _sort_trade_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda item: (str(item.get("symbol")), int(item.get("id") or 0)))


def render_daily_trade_links(report_date: str, rows: list[dict]) -> str:
    """Render daily backlinks from cash-bleed notes to generated trade cards."""
    lines = ["", "## Trade Cards Closed This Date"]
    matching = _closed_rows_on_date(rows, report_date)

    if matching:
        lines.extend(_trade_link_line(row) for row in _sort_trade_rows(matching))
        return "\n".join(lines)

    lines.append("_No closed trade cards matched this report date._")
    available_dates = sorted(
        {
            closed_at.date().isoformat()
            for row in rows
            if row.get("id") and row.get("symbol") and (closed_at := _exit_at(row)) and closed_at.date().isoformat() <= report_date
        }
    )
    if not available_dates:
        return "\n".join(lines)

    latest_date = available_dates[-1]
    recent_rows = _closed_rows_on_date(rows, latest_date)
    lines.extend(["", f"## Most Recent Closed Trade Cards ({latest_date})"])
    lines.extend(_trade_link_line(row) for row in _sort_trade_rows(recent_rows))
    return "\n".join(lines)


def export_cash_bleed_snapshot(root: Path, reports_dir: Path = ROOT / "reports", rows: list[dict] | None = None) -> Path:
    for folder in EXPORT_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    report = build_report()
    write_outputs(report, reports_dir)
    note_id = f"cash-bleed-{report['date']}"
    path = root / "Daily" / f"{report['date']} - Cash Bleed Review.md"
    trade_rows = rows if rows is not None else load_all_trade_rows()
    atomic_write(path, _frontmatter("daily_summary", note_id) + render_markdown(report) + render_daily_trade_links(report["date"], trade_rows))
    return path


def render_active_blueprints_markdown(orders: dict, breakout_state: dict) -> str:
    lines = [
        "# Active Blueprint Kanban",
        "",
        "Updated: " + datetime.now().isoformat(timespec="seconds"),
        "",
        "Executor: OpenClaw breakout trigger watcher → testnet webhook :5001",
        "",
        "Purpose: show only actionable OpenClaw watch levels and the evidence attached to them.",
        "",
    ]
    last_results = {row.get("symbol"): row for row in breakout_state.get("last_results", []) if isinstance(row, dict)}
    if not orders:
        lines.append("_No active blueprints._")
        return "\n".join(lines)

    for symbol, data in sorted(orders.items()):
        if str(symbol).startswith("_") or not isinstance(data, dict):
            continue
        status = data.get("status", "UNKNOWN")
        side = data.get("side", "UNKNOWN")
        entry = data.get("entry_price", "0")
        strategy_missing = data.get("strategy_label") in (None, "")
        regime_missing = data.get("regime_label") in (None, "")
        strategy_label = _first_present(data.get("strategy_label"), "BREAKOUT_RETEST")
        regime_label = _first_present(data.get("regime_label"), "OPENCLAW_4H_MACRO_BREAKOUT")
        strategy_note = " (inferred)" if strategy_missing else ""
        regime_note = " (inferred)" if regime_missing else ""
        lane = _first_present(data.get("configured_lane"), data.get("timeframe_cascade"), "OpenClaw")
        last = last_results.get(symbol, {})
        watcher = last.get("status", "NOT_SCANNED")
        reasons = ", ".join(last.get("reasons", [])[:3]) if isinstance(last.get("reasons"), list) else ""
        ctx = last.get("derivatives_context") if isinstance(last.get("derivatives_context"), dict) else {}
        derivatives = ""
        if ctx:
            derivatives = f" | Derivatives: {ctx.get('verdict', 'unavailable')} (score {ctx.get('score', 0)})"
        lines.append(
            f"- [ ] {side} {_symbol_link(symbol)} @ {entry} | Lane: {lane} | "
            f"Strategy: {_strategy_link(strategy_label)}{strategy_note} | Regime: {_regime_link(regime_label)}{regime_note} | "
            f"Blueprint: {status} | Watcher: {watcher} {reasons}{derivatives}"
        )
    return "\n".join(lines)


def export_active_blueprints(root: Path) -> Path | None:
    """Export active orders from OpenClaw to Alerts/Active_Setups.md."""
    orders_path = ROOT / "shared" / "active_orders.json"
    if not orders_path.exists():
        plain_log("OBSIDIAN_ACTIVE_ORDERS_SKIPPED", {"reason": "active_orders.json not found"})
        return None
    orders = _load_json_file(orders_path)

    state_path = ROOT / "shared" / "openclaw_breakout_state.json"
    breakout_state = _load_json_file(state_path)

    (root / "Alerts").mkdir(parents=True, exist_ok=True)
    note_id = "active-openclaw-setups"
    path = root / "Alerts" / f"{ACTIVE_SETUPS_NOTE}.md"
    atomic_write(path, _frontmatter("active_setups", note_id) + render_active_blueprints_markdown(orders, breakout_state))
    plain_log("OBSIDIAN_ACTIVE_ORDERS_EXPORTED", {"path": str(path), "symbol_count": len(orders)})
    return path


def _stats_lines(stats: dict[str, object]) -> list[str]:
    win_rate = "n/a" if stats.get("win_rate") is None else f"{stats.get('win_rate')}%"
    avg_r = "n/a" if stats.get("avg_r_multiple") is None else str(stats.get("avg_r_multiple"))
    return [
        f"- Rows: {stats.get('total', 0)}",
        f"- Resolved: {stats.get('resolved', 0)}",
        f"- Win rate: {win_rate}",
        f"- Avg score: {stats.get('avg_score', 0.0)}",
        f"- Avg R: {avg_r}",
        f"- Verdict counts: {stats.get('verdict_counts', {})}",
    ]


def _render_derivatives_dimension_note(title: str, stats: dict[str, object]) -> str:
    lines = [
        f"# {title} Derivatives Shadow Evidence",
        "",
        "Scope: advisory-only derivatives context. This note reports evidence only; it is not a gate, sizer, or trade veto.",
        "",
        "## Summary",
        *_stats_lines(stats),
        "",
        "## Promotion Rule",
        "Promote nothing to gates or sizing until enough resolved samples show positive expectancy after costs and protection exits.",
    ]
    return "\n".join(lines)


def export_derivatives_shadow_pages(root: Path, events: list[dict] | None = None) -> list[Path]:
    """Export advisory-only derivatives shadow summaries into Obsidian."""
    for folder in ("Derivatives_Shadow", "Derivatives_Shadow/Symbols", "Derivatives_Shadow/Setups"):
        (root / folder).mkdir(parents=True, exist_ok=True)

    if events is None:
        events, stats, markdown = build_derivatives_shadow_report(
            DERIVATIVES_LOG_PATH,
            since_days=14,
            tolerance_minutes=180,
        )
    else:
        stats = aggregate_by_verdict(events)
        markdown = render_derivatives_markdown_report(events, stats)

    by_symbol = aggregate_by_dimension(events, "symbol")
    by_setup = aggregate_by_dimension(events, "entry_setup_label")
    written: list[Path] = []

    index_lines = [
        markdown,
        "",
        "## Obsidian Evidence Pages",
        "",
        "### Symbols",
    ]
    if by_symbol:
        for symbol in sorted(by_symbol):
            index_lines.append(f"- [[Derivatives_Shadow/Symbols/{_note_name(symbol)}|{symbol}]]")
    else:
        index_lines.append("_No symbol-level derivatives rows yet._")
    index_lines.extend(["", "### Entry Setups"])
    if by_setup:
        for setup in sorted(by_setup):
            index_lines.append(f"- [[Derivatives_Shadow/Setups/{_note_name(setup)}|{setup}]]")
    else:
        index_lines.append("_No setup-level derivatives rows yet._")

    index_path = root / "Derivatives_Shadow" / f"{DERIVATIVES_SHADOW_NOTE}.md"
    atomic_write(index_path, _frontmatter("derivatives_shadow", "derivatives-shadow-evidence") + "\n".join(index_lines), encoding="utf-8")
    written.append(index_path)

    for symbol, symbol_stats in by_symbol.items():
        path = root / "Derivatives_Shadow" / "Symbols" / f"{_note_name(symbol)}.md"
        atomic_write(path, _frontmatter("derivatives_shadow_symbol", f"derivatives-symbol-{symbol}") + _render_derivatives_dimension_note(str(symbol), symbol_stats), encoding="utf-8")
        written.append(path)

    for setup, setup_stats in by_setup.items():
        path = root / "Derivatives_Shadow" / "Setups" / f"{_note_name(setup)}.md"
        atomic_write(path, _frontmatter("derivatives_shadow_setup", f"derivatives-setup-{setup}") + _render_derivatives_dimension_note(str(setup), setup_stats), encoding="utf-8")
        written.append(path)

    plain_log("OBSIDIAN_DERIVATIVES_SHADOW_EXPORTED", {"count": len(written), "row_count": len(events)})
    return written


def render_trade_card_markdown(row: dict) -> str:
    tid = row.get("id")
    symbol = row.get("symbol") or "UNKNOWN"
    status = row.get("execution_state", "unknown")
    grade = row.get("setup_grade", "-")
    vol = row.get("volume_ratio", "-")
    exit_reason = row.get("exit_reason", "-")
    pnl = row.get("pnl", "-")
    strategy_label = _first_present(row.get("strategy_label"), row.get("strategy"), "UNKNOWN")
    entry_setup_label = _first_present(row.get("entry_setup_label"), "UNKNOWN")
    regime_label = _first_present(row.get("regime_label"), "UNKNOWN")
    source_service = _first_present(row.get("source_service"), "-")
    is_pre_label_era = entry_setup_label == "UNKNOWN" and regime_label == "UNKNOWN"

    context = {}
    if row.get("context_json"):
        try:
            context = json.loads(row["context_json"])
        except Exception:
            context = {}

    flags = context.get("chart_quality_flags", [])
    confirmations = context.get("chart_quality_confirmations", [])

    lines = [
        f"# {symbol} Trade #{tid}",
        "",
        "## Profitability Links",
        f"- **Symbol:** {_symbol_link(symbol)}",
        f"- **Strategy:** {_strategy_link(strategy_label)}",
        f"- **Entry Setup:** {_setup_link(entry_setup_label)}",
        f"- **Regime:** {_regime_link(regime_label)}",
        f"- **Source Service:** {source_service}",
        "",
        "## Trade Result",
        f"**Status:** {status}",
        f"**Exit Reason:** {exit_reason}",
        f"**PnL:** {pnl}",
        f"**Grade:** {grade} | **Volume Ratio:** {vol}",
        "",
    ]
    if is_pre_label_era:
        lines.extend(
            [
                "## Data Quality",
                "⚠️ **Pre-label era:** this trade predates reliable entry setup/regime labels. Labels are intentionally left `UNKNOWN` and not backfilled to avoid corrupting profitability evidence.",
                "",
            ]
        )
    lines.extend([
        "## SMC Context",
    ])

    if flags:
        lines.append("**Flags / Penalties:**")
        for flag in flags:
            lines.append(f"- {flag}")
    if confirmations:
        lines.append("**Confirmations:**")
        for confirmation in confirmations:
            lines.append(f"- {confirmation}")
    if not flags and not confirmations:
        lines.append("No advanced SMC flags recorded.")
    return "\n".join(lines)


def export_trade_strategy_pages(root: Path, rows: list[dict]) -> list[Path]:
    """Create typed label pages for labels that appear in historical trades."""
    for meta in LABEL_TYPES.values():
        (root / str(meta["folder"])).mkdir(parents=True, exist_ok=True)

    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        seen_for_row: set[tuple[str, str]] = set()
        for label_type, key in TRADE_LABEL_FIELDS:
            label = row.get(key)
            if not label:
                continue
            bucket_key = (label_type, _note_name(label))
            if bucket_key in seen_for_row:
                continue
            seen_for_row.add(bucket_key)
            buckets.setdefault(bucket_key, []).append(row)

    written: list[Path] = []
    for (label_type, label), label_rows in sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1])):
        meta = LABEL_TYPES[label_type]
        folder = str(meta["folder"])
        title = str(meta["title"])
        note_type = str(meta["note_type"])
        symbols = sorted({str(row.get("symbol") or "UNKNOWN").upper() for row in label_rows})
        path = root / folder / f"{label}.md"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if "source: ozzy-bot" not in existing and "Trade-derived label" not in existing and "## Trade-derived label" not in existing:
                continue
        stats = summarize_trade_rows([{**row, "label": label} for row in label_rows], "label").get(label)
        lines = [
            f"# {label}",
            "",
            "## Trade-derived label",
            f"This {title} label appears in executed trade cards. Use it to group results and decide whether the edge deserves more capital, less capital, or removal.",
            "",
            "## Performance Summary",
            *_performance_lines(stats),
            "",
            "## Linked Symbols",
        ]
        lines.extend(f"- {_symbol_link(symbol)}" for symbol in symbols)
        lines.extend(["", "## Profitability Rule", "Keep only if the linked trades show positive expectancy after costs and protection exits."])
        atomic_write(path, _frontmatter(note_type, f"{note_type}-{label}") + "\n".join(lines), encoding="utf-8")
        written.append(path)
        if label_type != "strategy":
            _write_legacy_label_redirect(root, label, label_type)
    return written


def _write_legacy_label_redirect(root: Path, label: str, label_type: str) -> Path | None:
    """Replace old generated Strategies/<label> pages with a safe move notice."""
    legacy_path = root / "Strategies" / f"{label}.md"
    if not legacy_path.exists():
        return None
    existing = legacy_path.read_text(encoding="utf-8")
    if "source: ozzy-bot" not in existing:
        return None
    if "Trade-derived label" not in existing and "Moved generated label" not in existing:
        return None
    link_fn = LABEL_TYPES[label_type]["link"]
    moved_link = link_fn(label)  # type: ignore[operator]
    lines = [
        f"# {label}",
        "",
        "## Moved generated label",
        f"This generated label page moved to {moved_link} during the Strategies/Setups/Regimes/Lanes split.",
        "",
        "Old links are kept as redirects only; new exports should link to the typed folder.",
    ]
    atomic_write(legacy_path, _frontmatter("moved_label", f"moved-{label}") + "\n".join(lines), encoding="utf-8")
    return legacy_path


def export_trade_cards(root: Path, rows: list[dict] | None = None):
    """Export SMC Trade Cards."""
    (root / "Trades").mkdir(parents=True, exist_ok=True)

    rows = rows if rows is not None else load_all_trade_rows()
    export_trade_strategy_pages(root, rows)
    written = 0
    written_paths: set[Path] = set()
    for row in rows:
        tid = row.get("id")
        symbol = row.get("symbol")
        if not tid or not symbol:
            continue

        note_id = f"{symbol}-{tid}"
        path = root / "Trades" / f"{note_id}.md"
        lane = row.get("lane") or "UNKNOWN"
        atomic_write(
            path,
            _frontmatter("trade_card", note_id, lane=lane) + render_trade_card_markdown(row),
        )
        written += 1
        written_paths.add(path)

    plain_log(
        "OBSIDIAN_TRADE_CARDS_EXPORTED",
        {
            "count": len(written_paths),
            "row_count": written,
            "collision_count": written - len(written_paths),
        },
    )


def _collect_label_names(regimes: dict, active_orders: dict, trade_rows: list[dict] | None = None) -> dict[str, set[str]]:
    names: dict[str, set[str]] = {label_type: set() for label_type in LABEL_TYPES}
    for data in regimes.values():
        if isinstance(data, dict):
            for key in ("signal_strategy", "assigned_strategy"):
                value = data.get(key)
                if value:
                    names["strategy"].add(_note_name(value))
            lane = data.get("configured_lane")
            if lane:
                names["lane"].add(_note_name(lane))
    for data in active_orders.values():
        if isinstance(data, dict):
            field_types = (
                ("strategy", "strategy_label"),
                ("setup", "entry_setup_label"),
                ("regime", "regime_label"),
                ("lane", "configured_lane"),
            )
            for label_type, key in field_types:
                value = data.get(key)
                if value:
                    names[label_type].add(_note_name(value))
    for row in trade_rows or []:
        for label_type, key in TRADE_LABEL_FIELDS:
            value = row.get(key)
            if value:
                names[label_type].add(_note_name(value))
    names["strategy"].update({"BREAKOUT_RETEST"})
    names["setup"].update({"OPENCLAW_BREAKOUT"})
    names["regime"].update({"OPENCLAW_4H_MACRO_BREAKOUT"})
    return names


def _link_for_type(label_type: str, label: object) -> str:
    link_fn = LABEL_TYPES[label_type]["link"]
    return link_fn(label)  # type: ignore[operator]


def _symbols_using_label(label_type: str, label: str, regimes: dict, active_orders: dict) -> list[str]:
    using: list[str] = []
    for symbol, data in regimes.items():
        if not isinstance(data, dict):
            continue
        candidates: set[str] = set()
        if label_type == "strategy":
            candidates = {_note_name(data.get("signal_strategy")), _note_name(data.get("assigned_strategy"))}
        elif label_type == "lane":
            candidates = {_note_name(data.get("configured_lane"))}
        if label in candidates:
            using.append(str(symbol))
    for symbol, data in active_orders.items():
        if not isinstance(data, dict):
            continue
        field_by_type = {
            "strategy": "strategy_label",
            "setup": "entry_setup_label",
            "regime": "regime_label",
            "lane": "configured_lane",
        }
        key = field_by_type[label_type]
        if label == _note_name(data.get(key)):
            using.append(str(symbol))
    return sorted(set(using))


def export_navigation_pages(root: Path, regimes: dict, active_orders: dict, trade_rows: list[dict] | None = None) -> list[Path]:
    """Create linked control-room notes that turn exports into a useful graph."""
    trade_rows = trade_rows or []
    symbol_stats = summarize_trade_rows(trade_rows, "symbol")
    stats_by_type = {
        "strategy": summarize_trade_rows(trade_rows, "strategy_label"),
        "setup": summarize_trade_rows(trade_rows, "entry_setup_label"),
        "regime": summarize_trade_rows(trade_rows, "regime_label"),
        "lane": {},
    }
    label_names = _collect_label_names(regimes, active_orders, trade_rows)
    for folder in EXPORT_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    active_symbols = sorted(str(k) for k in active_orders if not str(k).startswith("_"))
    regime_symbols = sorted(str(k) for k in regimes)
    symbols = sorted(set(active_symbols) | set(regime_symbols))

    home_lines = [
        "# Profitability Control Room",
        "",
        "This vault is not decoration. It links trades, symbols, lanes, regimes, active setups, and risk reports so weak edges can be killed and strong edges can be scaled.",
        "",
        "## V2 Edge Spotlight",
    ]
    breakout_stats = stats_by_type["strategy"].get("BREAKOUT_RETEST")
    if breakout_stats:
        home_lines.extend(
            [
                f"- {_strategy_link('BREAKOUT_RETEST')}: {breakout_stats.get('count')} trades | win rate {breakout_stats.get('win_rate')}% | PnL {_fmt_money(_as_float(breakout_stats.get('pnl')))}",
                "- Treat this as evidence to monitor, not permission to change gates/sizing yet.",
            ]
        )
    else:
        home_lines.append("- No BREAKOUT_RETEST executed trade stats yet.")
    home_lines.extend([
        "",
        "## Daily Operating Links",
        f"- [[Dashboards/{OPERATING_DASHBOARD_NOTE}|OzzyBot Operating Dashboard]]",
        f"- [[Daily/{CASH_BLEED_INDEX_NOTE}|Cash Bleed Review Index]]",
        f"- [[Alerts/{ACTIVE_SETUPS_NOTE}|Active OpenClaw Setups]]",
        f"- [[DangerBoard/{MARKET_REGIME_NOTE}|Market Regime Map]]",
        f"- [[Derivatives_Shadow/{DERIVATIVES_SHADOW_NOTE}|Derivatives Shadow Evidence]]",
        f"- [[System_Architecture/{GRAPHIFY_NOTE}|Graphify Pilot]]",
        "",
        "## Visual Navigation",
        "- [[OzzyBot Visual Control Room.canvas|OzzyBot Visual Control Room]]",
        "- [[System_Architecture/OzzyBot Graph Legend|Graph Colour Legend]]",
        "- [[DangerBoard/Auto Protect Evidence Index|Auto Protect Evidence Index]]",
        "",
        "## Symbols",
    ])
    home_lines.extend(f"- {_symbol_link(symbol)}" for symbol in symbols)
    home_lines.extend(["", "## Label Pages"])
    for label_type in ("strategy", "setup", "regime", "lane"):
        labels = sorted(label_names[label_type])
        if not labels:
            continue
        title = str(LABEL_TYPES[label_type]["section_title"])
        home_lines.extend(["", f"### {title}"])
        for name in labels:
            home_lines.append(f"- {_link_for_type(label_type, name)}")
    home_path = root / "00_Home.md"
    atomic_write(home_path, _frontmatter("control_room", "profitability-control-room") + "\n".join(home_lines), encoding="utf-8")
    written.append(home_path)

    for symbol in symbols:
        regime = regimes.get(symbol, {}) if isinstance(regimes.get(symbol, {}), dict) else {}
        order = active_orders.get(symbol, {}) if isinstance(active_orders.get(symbol, {}), dict) else {}
        strategy = _first_present(regime.get("signal_strategy"), order.get("strategy_label"), "UNKNOWN")
        lane = _first_present(regime.get("configured_lane"), order.get("configured_lane"), "-")
        entry_setup = _first_present(order.get("entry_setup_label"), "-")
        regime_label = _first_present(order.get("regime_label"), "-")
        symbol_lines = [
            f"# {symbol}",
            "",
            "## Current Lane",
            f"- Lane: {_lane_link(lane) if lane != '-' else '-'}",
            f"- Timeframe: {_first_present(regime.get('lane_timeframe'), order.get('timeframe_cascade'), '-')}",
            f"- Strategy: {_strategy_link(strategy)}",
            f"- Entry setup: {_setup_link(entry_setup) if entry_setup != '-' else '-'}",
            f"- Regime: {_regime_link(regime_label) if regime_label != '-' else '-'}",
            f"- Bias: {_first_present(regime.get('directional_bias'), '-')}",
            f"- Active setup: {'yes' if order else 'no'}",
            "",
            "## Performance Summary",
            *_performance_lines(symbol_stats.get(symbol)),
            "",
            "## Linked Evidence",
            f"- [[Alerts/{ACTIVE_SETUPS_NOTE}|Active Setups]]",
            f"- [[DangerBoard/{MARKET_REGIME_NOTE}|Regime Map]]",
            f"- [[Derivatives_Shadow/{DERIVATIVES_SHADOW_NOTE}|Derivatives Shadow Evidence]]",
        ]
        path = root / "Symbols" / f"{_note_name(symbol)}.md"
        atomic_write(path, _frontmatter("symbol", f"symbol-{symbol}") + "\n".join(symbol_lines), encoding="utf-8")
        written.append(path)

    for label_type in ("strategy", "setup", "regime", "lane"):
        meta = LABEL_TYPES[label_type]
        folder = str(meta["folder"])
        note_type = str(meta["note_type"])
        title = str(meta["title"])
        for label in sorted(label_names[label_type]):
            using = _symbols_using_label(label_type, label, regimes, active_orders)
            lines = [
                f"# {label}",
                "",
                "## Role in profitability",
                f"Track whether this {title} contributes positive expectancy after costs, slippage, and protection exits. Keep it only if evidence supports it.",
                "",
                "## Performance Summary",
                *_performance_lines(stats_by_type[label_type].get(label)),
                "",
                f"## Symbols using this {title}",
            ]
            lines.extend(f"- {_symbol_link(symbol)}" for symbol in using) if using else lines.append("_None currently._")
            lines.extend(["", "## Evidence Links", f"- [[Daily/{CASH_BLEED_INDEX_NOTE}|Daily Reports]]", f"- [[Derivatives_Shadow/{DERIVATIVES_SHADOW_NOTE}|Derivatives Shadow Evidence]]"])
            path = root / folder / f"{_note_name(label)}.md"
            atomic_write(path, _frontmatter(note_type, f"{note_type}-{label}") + "\n".join(lines), encoding="utf-8")
            written.append(path)

    graphify_path = root / "System_Architecture" / f"{GRAPHIFY_NOTE}.md"
    atomic_write(graphify_path,
        _frontmatter("architecture", "graphify-pilot")
        + "# Graphify Pilot\n\n"
        + "Role: optional architecture graph for code/docs relationships. It is useful only if it helps identify execution/risk/reporting dependencies faster. It is not part of trading execution.\n\n"
        + "Profit filter: keep Graphify only if it reduces debugging/review time or exposes hidden system coupling that affects trading quality.\n",
        encoding="utf-8",
    )
    written.append(graphify_path)
    plain_log("OBSIDIAN_NAVIGATION_EXPORTED", {"count": len(written)})
    return written


def export_placeholder_pages(root: Path) -> list[Path]:
    """Create deterministic placeholder pages for legacy links so the graph has no broken nodes."""
    written: list[Path] = []
    placeholders = {
        root / "Setups" / "UNKNOWN.md": (
            _frontmatter("setup", "setup-UNKNOWN")
            + "# UNKNOWN\n\nPre-label-era placeholder for trade cards that do not have an `entry_setup_label`.\n\n## Rule\n\nDo not treat this as an active setup. Use it only to keep legacy backlinks resolved while labelled trade data improves.\n"
        ),
        root / "Regimes" / "UNKNOWN.md": (
            _frontmatter("regime", "regime-UNKNOWN")
            + "# UNKNOWN\n\nPre-label-era placeholder for trade cards that do not have a `regime_label`.\n\n## Rule\n\nDo not treat this as an active regime. Use it only to keep legacy backlinks resolved while labelled regime data improves.\n"
        ),
    }
    legacy_symbols = {
        "BTCUSD": "Legacy TradingView/MT5 BTC symbol. Prefer [[Symbols/BTCUSDT|BTCUSDT]] for current Binance Futures evidence.",
        "ETHUSD": "Legacy TradingView/MT5 ETH symbol. Prefer [[Symbols/ETHUSDT|ETHUSDT]] for current Binance Futures evidence.",
        "XRPUSDT": "Legacy/scouting XRP symbol. Currently not an active primary symbol unless reintroduced by evidence.",
        "XAUUSD": "Legacy gold symbol. Prefer [[Symbols/XAUUSDT|XAUUSDT]] where Binance-style normalized evidence exists.",
        "EURUSD": "Legacy FX symbol. Forex/MetaAPI path is paused; Binance crypto evidence is primary.",
    }
    for symbol, note in legacy_symbols.items():
        placeholders[root / "Symbols" / f"{symbol}.md"] = (
            _frontmatter("symbol", f"symbol-{symbol}")
            + f"# {symbol}\n\n{note}\n\n## Rule\n\nDo not treat this page as an active trading mandate. It exists to keep historical links resolved.\n"
        )

    for path, content in placeholders.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if "status: legacy_placeholder" not in existing and "Pre-label-era placeholder" not in existing and "historical links resolved" not in existing:
                continue
        if "status: legacy_placeholder" not in content:
            content = content.replace("source: ozzy-bot", "source: ozzy-bot\nstatus: legacy_placeholder")
        atomic_write(path, content, encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preferred-root", type=Path, default=PREFERRED_ROOT)
    parser.add_argument("--fallback-root", type=Path, default=FALLBACK_ROOT)
    args = parser.parse_args()

    root = resolve_export_root(args.preferred_root, args.fallback_root)
    if root is None:
        return 0
    paths = []
    regimes = _load_json_file(ROOT / "shared" / "market_regimes.json")
    active_orders = _load_json_file(ROOT / "shared" / "active_orders.json")
    trade_rows = load_all_trade_rows()
    paths.extend(export_navigation_pages(root, regimes, active_orders, trade_rows=trade_rows))
    paths.extend(export_derivatives_shadow_pages(root))
    paths.append(export_cash_bleed_snapshot(root, rows=trade_rows))

    regime_path = export_dangerboard_regimes(root)
    if regime_path:
        paths.append(regime_path)

    orders_path = export_active_blueprints(root)
    if orders_path:
        paths.append(orders_path)

    export_trade_cards(root, rows=trade_rows)
    paths.extend(export_placeholder_pages(root))

    for p in paths:
        print(f"Wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
