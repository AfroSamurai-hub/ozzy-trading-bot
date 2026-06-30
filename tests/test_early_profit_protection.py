import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import binance_monitor as bm


class TestEarlyProfitProtection(unittest.TestCase):
    def setUp(self):
        bm.PAPER_MODE = False
        bm._position_state.clear()
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(bm.trade_db, "DB_PATH", Path(self.tempdir.name) / "trades.db")
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.tempdir.cleanup()

    def _make_position(self, current_price=105.0, profit=50.0, volume=10.0):
        return {
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "openPrice": 100.0,
            "currentPrice": current_price,
            "type": "BUY",
            "profit": profit,
            "volume": volume,
        }

    @patch("binance_monitor.close_position_qty")
    @patch("binance_monitor.move_sl_to_breakeven")
    @patch("binance_monitor._refresh_remaining_protection_after_partial")
    @patch("binance_monitor._send_telegram")
    @patch("binance_monitor.trade_db.log_exit")
    def test_first_scale_closes_25_percent(
        self, mock_log_exit, mock_tg, mock_refresh, mock_be, mock_close
    ):
        position = self._make_position(profit=30.0)  # 0.75R -> only first scale
        state = bm._get_state("ETHUSDT")
        cc_state = bm._get_position_state("ETHUSDT")
        state["trade_id"] = 1
        state["lane"] = "1H_TREND"
        state["original_qty"] = 10.0
        cc_state["original_sl_distance"] = 4.0  # 1R = $40; profit $30 = 0.75R

        mock_close.return_value = {"status": "ok"}
        bm._check_early_profit_protection(position)

        mock_close.assert_called_once()
        args, kwargs = mock_close.call_args
        self.assertEqual(args[0], "ETHUSDT")
        self.assertAlmostEqual(args[1], 2.5, places=1)
        mock_be.assert_called_once_with("ETHUSDT", 100.0)
        self.assertTrue(state.get("early_profit_first_scale"))

    @patch("binance_monitor.close_position_qty")
    @patch("binance_monitor.move_sl_to_breakeven")
    @patch("binance_monitor._refresh_remaining_protection_after_partial")
    @patch("binance_monitor._send_telegram")
    @patch("binance_monitor.trade_db.log_exit")
    def test_second_scale_waits_for_a_fresh_position_snapshot(
        self, mock_log_exit, mock_tg, mock_refresh, mock_be, mock_close
    ):
        position = self._make_position(current_price=110.0, profit=100.0)
        state = bm._get_state("ETHUSDT")
        cc_state = bm._get_position_state("ETHUSDT")
        state["trade_id"] = 1
        state["lane"] = "1H_TREND"
        cc_state["original_sl_distance"] = 4.0  # 1R = $40; profit $100 = 2.5R

        mock_close.return_value = {"status": "ok"}
        bm._check_early_profit_protection(position)

        # One position snapshot may produce only one broker mutation.
        self.assertEqual(mock_close.call_count, 1)
        self.assertTrue(state.get("early_profit_first_scale"))
        self.assertFalse(state.get("early_profit_second_scale", False))

        # The next fresh exchange snapshot may apply the second scale.
        state["_exit_action_claimed"] = False
        bm._check_early_profit_protection(position)
        self.assertEqual(mock_close.call_count, 2)
        self.assertTrue(state.get("early_profit_second_scale"))

    @patch("binance_monitor.close_position_qty")
    @patch("binance_monitor.move_sl_to_breakeven")
    @patch("binance_monitor._refresh_remaining_protection_after_partial")
    @patch("binance_monitor._send_telegram")
    @patch("binance_monitor.trade_db.log_exit")
    def test_disabled_policy_skips_scales(
        self, mock_log_exit, mock_tg, mock_refresh, mock_be, mock_close
    ):
        position = self._make_position()
        state = bm._get_state("ETHUSDT")
        cc_state = bm._get_position_state("ETHUSDT")
        state["trade_id"] = 1
        state["lane"] = "DISABLED_LANE"
        cc_state["original_sl_distance"] = 4.0

        with patch.object(bm, "EARLY_PROFIT_PROTECTION", {"enabled": False}):
            bm._check_early_profit_protection(position)

        mock_close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
