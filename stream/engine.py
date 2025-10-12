"""High-level orchestration for the streaming pipeline."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.pattern_builder import RealtimePatternBuilder
from intelligence.rolling_window_db import RollingWindowPatternDB
from stream.market_feed import BybitMarketStream, MockTickFeed

logger = logging.getLogger(__name__)


class StreamingEngine:
    """Glue together market feed and pattern builder."""

    def __init__(
        self,
        symbol: str,
        interval_seconds: int = 300,
        use_mock_feed: bool = False,
        mock_tick_interval_ms: int = 1000,
        testnet: bool = False,
    ) -> None:
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.use_mock_feed = use_mock_feed
        self.mock_tick_interval_ms = mock_tick_interval_ms
        self.testnet = testnet
        self.pattern_db = RollingWindowPatternDB()
        self.pattern_builder = RealtimePatternBuilder(
            self.pattern_db, interval_seconds=interval_seconds
        )
        self._stop = asyncio.Event()

    async def run(self, runtime_seconds: Optional[int] = None) -> None:
        async with AsyncExitStack() as stack:
            if self.use_mock_feed:
                feed = MockTickFeed(symbol=self.symbol, interval_ms=self.mock_tick_interval_ms)
                stack.push_async_callback(self._stop_mock_feed, feed)
                tick_iter = feed.ticks()
            else:
                stream = BybitMarketStream(symbol=self.symbol, testnet=self.testnet)
                await stack.enter_async_context(stream)
                tick_iter = stream.ticks()

            async def iterator():
                if runtime_seconds is None:
                    async for tick in tick_iter:
                        if self._stop.is_set():
                            break
                        await self.pattern_builder.process_tick(tick.as_dict())
                else:
                    end_time = asyncio.get_running_loop().time() + runtime_seconds
                    async for tick in tick_iter:
                        if asyncio.get_running_loop().time() >= end_time or self._stop.is_set():
                            break
                        await self.pattern_builder.process_tick(tick.as_dict())

            await iterator()
            self.pattern_builder.finalize()

    async def _stop_mock_feed(self, feed: MockTickFeed) -> None:
        feed.stop()

    def stop(self) -> None:
        self._stop.set()


async def run_demo(runtime_seconds: int = 30) -> None:  # pragma: no cover - manual smoke test
    engine = StreamingEngine(
        symbol="BTCUSDT",
        interval_seconds=5,
        use_mock_feed=True,
        mock_tick_interval_ms=100,
    )
    await engine.run(runtime_seconds=runtime_seconds)
    logger.info("Finished demo run – patterns stored: %s", engine.pattern_db.count())


if __name__ == "__main__":  # pragma: no cover - manual debug hook
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_demo())
