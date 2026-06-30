import tempfile
import unittest
import os
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import binance_monitor
import logger
import trade_db
import loss_cooldowns

def get_mock_trade(minutes_old: float, qty: float = 10.0, sl: float = 9.0, tp: float = 11.0, direction: str = "BUY") -> dict:
    ts = (datetime.now(UTC) - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": 123,
        "symbol": "LINKUSDT",
        "direction": direction,
        "entry_price": 10.0,
        "exit_price": None,
        "qty": qty,
        "sl": sl,
        "tp": tp,
        "risk_dollars": 10.0,
        "setup_grade": "A",
        "strategy": "pullback",
        "timeframe": "1h",
        "ts": ts,
        "execution_state": "confirmed"
    }

class BinanceMonitorSluggishInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.log_patch = patch.object(logger, "LOG_FILE", Path(self.tempdir.name) / "trades.log")
        self.log_patch.start()
        binance_monitor._position_state.clear()
        
        # Setup temporary cooldown file
        self.cooldown_file = Path(self.tempdir.name) / "loss_cooldowns.json"
        with open(self.cooldown_file, "w") as f:
            json.dump([], f)
        self.cooldown_patch = patch.object(loss_cooldowns, "COOLDOWN_FILE", self.cooldown_file)
        self.cooldown_patch.start()

    def tearDown(self):
        self.log_patch.stop()
        self.cooldown_patch.stop()
        self.tempdir.cleanup()

    def _position(self, side="BUY", current=9.23, volume=10.0):
        # Entry = 10.0, SL = 9.0 (dist = 1.0).
        # currentPrice of 9.23 means current_r = (9.23 - 10.0) / 1.0 = -0.77R
        profit = (current - 10.0) * volume if side == "BUY" else (10.0 - current) * volume
        return {
            "symbol": "LINKUSDT",
            "tv_symbol": "LINKUSDT",
            "type": side,
            "currentPrice": current,
            "volume": volume,
            "profit": profit,
            "updateTime": int(datetime.now(UTC).timestamp() * 1000),
        }

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_live_micro_sluggish_trade_closes_successfully(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0, qty=10.0)

        # Mock SL verified
        mock_protection = {"has_sl": True, "has_tp": True}

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(trade_db, "log_exit") as log_exit_mock,
            patch.object(trade_db, "close_trade") as close_trade_mock,
            patch.object(binance_monitor, "_get_client") as client_mock,
            patch.object(binance_monitor, "inspect_exchange_protection", return_value=mock_protection),
            patch.object(binance_monitor, "_protective_close", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        # Asserts
        close_mock.assert_called_once_with("LINKUSDT", 10.0, "LIVE_MICRO_SLUGGISH_INVALIDATION")
        log_exit_mock.assert_called_once()
        close_trade_mock.assert_called_once_with(
            trade_id=123,
            exit_price=9.23,
            pnl=unittest.mock.ANY,
            gross_pnl=unittest.mock.ANY,
            exit_reason="live_micro_sluggish_invalidation",
            duration_min=80
        )

    @patch.dict(os.environ, {"HERMES_LIVE_MICRO_LOSS_COOLDOWN_ENABLED": "true"})
    def test_loss_cooldown_registered_correctly(self):
        # We test that loss_cooldowns.register_cooldown creates a cooldown JSON record
        loss_cooldowns.register_cooldown(
            trade_id=123,
            symbol="LINKUSDT",
            direction="BUY",
            setup_grade="A",
            strategy="pullback",
            timeframe="1h",
            pnl=-7.70,
            is_live_micro=True
        )
        cooldowns = loss_cooldowns.load_cooldowns()
        self.assertEqual(len(cooldowns), 1)
        self.assertEqual(cooldowns[0]["symbol"], "LINKUSDT")
        self.assertEqual(cooldowns[0]["instance"], "LIVE_MICRO")

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_live_micro_trade_age_60m_does_not_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=60.0)

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_live_micro_trade_peak_r_020_does_not_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.20
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0)

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_live_micro_trade_current_r_neg_020_does_not_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0)

        # current=9.80 means current_r = (9.80 - 10.0) / 1.0 = -0.20R
        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.80, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "STANDARD_TESTNET"})
    def test_testnet_trade_with_same_conditions_does_not_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0)

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=[]),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_missing_db_trade_does_not_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 999  # Does not match get_trade_by_id returning None

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=None),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_quantity_mismatch_safety_aborts_close(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0, qty=10.0)

        # DB has exits amounting to 2.5 units closed (expected remaining = 7.5)
        # But exchange quantity is 10.0 (mismatch!)
        mock_exits = [{"qty_pct": 0.25}]

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=mock_exits),
            patch.object(binance_monitor, "_protective_close") as close_mock,
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=10.0))

        close_mock.assert_not_called()

    @patch.dict(os.environ, {"HERMES_INSTANCE_NAME": "LIVE MICRO"})
    def test_closes_using_remaining_exchange_qty(self):
        state = binance_monitor._get_state("LINKUSDT")
        state["trade_id"] = 123
        state["_peak_r"] = 0.00
        state["entry_price"] = 10.0
        state["original_sl_distance"] = 1.0

        mock_trade = get_mock_trade(minutes_old=80.0, qty=10.0)

        # DB expected remaining is 7.5 (25% closed). Exchange matches 7.5.
        mock_exits = [{"qty_pct": 0.25}]
        mock_protection = {"has_sl": True, "has_tp": True}

        with (
            patch.object(trade_db, "get_trade_by_id", return_value=mock_trade),
            patch.object(trade_db, "get_exits_for_trade", return_value=mock_exits),
            patch.object(trade_db, "log_exit"),
            patch.object(trade_db, "close_trade"),
            patch.object(binance_monitor, "_get_client"),
            patch.object(binance_monitor, "inspect_exchange_protection", return_value=mock_protection),
            patch.object(binance_monitor, "_protective_close", return_value={"status": "closed"}) as close_mock,
            patch.object(binance_monitor, "_send_telegram"),
        ):
            binance_monitor._check_sluggish_invalidation(self._position(current=9.23, volume=7.5))

        # Should close 7.5 units, not 10.0 units!
        close_mock.assert_called_once_with("LINKUSDT", 7.5, "LIVE_MICRO_SLUGGISH_INVALIDATION")

if __name__ == "__main__":
    unittest.main()
