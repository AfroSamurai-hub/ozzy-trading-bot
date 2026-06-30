#!/usr/bin/env python3
"""OpenClaw trend blueprint executor.

This component does not place exchange orders. It converts fresh 4H regime
state into 1H trigger blueprints consumed by reporting/control layers.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from binance_indicators import get_binance_klines
from config import get_symbol_strategy_profile
from logger import plain_log


MAX_SCOUT_AGE_SECONDS = int(os.getenv("HERMES_OPENCLAW_MAX_SCOUT_AGE_SECONDS", str(5 * 60 * 60)))


def _as_float(value, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class TrendExecutorAgent:
    def __init__(self):
        self.state_path = ROOT / "shared" / "market_regimes.json"
        self.order_path = ROOT / "shared" / "active_orders.json"
        self.heartbeat_path = ROOT / "shared" / "executor.heartbeat"

    def load_market_regimes(self):
        if not self.state_path.exists():
            plain_log("OPENCLAW_TREND_EXECUTOR_SKIP", {"reason": "missing_market_regimes"})
            return False
        if time.time() - self.state_path.stat().st_mtime > MAX_SCOUT_AGE_SECONDS:
            plain_log("OPENCLAW_TREND_EXECUTOR_SKIP", {"reason": "stale_market_regimes"})
            return False
        with open(self.state_path, "r", encoding="utf-8") as f:
            self.regimes = json.load(f)
        return True

    @staticmethod
    def calculate_dynamic_1h_ceiling(symbol: str, side: str) -> dict | None:
        df = get_binance_klines(symbol, interval="1h", limit=80)
        if df.empty or len(df) < 25:
            return None

        closed = df.iloc[:-1].tail(20)
        current = float(df.iloc[-2]["close"])
        high_20h = float(closed["high"].max())
        low_20h = float(closed["low"].min())
        if side == "SELL":
            return {"current": current, "trigger": round(low_20h, 8), "high_20h": round(high_20h, 8), "low_20h": round(low_20h, 8)}
        return {"current": current, "trigger": round(high_20h, 8), "high_20h": round(high_20h, 8), "low_20h": round(low_20h, 8)}

    @staticmethod
    def _side_from_bias(bias: str | None) -> str | None:
        normalized = str(bias).upper()
        if normalized == "UP":
            return "BUY"
        if normalized == "DOWN":
            return "SELL"
        return None

    @staticmethod
    def _side_from_4h_metrics(data: dict) -> str | None:
        """Derive a testnet research direction from 4H structure when 1D is mixed."""
        metrics = data.get("metrics") or {}
        close = _as_float(metrics.get("close"))
        ema200 = _as_float(metrics.get("ema200"))
        supertrend = str(metrics.get("supertrend_direction") or "").lower()
        if close is None or ema200 is None or ema200 <= 0:
            return None
        if supertrend == "long" and close >= ema200:
            return "BUY"
        if supertrend == "short" and close <= ema200:
            return "SELL"
        return None

    @staticmethod
    def _setup_profile_for_symbol(symbol: str) -> dict:
        profile = get_symbol_strategy_profile(symbol)
        return {
            "openclaw_personality": profile.get("openclaw_personality", "bench_watch"),
            "assigned_setup_type": profile.get("openclaw_primary_setup", "SHADOW_ONLY"),
            "secondary_setup_type": profile.get("openclaw_secondary_setup", "NONE") or "NONE",
            "personality_reason": profile.get("openclaw_personality_reason", "no_profile_reason"),
        }

    @classmethod
    def _blueprint_plan(cls, strategy: str, configured_lane: str, data: dict) -> dict | None:
        """Return the OpenClaw V2 daily-profile plan for a regime row.

        v2026-06-15 — TESTNET daily profile: keep legacy 1H archived, but stop
        starving recipe discovery by arming B-lane mixed macro breakouts and
        C-lane moderate-trend retests when 4H structure gives a clear side.
        """
        if str(configured_lane or "").lower() != "macro":
            return None

        if strategy == "4H_MACRO_BREAKOUT":
            side = cls._side_from_bias(data.get("directional_bias"))
            if side:
                return {
                    "side": side,
                    "entry_setup_label": "OPENCLAW_BREAKOUT_A_ALIGNED",
                    "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT",
                    "lane_tier": "A",
                    "basis": "4h_1d_aligned_bias",
                }
            side = cls._side_from_4h_metrics(data)
            if side:
                return {
                    "side": side,
                    "entry_setup_label": "OPENCLAW_BREAKOUT_B_MIXED",
                    "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT_MIXED",
                    "lane_tier": "B",
                    "basis": "mixed_1d_but_clear_4h_structure",
                }
            return None

        if strategy == "4H_MODERATE_TREND":
            side = cls._side_from_4h_metrics(data)
            if side:
                return {
                    "side": side,
                    "entry_setup_label": "OPENCLAW_RETEST_C_MODERATE",
                    "regime_label": "OPENCLAW_4H_MODERATE_TREND",
                    "lane_tier": "C",
                    "basis": "moderate_4h_retest",
                }
        return None

    def process_triggers(self):
        self.order_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.load_market_regimes():
            return

        print("\n🚀 OZZYBOT OPENCLAW: Processing Binance-native 1H blueprints...")
        print("────────────────────────────────────────────────────────")
        active_triggers = {}

        for symbol, data in self.regimes.items():
            strategy = data.get("assigned_strategy")
            profile = get_symbol_strategy_profile(symbol)
            configured_lane = str(data.get("configured_lane") or profile.get("execution_lane") or "")
            plan = self._blueprint_plan(strategy, configured_lane, data)
            if not plan:
                plain_log(
                    "OPENCLAW_TREND_BLUEPRINT_SKIP",
                    {
                        "symbol": symbol,
                        "reason": "not_in_openclaw_daily_profile_or_no_clear_4h_side",
                        "strategy": strategy,
                        "configured_lane": configured_lane,
                        "bias": data.get("directional_bias"),
                    },
                )
                continue

            side = plan["side"]
            setup_profile = self._setup_profile_for_symbol(symbol)
            market_structure = self.calculate_dynamic_1h_ceiling(symbol, side)
            if market_structure is None:
                plain_log("OPENCLAW_TREND_BLUEPRINT_SKIP", {"symbol": symbol, "reason": "missing_1h_klines"})
                continue

            entry_trigger = market_structure["trigger"]
            if side == "SELL":
                hard_stop = round(entry_trigger * 1.015, 8)
                ratchet_activation = round(entry_trigger * 0.995, 8)
            else:
                hard_stop = round(entry_trigger * 0.985, 8)
                ratchet_activation = round(entry_trigger * 1.005, 8)

            print(f"⚔️ 1H ENGINE ARMED -> {symbol}")
            print(f"  • OpenClaw Lane      : {plan['lane_tier']} [{plan['basis']}]")
            print(f"  • Directional Filter : 4H Structure [{side}]")
            print(f"  • Breakout Trigger   : {side} stop blueprint at ${entry_trigger}")
            print(f"  • Stop Loss Guard    : Hard protection at ${hard_stop}")
            print(f"  • Profit Catch Floor : Cash ratchet activates at ${ratchet_activation}")
            print("  ──────────────────────────────────────────────")

            active_triggers[symbol] = {
                "symbol": symbol,
                "side": side,
                "timeframe_cascade": "4H_FILTER_TO_1H_TRIGGER",
                "entry_price": entry_trigger,
                "stop_loss": hard_stop,
                "ratchet_activation": ratchet_activation,
                "status": "ARMED",
                "source": "openclaw_binance_native",
                "updated_at": int(time.time()),
                "market_structure": market_structure,
                "openclaw_lane_tier": plan["lane_tier"],
                "openclaw_basis": plan["basis"],
                "entry_setup_label": plan["entry_setup_label"],
                "regime_label": plan["regime_label"],
                "assigned_strategy": strategy,
                "directional_bias": data.get("directional_bias"),
                "openclaw_personality": setup_profile["openclaw_personality"],
                "assigned_setup_type": setup_profile["assigned_setup_type"],
                "secondary_setup_type": setup_profile["secondary_setup_type"],
                "personality_reason": setup_profile["personality_reason"],
            }

        with open(self.order_path, "w", encoding="utf-8") as f:
            json.dump(active_triggers, f, indent=4, sort_keys=True)

        with open(self.heartbeat_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))

        plain_log("OPENCLAW_TREND_EXECUTOR_COMPLETE", {"armed_blueprints": len(active_triggers)})
        print("💾 OpenClaw 1H blueprints updated on disk.")


if __name__ == "__main__":
    executor = TrendExecutorAgent()
    executor.process_triggers()
