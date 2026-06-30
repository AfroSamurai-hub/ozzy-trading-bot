import json
import tempfile
import unittest
from pathlib import Path

from scripts.ozzy_log_viewer import (
    format_table,
    group_events,
    grouped_headers_for_view,
    is_live_disabled_heartbeat,
    is_unsafe_event,
    matches_symbol,
    matches_view,
    matches_mode,
    parse_json_log_line,
    read_observer_auto_actions,
    row_for_group,
    row_for_event,
)


class OzzyLogViewerTests(unittest.TestCase):
    def test_parse_json_log_line_handles_journal_prefix(self):
        line = (
            'Jun 03 08:40:47 host python[123]: {"ts": "2026-06-03 08:40:47", '
            '"event": "AUTO_PROTECT_HEARTBEAT", "mode": "TESTNET", "enabled": true}'
        )

        event = parse_json_log_line(line)

        self.assertIsNotNone(event)
        self.assertEqual(event["event"], "AUTO_PROTECT_HEARTBEAT")
        self.assertTrue(event["enabled"])

    def test_parse_json_log_line_ignores_non_json(self):
        self.assertIsNone(parse_json_log_line("Jun 03 plain service noise"))
        self.assertIsNone(parse_json_log_line("not-json {broken"))

    def test_auto_protect_row_uses_missing_field_dashes(self):
        event = {
            "ts": "2026-06-03 08:40:47",
            "event": "AUTO_PROTECT_HEARTBEAT",
            "mode": "TESTNET",
            "enabled": True,
            "dry_run": True,
            "cash_ratchet_enabled": True,
            "live_auto_protect_enabled": False,
            "open_positions": 7,
            "candidates_created": 0,
        }

        row = row_for_event(event, "auto-protect")

        self.assertEqual(row[1], "TESTNET")
        self.assertEqual(row[2], "true")
        self.assertEqual(row[4], "true")
        self.assertEqual(row[5], "false")
        self.assertEqual(row[8], "-")

    def test_trade_and_protection_view_matching(self):
        self.assertTrue(matches_view({"event": "APPROVED"}, "trades"))
        self.assertTrue(matches_view({"event": "ROUNDTRIP_GUARD_R1_SKIPPED"}, "protection"))
        self.assertTrue(matches_view({"event": "PROTECTION_VERIFIED"}, "protection"))
        self.assertFalse(matches_view({"event": "POSITION_QTY_RECONCILED"}, "trades"))

    def test_symbol_filter_checks_nested_protection_detail(self):
        event = {"event": "ROUNDTRIP_GUARD_R1_SKIPPED", "protection_detail": {"symbol": "HYPEUSDT"}}

        self.assertTrue(matches_symbol(event, "HYPEUSDT"))
        self.assertFalse(matches_symbol(event, "ETHUSDT"))

    def test_read_observer_auto_actions_normalizes_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            observer = Path(tmp)
            (observer / "auto_protect_actions.json").write_text(
                json.dumps(
                    [
                        {
                            "created_at": "2026-06-03T05:27:21+00:00",
                            "mode": "TESTNET",
                            "symbol": "HYPEUSDT",
                            "trade_id": 100045,
                            "rule": "roundtrip_winner",
                            "intended_action": "PROTECT",
                            "dry_run": True,
                            "executed": False,
                            "reason": "testnet_auto_protect_disabled_report_only",
                        }
                    ]
                )
            )

            rows = read_observer_auto_actions(observer)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "AUTO_PROTECT_ACTION")
        self.assertEqual(rows[0]["ts"], "2026-06-03T05:27:21+00:00")

    def test_format_table_renders_headers_and_rows(self):
        table = format_table(["time", "event"], [["2026-06-03", "APPROVED"]])

        self.assertIn("time", table)
        self.assertIn("APPROVED", table)

    def test_mode_filter_matches_testnet_and_live(self):
        self.assertTrue(matches_mode({"mode": "TESTNET"}, "TESTNET"))
        self.assertTrue(matches_mode({"execution_mode": "live"}, "LIVE"))
        self.assertTrue(matches_mode({"mode": "LIVE"}, "ALL"))
        self.assertFalse(matches_mode({"mode": "LIVE"}, "TESTNET"))

    def test_mode_filter_recognizes_unified_instance_synonyms(self):
        self.assertTrue(matches_mode({"mode": "standard_testnet"}, "TESTNET"))
        self.assertTrue(matches_mode({"mode": "live_micro"}, "LIVE"))
        self.assertTrue(matches_mode({"execution_mode": "LIVE_MICRO"}, "LIVE"))
        self.assertTrue(matches_mode({"execution_mode": "STANDARD_TESTNET"}, "TESTNET"))

    def test_live_disabled_heartbeat_detected(self):
        event = {
            "event": "AUTO_PROTECT_HEARTBEAT",
            "mode": "LIVE",
            "enabled": False,
            "reason": "live_auto_protect_disabled",
        }

        self.assertTrue(is_live_disabled_heartbeat(event))

    def test_group_repeated_roundtrip_skips(self):
        events = [
            {
                "ts": "2026-06-03 08:27:49",
                "event": "ROUNDTRIP_GUARD_R1_SKIPPED",
                "symbol": "HYPEUSDT",
                "trade_id": 100045,
                "protection_detail": {"has_sl": False, "has_tp": True, "protected": False},
                "reason": "sl_not_exchange_visible",
            },
            {
                "ts": "2026-06-03 08:47:52",
                "event": "ROUNDTRIP_GUARD_R1_SKIPPED",
                "symbol": "HYPEUSDT",
                "trade_id": 100045,
                "protection_detail": {"has_sl": False, "has_tp": True, "protected": False},
                "reason": "sl_not_exchange_visible",
            },
        ]

        groups = group_events(events, "protection")
        row = row_for_group(groups[0], "protection")

        self.assertEqual(len(groups), 1)
        self.assertEqual(row[:10], [
            "08:27:49",
            "08:47:52",
            "2",
            "ROUNDTRIP_GUARD_R1_SKIPPED",
            "HYPEUSDT",
            "100045",
            "false",
            "true",
            "false",
            "sl_not_exchange_visible",
        ])

    def test_errors_only_detects_unsafe_rows(self):
        self.assertTrue(is_unsafe_event({"event": "AUTO_PROTECT_ACTION", "executed": True}))
        self.assertTrue(is_unsafe_event({"event": "AUTO_PROTECT_HEARTBEAT", "mode": "LIVE"}))
        self.assertTrue(is_unsafe_event({"event": "AUTO_PROTECT_HEARTBEAT", "dry_run": False}))
        self.assertTrue(is_unsafe_event({"event": "AUTO_PROTECT_HEARTBEAT", "live_auto_protect_enabled": True}))
        self.assertTrue(is_unsafe_event({"event": "X", "protection_detail": {"has_sl": False}}))
        self.assertFalse(is_unsafe_event({"event": "AUTO_PROTECT_HEARTBEAT", "mode": "TESTNET", "dry_run": True}))

    def test_grouped_headers_include_desired_protection_columns(self):
        headers = grouped_headers_for_view("protection")

        self.assertEqual(headers[:10], [
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
        ])


if __name__ == "__main__":
    unittest.main()
