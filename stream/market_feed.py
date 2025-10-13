"""Asynchronous market data stream helpers.

Provides a Bybit WebSocket wrapper that exposes live trades as an
async iterator, plus a lightweight mock feed for local testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional

from pybit.unified_trading import WebSocket

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Tick:
    symbol: str
    price: float
    volume: float
    timestamp: int  # milliseconds

    def as_dict(self) -> Dict[str, float]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }


class BybitMarketStream:
    """Wrap Bybit's WebSocket in an async tick iterator."""

    def __init__(
        self,
        symbol: str,
        category: str = "linear",
        channel: str = "publicTrade",
        queue_size: int = 2048,
        testnet: bool = False,
        max_retries: int = 5,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.symbol = symbol
        self.category = category
        self.channel = channel
        self._ws: Optional[WebSocket] = None
        self._queue: "asyncio.Queue[Tick]" = asyncio.Queue(maxsize=queue_size)
        self._loop = asyncio.get_running_loop()
        self._connected = asyncio.Event()
        self._testnet = testnet
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    async def __aenter__(self) -> "BybitMarketStream":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._ws is not None:
            return

        self._connected.clear()

        def _trade_callback(message: Dict[str, Any]) -> None:
            try:
                # Trade payload comes under "data" list
                for item in message.get("data", []):
                    tick = Tick(
                        symbol=item.get("s", self.symbol),
                        price=float(item.get("p")),
                        volume=float(item.get("v", 0.0)),
                        timestamp=int(item.get("T", int(time.time() * 1000))),
                    )
                    self._loop.call_soon_threadsafe(self._enqueue_tick, tick)
            except Exception as err:  # pragma: no cover - defensive logging
                logger.exception("Failed to process trade payload: %s", err)

        attempt = 0
        last_error: Optional[Exception] = None

        while attempt < self._max_retries:
            try:
                logger.info(
                    "🔌 Connecting WebSocket for %s (%s) [testnet=%s, attempt=%s]",
                    self.symbol,
                    self.channel,
                    self._testnet,
                    attempt + 1,
                )
                self._ws = WebSocket(channel_type=self.category, testnet=self._testnet)
                self._ws.trade_stream(symbol=self.symbol, callback=_trade_callback)
                self._connected.set()
                logger.info("✅ WebSocket connected for %s", self.symbol)
                return
            except Exception as err:  # pragma: no cover - defensive logging
                last_error = err
                attempt += 1
                wait_time = self._retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "⚠️ WebSocket connection failed (attempt %s/%s): %s",
                    attempt,
                    self._max_retries,
                    err,
                )
                await asyncio.sleep(wait_time)

        raise ConnectionError("Failed to establish Bybit WebSocket") from last_error

    def _enqueue_tick(self, tick: Tick) -> None:
        if self._queue.full():
            dropped = self._queue.get_nowait()
            logger.warning(
                "Dropping stale tick to maintain backpressure: %s", json.dumps(dropped.as_dict())
            )
        self._queue.put_nowait(tick)

    async def ticks(self) -> AsyncIterator[Tick]:
        await self._connected.wait()
        while True:
            tick = await self._queue.get()
            yield tick

    async def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.exit()
            finally:
                self._ws = None
        self._connected.clear()
        logger.info("🛑 WebSocket for %s closed", self.symbol)


class MockTickFeed:
    """Deterministic tick generator for tests and offline development."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval_ms: int = 1000,
        base_price: float = 60_000.0,
        drift: float = 0.0,
        volatility: float = 0.003,
        mean_reversion: float = 0.1,
    ) -> None:
        self.symbol = symbol
        self.interval_ms = interval_ms
        self.base_price = base_price
        self.drift = drift
        self.volatility = volatility
        self.mean_reversion = mean_reversion
        self._running = False

    async def ticks(self) -> AsyncIterator[Tick]:
        price = self.base_price
        self._running = True
        target = self.base_price
        while self._running:
            ts = int(time.time() * 1000)
            # Ornstein-Uhlenbeck style process to avoid monotonic drift.
            shock = random.gauss(self.drift, self.volatility)
            reversion = self.mean_reversion * (target - price) / price
            price = max(1.0, price * (1 + shock + reversion))
            volume = max(0.01, abs(random.gauss(1.0, 0.2)))
            yield Tick(symbol=self.symbol, price=price, volume=volume, timestamp=ts)
            await asyncio.sleep(self.interval_ms / 1000)

    def stop(self) -> None:
        self._running = False


async def _demo() -> None:  # pragma: no cover - smoke test helper
    feed = MockTickFeed()
    async for tick in feed.ticks():
        logger.info("Tick: %s", tick)
        await asyncio.sleep(0.1)


if __name__ == "__main__":  # pragma: no cover - manual debug hook
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_demo())
