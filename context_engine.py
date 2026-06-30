"""
Context Engine — Dynamic Position Sizing for OzzyBot
v2026-04-28

NOT a filter. NOT a blocker.
A position sizing engine that trades BIGGER on high-conviction setups
and smaller on risky ones.

Sources:
  - Fear & Greed Index: alternative.me (free, no API key)
  - Funding Rate: Binance native API (free, no extra key)

Cache:
  - fear_greed.json  → 6 hour TTL
  - funding_rate.json → 4 hour TTL
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from filelock import FileLock

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(os.getenv("HERMES_CACHE_DIR", "/home/rick/ozzy-bot/.cache"))
CACHE_DIR.mkdir(exist_ok=True)

FEAR_GREED_CACHE = CACHE_DIR / "fear_greed.json"
FUNDING_CACHE = CACHE_DIR / "funding_rate.json"

# Danger keywords for news scanning (placeholder — Firecrawl deferred to Phase 2)
DANGER_WORDS = ["hack", "exploit", "crash", "ban", "sec lawsuit", "regulatory action"]

# Symbol mapping: TV symbol → Binance futures symbol for funding rate
TV_TO_FUNDING_SYMBOL = {
    "BTCUSD": "BTCUSDT",
    "BTCUSDT": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSD": "SOLUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSD": "XRPUSDT",
    "XRPUSDT": "XRPUSDT",
    "SUIUSDT": "SUIUSDT",
    "HYPEUSDT": "HYPEUSDT",
}


def _load_cache(path: Path, ttl_seconds: int) -> Optional[dict]:
    """Load cached data if still fresh."""
    if not path.exists():
        return None
    try:
        lock_path = path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            data = json.loads(path.read_text())
        if time.time() - data.get("_cached_at", 0) < ttl_seconds:
            return data
    except Exception as e:
        logger.error("Context load failed — bot trading without strategy context: %s", e)
    return None


def _save_cache(path: Path, data: dict) -> None:
    """Save data to cache with timestamp."""
    data["_cached_at"] = time.time()
    lock_path = path.with_suffix(".lock")
    with FileLock(str(lock_path)):
        path.write_text(json.dumps(data))


def fetch_fear_greed() -> dict:
    """
    Fetch Crypto Fear & Greed Index from alternative.me.
    Returns: {"value": int, "classification": str, "timestamp": str}
    """
    cached = _load_cache(FEAR_GREED_CACHE, 6 * 3600)
    if cached:
        return {
            "value": cached.get("value", 50),
            "classification": cached.get("classification", "Neutral"),
            "timestamp": cached.get("timestamp", ""),
        }

    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", [{}])[0]
        result = {
            "value": int(data.get("value", 50)),
            "classification": data.get("value_classification", "Neutral"),
            "timestamp": data.get("timestamp", ""),
        }
        _save_cache(FEAR_GREED_CACHE, result)
        return result
    except Exception as e:
        # Fail-open: return neutral on error so we don't block trades
        return {"value": 50, "classification": "Neutral", "timestamp": "", "error": str(e)}


def fetch_funding_rate(symbol: str) -> dict:
    """
    Fetch funding rate from Binance native API.
    symbol: TradingView symbol (e.g. "ETHUSD")
    Returns: {"rate": float, "time": int}
    """
    binance_symbol = TV_TO_FUNDING_SYMBOL.get(symbol, symbol)

    # Check per-symbol cache
    cached = _load_cache(FUNDING_CACHE, 4 * 3600)
    if cached and binance_symbol in cached:
        return {
            "rate": float(cached[binance_symbol]["rate"]),
            "time": int(cached[binance_symbol]["time"]),
        }

    try:
        resp = requests.get(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={binance_symbol}&limit=1",
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload[0] if payload else {}
        result = {
            "rate": float(data.get("fundingRate", 0.0)),
            "time": int(data.get("fundingTime", 0)),
        }
        # Merge with existing cache
        cache_data = cached or {}
        cache_data[binance_symbol] = result
        _save_cache(FUNDING_CACHE, cache_data)
        return result
    except Exception as e:
        return {"rate": 0.0, "time": 0, "error": str(e)}


def get_size_multiplier(symbol: str, direction: str, risk_pct: float = 0.02) -> dict:
    """
    Calculate position size multiplier based on market context.

    Args:
        symbol: TradingView symbol (e.g. "ETHUSD")
        direction: "BUY" or "SELL"
        risk_pct: base risk percentage (e.g. 0.02 = 2%)

    Returns:
        {
            "multiplier": float,      # 0.0 to 1.75
            "adjusted_risk_pct": float,  # capped at 0.08 (8%)
            "fear_greed": int,
            "fear_greed_class": str,
            "funding_rate": float,
            "news_status": str,
            "reasoning": str,
        }
    """
    # Fetch context data
    fg = fetch_fear_greed()
    funding = fetch_funding_rate(symbol)

    score = fg["value"]
    funding_rate = funding["rate"]

    # News scanning — placeholder, Firecrawl deferred to Phase 2
    # For now, always clear. Phase 2 will add RSS/Firecrawl keyword scan.
    breaking_danger_news = False
    news_status = "clear"

    # ── SIZING LOGIC ──
    # 1. SIZE UP (1.75x) — extreme fear + buy, extreme greed + short
    if score < 25 and direction == "BUY":
        multiplier = 1.75
        reasoning = f"Extreme fear ({score}) + {direction} = maximum conviction"
    elif score > 75 and direction == "SELL":
        multiplier = 1.75
        reasoning = f"Extreme greed ({score}) + {direction} = maximum conviction"

    # 2. SIZE DOWN (0.5x) — greed + buy, fear + short, extreme funding
    elif score > 75 and direction == "BUY":
        multiplier = 0.5
        reasoning = f"High greed ({score}) + {direction} = elevated risk"
    elif score < 25 and direction == "SELL":
        multiplier = 0.5
        reasoning = f"High fear ({score}) + {direction} = elevated risk"
    elif funding_rate > 0.01 and direction == "BUY":
        multiplier = 0.5
        reasoning = f"High positive funding ({funding_rate:.4%}) + {direction} = crowded longs"
    elif funding_rate < -0.01 and direction == "SELL":
        multiplier = 0.5
        reasoning = f"High negative funding ({funding_rate:.4%}) + {direction} = crowded shorts"

    # 3. NORMAL (1.0x)
    else:
        multiplier = 1.0
        reasoning = f"Neutral context (FG={score}, funding={funding_rate:.4%})"

    # 4. SKIP (0.0x) — only on breaking danger news
    if breaking_danger_news:
        multiplier = 0.0
        reasoning = "Breaking danger news detected — skip trade"
        news_status = "danger"

    # Hard cap at 8% max risk
    adjusted_risk_pct = min(risk_pct * multiplier, 0.08)

    return {
        "multiplier": multiplier,
        "adjusted_risk_pct": adjusted_risk_pct,
        "fear_greed": score,
        "fear_greed_class": fg["classification"],
        "funding_rate": funding_rate,
        "news_status": news_status,
        "reasoning": reasoning,
    }


if __name__ == "__main__":
    # Quick sanity test
    print("=== Context Engine Test ===")
    for sym, dir_ in [("ETHUSDT", "BUY"), ("ETHUSDT", "SELL"), ("SOLUSDT", "BUY")]:
        ctx = get_size_multiplier(sym, dir_, risk_pct=0.05)
        print(f"\n{sym} {dir_}:")
        for k, v in ctx.items():
            print(f"  {k}: {v}")
