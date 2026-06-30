import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trade_db
from scripts.report_derivatives_shadow import (
    aggregate_by_dimension,
    aggregate_by_verdict,
    correlate_outcomes,
    extract_shadow_events,
    load_trade_outcomes,
    render_markdown_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class DerivativesShadowReportTests(unittest.TestCase):
    def test_extracts_only_openclaw_rows_with_derivatives_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trades.log"
            _write_jsonl(
                log_path,
                [
                    {"ts": "2026-06-14 10:00:00", "event": "OTHER", "symbol": "SOLUSDT"},
                    {
                        "ts": "2026-06-14 10:01:00",
                        "event": "OPENCLAW_BREAKOUT_CHECK",
                        "verdict": {
                            "symbol": "SOLUSDT",
                            "signal": "BUY",
                            "passed": False,
                            "derivatives_context": {
                                "verdict": "supportive",
                                "score": 3,
                                "reasons": ["oi_confirms_new_longs"],
                                "metrics": {"open_interest_delta_pct": 2.5},
                            },
                        },
                    },
                ],
            )

            events = extract_shadow_events(log_path)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "WAIT")
        self.assertEqual(events[0]["symbol"], "SOLUSDT")
        self.assertEqual(events[0]["derivatives_verdict"], "supportive")
        self.assertEqual(events[0]["score"], 3)

    def test_extracts_entry_setup_strategy_and_regime_labels_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trades.log"
            _write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-06-14 10:01:00",
                        "event": "OPENCLAW_BREAKOUT_FIRED",
                        "blueprint": {"symbol": "XAUUSDT", "side": "BUY", "entry_setup_label": "OPENCLAW_BREAKOUT"},
                        "verdict": {
                            "strategy_label": "BREAKOUT_RETEST",
                            "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT",
                            "configured_lane": "Macro",
                            "derivatives_context": {"verdict": "supportive", "score": 2},
                        },
                    }
                ],
            )

            events = extract_shadow_events(log_path)

        self.assertEqual(events[0]["entry_setup_label"], "OPENCLAW_BREAKOUT")
        self.assertEqual(events[0]["strategy_label"], "BREAKOUT_RETEST")
        self.assertEqual(events[0]["regime_label"], "OPENCLAW_4H_MACRO_BREAKOUT")
        self.assertEqual(events[0]["configured_lane"], "Macro")

    def test_correlates_nearest_outcome_by_symbol_signal_and_time(self):
        events = [
            {
                "ts": "2026-06-14 10:01:00",
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "derivatives_verdict": "supportive",
                "score": 3,
                "status": "FIRED",
            }
        ]
        trade_outcomes = [
            {
                "trade_id": 1,
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "_parsed_ts": datetime.fromisoformat("2026-06-14T10:20:00+00:00"),
                "_outcome": "win",
                "r_multiple": 2.5,
            }
        ]

        correlated = correlate_outcomes(events, trade_outcomes=trade_outcomes, tolerance_minutes=90)

        self.assertEqual(correlated[0]["outcome"], "win")
        self.assertEqual(correlated[0]["r_multiple"], 2.5)

    def test_aggregate_by_verdict_counts_status_and_outcomes(self):
        events = [
            {"derivatives_verdict": "supportive", "status": "WAIT", "outcome": "unresolved", "score": 3},
            {"derivatives_verdict": "supportive", "status": "FIRED", "outcome": "win", "score": 2},
            {"derivatives_verdict": "conflict", "status": "FIRED", "outcome": "loss", "score": -2},
        ]

        stats = aggregate_by_verdict(events)

        self.assertEqual(stats["supportive"]["total"], 2)
        self.assertEqual(stats["supportive"]["status_counts"]["WAIT"], 1)
        self.assertEqual(stats["supportive"]["outcome_counts"]["win"], 1)
        self.assertEqual(stats["supportive"]["avg_score"], 2.5)
        self.assertEqual(stats["conflict"]["outcome_counts"]["loss"], 1)

    def test_aggregate_by_dimension_summarizes_symbols_and_setups(self):
        events = [
            {"symbol": "SOLUSDT", "entry_setup_label": "OPENCLAW_BREAKOUT", "derivatives_verdict": "supportive", "status": "FIRED", "outcome": "win", "score": 3, "r_multiple": 2.5},
            {"symbol": "SOLUSDT", "entry_setup_label": "OPENCLAW_BREAKOUT", "derivatives_verdict": "conflict", "status": "WAIT", "outcome": "unresolved", "score": -1},
            {"symbol": "ETHUSDT", "entry_setup_label": "PULLBACK_B", "derivatives_verdict": "crowded", "status": "FIRED", "outcome": "loss", "score": -2, "r_multiple": -1.0},
        ]

        by_symbol = aggregate_by_dimension(events, "symbol")
        by_setup = aggregate_by_dimension(events, "entry_setup_label")

        self.assertEqual(by_symbol["SOLUSDT"]["total"], 2)
        self.assertEqual(by_symbol["SOLUSDT"]["resolved"], 1)
        self.assertEqual(by_symbol["SOLUSDT"]["win_rate"], 100.0)
        self.assertEqual(by_symbol["SOLUSDT"]["verdict_counts"]["supportive"], 1)
        self.assertEqual(by_setup["OPENCLAW_BREAKOUT"]["avg_r_multiple"], 2.5)
        self.assertEqual(by_setup["PULLBACK_B"]["win_rate"], 0.0)

    def test_markdown_report_includes_symbol_and_setup_breakdowns(self):
        events = [
            {"symbol": "SOLUSDT", "entry_setup_label": "OPENCLAW_BREAKOUT", "derivatives_verdict": "supportive", "status": "FIRED", "outcome": "win", "score": 3, "r_multiple": 2.5}
        ]
        markdown = render_markdown_report(events, aggregate_by_verdict(events))

        self.assertIn("## By Symbol", markdown)
        self.assertIn("SOLUSDT", markdown)
        self.assertIn("## By Entry Setup", markdown)
        self.assertIn("OPENCLAW_BREAKOUT", markdown)

    def test_markdown_report_includes_insufficient_data_warning(self):
        markdown = render_markdown_report([], {})

        self.assertIn("Derivatives Shadow Report", markdown)
        self.assertIn("No derivatives-context rows found", markdown)

    def test_load_trade_outcomes_handles_sqlite_row_factory_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "trades.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute(
                    "CREATE TABLE trades (id INTEGER PRIMARY KEY, ts TEXT, symbol TEXT, direction TEXT, exit_price REAL, pnl REAL, r_multiple REAL)"
                )
                conn.execute(
                    "INSERT INTO trades (id, ts, symbol, direction, exit_price, pnl, r_multiple) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (1, "2026-06-14 10:20:00", "SOLUSDT", "BUY", 101.5, 2.25, 2.5),
                )
                conn.commit()

            @contextmanager
            def fake_connect():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                finally:
                    conn.close()

            with patch.object(trade_db, "_connect", fake_connect):
                outcomes = load_trade_outcomes()

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["symbol"], "SOLUSDT")
        self.assertEqual(outcomes[0]["signal"], "BUY")
        self.assertEqual(outcomes[0]["_outcome"], "win")
        self.assertEqual(outcomes[0]["r_multiple"], 2.5)


if __name__ == "__main__":
    unittest.main()
