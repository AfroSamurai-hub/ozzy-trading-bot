#!/usr/bin/env python3
"""Generate read-only cash-bleed reports from the unified trade DB."""

from __future__ import annotations

import argparse
import csv
from contextlib import closing
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTNET_DB = ROOT / "trades.db"
DEFAULT_LIVE_DB = ROOT / "trades.db"
DEFAULT_OBSERVER_DIR = ROOT / "observer"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        try:
            parsed = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _read_trades(path: Path) -> tuple[list[dict], list[str]]:
    warnings = []
    if not path.exists():
        return [], [f"missing DB: {path}"]
    try:
        with closing(_connect_readonly(path)) as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM trades").fetchall()]
    except Exception as exc:
        return [], [f"failed to read {path}: {exc}"]
    if rows:
        sample = rows[0]
        for column in ("strategy_label", "entry_setup_label", "regime_label", "execution_mode"):
            if column not in sample:
                warnings.append(f"{path.name} missing column {column}; falling back where possible")
    return rows, warnings


def _row_mode(row: dict) -> str:
    mode = row.get("mode") or row.get("execution_mode") or ""
    return str(mode).strip().lower()


def _rows_for_dataset(rows: list[dict], dataset: str) -> list[dict]:
    wanted_modes = {
        "STANDARD_TESTNET": {"testnet", "standard_testnet"},
        "LIVE_MICRO": {"live", "live_micro"},
    }.get(dataset.upper(), set())
    if not wanted_modes:
        return list(rows)
    selected = [row for row in rows if _row_mode(row) in wanted_modes]
    return selected


def _read_json_list(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _num(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) if row.get(key) is not None else default)
    except Exception:
        return default


def _final_r(row: dict) -> float | None:
    existing = row.get("r_multiple")
    if existing is not None:
        try:
            return float(existing)
        except Exception:
            pass
    risk = _num(row, "risk_dollars")
    if risk <= 0:
        return None
    return _num(row, "pnl") / risk


def _peak_r(row: dict) -> float | None:
    risk = _num(row, "risk_dollars")
    if risk <= 0:
        return None
    return _num(row, "peak_pnl") / risk


def _giveback_pct(row: dict) -> float | None:
    peak = _peak_r(row)
    final = _final_r(row)
    if peak is None or final is None or peak <= 0:
        return None
    return max(0.0, ((peak - final) / peak) * 100.0)


def _exit_at(row: dict) -> datetime | None:
    opened = _parse_dt(row.get("ts"))
    if not opened:
        return None
    duration = row.get("duration_min")
    try:
        return opened + timedelta(minutes=float(duration or 0))
    except Exception:
        return opened


def _filter_closed(rows: list[dict], since: datetime) -> list[dict]:
    selected = []
    for row in rows:
        if row.get("exit_price") is None:
            continue
        ts = _exit_at(row) or _parse_dt(row.get("ts"))
        if ts and ts >= since:
            selected.append(row)
    return selected


def _bucket(rows: list[dict], key: str) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0, "gross_pnl": 0.0})
    for row in rows:
        label = row.get(key) or ("UNKNOWN" if key != "strategy_label" else row.get("strategy") or "UNKNOWN")
        bucket = buckets[str(label)]
        pnl = _num(row, "pnl")
        bucket["count"] += 1
        bucket["wins"] += 1 if pnl > 0 else 0
        bucket["pnl"] += pnl
        bucket["gross_pnl"] += _num(row, "gross_pnl", pnl)
    return [
        {
            "bucket": name,
            "count": data["count"],
            "wins": data["wins"],
            "pnl": round(data["pnl"], 4),
            "gross_pnl": round(data["gross_pnl"], 4),
        }
        for name, data in sorted(buckets.items(), key=lambda item: item[1]["pnl"])
    ]


def _green_to_red(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        pnl = _num(row, "pnl")
        peak_pnl = _num(row, "peak_pnl")
        if pnl < 0 and peak_pnl > 0:
            result.append(_trade_summary(row))
    return result


def _grade_b_no_progress(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        if str(row.get("setup_grade") or "").upper() != "B":
            continue
        peak = _peak_r(row)
        pnl = _num(row, "pnl")
        if pnl < 0 and (peak is None or peak < 0.1):
            result.append(_trade_summary(row))
    return result


def _trade_summary(row: dict) -> dict:
    return {
        "trade_id": row.get("id"),
        "symbol": row.get("symbol"),
        "side": row.get("direction"),
        "strategy_label": row.get("strategy_label") or row.get("strategy") or "UNKNOWN",
        "strategy": row.get("strategy"),
        "timeframe": row.get("timeframe"),
        "setup_grade": row.get("setup_grade"),
        "exit_reason": row.get("exit_reason"),
        "pnl": round(_num(row, "pnl"), 4),
        "peak_pnl": round(_num(row, "peak_pnl"), 4),
        "final_r": round(_final_r(row), 4) if _final_r(row) is not None else None,
        "peak_r": round(_peak_r(row), 4) if _peak_r(row) is not None else None,
        "giveback_pct": round(_giveback_pct(row), 2) if _giveback_pct(row) is not None else None,
        "duration_min": row.get("duration_min"),
    }


def _candidate_by_trade(observer_dir: Path) -> dict[str, dict]:
    candidates = _read_json_list(observer_dir / "loss_minimization_candidates.json")
    indexed = {}
    for item in candidates:
        trade_id = item.get("trade_id")
        if trade_id is not None:
            indexed[str(trade_id)] = item
    return indexed


def _candidate_timing(rows: list[dict], observer_dir: Path) -> list[dict]:
    candidates = _candidate_by_trade(observer_dir)
    result = []
    for row in rows:
        candidate = candidates.get(str(row.get("id")))
        if not candidate:
            continue
        created = _parse_dt(candidate.get("created_at") or candidate.get("first_seen_at"))
        exit_at = _exit_at(row)
        minutes = None
        if created and exit_at:
            minutes = round((exit_at - created).total_seconds() / 60.0, 2)
        result.append(
            {
                "trade_id": row.get("id"),
                "symbol": row.get("symbol"),
                "exit_reason": row.get("exit_reason"),
                "candidate_id": candidate.get("id") or candidate.get("candidate_id"),
                "candidate_status": candidate.get("status"),
                "candidate_to_close_min": minutes,
            }
        )
    return result


def _accounting_warnings(rows: list[dict], observer_dir: Path, log_paths: list[Path]) -> list[str]:
    warnings = []
    for row in rows:
        peak = _num(row, "peak_pnl")
        pnl = _num(row, "pnl")
        if row.get("exit_price") is None and peak < pnl:
            warnings.append(f"peak_pnl inconsistency trade_id={row.get('id')} symbol={row.get('symbol')}: peak {peak} < pnl {pnl}")
        accounting = str(row.get("accounting_status") or "clean").lower()
        if accounting not in {"", "clean", "unchecked"}:
            warnings.append(f"dirty accounting trade_id={row.get('id')} symbol={row.get('symbol')}: {accounting}")

    queue = _read_json_list(observer_dir / "action_queue.json")
    now = datetime.now(UTC)
    stale = 0
    for item in queue:
        created = _parse_dt(item.get("created_at") or item.get("ts") or item.get("timestamp"))
        status = str(item.get("status") or "pending").lower()
        if created and (now - created).total_seconds() > 6 * 3600 and status in {"pending", "open", "active"}:
            stale += 1
    if stale:
        warnings.append(f"stale action_queue entries: {stale}")

    for path in log_paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()[-5000:]
        except Exception:
            continue
        orphan_count = sum(1 for line in lines if "ORPHAN_EXCHANGE_POSITION" in line)
        ghost_count = sum(1 for line in lines if "DB_GHOST_TRADE" in line)
        if orphan_count:
            warnings.append(f"{path}: ORPHAN_EXCHANGE_POSITION seen {orphan_count} times in last 5000 lines")
        if ghost_count:
            warnings.append(f"{path}: DB_GHOST_TRADE seen {ghost_count} times in last 5000 lines")
    return warnings


def _section_for(label: str, rows: list[dict], observer_dir: Path, warnings: list[str]) -> dict:
    return {
        "label": label,
        "closed_count": len(rows),
        "pnl_by_exit_reason": _bucket(rows, "exit_reason"),
        "pnl_by_strategy_label": _bucket(rows, "strategy_label"),
        "pnl_by_symbol": _bucket(rows, "symbol"),
        "pnl_by_timeframe": _bucket(rows, "timeframe"),
        "momentum_exit_losses": [_trade_summary(row) for row in rows if row.get("exit_reason") == "momentum_exit" and _num(row, "pnl") < 0],
        "micro_bleed_losses": [_trade_summary(row) for row in rows if row.get("exit_reason") == "micro_bleed_exit" and _num(row, "pnl") < 0],
        "protective_results": [_bucket([row for row in rows if row.get("exit_reason") in {"trail", "profit_protect", "tp"}], "exit_reason")],
        "green_to_red": _green_to_red(rows),
        "grade_b_no_progress": _grade_b_no_progress(rows),
        "candidate_timing": _candidate_timing(rows, observer_dir),
        "warnings": warnings,
    }


def build_report(
    *,
    testnet_db: Path = DEFAULT_TESTNET_DB,
    live_db: Path = DEFAULT_LIVE_DB,
    observer_dir: Path = DEFAULT_OBSERVER_DIR,
    report_date: date | None = None,
) -> dict:
    report_date = report_date or datetime.now().date()
    datasets = []
    all_warnings = []
    for mode, path in (("STANDARD_TESTNET", testnet_db), ("LIVE_MICRO", live_db)):
        rows, warnings = _read_trades(path)
        rows = _rows_for_dataset(rows, mode)
        all_warnings.extend(f"{mode}: {warning}" for warning in warnings)
        log_paths = [ROOT / "trades.log", ROOT / "live_micro" / "trades_live.log"]
        all_warnings.extend(f"{mode}: {warning}" for warning in _accounting_warnings(rows, observer_dir, log_paths))
        now = datetime.now(UTC)
        datasets.append(
            {
                "mode": mode,
                "path": str(path),
                "sections": [
                    _section_for("last_48h", _filter_closed(rows, now - timedelta(hours=48)), observer_dir, warnings),
                    _section_for("last_7d", _filter_closed(rows, now - timedelta(days=7)), observer_dir, warnings),
                ],
            }
        )
    return {"date": report_date.isoformat(), "datasets": datasets, "warnings": all_warnings}


def _markdown_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "_None._\n"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict) -> str:
    lines = [f"# Cash Bleed Report {report['date']}", ""]
    for dataset in report["datasets"]:
        lines.extend([f"## {dataset['mode']}", f"DB: `{dataset['path']}`", ""])
        for section in dataset["sections"]:
            lines.extend([f"### {section['label']}", f"Closed trades: {section['closed_count']}", ""])
            for title, key in (
                ("PnL by exit_reason", "pnl_by_exit_reason"),
                ("PnL by strategy_label", "pnl_by_strategy_label"),
                ("PnL by symbol", "pnl_by_symbol"),
                ("PnL by timeframe", "pnl_by_timeframe"),
            ):
                lines.extend([f"#### {title}", _markdown_table(section[key], ["bucket", "count", "wins", "pnl", "gross_pnl"])])
            lines.extend(
                [
                    "#### MOMENTUM_EXIT Losses",
                    _markdown_table(section["momentum_exit_losses"], ["trade_id", "symbol", "side", "pnl", "peak_r", "final_r", "giveback_pct"]),
                    "#### MICRO_BLEED Purge Trades",
                    _markdown_table(section["micro_bleed_losses"], ["trade_id", "symbol", "side", "pnl", "peak_r", "final_r", "giveback_pct"]),
                    "#### Trail / Profit Protect / TP Results",
                    _markdown_table(section["protective_results"][0], ["bucket", "count", "wins", "pnl", "gross_pnl"]),
                    "#### Green To Red Trades",
                    _markdown_table(section["green_to_red"], ["trade_id", "symbol", "side", "pnl", "peak_pnl", "peak_r", "final_r", "giveback_pct"]),
                    "#### Grade B No-Progress Trades",
                    _markdown_table(section["grade_b_no_progress"], ["trade_id", "symbol", "side", "pnl", "peak_r", "final_r", "exit_reason"]),
                    "#### EXIT_REVIEW Candidate To Close",
                    _markdown_table(section["candidate_timing"], ["trade_id", "symbol", "exit_reason", "candidate_status", "candidate_to_close_min"]),
                ]
            )
    lines.extend(["## DB / Accounting Warnings", _markdown_table([{"warning": w} for w in report["warnings"]], ["warning"])])
    return "\n".join(lines)


def write_outputs(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"cash_bleed_report_{report['date'].replace('-', '')}.md"
    csv_path = output_dir / f"cash_bleed_report_{report['date'].replace('-', '')}.csv"
    md_path.write_text(render_markdown(report))
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["mode", "window", "table", "bucket", "count", "wins", "pnl", "gross_pnl"])
        writer.writeheader()
        for dataset in report["datasets"]:
            for section in dataset["sections"]:
                for table in ("pnl_by_exit_reason", "pnl_by_strategy_label", "pnl_by_symbol", "pnl_by_timeframe"):
                    for row in section[table]:
                        writer.writerow({"mode": dataset["mode"], "window": section["label"], "table": table, **row})
    return md_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--testnet-db", type=Path, default=DEFAULT_TESTNET_DB)
    parser.add_argument("--live-db", type=Path, default=DEFAULT_LIVE_DB)
    parser.add_argument("--observer-dir", type=Path, default=DEFAULT_OBSERVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()

    report = build_report(testnet_db=args.testnet_db, live_db=args.live_db, observer_dir=args.observer_dir)
    md_path, csv_path = write_outputs(report, args.output_dir)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
