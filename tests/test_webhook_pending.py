import time
import unittest

import webhook


class WebhookPendingTests(unittest.TestCase):
    def setUp(self):
        webhook._pending.clear()

    def tearDown(self):
        webhook._pending.clear()

    def test_position_aliases_treat_btcusd_and_btcusdt_as_same_broker_symbol(self):
        self.assertEqual(
            webhook._position_aliases("BTCUSD"),
            {"BTCUSD", "BTCUSDT"}
        )
        self.assertEqual(
            webhook._position_aliases("BTCUSDT"),
            {"BTCUSDT"}
        )

    def test_has_pending_alias_blocks_btcusdt_when_btcusd_is_pending(self):
        webhook._mark_pending("BTCUSDT")
        self.assertTrue(webhook._has_pending_alias("BTCUSD"))
        self.assertTrue(webhook._has_pending_alias("BTCUSDT"))

    def test_is_pending_uses_180_second_default_ttl(self):
        webhook._pending["BTCUSDm"] = time.time() - 150
        self.assertTrue(webhook._is_pending("BTCUSDm"))
        webhook._pending["BTCUSDm"] = time.time() - 181
        self.assertFalse(webhook._is_pending("BTCUSDm"))


if __name__ == "__main__":
    unittest.main()
