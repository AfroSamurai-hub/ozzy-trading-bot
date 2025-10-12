"""Real-time pattern construction from streaming ticks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

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

    def _close_candle(self, symbol: str, candle: Dict[str, float]) -> None:
        history = self._history[symbol]
        history.append(candle)
        if len(history) > 200:
            history.pop(0)

        df = pd.DataFrame(history)
        if len(df) < 20:
            return

        df["rsi"] = df["close"].rolling(window=14).apply(self._rsi_calc, raw=True)
        df["ema_short"] = df["close"].ewm(span=13, adjust=False).mean()
        df["ema_long"] = df["close"].ewm(span=23, adjust=False).mean()
        latest = df.iloc[-1]

        embedding = [
            float(latest["rsi"] or 50) / 100.0,
            float(latest["ema_short"] / latest["ema_long"]) if latest["ema_long"] else 1.0,
            float(latest["volume_change"]),
            float(latest["price_change"]),
        ]

        metadata = {
            "timestamp": candle["end_ts"] / 1000,
            "label": candle.get("label", "UNKNOWN"),
            "rsi": float(latest["rsi"] or 50),
            "ema_ratio": float(latest["ema_short"] / latest["ema_long"]) if latest["ema_long"] else 1.0,
        }

        self.pattern_db.add_pattern(
            PatternEmbedding(
                id=f"{symbol}_{int(candle['end_ts'])}",
                embedding=embedding,
                metadata=metadata,
            )
        )
        logger.info("✅ Pattern stored for %s (total: %s)", symbol, self.pattern_db.count())

    @staticmethod
    def _rsi_calc(values: List[float]) -> float:
        series = pd.Series(values)
        delta = series.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        avg_gain = up.rolling(window=14, min_periods=14).mean()
        avg_loss = down.rolling(window=14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace({0: float("inf")})
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else 50

    async def process_tick(self, tick: Dict[str, float]) -> None:
        symbol = tick["symbol"]
        price = float(tick["price"])
        volume = float(tick.get("volume", 0))
        timestamp_ms = int(tick["timestamp"])

        bucket_start = self._get_bucket_start(timestamp_ms)
        candle = self._candles[symbol]

        if not candle:
            candle.update(
                {
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume,
                    "start_ts": bucket_start,
                    "end_ts": bucket_start + self.interval_seconds * 1000,
                    "volume_change": 0.0,
                    "price_change": 0.0,
                }
            )
            return

        if timestamp_ms >= candle["end_ts"]:
            self._close_candle(symbol, candle.copy())
            candle.clear()
            return

        candle["high"] = max(candle["high"], price)
        candle["low"] = min(candle["low"], price)
        candle["close"] = price
        candle["volume"] += volume
        candle["price_change"] = (price - candle["open"]) / candle["open"] if candle["open"] else 0.0
        candle["volume_change"] = volume

    async def run(self, tick_async_iterable) -> None:
        async for tick in tick_async_iterable:
            await self.process_tick(tick)


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
