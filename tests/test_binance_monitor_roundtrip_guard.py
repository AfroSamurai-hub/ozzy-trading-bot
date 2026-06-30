import json
import tempfile
import unittest
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import binance_monitor


def trade_row(
    trade_id=100018,
    *,
    direction="BUY",
    qty=126.29,
    risk_dollars=200.06,
    peak_pnl=82.77,
    sl=71.174,
    execution_state="open",
    exit_price=None,
):
    ts = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": trade_id,
        "ts": ts,
        "symbol": "HYPEUSDT",
        "direction": direction,
        "qty": qty,
        "risk_dollars": risk_dollars,
        "peak_pnl": peak_pnl,
        "sl": sl,
        "entry_price": 72.721,
        "timeframe": "60",
        "setup_grade": "A",
        "execution_state": execution_state,
        "exit_price": exit_price,
    }


class RoundtripGuardR1Tests(unittest.TestCase):
    def setUp(self):
        binance_monitor._position_state.clear()
        self.tempdir = tempfile.TemporaryDirectory()
        self.observer_dir = Path(self.tempdir.name)
        self.observer_patch = patch.object(binance_monitor, "ROUNDTRIP_GUARD_OBSERVER_DIR", str(self.observer_dir))
        self.observer_patch.start()

    def tearDown(self):
        self.observer_patch.stop()
        self.tempdir.cleanup()
        binance_monitor._position_state.clear()

    def _position(self, *, current=71.85975, volume=126.29, side="BUY"):
        return {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "type": side,
            "openPrice": 72.721,
            "currentPrice": current,
            "volume": volume,
            "profit": -113.57,
        }

    def _prime_state(self, *, trade_id=100018, peak_r=0.414, peak_pnl=82.77):
        state = binance_monitor._get_state("HYPEUSDT")
        state.update(
            {
                "trade_id": trade_id,
                "entry_price": 72.721,
                "original_sl_distance": 1.547,
                "_peak_r": peak_r,
                "peak_pnl": peak_pnl,
            }
        )
        return state

    def _safe_patches(self, trade=None, exits=None, protection=None):
        client = Mock()
        client.futures_get_open_orders.return_value = [{"symbol": "HYPEUSDT"}]
        client.futures_get_open_algo_orders.return_value = []
        return (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade or trade_row()),
            patch.object(binance_monitor.trade_db, "get_exits_for_trade", return_value=exits if exits is not None else []),
            patch.object(binance_monitor.trade_db, "update_trade_peak"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(
                binance_monitor,
                "inspect_exchange_protection",
                return_value=protection
                if protection is not None
                else {"has_sl": True, "has_tp": True, "protected": True},
            ),
            patch.object(binance_monitor, "_open_trade_direction_mismatch", return_value=False),
        )

    def test_testnet_hype_style_trade_closes(self):
        self._prime_state()
        patches = self._safe_patches()
        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(
                    "os.environ",
                    {"HERMES_INSTANCE_NAME": "STANDARD TESTNET", "HERMES_PORT": "5000"},
                    clear=False,
                )
            )
            for p in patches:
                stack.enter_context(p)
            close_mock = stack.enter_context(
                patch.object(binance_monitor, "_protective_close", return_value={"status": "closed"})
            )
            log_exit = stack.enter_context(patch.object(binance_monitor.trade_db, "log_exit"))
            stack.enter_context(patch.object(binance_monitor, "_send_telegram"))
            plain_log = stack.enter_context(patch.object(binance_monitor, "plain_log"))
            binance_monitor._check_roundtrip_guard_r1(self._position())

        close_mock.assert_called_once_with("HYPEUSDT", 126.29, "roundtrip_guard_r1")
        log_exit.assert_called_once()
        self.assertEqual(log_exit.call_args.args[1], "roundtrip_guard_r1")
        self.assertTrue(any(c.args[0] == "ROUNDTRIP_GUARD_R1_TRIGGERED" for c in plain_log.call_args_list))

    def test_live_micro_creates_review_candidate_only(self):
        self._prime_state()
        patches = self._safe_patches()
        with ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {"HERMES_INSTANCE_NAME": "LIVE MICRO"}, clear=False))
            for p in patches:
                stack.enter_context(p)
            close_mock = stack.enter_context(patch.object(binance_monitor, "_protective_close"))
            notify = stack.enter_context(
                patch.object(binance_monitor.telegram_client, "notify_loss_minimization_candidate")
            )
            binance_monitor._check_roundtrip_guard_r1(self._position())

        close_mock.assert_not_called()
        notify.assert_called_once()
        data = json.loads((self.observer_dir / "loss_minimization_candidates.json").read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["candidate_id"], "LIVE_MICRO_HYPEUSDT_100018_ROUNDTRIP_CANDIDATE")
        self.assertEqual(data[0]["recommendation"], "EXIT_REVIEW")

    def test_peak_r_below_threshold_does_not_trigger(self):
        self._prime_state(peak_r=0.29, peak_pnl=58.0)
        with (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(peak_pnl=58.0)),
            patch.object(binance_monitor.trade_db, "update_trade_peak"),
            patch.object(binance_monitor, "_roundtrip_guard_safe_context") as safe,
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_roundtrip_guard_r1(self._position())
        safe.assert_not_called()
        close_mock.assert_not_called()

    def test_current_r_above_threshold_does_not_trigger(self):
        self._prime_state()
        with patch.object(binance_monitor, "_roundtrip_guard_safe_context") as safe, patch.object(
            binance_monitor, "_protective_close"
        ) as close_mock:
            binance_monitor._check_roundtrip_guard_r1(self._position(current=72.68))
        safe.assert_not_called()
        close_mock.assert_not_called()

    def test_giveback_below_threshold_does_not_trigger(self):
        self._prime_state(peak_r=0.414, peak_pnl=200.0)
        position = self._position(current=72.62)
        position["profit"] = 50.0
        with (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(peak_pnl=200.0)),
            patch.object(binance_monitor.trade_db, "update_trade_peak"),
            patch.object(binance_monitor, "_roundtrip_guard_safe_context") as safe,
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_roundtrip_guard_r1(position)
        safe.assert_not_called()
        close_mock.assert_not_called()

    def test_missing_exchange_position_does_not_close(self):
        self._prime_state()
        patches = self._safe_patches()
        with ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False))
            for p in patches:
                stack.enter_context(p)
            close_mock = stack.enter_context(patch.object(binance_monitor, "_protective_close"))
            plain_log = stack.enter_context(patch.object(binance_monitor, "plain_log"))
            binance_monitor._check_roundtrip_guard_r1(self._position(volume=0.0))

        close_mock.assert_not_called()
        self.assertTrue(any(c.args[0] == "ROUNDTRIP_GUARD_R1_SKIPPED" for c in plain_log.call_args_list))

    def test_duplicate_live_candidate_does_not_spam(self):
        self._prime_state()
        patches = self._safe_patches()
        with ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {"HERMES_INSTANCE_NAME": "LIVE MICRO"}, clear=False))
            for p in patches:
                stack.enter_context(p)
            notify = stack.enter_context(
                patch.object(binance_monitor.telegram_client, "notify_loss_minimization_candidate")
            )
            binance_monitor._check_roundtrip_guard_r1(self._position())
            binance_monitor._check_roundtrip_guard_r1(self._position())

        notify.assert_called_once()
        data = json.loads((self.observer_dir / "loss_minimization_candidates.json").read_text())
        self.assertEqual(len(data), 1)

    def test_protection_unknown_does_not_close(self):
        self._prime_state()
        client = Mock()
        client.futures_get_open_orders.side_effect = RuntimeError("orders unavailable")
        with (
            patch.dict("os.environ", {"HERMES_INSTANCE_NAME": "STANDARD TESTNET"}, clear=False),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row()),
            patch.object(binance_monitor.trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(binance_monitor.trade_db, "update_trade_peak"),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_open_trade_direction_mismatch", return_value=False),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_roundtrip_guard_r1(self._position())

        close_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
