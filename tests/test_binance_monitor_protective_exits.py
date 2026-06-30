import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import binance_monitor
import logger


def trade_row(hours_old: float) -> dict:
    ts = (datetime.now(UTC) - timedelta(hours=hours_old)).strftime("%Y-%m-%d %H:%M:%S")
    return {"ts": ts}


class BinanceMonitorProtectiveExitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.log_patch = patch.object(logger, "LOG_FILE", Path(self.tempdir.name) / "trades.log")
        self.db_patch = patch.object(
            binance_monitor.trade_db,
            "DB_PATH",
            Path(self.tempdir.name) / "trades.db",
        )
        self.log_patch.start()
        self.db_patch.start()
        binance_monitor._position_state.clear()

    def tearDown(self):
        self.db_patch.stop()
        self.log_patch.stop()
        self.tempdir.cleanup()

    def _position(self, side="SELL", current=90.0, volume=10.0):
        return {
            "symbol": "SOLUSDT",
            "tv_symbol": "SOLUSDT",
            "type": side,
            "currentPrice": current,
            "volume": volume,
            "updateTime": int(datetime.now(UTC).timestamp() * 1000),
        }

    def test_time_reduce_closes_exactly_half_using_db_open_time(self):
        state = binance_monitor._get_state("SOLUSDT")
        state["trade_id"] = 101
        state["original_qty"] = 10.0

        with (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(17)),
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=False),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(
                binance_monitor,
                "close_position_qty",
                return_value={
                    "status": "partial_closed",
                    "quantity": 3.0,
                    "quantity_source": "create_response.executedQty",
                    "accounting_confirmed": True,
                },
            ) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_time_based_exit(self._position(volume=6.0))

        close_mock.assert_called_once_with("SOLUSDT", 3.0, reason="time_reduce")
        log_exit.assert_called_once()
        self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.3, delta=1e-12)
        self.assertTrue(state["time_reduced"])

    def test_tiered_exit_records_fraction_of_original_not_current_position(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({"trade_id": 704, "original_qty": 100.0, "tiered_exits": []})
        cc_state = binance_monitor._get_position_state("SOLUSDT")
        cc_state["original_sl_distance"] = 10.0
        position = {
            "symbol": "SOLUSDT",
            "tv_symbol": "SOLUSDT",
            "type": "BUY",
            "openPrice": 100.0,
            "currentPrice": 115.0,
            "profit": 750.0,
            "volume": 50.0,
        }
        close_result = {
            "status": "partial_closed",
            "quantity": 25.0,
            "requested_quantity": 25.0,
            "quantity_source": "create_response.executedQty",
            "accounting_confirmed": True,
            "order_id": 705,
            "fill_ids": [],
        }
        with (
            patch.object(binance_monitor, "PAPER_MODE", False),
            patch.object(binance_monitor, "close_position_qty", return_value=close_result),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_tiered_exits(position)

        self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.25, delta=1e-12)

    def test_time_exit_closes_remaining_and_uses_db_time_not_position_update_time(self):
        state = binance_monitor._get_state("SOLUSDT")
        state["trade_id"] = 102

        with (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(25)),
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=False),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_time_based_exit(self._position(volume=7.0))

        close_mock.assert_called_once_with("SOLUSDT", 7.0, reason="time_exit")
        log_exit.assert_called_once()
        self.assertTrue(state["time_exited"])
        self.assertFalse(state.get("time_reduced", False))

    def test_failed_close_does_not_mark_exit_successful(self):
        state = binance_monitor._get_state("SOLUSDT")
        state["trade_id"] = 103

        with (
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(17)),
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=False),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "error", "error": "boom"}),
        ):
            binance_monitor._check_time_based_exit(self._position(volume=10.0))

        log_exit.assert_not_called()
        self.assertFalse(state.get("time_reduced", False))

    def test_prune_does_not_overwrite_already_closed_trade(self):
        state = binance_monitor._get_state("ETHUSDT")
        state.update({
            "trade_id": 120,
            "entry_price": 2127.25,
            "last_pnl": -0.0019,
            "last_price": 2126.73,
            "first_seen": binance_monitor.time.time(),
        })
        already_closed = {"exit_price": 2127.79, "exit_reason": "execution_failed"}

        with (
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=already_closed),
            patch.object(binance_monitor.trade_db, "close_trade") as close_trade,
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor.trade_db, "delete_binance_order_state") as delete_state,
            patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=True),
            patch.object(binance_monitor, "_send_telegram") as send_telegram,
        ):
            binance_monitor._prune_state(set())

        close_trade.assert_not_called()
        log_exit.assert_not_called()
        send_telegram.assert_not_called()
        delete_state.assert_called_once_with("ETHUSDT")

    def test_sell_momentum_reversal_fires_on_negative_r_change(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 104,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_r_history": [(binance_monitor.time.time() - 3600, 1.0)],
        })

        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_momentum_reversal(self._position(side="SELL", current=96.0, volume=4.0))

        close_mock.assert_called_once_with("SOLUSDT", 4.0, reason="momentum_exit")
        log_exit.assert_called_once()
        self.assertTrue(state["momentum_exited"])

    def test_buy_momentum_reversal_fires_on_negative_r_change(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 105,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_r_history": [(binance_monitor.time.time() - 3600, 1.0)],
        })

        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_momentum_reversal(self._position(side="BUY", current=104.0, volume=3.0))

        close_mock.assert_called_once_with("SOLUSDT", 3.0, reason="momentum_exit")
        log_exit.assert_called_once()
        self.assertTrue(state["momentum_exited"])

    def test_profit_protection_closes_after_1r_then_pullback(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 106,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_peak_r": 1.2,
        })

        with (
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=True),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_profit_protection(self._position(side="BUY", current=103.0, volume=2.0))

        close_mock.assert_called_once_with("SOLUSDT", 2.0, reason="profit_protect")
        log_exit.assert_called_once()
        self.assertTrue(state["profit_protected"])

    def test_profit_protection_recovers_r_distance_from_order_state(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 107,
            "_peak_r": 1.0,
        })
        order_state = {
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
        }

        with (
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=True),
            patch.object(binance_monitor.trade_db, "get_binance_order_state", return_value=order_state),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_profit_protection(self._position(side="BUY", current=103.0, volume=2.0))

        close_mock.assert_called_once_with("SOLUSDT", 2.0, reason="profit_protect")
        log_exit.assert_called_once()
        self.assertEqual(state["original_sl_distance"], 10.0)

    def test_early_giveback_closes_sub_1r_winner_after_configured_giveback(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 108,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_peak_r": 0.6,
        })

        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_early_giveback_guard(self._position(side="BUY", current=101.9, volume=3.0))

        close_mock.assert_called_once_with("SOLUSDT", 3.0, reason="early_giveback")
        log_exit.assert_called_once()
        self.assertTrue(state["early_giveback_exited"])

    def test_breakeven_move_does_not_promote_half_r_peak_or_trigger_giveback(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 208,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_peak_r": 0.52,
            "breakeven_moved": True,
        })
        position = self._position(side="BUY", current=103.9, volume=3.0)

        with (
            patch.object(binance_monitor.trade_db, "milestone_exists", return_value=False),
            patch.object(
                binance_monitor.trade_db,
                "get_trade_by_id",
                return_value={"risk_dollars": 30.0, "peak_pnl": 0.0},
            ),
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty") as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_profit_protection(position)
            binance_monitor._check_early_giveback_guard(position)

        self.assertAlmostEqual(state["_peak_r"], 0.52)
        close_mock.assert_not_called()
        log_exit.assert_not_called()

    def test_close_position_once_allows_only_one_broker_mutation_per_snapshot(self):
        state = binance_monitor._get_state("SOLUSDT")
        state["_exit_action_claimed"] = False

        with patch.object(
            binance_monitor,
            "close_position_qty",
            return_value={"status": "partial_closed"},
        ) as close_mock:
            first = binance_monitor._close_position_once("SOLUSDT", 2.0, reason="early_profit_first_scale")
            second = binance_monitor._close_position_once("SOLUSDT", 2.0, reason="milestone_0")

        self.assertEqual(first["status"], "partial_closed")
        self.assertEqual(second["status"], "skipped")
        close_mock.assert_called_once_with("SOLUSDT", 2.0, reason="early_profit_first_scale")

    def test_terminal_exit_fraction_uses_original_quantity(self):
        state = {"original_qty": 0.24}

        self.assertAlmostEqual(binance_monitor._remaining_original_fraction(state, 0.09), 0.375)

    def test_original_position_fraction_uses_float_epsilon_only(self):
        self.assertAlmostEqual(
            binance_monitor._original_position_fraction(100.0, 25.0),
            0.25,
            delta=1e-12,
        )
        self.assertEqual(
            binance_monitor._original_position_fraction(100.0, 100.0 + 5e-8),
            1.0,
        )
        self.assertIsNone(binance_monitor._original_position_fraction(100.0, 100.001))
        self.assertIsNone(binance_monitor._original_position_fraction(0.0, 1.0))

    def test_record_partial_exit_uses_confirmed_quantity_and_audit_fields(self):
        state = {"trade_id": 700, "original_qty": 100.0}
        result = {
            "quantity": 18.75,
            "requested_quantity": 18.75,
            "quantity_source": "create_response.executedQty",
            "accounting_confirmed": True,
            "order_id": 1234,
            "fill_ids": ["81", "82"],
        }
        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor.trade_db, "update_trade_accounting_status") as update_status,
        ):
            binance_monitor._record_partial_exit(
                trade_id=700,
                exit_type="milestone_0",
                price=105.0,
                pnl_contribution=12.0,
                state=state,
                close_result=result,
                requested_qty=18.75,
                configured_close_pct=0.25,
                base_notes="milestone",
            )

        self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.1875, delta=1e-12)
        notes = log_exit.call_args.kwargs["notes"]
        self.assertIn("closed_qty=18.75", notes)
        self.assertIn("original_qty=100", notes)
        self.assertIn("qty_source=create_response.executedQty", notes)
        self.assertIn("order_id=1234", notes)
        self.assertIn("fill_ids=81,82", notes)
        update_status.assert_not_called()

    def test_unconfirmed_partial_is_recorded_unknown_and_marks_accounting_unchecked(self):
        state = {"trade_id": 701, "original_qty": 0.0}
        result = {
            "quantity": 2.5,
            "quantity_source": "requested_rounded_unconfirmed",
            "accounting_confirmed": False,
            "order_id": 55,
            "fill_ids": [],
        }
        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor.trade_db, "update_trade_accounting_status") as update_status,
            patch.object(binance_monitor, "plain_log") as plain_log,
        ):
            binance_monitor._record_partial_exit(
                trade_id=701,
                exit_type="partial",
                price=100.0,
                pnl_contribution=None,
                state=state,
                close_result=result,
                requested_qty=2.5,
                configured_close_pct=0.25,
                base_notes="fallback",
            )

        self.assertIsNone(log_exit.call_args.kwargs["qty_pct"])
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[:2], (701, "unchecked"))
        self.assertIn(
            "PARTIAL_EXIT_ACCOUNTING_WARNING",
            [call.args[0] for call in plain_log.call_args_list],
        )

    def test_quantity_reconciliation_uses_one_exchange_step(self):
        with patch.object(binance_monitor, "get_quantity_step_size", return_value=0.01):
            self.assertTrue(binance_monitor._quantities_reconcile("BNBUSDT", 10.00, 10.01))
            self.assertFalse(binance_monitor._quantities_reconcile("BNBUSDT", 10.00, 10.0101))

    def test_known_exit_fraction_sum_ignores_unknown_rows(self):
        exits = [{"qty_pct": 0.25}, {"qty_pct": None}, {"qty_pct": 0.1875}]
        self.assertAlmostEqual(binance_monitor._known_exit_fraction_sum(exits), 0.4375, delta=1e-12)

    def test_prune_cleans_exchange_orders_before_deleting_closed_trade_state(self):
        state = binance_monitor._get_state("ETHUSDT")
        state.update({"trade_id": 220, "entry_price": 100.0, "first_seen": binance_monitor.time.time()})
        already_closed = {"exit_price": 101.0, "exit_reason": "early_giveback"}

        with (
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=already_closed),
            patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=True) as cleanup,
            patch.object(binance_monitor.trade_db, "delete_binance_order_state") as delete_state,
        ):
            binance_monitor._prune_state(set())

        cleanup.assert_called_once_with("ETHUSDT")
        delete_state.assert_called_once_with("ETHUSDT")

    def test_prune_retains_local_order_state_when_exchange_cleanup_fails(self):
        state = binance_monitor._get_state("ETHUSDT")
        state.update({"trade_id": 221, "entry_price": 100.0, "first_seen": binance_monitor.time.time()})
        already_closed = {"exit_price": 101.0, "exit_reason": "early_giveback"}

        with (
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=already_closed),
            patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=False),
            patch.object(binance_monitor.trade_db, "delete_binance_order_state") as delete_state,
        ):
            binance_monitor._prune_state(set())

        delete_state.assert_not_called()

    def test_prune_closes_trade_from_complete_exchange_fill_ledger(self):
        state = binance_monitor._get_state("BTCUSDT")
        state.update({
            "trade_id": 222,
            "entry_price": 60049.5,
            "last_price": 59913.4,
            "last_pnl": 11.0,
            "first_seen": binance_monitor.time.time(),
            "direction": "SELL",
            "original_qty": 0.24,
        })
        trade = {
            "id": 222,
            "symbol": "BTCUSDT",
            "direction": "SELL",
            "entry_price": 60049.5,
            "exit_price": None,
            "ts": "2026-06-28 14:00:09",
            "qty": 0.24,
            "risk_dollars": 83.02,
        }
        ledger = {
            "complete": True,
            "entry_qty": 0.24,
            "exit_qty": 0.24,
            "entry_price": 60044.2,
            "exit_price": 59919.025,
            "gross_pnl": 30.042,
            "fees": 11.5164696,
            "funding": 0.0,
            "net_pnl": 18.5255304,
        }

        with (
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade),
            patch.object(
                binance_monitor.trade_db,
                "get_exits_for_trade",
                return_value=[{"exit_type": "early_giveback", "price": 59913.4}],
            ),
            patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=True),
            patch.object(binance_monitor, "_fetch_exchange_trade_ledger", return_value=ledger),
            patch.object(binance_monitor, "_trade_open_age_hours", return_value=2.0),
            patch.object(binance_monitor.trade_db, "update_trade_fill") as update_fill,
            patch.object(binance_monitor.trade_db, "close_trade") as close_trade,
            patch.object(binance_monitor.trade_db, "delete_binance_order_state"),
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._prune_state(set())

        update_fill.assert_called_once_with(222, 60044.2, 0.24)
        self.assertEqual(close_trade.call_args.kwargs["exit_price"], 59919.025)
        self.assertEqual(close_trade.call_args.kwargs["pnl"], 18.5255304)
        self.assertEqual(close_trade.call_args.kwargs["gross_pnl"], 30.042)
        self.assertEqual(close_trade.call_args.kwargs["fees"], 11.5164696)
        self.assertEqual(close_trade.call_args.kwargs["accounting_status"], "clean")

    def test_early_giveback_ignores_noise_below_min_peak(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 109,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
            "_peak_r": 0.25,
        })

        with (
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "close_position_qty") as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_early_giveback_guard(self._position(side="BUY", current=100.5, volume=3.0))

        close_mock.assert_not_called()
        log_exit.assert_not_called()
        self.assertFalse(state.get("early_giveback_exited", False))

    def test_slot_pressure_review_alerts_old_low_r_winner_without_closing(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 207,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
        })
        old_trade = {
            "id": 207,
            "ts": (datetime.now(UTC) - timedelta(minutes=260)).strftime("%Y-%m-%d %H:%M:%S"),
            "risk_dollars": 20.0,
            "peak_pnl": 4.0,
        }

        with (
            patch.dict(binance_monitor.os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"}),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=old_trade),
            patch.object(binance_monitor, "close_position_qty") as close_mock,
            patch.object(binance_monitor, "_send_telegram") as send_telegram,
            patch.object(binance_monitor, "plain_log") as plain_log,
        ):
            binance_monitor._check_slot_pressure_duration_review(
                self._position(side="SELL", current=97.0, volume=2.0)
            )

        close_mock.assert_not_called()
        send_telegram.assert_called_once()
        plain_log.assert_called_once()
        self.assertEqual(plain_log.call_args.args[0], "LIVE_MICRO_SLOT_PRESSURE_REVIEW")
        self.assertTrue(state["_slot_pressure_review_sent"])

    def test_slot_pressure_review_skips_strong_runners(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({
            "trade_id": 208,
            "entry_price": 100.0,
            "original_sl_distance": 10.0,
        })
        old_trade = {
            "id": 208,
            "ts": (datetime.now(UTC) - timedelta(minutes=260)).strftime("%Y-%m-%d %H:%M:%S"),
            "risk_dollars": 20.0,
            "peak_pnl": 16.0,
        }

        with (
            patch.dict(binance_monitor.os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"}),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=old_trade),
            patch.object(binance_monitor, "close_position_qty") as close_mock,
            patch.object(binance_monitor, "_send_telegram") as send_telegram,
            patch.object(binance_monitor, "plain_log") as plain_log,
        ):
            binance_monitor._check_slot_pressure_duration_review(
                self._position(side="SELL", current=92.0, volume=2.0)
            )

        close_mock.assert_not_called()
        send_telegram.assert_not_called()
        plain_log.assert_not_called()
        self.assertFalse(state.get("_slot_pressure_review_sent", False))

    def test_latest_protective_exit_prefers_protective_reason(self):
        exits = [
            {"exit_type": "milestone_1", "price": 99.0},
            {"exit_type": "profit_protect", "price": 103.0},
            {"exit_type": "opposite", "price": 102.0},
        ]

        with patch.object(binance_monitor.trade_db, "get_exits_for_trade", return_value=exits):
            latest = binance_monitor._latest_protective_exit(108)

        self.assertEqual(latest["exit_type"], "profit_protect")

    def test_prune_preserves_logged_momentum_exit_reason(self):
        state = binance_monitor._get_state("LINKUSDT")
        state.update({
            "trade_id": 109,
            "entry_price": 9.89,
            "last_pnl": -20.78,
            "last_price": 9.8362,
            "first_seen": binance_monitor.time.time(),
            "direction": "BUY",
        })

        with (
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]),
            patch.object(
                binance_monitor.trade_db,
                "get_trade_by_id",
                return_value={"exit_price": None, "ts": trade_row(2)["ts"]},
            ),
            patch.object(
                binance_monitor.trade_db,
                "get_exits_for_trade",
                return_value=[{"exit_type": "momentum_exit", "price": 9.8362}],
            ),
            patch.object(binance_monitor.trade_db, "get_realized_exit_pnl", return_value=1.4),
            patch.object(binance_monitor.trade_db, "close_trade") as close_trade,
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor.trade_db, "delete_binance_order_state"),
            patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=True),
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._prune_state(set())

        self.assertEqual(close_trade.call_args.kwargs["exit_reason"], "momentum_exit")
        self.assertAlmostEqual(close_trade.call_args.kwargs["pnl"], -19.38)
        log_exit.assert_not_called()

    def test_half_r_milestone_closes_small_partial_and_keeps_runner(self):
        state = binance_monitor._get_state("LINKUSDT")
        state.update({"trade_id": 110, "original_qty": 100.0})
        position = {
            "symbol": "LINKUSDT",
            "tv_symbol": "LINKUSDT",
            "type": "BUY",
            "openPrice": 10.0,
            "currentPrice": 10.05,
            "profit": 5.0,
            "volume": 100.0,
        }

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 0.1}),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value={"id": 110, "direction": "BUY"}),
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[{"id": 110, "direction": "BUY"}]),
            patch.object(
                binance_monitor.trade_db,
                "get_milestone_config",
                return_value=[{"gate_name": "milestone_0", "threshold": 0.5, "close_pct": 0.25}],
            ),
            patch.object(binance_monitor, "_format_quantity", side_effect=lambda _symbol, qty: qty),
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "partial_closed"}) as close_mock,
            patch.object(binance_monitor.trade_db, "log_exit") as log_exit,
            patch.object(binance_monitor, "_refresh_remaining_protection_after_partial", return_value=True),
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_milestone_exits(position)

        close_mock.assert_called_once_with("LINKUSDT", 25.0, reason="milestone_0", position_side="LONG")
        log_exit.assert_called_once()
        self.assertIn("milestone_0", state["milestones_hit"])

    def test_milestone_skips_when_exchange_side_mismatches_open_db_trade(self):
        state = binance_monitor._get_state("HYPEUSDT")
        state.update({"trade_id": 126, "original_qty": 33.52})
        position = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "type": "SELL",
            "openPrice": 62.383,
            "currentPrice": 59.5,
            "profit": 90.0,
            "volume": 33.52,
        }
        open_trade = {"id": 126, "direction": "BUY"}

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 2.533}),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=open_trade),
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[open_trade]),
            patch.object(binance_monitor.trade_db, "update_trade_accounting_status") as mark_dirty,
            patch.object(binance_monitor, "close_position_qty") as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_milestone_exits(position)

        close_mock.assert_not_called()
        mark_dirty.assert_called_once()
        self.assertNotIn("milestone_0", state.get("milestones_hit", []))

    def test_milestone_error_sets_retry_backoff(self):
        state = binance_monitor._get_state("SOLUSDT")
        state.update({"trade_id": 124, "original_qty": 21.0})
        position = {
            "symbol": "SOLUSDT",
            "tv_symbol": "SOLUSDT",
            "type": "BUY",
            "openPrice": 83.27,
            "currentPrice": 83.92,
            "profit": 13.0,
            "volume": 21.0,
        }

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 0.07}),
            patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value={"id": 124, "direction": "BUY"}),
            patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[{"id": 124, "direction": "BUY"}]),
            patch.object(
                binance_monitor.trade_db,
                "get_milestone_config",
                return_value=[{"gate_name": "milestone_0", "threshold": 0.5, "close_pct": 0.25}],
            ),
            patch.object(binance_monitor, "_format_quantity", side_effect=lambda _symbol, qty: qty),
            patch.object(binance_monitor, "close_position_qty", return_value={"status": "error", "error": "APIError(code=-2022): ReduceOnly Order is rejected."}) as close_mock,
            patch.object(binance_monitor, "plain_log") as log,
        ):
            binance_monitor._check_milestone_exits(position)
            binance_monitor._check_milestone_exits(position)

        close_mock.assert_called_once_with("SOLUSDT", 5.25, reason="milestone_0", position_side="LONG")
        self.assertGreater(state["_milestone_retry_after"]["milestone_0"], binance_monitor.time.time())
        self.assertTrue(any(call.args[0] == "BINANCE_MILESTONE_ERROR" for call in log.call_args_list))

    def test_milestone_partial_protection_refresh_hedge_mode(self):
        # Simulate HYPEUSDT LONG with remaining_qty=29.81
        state = binance_monitor._get_state("HYPEUSDT")
        state.update({
            "trade_id": 172,
            "original_qty": 39.81,
            "current_sl": 63.174,
            "tp_price": 68.469,
        })
        position = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "type": "BUY",
            "openPrice": 64.689,
            "currentPrice": 65.64,
            "profit": 28.43,
            "volume": 29.81,
        }

        # Verify that it is called with positionSide='LONG' and reduceOnly is absent.
        client = type("Client", (), {})()
        placed_payloads = []
        def mock_create_order(**kwargs):
            placed_payloads.append(kwargs)
            return {"orderId": "mock_order_123", "success": True}
        client.futures_create_order = mock_create_order
        client.futures_get_open_orders = Mock(return_value=[])
        client.futures_get_open_algo_orders = Mock(return_value=[])
        client.futures_cancel_order = Mock()

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 1.51}),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "has_exchange_protection", return_value=(True, "mocked")),
            patch.object(binance_monitor, "plain_log") as log,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            res = binance_monitor._refresh_remaining_protection_after_partial(position, 29.81)

        self.assertTrue(res)
        self.assertEqual(len(placed_payloads), 2)
        for payload in placed_payloads:
            # Assert any Binance order payload includes positionSide='LONG'
            self.assertEqual(payload.get("positionSide"), "LONG")
            # Assert reduceOnly is absent
            self.assertNotIn("reduceOnly", payload)
            self.assertEqual(payload.get("symbol"), "HYPEUSDT")
            self.assertEqual(payload.get("side"), "SELL")

    def test_milestone_partial_protection_refresh_failure_retains_old(self):
        # Simulate HYPEUSDT LONG with remaining_qty=29.81
        state = binance_monitor._get_state("HYPEUSDT")
        state.update({
            "trade_id": 172,
            "original_qty": 39.81,
            "current_sl": 63.174,
            "tp_price": 68.469,
        })
        position = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "type": "BUY",
            "openPrice": 64.689,
            "currentPrice": 65.64,
            "profit": 28.43,
            "volume": 29.81,
        }

        # Simulate refresh failure
        client = type("Client", (), {})()
        client.futures_get_open_orders = Mock(return_value=[])
        client.futures_get_open_algo_orders = Mock(return_value=[])
        client.futures_cancel_order = Mock()

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 1.51}),
            patch.object(binance_monitor, "_get_client", return_value=client),
            patch.object(binance_monitor, "_place_sl_tp_order", return_value={"success": False, "error": "APIError(code=-4061): Order's position side does not match user's setting", "code": -4061}),
            patch.object(binance_monitor, "plain_log") as log,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            res = binance_monitor._refresh_remaining_protection_after_partial(position, 29.81)

        # Assert refresh fails (returns False)
        self.assertFalse(res)
        # Assert old protection is kept (cancel was never called)
        client.futures_cancel_order.assert_not_called()
        # Assert the failure is logged as warning/error, not swallowed
        self.assertTrue(any(call.args[0] == "BINANCE_PARTIAL_PROTECTION_REFRESH_FAILED_OLD_KEPT" for call in log.call_args_list))

    def test_orphan_position_suspends_simple_trailing(self):
        state = binance_monitor._get_state("BNBUSDT")
        state.update(
            {
                "_orphan_exchange_position": True,
                "entry_price": 650.0,
                "current_sl": 660.0,
                "trailing_active": True,
            }
        )
        position = {
            "symbol": "BNBUSDT",
            "tv_symbol": "BNBUSDT",
            "type": "SELL",
            "openPrice": 650.0,
            "currentPrice": 630.0,
            "profit": 25.0,
            "volume": 1.72,
            "stopLoss": 660.0,
        }

        with (
            patch.object(binance_monitor, "_get_position_state", return_value={"original_sl_distance": 10.0}),
            patch.object(binance_monitor, "_update_sl_order") as update_sl,
            patch.object(binance_monitor, "plain_log") as log,
        ):
            binance_monitor._check_simple_trailing_stop(position)

        update_sl.assert_not_called()
        self.assertTrue(any(call.args[0] == "ORPHAN_MANAGEMENT_SUSPENDED" for call in log.call_args_list))

    def test_partial_protection_refresh_backoff_skips_binance_call(self):
        state = binance_monitor._get_state("HYPEUSDT")
        state.update(
            {
                "trade_id": 172,
                "current_sl": 63.174,
                "tp_price": 68.469,
                "_partial_protection_refresh_backoff_until": binance_monitor.time.time() + 300,
                "_partial_protection_refresh_backoff_reason": "position_not_available_for_conditional_order",
            }
        )
        position = {
            "symbol": "HYPEUSDT",
            "tv_symbol": "HYPEUSDT",
            "type": "BUY",
            "openPrice": 64.689,
            "currentPrice": 65.64,
            "profit": 28.43,
            "volume": 29.81,
        }

        with (
            patch.object(binance_monitor, "_get_client") as get_client,
            patch.object(binance_monitor, "plain_log") as log,
        ):
            res = binance_monitor._refresh_remaining_protection_after_partial(position, 29.81)

        self.assertFalse(res)
        get_client.assert_not_called()
        self.assertTrue(any(call.args[0] == "BINANCE_PARTIAL_PROTECTION_REFRESH_BACKOFF" for call in log.call_args_list))


if __name__ == "__main__":
    unittest.main()
