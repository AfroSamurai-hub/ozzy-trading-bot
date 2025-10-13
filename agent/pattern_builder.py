"""Real-time pattern construction from streaming ticks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

from intelligence.rolling_window_db import PatternEmbedding, RollingWindowPatternDB

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_ts: int
    end_ts: int


class RealtimePatternBuilder:
    def __init__(self, pattern_db: RollingWindowPatternDB, interval_seconds: int = 300) -> None:
        self.pattern_db = pattern_db
        self.interval_seconds = interval_seconds
        self._candles: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._history: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    def _get_bucket_start(self, timestamp_ms: int) -> int:
        ts = timestamp_ms // 1000
        bucket = ts - (ts % self.interval_seconds)
        return bucket * 1000

    def _init_candle(
        self,
        symbol: str,
        price: float,
        volume: float,
        bucket_start: int,
    ) -> Dict[str, float]:
        candle = {
            "symbol": symbol,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
            "start_ts": bucket_start,
            "end_ts": bucket_start + self.interval_seconds * 1000,
        }
        return candle

    def _close_candle(self, symbol: str, candle: Dict[str, float]) -> None:
        history = self._history[symbol]
        history.append(candle)
        if len(history) > 200:
            history.pop(0)

        df = pd.DataFrame(history)
        if len(df) < 20:
            return

        df["price_change"] = df["close"].pct_change().fillna(0.0)
        df["volume_change"] = df["volume"].pct_change().fillna(0.0)

        rsi_series = RSIIndicator(close=df["close"], window=14).rsi()
        df["rsi"] = rsi_series
        latest_rsi = rsi_series.iloc[-1]
        if pd.isna(latest_rsi):
            logger.debug("RSI warm-up in progress for %s; skipping pattern close", symbol)
            return
        latest_rsi = float(max(0.0, min(latest_rsi, 100.0)))

        df["ema_short"] = EMAIndicator(close=df["close"], window=13).ema_indicator().bfill()
        df["ema_long"] = EMAIndicator(close=df["close"], window=23).ema_indicator().bfill()
        latest = df.iloc[-1]

        ema_long = float(latest["ema_long"]) if latest["ema_long"] else 0.0
        ema_ratio = float(latest["ema_short"]) / ema_long if ema_long else 1.0

        embedding = [
            latest_rsi / 100.0,
            ema_ratio,
            float(latest.get("volume_change", 0.0)),
            float(latest.get("price_change", 0.0)),
        ]

        metadata = {
            "timestamp": candle["end_ts"] / 1000,
            "label": candle.get("label", "UNKNOWN"),
            "rsi": latest_rsi,
            "ema_ratio": ema_ratio,
            "price_change": float(latest.get("price_change", 0.0)),
            "volume_change": float(latest.get("volume_change", 0.0)),
            "symbol": symbol,
            "hit_takeprofit": False,
            "hit_stoploss": False,
            "max_profit_pct": None,
            "max_drawdown_pct": None,
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        self.pattern_db.add_pattern(
            PatternEmbedding(
                id=f"{symbol}_{int(candle['end_ts'])}",
                embedding=embedding,
                metadata=metadata,
            )
        )
        logger.info("✅ Pattern stored for %s (total: %s)", symbol, self.pattern_db.count())

    async def process_tick(self, tick: Dict[str, float]) -> None:
        symbol = tick["symbol"]
        price = float(tick["price"])
        volume = float(tick.get("volume", 0))
        timestamp_ms = int(tick["timestamp"])

        bucket_start = self._get_bucket_start(timestamp_ms)
        candle = self._candles[symbol]

        if not candle:
            self._candles[symbol] = self._init_candle(symbol, price, volume, bucket_start)
            return

        if bucket_start >= candle["end_ts"]:
            self._close_candle(symbol, candle.copy())
            self._candles[symbol] = self._init_candle(symbol, price, volume, bucket_start)
            return

        candle["high"] = max(candle["high"], price)
        candle["low"] = min(candle["low"], price)
        candle["close"] = price
        candle["volume"] += volume

    async def run(self, tick_async_iterable) -> None:
        async for tick in tick_async_iterable:
            await self.process_tick(tick)

    def finalize(self) -> None:
        """Force-close any active candles (e.g., when the stream shuts down)."""

        for symbol, candle in list(self._candles.items()):
            if not candle:
                continue

            self._close_candle(symbol, candle.copy())
            self._candles[symbol] = {}


async def demo_loop():
    class DummyFeed:
        async def __aiter__(self):
            for i in range(600):
                yield {
                    "symbol": "BTCUSDT",
                    "price": 60000 + i,
                    "volume": 10,
                    "timestamp": int(time.time() * 1000) + i * 1000,
                }
                await asyncio.sleep(0.01)

    db = RollingWindowPatternDB(window_hours=48)
    builder = RealtimePatternBuilder(db)
    await builder.run(DummyFeed())


if __name__ == "__main__":
    asyncio.run(demo_loop())
