#!/usr/bin/env python3
"""Print Phase 1 Ozzy Memory outcome summaries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ozzy_memory


def _rows(sql: str) -> list[dict]:
    with ozzy_memory._connect() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def build_report(backfill: bool = False) -> dict:
    """Return a console-friendly memory report with mode separation."""
    backfill_result = ozzy_memory.label_pending_outcomes() if backfill else None
    return {
        "backfill": backfill_result,
        "event_counts": _rows(
            "SELECT instance_mode, decision, COUNT(*) AS count FROM setup_events "
            "GROUP BY instance_mode, decision ORDER BY instance_mode, decision"
        ),
        "rejected_winners": _rows(
            "SELECT e.instance_mode, e.symbol, e.direction, e.grade, e.decision, o.window, o.mfe_r "
            "FROM setup_events e JOIN setup_outcomes o ON o.event_id = e.event_id "
            "WHERE e.decision IN ('rejected', 'shadow', 'blocked') AND o.hit_1r = 1 "
            "ORDER BY o.measured_at DESC LIMIT 20"
        ),
        "approved_losers": _rows(
            "SELECT e.instance_mode, e.symbol, e.direction, e.grade, o.window, o.final_r, o.mae_r "
            "FROM setup_events e JOIN setup_outcomes o ON o.event_id = e.event_id "
            "WHERE e.decision = 'approved' AND (o.hit_sl = 1 OR o.final_r <= -1) "
            "ORDER BY o.measured_at DESC LIMIT 20"
        ),
        "good_entry_bad_exit": _rows(
            "SELECT e.instance_mode, e.symbol, e.direction, e.grade, o.window, o.mfe_r, o.final_r "
            "FROM setup_events e JOIN setup_outcomes o ON o.event_id = e.event_id "
            "WHERE o.mfe_r >= 1 AND o.final_r <= 0 ORDER BY o.measured_at DESC LIMIT 20"
        ),
        "grade_health_by_r": _rows(
            "SELECT e.instance_mode, e.grade, COUNT(*) AS sample_count, "
            "ROUND(AVG(o.mfe_r), 4) AS avg_mfe_r, ROUND(AVG(o.mae_r), 4) AS avg_mae_r, "
            "ROUND(AVG(o.final_r), 4) AS avg_final_r "
            "FROM setup_events e JOIN setup_outcomes o ON o.event_id = e.event_id "
            "WHERE e.grade IS NOT NULL GROUP BY e.instance_mode, e.grade ORDER BY e.instance_mode, e.grade"
        ),
        "symbol_direction_heat": _rows(
            "SELECT e.instance_mode, e.symbol, e.direction, e.grade, COUNT(*) AS sample_count, "
            "ROUND(AVG(o.mfe_r), 4) AS avg_mfe_r, ROUND(AVG(o.hit_1r), 4) AS hit_1r_rate "
            "FROM setup_events e JOIN setup_outcomes o ON o.event_id = e.event_id "
            "GROUP BY e.instance_mode, e.symbol, e.direction, e.grade "
            "ORDER BY sample_count DESC, e.symbol LIMIT 30"
        ),
        "protection_failures": _rows(
            "SELECT created_at, trade_id, symbol, event_type, new_state, actor "
            "FROM trade_journal_events "
            "WHERE event_type LIKE '%protection%' OR new_state IN ('protection_truth_failed', 'execution_failed') "
            "ORDER BY created_at DESC LIMIT 20"
        ),
    }


def print_report(report: dict) -> None:
    """Print a readable console report."""
    print("# Ozzy Memory Report")
    for title, rows in report.items():
        if title == "backfill":
            if rows is not None:
                print(f"\nBackfill: {rows}")
            continue
        print(f"\n## {title.replace('_', ' ').title()}")
        if not rows:
            print("None")
            continue
        print(json.dumps(rows, indent=2, default=str))


def main() -> int:
    """Run the memory report command."""
    parser = argparse.ArgumentParser(description="Ozzy Memory Phase 1 report")
    parser.add_argument("--backfill", action="store_true", help="Label due 1h/4h/8h/24h windows first")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()
    report = build_report(backfill=args.backfill)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
