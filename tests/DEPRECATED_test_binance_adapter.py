import os
import unittest

from adapters.binance import BinanceAdapter
from request_utils import validate_signal_payload


class BinanceAdapterPayloadTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
        self.adapter = BinanceAdapter()

    def _build_and_validate(
        self,
        symbol: str = "ETHUSD",
        side: str = "BUY",
        setup_type: str = "BREAKOUT",
        timeframe: str = "15m",
    ):
        payload = self.adapter._build_payload(
            symbol=symbol,
            side=side,
            entry_price=3500.0,
            stop_price=3400.0,
            target_price=3700.0,
            setup_type=setup_type,
            timeframe=timeframe,
            confidence=0.85,
            regime_label="smc_pro",
        )
        valid, errors = validate_signal_payload(payload)
        self.assertTrue(valid, errors)
        return payload

    def test_build_payload_buy_breakout(self):
        payload = self._build_and_validate(side="BUY", setup_type="BREAKOUT")
        self.assertEqual(payload["bias"], "bullish")
        self.assertEqual(payload["structure"], "bullish_bos")
        self.assertEqual(payload["strategy"], "breakout")
        self.assertEqual(payload["strategy_label"], "BREAKOUT_RETEST")
        self.assertEqual(payload["source"], "signal_generator")
        self.assertEqual(payload["source_service"], "openclaw_breakout_executor")
        self.assertEqual(payload["version"], "2.2.2")

    def test_build_payload_sell_momentum_burst(self):
        payload = self._build_and_validate(side="SELL", setup_type="MOMENTUM_BURST")
        self.assertEqual(payload["bias"], "bearish")
        self.assertEqual(payload["structure"], "bearish_bos")
        self.assertEqual(payload["strategy"], "momentum")
        self.assertEqual(payload["strategy_label"], "15M_REVERSAL_CAPTURE")

    def test_build_payload_all_setup_types_validate(self):
        for setup_type in ("BREAKOUT", "CONTINUATION", "PULLBACK", "RETEST", "MOMENTUM_BURST"):
            for side in ("BUY", "SELL"):
                with self.subTest(setup_type=setup_type, side=side):
                    self._build_and_validate(side=side, setup_type=setup_type)

    def test_build_payload_timeframe_normalization(self):
        payload = self._build_and_validate(timeframe="1h")
        self.assertEqual(payload["timeframe"], "60")

    def test_build_payload_execution_mode_normalizes_to_uppercase(self):
        os.environ["EXECUTION_MODE"] = "paper"
        try:
            payload = self._build_and_validate()
            self.assertEqual(payload["execution_mode"], "PAPER")
        finally:
            del os.environ["EXECUTION_MODE"]

    def test_init_accepts_testnet_parameter(self):
        adapter = BinanceAdapter(testnet=True)
        self.assertTrue(adapter.testnet)


if __name__ == "__main__":
    unittest.main()
