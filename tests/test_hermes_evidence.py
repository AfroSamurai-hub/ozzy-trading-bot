import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import hermes_evidence
import trade_db
from scripts import hermes_ai_brief


def _memory_report():
    return {
        "event_counts": [{"instance_mode": "TESTNET", "decision": "near", "count": 1}],
        "rejected_winners": [],
        "approved_losers": [],
        "good_entry_bad_exit": [],
        "grade_health_by_r": [],
        "symbol_direction_heat": [],
        "protection_failures": [],
    }


def _status(mode):
    return {
        "available": True,
        "source": f"local://{mode}",
        "data": {
            "execution_mode": "LIVE" if mode == "LIVE_MICRO" else "TESTNET",
            "active_symbols": ["ETHUSDT"],
            "effective_max_positions": 1,
            "risk": {"equity_usd": 34.0, "target_loss_at_sl_usd": 5.0},
            "daily_stop": {"model": "dollar_bootstrap", "live_blocked_for_day": False},
            "reconciliation": {"healthy": True, "warnings": [], "critical_mismatches": []},
            "protection_truth_required": True,
            "post_fill_protection_finalizer": {"active_mode": "repair"},
            "micro_bootstrap_active": mode == "LIVE_MICRO",
        },
    }


class HermesEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.live_db = root / "live.db"
        self.testnet_db = root / "testnet.db"
        self.live_log = root / "live.log"
        self.testnet_log = root / "testnet.log"
        self.journal_patch = patch.object(trade_db, "_journal_event")
        self.journal_patch.start()
        self._make_trade_db(self.live_db, "ETHUSDT", "live", 4)
        self._make_trade_db(self.testnet_db, "LINKUSDT", "testnet", 3)
        self.live_log.write_text(
            json.dumps({
                "ts": "2026-05-22 12:00:00",
                "event": "BINANCE_PROTECTION_TRUTH_FAILED",
                "symbol": "ETHUSDT",
                "trade_id": 7,
                "error": "missing stop",
            })
            + "\n"
        )
        self.testnet_log.write_text("")
        self.patches = [
            patch.object(hermes_evidence, "LIVE_DB_PATH", self.live_db),
            patch.object(hermes_evidence, "TESTNET_DB_PATH", self.testnet_db),
            patch.object(hermes_evidence, "LIVE_LOG_PATH", self.live_log),
            patch.object(hermes_evidence, "TESTNET_LOG_PATH", self.testnet_log),
            patch.object(hermes_evidence, "_fetch_status", side_effect=_status),
            patch.object(hermes_evidence, "build_memory_report", side_effect=lambda backfill=False: _memory_report()),
            patch.object(hermes_evidence, "_memory_journal_incidents", return_value=[]),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.journal_patch.stop()
        self.tempdir.cleanup()

    def _make_trade_db(self, path: Path, symbol: str, mode: str, count: int) -> None:
        with patch.object(trade_db, "DB_PATH", path):
            for idx in range(count):
                trade_id = trade_db.log_trade(
                    None,
                    symbol,
                    "BUY",
                    entry_price=100.0 + idx,
                    qty=1.0,
                    sl=99.0 if idx else None,
                    tp=102.5,
                    setup_grade="B",
                    risk_dollars=5.0 if idx else None,
                    mode="live",
                )
                if idx:
                    trade_db.update_trade_peak(trade_id, 3.0, 103.0)
                    trade_db.close_trade(trade_id, 100.0, -0.5, exit_reason="momentum_exit")
                    trade_db.log_exit(trade_id, "momentum_exit", price=100.0, pnl_contribution=-0.5)
                    trade_db.log_milestone(trade_id, "1R_breakeven", 102.0, 5.0)

    def test_pack_separates_live_and_testnet_and_bounds_lists(self):
        with patch.object(hermes_evidence, "HERMES_EVIDENCE_ROW_LIMIT", 2):
            pack = hermes_evidence.build_evidence_pack("review")

        self.assertEqual(pack["recent_live_trades"][0]["instance_mode"], "LIVE_MICRO")
        self.assertEqual(pack["recent_testnet_trades"][0]["instance_mode"], "TESTNET")
        self.assertLessEqual(len(pack["recent_live_trades"]), 2)
        self.assertLessEqual(len(pack["recent_testnet_trades"]), 2)
        self.assertEqual(pack["live_status"]["instance_mode"], "LIVE_MICRO")
        self.assertEqual(pack["testnet_status"]["instance_mode"], "TESTNET")

    def test_pack_omits_secrets_and_logs_real_incident_fields_without_cause(self):
        pack = hermes_evidence.build_evidence_pack()
        encoded = json.dumps(pack, default=str)
        incident = pack["protection_and_execution_incidents"]["structured_log_events"][0]

        self.assertNotIn("GEMINI_API_KEY", encoded)
        self.assertNotIn("TELEGRAM_TOKEN", encoded)
        self.assertEqual(incident["error"], "missing stop")
        self.assertNotIn("cause", incident)
        self.assertIn("No incident cause is known", pack["protection_and_execution_incidents"]["root_cause_policy"])

    def test_exit_quality_does_not_fabricate_r_without_anchor(self):
        pack = hermes_evidence.build_evidence_pack()
        givebacks = pack["exit_quality"]["profit_giveback_candidates"]

        self.assertTrue(all(candidate.get("peak_r_from_risk_usd") is not None for candidate in givebacks))
        unanchored = next(row for row in pack["recent_live_trades"] if row["risk_usd"] is None)
        self.assertIsNone(unanchored["r_multiple"])
        self.assertIsNone(unanchored["realized_r_from_risk_usd"])

    def test_trade_quality_flags_zero_entry_and_historical_fail_close_state(self):
        with patch.object(trade_db, "DB_PATH", self.live_db):
            bad_trade = trade_db.log_trade(
                None,
                "LINKUSDT",
                "BUY",
                entry_price=0.0,
                qty=1.0,
                sl=9.0,
                risk_dollars=5.0,
                mode="live",
            )
            trade_db.close_trade(bad_trade, exit_price=0.0, pnl=-2.5, exit_reason="execution_failed")
            with trade_db._connect() as conn:
                conn.execute("UPDATE trades SET execution_state = 'confirmed' WHERE id = ?", (bad_trade,))
                conn.commit()

        pack = hermes_evidence.build_evidence_pack()
        row = next(item for item in pack["recent_live_trades"] if item["trade_id"] == bad_trade)

        self.assertEqual(row["realized_r_from_risk_usd"], -0.5)
        self.assertIn("invalid_nonpositive_entry_anchor", row["data_quality_flags"])
        self.assertIn("historical_fail_close_state_not_normalized", row["data_quality_flags"])
        self.assertTrue(any("invalid nonpositive entry anchors" in note for note in pack["data_quality_notes"]))

    def test_missing_sources_are_explicit_data_quality_notes(self):
        missing = Path(self.tempdir.name) / "missing.db"
        with (
            patch.object(hermes_evidence, "LIVE_DB_PATH", missing),
            patch.object(
                hermes_evidence,
                "_fetch_status",
                side_effect=lambda mode: {
                    "available": False,
                    "source": "local://missing",
                    "error": "offline",
                },
            ),
        ):
            pack = hermes_evidence.build_evidence_pack()

        self.assertFalse(pack["live_status"]["available"])
        self.assertEqual(pack["recent_live_trades"], [])
        self.assertTrue(any("LIVE_MICRO recent trades unavailable" in note for note in pack["data_quality_notes"]))

    def test_brief_json_evidence_uses_v2_pack(self):
        output = StringIO()
        expected = {"runtime_context": {"advisor_role": "read_only_evidence_advisor"}}
        with (
            patch.object(hermes_ai_brief.hermes_evidence, "build_evidence_pack", return_value=expected),
            patch("sys.argv", ["hermes_ai_brief.py", "--json-evidence"]),
            redirect_stdout(output),
        ):
            self.assertEqual(hermes_ai_brief.main(), 0)

        self.assertEqual(json.loads(output.getvalue()), expected)


if __name__ == "__main__":
    unittest.main()
