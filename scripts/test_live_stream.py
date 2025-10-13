#!/usr/bin/env python3
"""Exercise the live streaming pipeline with periodic AI decisions."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.pattern_builder import RealtimePatternBuilder
from agent.trader import TradingAgent
from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer
from stream.market_feed import BybitMarketStream, MockTickFeed


def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        pass


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class DecisionRecord:
    index: int
    timestamp: float
    action: str
    confidence: float
    reason: str
    safety_status: str


async def _decision_loop(
    agent: TradingAgent,
    mcp_server: TradingMCPServer,
    symbol: str,
    interval_seconds: int,
    stop_event: asyncio.Event,
    results: List[DecisionRecord],
) -> None:
    counter = 0
    while not stop_event.is_set():
        counter += 1
        t_start = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] Decision #{counter}: running analysis...")
        try:
            decision = await agent.analyze_and_decide(symbol)
        except Exception as exc:  # pragma: no cover - diagnostic path
            print(f"   ❌ Decision failed: {exc}")
            results.append(
                DecisionRecord(
                    index=counter,
                    timestamp=time.time(),
                    action="SKIP",
                    confidence=0.0,
                    reason=f"Decision failed: {exc}",
                    safety_status="ERROR",
                )
            )
        else:
            action = str(decision.get("action", "SKIP")).upper()
            confidence = _safe_float(decision.get("confidence", 0.0))
            reason = str(decision.get("reasoning", "No reasoning provided"))
            safety_status = "PASSED" if action != "SKIP" else "SKIPPED"
            print(f"   → Action: {action} | Confidence: {confidence:.2f} | Reason: {reason}")
            results.append(
                DecisionRecord(
                    index=counter,
                    timestamp=time.time(),
                    action=action,
                    confidence=confidence,
                    reason=reason,
                    safety_status=safety_status,
                )
            )
        elapsed = time.time() - t_start
        if elapsed < 0.1:
            await asyncio.sleep(0.1)

        if stop_event.is_set():
            break

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue
        else:
            break


async def _stream_loop(
    builder: RealtimePatternBuilder,
    symbol: str,
    duration_seconds: int,
    use_mock: bool,
    testnet: bool,
    stop_event: asyncio.Event,
) -> Dict[str, Any]:
    ticks_processed = 0
    async def _pump_ticks() -> None:
        nonlocal ticks_processed
        async for tick in tick_iter:
            ticks_processed += 1
            await builder.process_tick(tick.as_dict())
            if time.perf_counter() >= deadline or stop_event.is_set():
                break

    source_label = "real"
    try:
        if use_mock:
            print("🌐 Using mock tick feed (offline mode)")
            feed = MockTickFeed(symbol=symbol, interval_ms=500)
            tick_iter = feed.ticks()
            context: Optional[Any] = None
            source_label = "mock"
        else:
            stream = BybitMarketStream(symbol=symbol, testnet=testnet)
            context = stream
            tick_iter = stream.ticks()
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"⚠️ Failed to initialise feed: {exc}. Falling back to mock feed.")
        feed = MockTickFeed(symbol=symbol, interval_ms=500)
        tick_iter = feed.ticks()
        context = None
        source_label = "mock"

    start_time = time.perf_counter()
    deadline = start_time + duration_seconds

    async def ticker() -> None:
        try:
            await _pump_ticks()
        finally:
            builder.finalize()
            stop_event.set()

    if context is None:
        await ticker()
    else:
        try:
            async with context:
                print("🌐 Connected to Bybit WebSocket")
                await ticker()
        except Exception as exc:  # pragma: no cover - fallback if connection fails
            print(f"⚠️ WebSocket connection failed: {exc}. Switching to mock feed.")
            feed = MockTickFeed(symbol=symbol, interval_ms=500)
            tick_iter = feed.ticks()
            context = None
            source_label = "mock"
            await ticker()

    runtime = time.perf_counter() - start_time
    candles = len(builder._history.get(symbol, []))  # type: ignore[attr-defined]
    return {
        "ticks_processed": ticks_processed,
        "candles": candles,
        "runtime": runtime,
        "source": source_label,
    }


async def run_live_stream(args: argparse.Namespace) -> None:
    _load_env_file()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Check your .env or environment variables.")

    symbol = args.symbol
    duration_seconds = args.duration
    decision_interval = args.decision_interval

    pattern_db = RollingWindowPatternDB()
    if args.bootstrap_csv:
        csv_path = PROJECT_ROOT / args.bootstrap_csv if not Path(args.bootstrap_csv).is_absolute() else Path(args.bootstrap_csv)
        if csv_path.exists():
            print(f"📥 Loading bootstrap patterns from {csv_path} ...", flush=True)
            try:
                loaded = pattern_db.load_from_csv(str(csv_path), clear_existing=False, apply_pruning=False)
            except Exception as exc:  # pragma: no cover - diagnostic log
                print(f"⚠️ Failed to load bootstrap patterns: {exc}")
            else:
                print(f"   → Loaded {loaded} patterns (DB total: {pattern_db.count()})")
        else:
            print(f"⚠️ Bootstrap CSV not found at {csv_path}, skipping preload")

    builder = RealtimePatternBuilder(pattern_db, interval_seconds=args.candle_seconds)
    mcp_server = TradingMCPServer(pattern_db)
    agent = TradingAgent(mcp_server, model=args.model)

    stop_event = asyncio.Event()
    decisions: List[DecisionRecord] = []
    patterns_before = pattern_db.count()

    stream_task = asyncio.create_task(
        _stream_loop(
            builder=builder,
            symbol=symbol,
            duration_seconds=duration_seconds,
            use_mock=args.mock,
            testnet=args.testnet,
            stop_event=stop_event,
        )
    )

    decision_task = asyncio.create_task(
        _decision_loop(
            agent=agent,
            mcp_server=mcp_server,
            symbol=symbol,
            interval_seconds=decision_interval,
            stop_event=stop_event,
            results=decisions,
        )
    )

    print(f"📊 Streaming {symbol} ({args.candle_seconds}-second candles) for {duration_seconds}s")
    try:
        stream_stats = await stream_task
    finally:
        stop_event.set()
        await decision_task

    print("\n📈 Session Summary")
    print(f"   Runtime: {stream_stats['runtime']:.2f}s")
    print(f"   Tick source: {stream_stats['source']}")
    print(f"   Ticks processed: {stream_stats['ticks_processed']}")
    print(f"   Candles: {stream_stats['candles']}")

    new_patterns = pattern_db.count()
    print(f"   Patterns stored total: {new_patterns} (new: {max(0, new_patterns - patterns_before)})")

    print("\n🤖 Decisions")
    if decisions:
        for record in decisions:
            ts = time.strftime("%H:%M:%S", time.localtime(record.timestamp))
            print(
                f"   [{ts}] #{record.index}: {record.action} (conf {record.confidence:.2f}) | {record.reason}"
            )
        if len(decisions) < max(1, duration_seconds // decision_interval):
            missing = max(0, duration_seconds // decision_interval - len(decisions))
            if missing:
                print(f"   (⚠️ Expected ~{duration_seconds // decision_interval} decisions; short by {missing}.)")
    else:
        print("   No decisions executed")

    print("\n💰 Cost Summary")
    print(f"   API calls: {agent.api_calls_today}")
    print(f"   Estimated cost today: ${agent.estimated_cost_today:.4f}")

    print("\n✅ Live stream test complete")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the live streaming pipeline")
    parser.add_argument("--symbol", default="BTCUSDT", help="Market symbol to stream (default: BTCUSDT)")
    parser.add_argument("--duration", type=int, default=120, help="Streaming duration in seconds (default: 120)")
    parser.add_argument(
        "--decision-interval",
        type=int,
        default=30,
        dest="decision_interval",
        help="Seconds between AI decisions (default: 30)",
    )
    parser.add_argument(
        "--candle-seconds",
        type=int,
        default=5,
        dest="candle_seconds",
        help="Candle interval in seconds (default: 5)",
    )
    parser.add_argument("--mock", action="store_true", help="Use mock tick feed instead of Bybit WebSocket")
    parser.add_argument("--testnet", action="store_true", help="Use Bybit testnet WebSocket")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use (default: gpt-4o-mini)")
    parser.add_argument(
        "--bootstrap-csv",
        default="",
        help="Optional CSV path with historical patterns to preload before streaming",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        asyncio.run(run_live_stream(args))
    except KeyboardInterrupt:
        print("Interrupted by user")
        return 130
    except Exception as exc:
        print(f"❌ Live stream test failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
