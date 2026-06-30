import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path
import os
import json
from datetime import datetime, timezone, timedelta
from contextlib import ExitStack

import webhook
import config
import trade_db
import loss_cooldowns
from dynamic_config import get_param


class LossCooldownsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trades.db"
        self.db_patch = patch.object(trade_db, "DB_PATH", self.db_path)
        self.db_patch.start()
        
        # Override cooldown JSON path to a temporary file
        self.cooldown_file = Path(self.tempdir.name) / "loss_cooldowns.json"
        self.file_patch = patch.object(loss_cooldowns, "COOLDOWN_FILE", self.cooldown_file)
        self.file_patch.start()
        self._orig_exists = os.path.exists
        self.halt_patch = patch(
            "webhook.os.path.exists",
            side_effect=lambda path: False if str(path) == webhook.HALT_FILE else self._orig_exists(path),
        )
        self.halt_patch.start()
        self.monitor_patch = patch.object(
            webhook,
            "_monitor_entry_gate_status",
            return_value={"allowed": True, "reason": "monitor_active", "service": "test"},
        )
        self.monitor_patch.start()
        self.client_patch = patch.object(webhook, "_get_binance_client", return_value=MagicMock())
        self.client_patch.start()
        self.age_patch = patch.object(webhook, "_check_signal_age", return_value={"allowed": True})
        self.age_patch.start()
        self.drift_patch = patch.object(webhook, "_check_entry_drift", return_value={"allowed": True})
        self.drift_patch.start()
        self.lane_patch = patch.object(webhook, "get_lane_for_signal", return_value="1H_TREND")
        self.lane_patch.start()
        self.positions_patch = patch.object(webhook, "_get_cached_positions", return_value=([], True))
        self.positions_patch.start()
        self.equity_patch = patch.object(webhook, "_get_live_equity", return_value=10000.0)
        self.equity_patch.start()
        self.drawdown_patch = patch.object(webhook, "_check_live_drawdown", return_value=False)
        self.drawdown_patch.start()
        self.reconcile_patch = patch(
            "webhook.live_reconcile.reconcile_live_state",
            return_value={"healthy": True, "critical_mismatches": [], "warnings": []},
        )
        self.reconcile_patch.start()
        self.indicators_patch = patch(
            "webhook.get_binance_indicators",
            return_value={
                "rsi": 45.0,
                "ema200": 2900.0,
                "atr": 80.0,
                "volume": 15000.0,
                "volume_avg20": 10000.0,
                "supertrend_direction": "short",
                "supertrend_value": 3010.0,
                "close": 3000.0,
            },
        )
        self.indicators_patch.start()
        webhook._pending.clear()

    def tearDown(self):
        webhook._pending.clear()
        self.indicators_patch.stop()
        self.reconcile_patch.stop()
        self.drawdown_patch.stop()
        self.equity_patch.stop()
        self.positions_patch.stop()
        self.lane_patch.stop()
        self.drift_patch.stop()
        self.age_patch.stop()
        self.client_patch.stop()
        self.monitor_patch.stop()
        self.halt_patch.stop()
        self.file_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_cooldown_created_on_loss_only(self):
        """Test that cooldown is created only when realized pnl is negative, not on profit or scratch."""
        # 1. Realized loss creates cooldown
        loss_cooldowns.register_cooldown(
            trade_id=101, symbol="ETHUSDT", direction="SELL",
            setup_grade="A", strategy="pullback", timeframe="1h",
            pnl=-50.0, is_live_micro=False
        )
        active = loss_cooldowns.load_cooldowns()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["previous_trade_id"], 101)
        self.assertEqual(active[0]["realized_pnl"], -50.0)

        # 2. Profitable trade does not create cooldown
        loss_cooldowns.register_cooldown(
            trade_id=102, symbol="BNBUSDT", direction="BUY",
            setup_grade="B", strategy="momentum", timeframe="1h",
            pnl=25.0, is_live_micro=False
        )
        active = loss_cooldowns.load_cooldowns()
        # Still only 1 active cooldown from before
        self.assertEqual(len(active), 1)
        self.assertFalse(any(item["previous_trade_id"] == 102 for item in active))

        # 3. Scratch (PnL=0) trade does not create cooldown
        loss_cooldowns.register_cooldown(
            trade_id=103, symbol="LINKUSDT", direction="BUY",
            setup_grade="A", strategy="pullback", timeframe="1h",
            pnl=0.0, is_live_micro=False
        )
        active = loss_cooldowns.load_cooldowns()
        self.assertEqual(len(active), 1)
        self.assertFalse(any(item["previous_trade_id"] == 103 for item in active))

    def test_testnet_cooldown_matching_logic(self):
        """Test that TESTNET same-symbol loss cooldown requires same symbol + direction + setup/profile to block."""
        # Register TESTNET loss cooldown (symbol=ETHUSDT, direction=SELL, setup=A, strategy=pullback)
        loss_cooldowns.register_cooldown(
            trade_id=201, symbol="ETHUSDT", direction="SELL",
            setup_grade="A", strategy="pullback", timeframe="1h",
            pnl=-100.0, is_live_micro=False
        )

        # 1. Same symbol + same direction + same setup is BLOCKED
        self.assertIsNotNone(
            loss_cooldowns.check_cooldown(
                symbol="ETHUSDT", direction="SELL", setup_grade="A",
                strategy="pullback", timeframe="1h", is_live_micro=False
            )
        )

        # 2. Opposite direction is ALLOWED
        self.assertNil = loss_cooldowns.check_cooldown(
            symbol="ETHUSDT", direction="BUY", setup_grade="A",
            strategy="pullback", timeframe="1h", is_live_micro=False
        )
        self.assertIsNone(self.assertNil)

        # 3. Same symbol + same direction but different grade (setup) is ALLOWED
        self.assertIsNone(
            loss_cooldowns.check_cooldown(
                symbol="ETHUSDT", direction="SELL", setup_grade="B",
                strategy="pullback", timeframe="1h", is_live_micro=False
            )
        )

        # 4. Same symbol + same direction but different strategy (profile) is ALLOWED
        self.assertIsNone(
            loss_cooldowns.check_cooldown(
                symbol="ETHUSDT", direction="SELL", setup_grade="A",
                strategy="momentum", timeframe="1h", is_live_micro=False
            )
        )

    def test_live_micro_cooldown_stricter_matching_logic(self):
        """Test that LIVE_MICRO same-symbol loss cooldown blocks the same symbol after ANY realized loss (any setup/direction)."""
        with patch.dict(os.environ, {"HERMES_LIVE_MICRO_LOSS_COOLDOWN_ENABLED": "true"}):
            # Register LIVE_MICRO loss cooldown (symbol=ETHUSDT, direction=SELL, setup=A, strategy=pullback)
            loss_cooldowns.register_cooldown(
                trade_id=301, symbol="ETHUSDT", direction="SELL",
                setup_grade="A", strategy="pullback", timeframe="1h",
                pnl=-10.0, is_live_micro=True
            )

            # 1. Same symbol + same direction + same setup is BLOCKED
            self.assertIsNotNone(
                loss_cooldowns.check_cooldown(
                    symbol="ETHUSDT", direction="SELL", setup_grade="A",
                    strategy="pullback", timeframe="1h", is_live_micro=True
                )
            )

            # 2. Opposite direction BUY is BLOCKED
            self.assertIsNotNone(
                loss_cooldowns.check_cooldown(
                    symbol="ETHUSDT", direction="BUY", setup_grade="A",
                    strategy="pullback", timeframe="1h", is_live_micro=True
                )
            )

            # 3. Different grade and different strategy is BLOCKED
            self.assertIsNotNone(
                loss_cooldowns.check_cooldown(
                    symbol="ETHUSDT", direction="BUY", setup_grade="B",
                    strategy="momentum", timeframe="1h", is_live_micro=True
                )
            )

            # 4. Different symbol is ALLOWED
            self.assertIsNone(
                loss_cooldowns.check_cooldown(
                    symbol="BNBUSDT", direction="BUY", setup_grade="A",
                    strategy="pullback", timeframe="1h", is_live_micro=True
                )
            )

    def test_live_micro_cooldown_is_disabled_by_default(self):
        """LIVE_MICRO loss cooldowns are off unless explicitly enabled."""
        loss_cooldowns.register_cooldown(
            trade_id=302, symbol="ETHUSDT", direction="SELL",
            setup_grade="A", strategy="pullback", timeframe="1h",
            pnl=-10.0, is_live_micro=True
        )

        self.assertEqual(loss_cooldowns.load_cooldowns(), [])
        self.assertIsNone(
            loss_cooldowns.check_cooldown(
                symbol="ETHUSDT", direction="SELL", setup_grade="A",
                strategy="pullback", timeframe="1h", is_live_micro=True
            )
        )

    def test_cooldown_expiry_behavior(self):
        """Test that expired cooldowns are ignored and filtered out."""
        # Create an expired cooldown (10 hours ago)
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(hours=10)
        expires_at = expired_time + timedelta(hours=4)  # Expired 6 hours ago
        
        expired_record = {
            "previous_trade_id": 401,
            "previous_symbol": "ETHUSDT",
            "instance": "STANDARD_TESTNET",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "setup_grade": "A",
            "strategy": "pullback",
            "timeframe": "1h",
            "realized_pnl": -50.0,
            "closed_at": expired_time.isoformat(),
            "expires_at": expires_at.isoformat(),
            "reason": "Expired"
        }
        
        loss_cooldowns.save_cooldowns([expired_record])
        
        # Load and verify it is not returned (filtered out)
        active = loss_cooldowns.load_cooldowns()
        self.assertEqual(len(active), 0)
        
        # Verify check_cooldown allows the trade
        self.assertIsNone(
            loss_cooldowns.check_cooldown(
                symbol="ETHUSDT", direction="SELL", setup_grade="A",
                strategy="pullback", timeframe="1h", is_live_micro=False
            )
        )

    def test_cooldown_durable_persistence(self):
        """Test that cooldowns survive in JSON file across multiple load/save cycles."""
        loss_cooldowns.register_cooldown(
            trade_id=501, symbol="ETHUSDT", direction="SELL",
            setup_grade="A", strategy="pullback", timeframe="1h",
            pnl=-50.0, is_live_micro=False
        )
        
        # Read directly from file to verify persistence
        with open(self.cooldown_file, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["previous_trade_id"], 501)

    def test_webhook_cooldown_gate_integration(self):
        """Test that the webhook entry gate successfully blocks signals when loss cooldown is active."""
        # Setup active cooldown in JSON
        loss_cooldowns.register_cooldown(
            trade_id=601, symbol="ETHUSDT", direction="SELL",
            setup_grade="A", strategy="momentum", timeframe="1h",
            pnl=-50.0, is_live_micro=False
        )

        with ExitStack() as stack:
            stack.enter_context(patch("webhook.WEBHOOK_SECRET", "test_secret"))
            stack.enter_context(patch.object(webhook, "MICRO_BOOTSTRAP_MODE", False)) # Testnet
            stack.enter_context(patch.object(webhook, "BINANCE_FUTURES_MODE", True))
            stack.enter_context(patch("webhook.validate_signal_payload", return_value=(True, [])))
            stack.enter_context(patch("webhook.telegram_client.notify_rejected"))
            # Make sure get_param returns active symbols including ETHUSDT
            stack.enter_context(patch("dynamic_config.get_param", side_effect=lambda key, default: 
                ["BTCUSDT", "ETHUSDT", "BNBUSDT"] if key == "active_symbols" else default
            ))

            with webhook.app.test_client() as client:
                payload = {
                    "secret": "test_secret",
                    "signal": "SELL",
                    "symbol": "ETHUSDT",
                    "entry": 3000.0,
                    "grade": "A",
                    "strategy": "pullback",
                    "timeframe": "1h",
                    "timestamp": 1779613507000,
                }
                resp = client.post("/webhook", json=payload)
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data["status"], "rejected")
                self.assertEqual(data["reason"], "loss_cooldown_active")
                self.assertIn("Signal rejected: same-symbol loss cooldown active", data["message"])


if __name__ == "__main__":
    unittest.main()
