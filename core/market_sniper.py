#!/usr/bin/env python3
"""OpenClaw 15m sniper lane state writer.

This does not execute trades. The live Binance 15m scanner remains the entry
engine; this file keeps OpenClaw lane state aligned with the regime ledger.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import get_symbol_strategy_profile
from logger import plain_log


class MarketSniperAgent:
    def __init__(self):
        self.state_path = ROOT / "shared" / "market_regimes.json"
        self.candidate_path = ROOT / "shared" / "sniper_candidates.json"
        self.heartbeat_path = ROOT / "shared" / "sniper.heartbeat"

    def load_market_regimes(self):
        if not self.state_path.exists():
            plain_log("OPENCLAW_SNIPER_SKIP", {"reason": "missing_market_regimes"})
            return False
        with open(self.state_path, "r", encoding="utf-8") as f:
            self.regimes = json.load(f)
        return True

    def process_range_snipes(self):
        self.candidate_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.load_market_regimes():
            return

        print("\n🎯 OZZYBOT OPENCLAW: Updating 15m sniper lane state...")
        candidates = {}
        for symbol, data in self.regimes.items():
            profile = get_symbol_strategy_profile(symbol)
            configured_lane = str(data.get("configured_lane") or profile.get("execution_lane") or "")
            if configured_lane.lower() != "sniper":
                continue
            if data.get("assigned_strategy") != "15M_MEAN_REVERSION":
                continue
            candidates[symbol] = {
                "symbol": symbol,
                "timeframe": "15m",
                "status": "WATCHING",
                "source": "openclaw_binance_native",
                "updated_at": int(time.time()),
                "metrics": data.get("metrics") or {},
            }

        with open(self.candidate_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, indent=4, sort_keys=True)

        with open(self.heartbeat_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))

        plain_log("OPENCLAW_SNIPER_COMPLETE", {"watching": len(candidates)})
        print(f"🟢 OpenClaw sniper candidates updated: {len(candidates)}")


if __name__ == "__main__":
    sniper = MarketSniperAgent()
    sniper.process_range_snipes()
