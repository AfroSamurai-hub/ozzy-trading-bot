import unittest

import webhook


class WebhookAdxOverrideTests(unittest.TestCase):
    def test_xau_volume_override_allows_aligned_high_volume_low_adx(self):
        allowed, details = webhook._adx_volume_override_allows(
            "XAUUSDT",
            "SELL",
            "momentum",
            17.5,
            25.0,
            {
                "close": 4320.0,
                "ema200": 4428.0,
                "supertrend_direction": "short",
                "volume_expansion": 8.6,
            },
            8.6,
            {
                "enabled": True,
                "allowed_signals": ["SELL"],
                "allowed_strategies": ["momentum"],
                "min_adx": 16.0,
                "min_volume_ratio": 1.8,
                "require_supertrend_alignment": True,
                "require_ema_side": True,
            },
        )

        self.assertTrue(allowed, details)
        self.assertEqual(details["reason"], "volume_override_allowed")

    def test_xau_volume_override_blocks_weak_volume(self):
        allowed, details = webhook._adx_volume_override_allows(
            "XAUUSDT",
            "SELL",
            "momentum",
            18.3,
            25.0,
            {
                "close": 4314.0,
                "ema200": 4425.0,
                "supertrend_direction": "short",
                "volume_expansion": 1.12,
            },
            1.12,
            {
                "enabled": True,
                "allowed_signals": ["SELL"],
                "allowed_strategies": ["momentum"],
                "min_adx": 16.0,
                "min_volume_ratio": 1.8,
                "require_supertrend_alignment": True,
                "require_ema_side": True,
            },
        )

        self.assertFalse(allowed)
        self.assertEqual(details["reason"], "volume_below_override_floor")

    def test_xau_volume_override_blocks_wrong_direction(self):
        allowed, details = webhook._adx_volume_override_allows(
            "XAUUSDT",
            "BUY",
            "momentum",
            17.5,
            25.0,
            {
                "close": 4430.0,
                "ema200": 4428.0,
                "supertrend_direction": "long",
                "volume_expansion": 8.6,
            },
            8.6,
            {
                "enabled": True,
                "allowed_signals": ["SELL"],
                "allowed_strategies": ["momentum"],
                "min_adx": 16.0,
                "min_volume_ratio": 1.8,
                "require_supertrend_alignment": True,
                "require_ema_side": True,
            },
        )

        self.assertFalse(allowed)
        self.assertEqual(details["reason"], "signal_not_allowed")


if __name__ == "__main__":
    unittest.main()
