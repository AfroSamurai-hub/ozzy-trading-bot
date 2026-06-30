#!/usr/bin/env python3
"""OpenClaw regime scout.

Binance klines are the primary data source for the live-micro symbol universe.
Hyperliquid mids are optional confluence only; they never decide routing and
unsupported Hyperliquid assets are not skipped.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from binance_indicators import calculate_adx, get_live_indicators, normalize_binance_symbol
from config import get_signal_strategy_for_symbol, get_symbol_strategy_profile
from logger import plain_log


class MacroScoutAgent:
    def __init__(self):
        self.config_path = ROOT / "config" / "openclaw_manifest.json"
        self.state_path = ROOT / "shared" / "market_regimes.json"
        self.heartbeat_path = ROOT / "shared" / "scout.heartbeat"
        self.load_config()

    def load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        regime_cfg = self.config.get("regime_detection") or {}
        self.trend_limit = float(regime_cfg.get("trend_threshold_adx", 35.0))
        self.range_limit = float(regime_cfg.get("range_threshold_adx", 22.0))
        self.assets = self._load_active_symbols()

    def _load_active_symbols(self) -> list[str]:
        env_symbols = (
            os.getenv("HERMES_OPENCLAW_SYMBOLS")
            or os.getenv("HERMES_SIGNAL_SYMBOLS")
            or os.getenv("HERMES_BINANCE_SYMBOLS")
            or ""
        )
        raw_assets = [item.strip() for item in env_symbols.split(",") if item.strip()]
        if not raw_assets:
            raw_assets = self.config.get("assets") or []

        symbols: list[str] = []
        seen: set[str] = set()
        for asset in raw_assets:
            symbol = normalize_binance_symbol(asset)
            if symbol and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
        return symbols

    def _load_hyperliquid_mids(self) -> dict:
        if os.getenv("HERMES_OPENCLAW_HYPERLIQUID_CONFLUENCE", "true").lower() not in {"1", "true", "yes", "on"}:
            return {}
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants

            return Info(constants.TESTNET_API_URL, skip_ws=True).all_mids()
        except Exception as exc:
            plain_log("OPENCLAW_HYPERLIQUID_CONFLUENCE_UNAVAILABLE", {"error": str(exc)})
            return {}

    @staticmethod
    def _hyperliquid_asset(symbol: str) -> str:
        return symbol[:-4] if symbol.endswith("USDT") else symbol

    @staticmethod
    def _directional_bias(indicators_4h: dict, indicators_1d: dict | None = None) -> str:
        """Return directional bias only when 4H and 1D agree.

        Momentum V2 must not arm breakouts from a single-timeframe trend. A
        missing/unaligned 1D confirmation deliberately returns MIXED so the
        downstream blueprint executor can stand down instead of chasing.
        """
        indicators_1d = indicators_1d or {}

        def _tf_bias(indicators: dict) -> str:
            close = indicators.get("close")
            ema200 = indicators.get("ema200")
            supertrend_direction = str(indicators.get("supertrend_direction") or "").lower()
            if close is None or ema200 is None:
                return "MIXED"
            if close >= ema200 and supertrend_direction == "long":
                return "UP"
            if close < ema200 and supertrend_direction == "short":
                return "DOWN"
            return "MIXED"

        bias_4h = _tf_bias(indicators_4h)
        bias_1d = _tf_bias(indicators_1d)
        if bias_4h in {"UP", "DOWN"} and bias_4h == bias_1d:
            return bias_4h
        return "MIXED"

    def _classify_strategy(self, symbol: str, adx: float | None, indicators: dict) -> tuple[str, str]:
        profile = get_symbol_strategy_profile(symbol)
        configured_lane = str(profile.get("execution_lane") or "Macro")
        if adx is None or not indicators:
            return "DATA_UNAVAILABLE", configured_lane

        if configured_lane.lower() == "sniper":
            if adx <= self.trend_limit:
                return "15M_MEAN_REVERSION", configured_lane
            return "STANDBY", configured_lane

        if adx >= self.trend_limit:
            return "4H_MACRO_BREAKOUT", configured_lane

        if self.range_limit <= adx < self.trend_limit:
            return "4H_MODERATE_TREND", configured_lane

        return "STANDBY", configured_lane

    def analyze_regimes(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        hyperliquid_mids = self._load_hyperliquid_mids()
        regime_ledger = {}

        print(f"\n🔍 OZZYBOT OPENCLAW: Binance-native scan over {len(self.assets)} symbols...")
        print("────────────────────────────────────────────────────────")

        for symbol in self.assets:
            indicators = get_live_indicators(symbol, interval="4h")
            indicators_1d = get_live_indicators(symbol, interval="1d")
            adx = calculate_adx(symbol, interval="4h", limit=80)
            assigned_strategy, configured_lane = self._classify_strategy(symbol, adx, indicators)
            bias = self._directional_bias(indicators, indicators_1d)
            hl_asset = self._hyperliquid_asset(symbol)
            hl_mid_raw = hyperliquid_mids.get(hl_asset)
            hl_mid = float(hl_mid_raw) if hl_mid_raw is not None else None

            close = indicators.get("close")
            status = assigned_strategy
            if assigned_strategy == "4H_MACRO_BREAKOUT":
                status = f"TREND_{bias}"
            elif assigned_strategy == "15M_MEAN_REVERSION":
                status = "RANGE_CHOP"
            elif assigned_strategy == "DATA_UNAVAILABLE":
                status = "DATA_UNAVAILABLE"

            regime_ledger[symbol] = {
                "symbol": symbol,
                "hyperliquid_asset": hl_asset,
                "configured_lane": configured_lane,
                "lane_timeframe": str(get_symbol_strategy_profile(symbol).get("lane_timeframe") or ""),
                "signal_strategy": get_signal_strategy_for_symbol(symbol),
                "assigned_strategy": assigned_strategy,
                "directional_bias": bias,
                "data_source": "binance_klines",
                "timeframe": "4h",
                "updated_at": int(time.time()),
                "metrics": {
                    "adx": adx,
                    "trend_threshold_adx": self.trend_limit,
                    "range_threshold_adx": self.range_limit,
                    "close": close,
                    "ema200": indicators.get("ema200"),
                    "ema200_1d": indicators_1d.get("ema200"),
                    "atr": indicators.get("atr"),
                    "supertrend_direction": indicators.get("supertrend_direction"),
                    "supertrend_direction_1d": indicators_1d.get("supertrend_direction"),
                    "close_1d": indicators_1d.get("close"),
                    "kline_source": indicators.get("kline_source"),
                    "hyperliquid_mid": hl_mid,
                    "hyperliquid_confluence_available": hl_mid is not None,
                },
            }

            adx_text = "n/a" if adx is None else f"{adx:.2f}"
            close_text = "n/a" if close is None else f"{float(close):.4f}"
            print(f"• {symbol:<12} | Lane: {configured_lane:<6} | Close: {close_text:<12} | ADX: {adx_text:<6} | {status}")

        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(regime_ledger, f, indent=4, sort_keys=True)

        with open(self.heartbeat_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))

        plain_log("OPENCLAW_MACRO_SCOUT_COMPLETE", {"symbols_checked": len(regime_ledger), "source": "binance_klines"})
        print("────────────────────────────────────────────────────────")
        print("💾 OpenClaw regime ledger updated from Binance-native data.")


if __name__ == "__main__":
    scout = MacroScoutAgent()
    scout.analyze_regimes()
