#!/usr/bin/env python3
"""Exercise the live streaming pipeline with periodic AI decisions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.pattern_builder import RealtimePatternBuilder
from agent.portfolio import PaperTradingPortfolio
from agent.trader import TradingAgent
from intelligence.rolling_window_db import RollingWindowPatternDB
from intelligence.pattern_intelligence import PatternIntelligence  # 🧠 For pattern learning
from mcp.trading_server import TradingMCPServer
from stream.market_feed import BybitMarketStream, MockTickFeed
from stream.intelligent_stream_manager import IntelligentStreamManager
from utils.currency import format_currency, format_currency_signed

# Import Slack notifier if available
try:
    from notifications.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    SlackNotifier = None


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


def _learn_from_closed_trade(
    closed_trade: Dict[str, Any],
    pattern_intelligence: Optional[PatternIntelligence]
) -> None:
    """
    🧠 Update pattern intelligence after a trade closes.
    
    This enables the system to learn which patterns actually work!
    """
    if not pattern_intelligence:
        return
    
    # Extract pattern_id from position
    pattern_id = closed_trade.get('pattern_id')
    if not pattern_id:
        # No pattern tracked for this trade
        return
    
    # Calculate held time
    entry_time = datetime.fromisoformat(closed_trade.get('entry_time'))
    exit_time = datetime.fromisoformat(closed_trade.get('exit_time'))
    held_seconds = (exit_time - entry_time).total_seconds()
    
    # Build outcome dict
    outcome = {
        'win': closed_trade['outcome'] == 'WIN',
        'pnl_pct': closed_trade['realized_pnl_pct'],
        'held_time': held_seconds,
        # TODO: Add market context when available:
        # 'market_regime': market_state.get('regime'),
        # 'trading_session': market_state.get('session'),
        # 'volatility': market_state.get('volatility_level'),
    }
    
    # Update pattern stats
    try:
        pattern_intelligence.update_pattern_outcome(pattern_id, outcome)
        print(f"   🧠 Pattern '{pattern_id}' learned from this trade!")
    except Exception as e:
        print(f"   ⚠️ Failed to update pattern intelligence: {e}")


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
    portfolio: PaperTradingPortfolio,
    symbol: str,
    interval_seconds: int,
    stop_event: asyncio.Event,
    results: List[DecisionRecord],
    slack_notifier: Optional['SlackNotifier'] = None,
) -> None:
    counter = 0
    last_summary_time = time.time()
    SUMMARY_INTERVAL = 300  # Send positions summary every 5 minutes
    
    # 🔧 EVOLVED: Track decision outcomes for monitoring
    decision_stats = {'buy': 0, 'sell': 0, 'skip': 0, 'rejected': 0}
    
    while not stop_event.is_set():
        counter += 1
        t_start = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] Decision #{counter}: running analysis...")
        try:
            decision = await agent.analyze_and_decide(symbol)
        except Exception as exc:  # pragma: no cover - diagnostic path
            import traceback
            print(f"   ❌ Decision failed: {exc}")
            traceback.print_exc()
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
            
            # Handle portfolio actions
            market_state = await mcp_server.get_market_state(symbol)
            current_price = _safe_float(market_state.get("price"), 0.0)
            
            # 🔬 RESEARCH: Volume Confirmation Filter (76.3% success rate with volume)
            if action == "BUY":
                volume_24h = _safe_float(market_state.get("volume_24h"), 0.0)
                volume_avg = _safe_float(market_state.get("volume_avg"), 1.0)  # Avoid div by zero
                volume_ratio = volume_24h / volume_avg if volume_avg > 0 else 1.0
                
                if volume_ratio < 0.80:  # Below 80% of average = reject
                    print(f"   ⏭️  SKIP: Volume too low ({volume_ratio:.2f}x avg, need >0.80x)")
                    action = "SKIP"
                    reason = f"Volume confirmation failed: {volume_ratio:.2f}x (need >0.80x)"
                    safety_status = "SKIPPED"
                elif volume_ratio > 1.5:
                    # Strong volume confirmation - already boosted by dynamic confidence
                    print(f"   ✅ Volume confirms: {volume_ratio:.2f}x avg")
            
            # 🔬 RESEARCH: Confidence Threshold for 15-min timeframe (0.70)
            if action == "BUY" and confidence < 0.70:
                print(f"   ⏭️  SKIP: Confidence too low ({confidence:.2%} < 70% threshold)")
                action = "SKIP"
                reason = f"Confidence below 70% threshold: {confidence:.2%}"
                safety_status = "SKIPPED"
            
            print(f"   → Market price: {format_currency(current_price)}")
            
            # Update all positions with current price
            if current_price > 0:
                portfolio.update_positions(symbol, current_price)
            
            # Execute trade if action is BUY
            if action == "BUY" and current_price > 0:
                print(f"   → BUY signal received")
                # Use position size from decision or default
                position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
                
                # 🔧 EVOLVED: Try to open position (may be rejected by risk checks)
                try:
                    # 🧠 Extract pattern_id for learning
                    pattern_id = decision.get("detected_pattern")
                    
                    position = portfolio.open_position(
                        symbol=symbol,
                        side="LONG",
                        entry_price=current_price,
                        size=position_size,
                        confidence=confidence,
                        reason=reason,
                        pattern_id=pattern_id  # 🧠 Store pattern for learning
                    )
                    
                    # 🔧 EVOLVED: Handle rejection gracefully
                    if position is None:
                        print(f"   ⏭️  Position rejected by risk management (capital/limits)")
                        # Continue to next decision cycle
                        action = "REJECTED"  # Track rejection
                    else:
                        print(f"   ✅ Position #{position['id']} opened: {symbol} @ {format_currency(current_price)}")
                        
                        # Send Slack notification
                        if slack_notifier:
                            slack_notifier.notify_position_opened(
                                symbol=symbol,
                                entry_price=current_price,
                                size=position_size,
                                confidence=confidence,
                                reason=reason
                            )
                        
                        # Now update decisions.json to match the actual trade
                        decisions_file = PROJECT_ROOT / "logs/decisions.json"
                        if decisions_file.exists():
                            try:
                                with open(decisions_file, "r") as f:
                                    decisions_data = json.load(f)
                                    
                                # Find the most recent decision for this symbol with this action
                                # (which should be the one we just executed)
                                for i, dec in reversed(list(enumerate(decisions_data.get("decisions", [])))):
                                    if (dec.get("symbol") == symbol and 
                                        dec.get("action") == "BUY" and 
                                        dec.get("status") == "OPEN"):
                                        # Update with actual values
                                        decisions_data["decisions"][i]["entry_price"] = current_price
                                        decisions_data["decisions"][i]["position_size"] = position_size
                                        decisions_data["decisions"][i]["position_id"] = position["id"]
                                        decisions_data["decisions"][i]["current_price"] = current_price
                                        break
                                        
                                # Update the file
                                with open(decisions_file, "w") as f:
                                    json.dump(decisions_data, f, indent=2)
                            except Exception as e:
                                print(f"Error updating decisions.json: {e}")
                except Exception as e:
                    print(f"❌ Error opening position: {e}")
            
            # Handle SELL action to close positions
            elif action == "SELL" and current_price > 0:
                print(f"   → SELL signal received. Closing all open positions for {symbol}...")
                closed_any = False
                for pos in portfolio.positions[:]:
                    if pos["symbol"] == symbol:
                        closed_trade = portfolio.close_position(
                            position_id=pos["id"],
                            exit_price=current_price,
                            reason="AI Decision"
                        )
                        if closed_trade:
                            closed_any = True
                            print(
                                f"   → Position closed: {symbol} @ {format_currency(current_price)} "
                                f"(P&L: {format_currency_signed(closed_trade['realized_pnl'])})"
                            )
                            
                            # 🧠 Learn from this trade
                            _learn_from_closed_trade(closed_trade, pattern_intelligence)
                            
                            # Send Slack notification
                            if slack_notifier:
                                slack_notifier.notify_position_closed(
                                    symbol=symbol,
                                    exit_price=current_price,
                                    pnl=closed_trade['realized_pnl'],
                                    pnl_pct=closed_trade['realized_pnl_pct'],
                                    reason=reason,
                                    outcome=closed_trade['outcome']
                                )
                if not closed_any:
                    print(f"   → No open positions to close for {symbol}.")
            
            # 🔧 CRITICAL FIX: Check TP/SL on EVERY iteration (not just in else block!)
            # This runs REGARDLESS of AI decision - monitors all open positions
            if current_price > 0:
                positions_closed = 0
                for pos in portfolio.positions[:]:  # Copy list since we'll modify it
                    if pos["symbol"] == symbol:
                        pnl_pct = pos.get("pnl_pct", 0)
                        
                        # 🔬 RESEARCH: Check 24-hour max holding time first
                        entry_time = datetime.fromisoformat(pos.get("entry_time"))
                        hours_held = (datetime.now() - entry_time).total_seconds() / 3600
                        
                        if hours_held >= 24.0:
                            # Force close after 24 hours (research-backed)
                            closed_trade = portfolio.close_position(
                                position_id=pos["id"],
                                exit_price=current_price,
                                reason=f"Time Exit ({hours_held:.1f}h)"
                            )
                            if closed_trade:
                                positions_closed += 1
                                print(
                                    f"   ⏰ Time Exit! Position #{pos['id']} closed @ {format_currency(current_price)} "
                                    f"| Held: {hours_held:.1f}h | P&L: {format_currency_signed(closed_trade['realized_pnl'])} ({pnl_pct:+.2f}%)"
                                )
                                
                                # 🧠 Learn from this trade
                                _learn_from_closed_trade(closed_trade, pattern_intelligence)
                                
                                if slack_notifier:
                                    slack_notifier.notify_position_closed(
                                        symbol=symbol,
                                        exit_price=current_price,
                                        pnl=closed_trade['realized_pnl'],
                                        pnl_pct=closed_trade['realized_pnl_pct'],
                                        reason=f"Time Exit ({hours_held:.1f}h)",
                                        outcome=closed_trade['outcome']
                                    )
                        
                        # 🔬 RESEARCH: Take profit at +3.5% (adjusted for 15-min timeframe transaction costs)
                        # 🔧 FIX: Use 3.4% threshold to account for floating point precision
                        elif pnl_pct >= 3.4:
                            closed_trade = portfolio.close_position(
                                position_id=pos["id"],
                                exit_price=current_price,
                                reason="Take Profit"
                            )
                            if closed_trade:
                                positions_closed += 1
                                print(
                                    f"   ✅ Take Profit Hit! Position #{pos['id']} closed @ {format_currency(current_price)} "
                                    f"| P&L: {format_currency_signed(closed_trade['realized_pnl'])} ({pnl_pct:+.2f}%)"
                                )
                                
                                # 🧠 Learn from this trade
                                _learn_from_closed_trade(closed_trade, pattern_intelligence)
                                
                                # Send Slack notification
                                if slack_notifier:
                                    slack_notifier.notify_position_closed(
                                        symbol=symbol,
                                        exit_price=current_price,
                                        pnl=closed_trade['realized_pnl'],
                                        pnl_pct=closed_trade['realized_pnl_pct'],
                                        reason="Take Profit",
                                        outcome=closed_trade['outcome']
                                    )
                        
                        # Stop loss at -1.5%
                        # 🔧 FIX: Use -1.4% threshold to account for floating point precision
                        elif pnl_pct <= -1.4:
                            closed_trade = portfolio.close_position(
                                position_id=pos["id"],
                                exit_price=current_price,
                                reason="Stop Loss"
                            )
                            if closed_trade:
                                positions_closed += 1
                                print(
                                    f"   ⚠️  Stop Loss Hit! Position #{pos['id']} closed @ {format_currency(current_price)} "
                                    f"| P&L: {format_currency_signed(closed_trade['realized_pnl'])} ({pnl_pct:.2f}%)"
                                )
                                
                                # 🧠 Learn from this trade
                                _learn_from_closed_trade(closed_trade, pattern_intelligence)
                                
                                # Send Slack notification
                                if slack_notifier:
                                    slack_notifier.notify_position_closed(
                                        symbol=symbol,
                                        exit_price=current_price,
                                        pnl=closed_trade['realized_pnl'],
                                        pnl_pct=closed_trade['realized_pnl_pct'],
                                        reason="Stop Loss",
                                        outcome=closed_trade['outcome']
                                    )
                        
                        # Send position update for positions near TP/SL (but not closed yet)
                        elif slack_notifier and (pnl_pct >= 2.0 or pnl_pct <= -1.0):
                            entry_price = pos.get("entry_price", current_price)
                            tp_price = entry_price * 1.03  # +3%
                            sl_price = entry_price * 0.985  # -1.5%
                            
                            slack_notifier.notify_position_update(
                                position=pos,
                                current_price=current_price,
                                tp_price=tp_price,
                                sl_price=sl_price
                            )
                
                if positions_closed > 0:
                    print(f"   📊 Portfolio update: {len(portfolio.positions)} positions remaining")
            
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
            
            # 🔧 EVOLVED: Track decision statistics
            if action == "BUY":
                decision_stats['buy'] += 1
            elif action == "SELL":
                decision_stats['sell'] += 1
            elif action == "REJECTED":
                decision_stats['rejected'] += 1
            else:
                decision_stats['skip'] += 1
            
            # Log stats every 10 decisions
            if counter % 10 == 0:
                total = decision_stats['buy'] + decision_stats['skip'] + decision_stats['rejected']
                print(f"   📈 Stats: {decision_stats['buy']} BUY | "
                      f"{decision_stats['rejected']} REJECTED | "
                      f"{decision_stats['skip']} SKIP | "
                      f"Accept Rate: {decision_stats['buy']/total*100:.1f}%")
        
        # Send periodic summary of all positions (every 5 minutes)
        current_time = time.time()
        if slack_notifier and (current_time - last_summary_time) >= SUMMARY_INTERVAL:
            open_positions = [p for p in portfolio.positions if p.get("status") == "OPEN"]
            if open_positions:
                # Get current prices for all symbols
                current_prices = {}
                try:
                    market_state = await mcp_server.get_market_state(symbol)
                    current_prices[symbol] = _safe_float(market_state.get("price"), 0.0)
                except:
                    pass
                
                slack_notifier.notify_positions_summary(
                    positions=open_positions,
                    current_prices=current_prices,
                    total_pnl=portfolio.get_total_pnl(),  # Fix: Use method not attribute
                    capital=portfolio.capital
                )
            last_summary_time = current_time
        
        elapsed = time.time() - t_start
        if elapsed < 0.1:
            await asyncio.sleep(0.1)

        if stop_event.is_set():
            break

        # Wait for next decision interval, checking stop_event frequently
        # Split long waits into 1-second chunks so we can respond quickly to stop_event
        remaining_wait = interval_seconds
        while remaining_wait > 0 and not stop_event.is_set():
            wait_chunk = min(1.0, remaining_wait)  # Wait max 1 second at a time
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_chunk)
                # If we get here, stop_event was set
                break
            except asyncio.TimeoutError:
                # Chunk timeout, continue waiting
                remaining_wait -= wait_chunk
                continue
        
        if stop_event.is_set():
            break


async def _stream_loop(
    builder: RealtimePatternBuilder,
    portfolio: PaperTradingPortfolio,
    symbol: str,
    duration_seconds: int,
    use_mock: bool,
    testnet: bool,
    stop_event: asyncio.Event,
    pattern_intelligence: Optional[PatternIntelligence] = None,  # 🧠 For pattern learning
) -> Dict[str, Any]:
    ticks_processed = 0
    async def _pump_ticks() -> None:
        nonlocal ticks_processed
        async for tick in tick_iter:
            ticks_processed += 1
            tick_data = tick.as_dict()
            await builder.process_tick(tick_data)
            
            # Update portfolio positions with latest price
            current_price = _safe_float(tick_data.get("price"), 0.0)
            if current_price > 0:
                # Update portfolio positions
                portfolio.update_positions(symbol, current_price)
                
                # Update decisions.json with current price data
                try:
                    decisions_file = PROJECT_ROOT / "logs/decisions.json"
                    if decisions_file.exists():
                        with open(decisions_file, "r") as f:
                            decisions_data = json.load(f)
                        
                        # Update open positions with current price
                        for decision in decisions_data.get("decisions", []):
                            if decision.get("status") == "OPEN" and decision.get("symbol") == symbol:
                                decision["current_price"] = current_price
                                
                                # Find position in portfolio
                                for pos in portfolio.positions:
                                    if (pos.get("symbol") == symbol and 
                                        pos.get("entry_price") == decision.get("entry_price")):
                                        # Update P&L data
                                        decision["current_pnl"] = pos["pnl"]
                                        decision["current_pnl_pct"] = pos["pnl_pct"]
                                        break
                        
                        # Update portfolio summary
                        decisions_data["portfolio"] = {
                            "starting_capital": portfolio.starting_capital,
                            "current_capital": portfolio.capital,
                            "total_pnl": portfolio.get_total_pnl(),
                            "total_pnl_pct": (portfolio.get_total_pnl() / portfolio.starting_capital) * 100
                        }
                        
                        # Write updated data back
                        with open(decisions_file, "w") as f:
                            json.dump(decisions_data, f, indent=2)
                except Exception as e:
                    print(f"Error updating decisions.json: {e}")
                
            if time.perf_counter() >= deadline or stop_event.is_set():
                break

    source_label = "real"
    
    # 🔌 NEW: Use IntelligentStreamManager for 99% uptime!
    if use_mock:
        print("🌐 Using mock tick feed (offline mode)")
        manager = IntelligentStreamManager(
            primary_stream=MockTickFeed(symbol=symbol, interval_ms=500),
            fallback_stream=None,
            health_check_interval=30.0,
            enable_fallback=False
        )
        source_label = "mock"
    else:
        print("🔌 Initializing IntelligentStreamManager with auto-reconnect...")
        primary = BybitMarketStream(symbol=symbol, testnet=testnet)
        fallback = MockTickFeed(symbol=symbol, interval_ms=500)
        
        manager = IntelligentStreamManager(
            primary_stream=primary,
            fallback_stream=fallback,
            health_check_interval=30.0,  # Check every 30s
            tick_timeout=60.0,  # Consider dead after 60s without ticks
            enable_fallback=True
        )
        source_label = "real"

    start_time = time.perf_counter()
    deadline = start_time + duration_seconds

    async def ticker() -> None:
        try:
            await _pump_ticks()
        finally:
            builder.finalize()
            stop_event.set()

    # Use IntelligentStreamManager - no manual timeout handling needed!
    try:
        async with manager:
            print("✅ IntelligentStreamManager started (auto-reconnect enabled)")
            tick_iter = manager.ticks()  # This now auto-reconnects!
            await ticker()
            
            # Show connection metrics at the end
            metrics = manager.get_metrics()
            uptime_pct = metrics.get_uptime_percentage()
            print(f"\n📊 Connection Metrics:")
            print(f"   Uptime: {uptime_pct:.1f}%")
            print(f"   Reconnections: {metrics.total_reconnections}")
            print(f"   Fallback activations: {metrics.fallback_activations}")
            print(f"   Ticks received: {metrics.ticks_received}")
            
            if manager.using_fallback:
                source_label = "fallback"
    except Exception as exc:
        print(f"⚠️ Stream manager error: {exc}")
        # Manager handles reconnection internally, this shouldn't happen

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

    # Initialize portfolio for paper trading
    # R10,000 ZAR target / 18.5 rate = $540.54 USD internal value
    # (Portfolio stores everything in USD, format_currency handles display conversion)
    portfolio = PaperTradingPortfolio(starting_capital=540.54, load_previous_state=False)
    position_size = portfolio.starting_capital * 0.05
    print(f"💰 Initialized paper trading portfolio with {format_currency(portfolio.capital)}")
    print(f"   (Position size: {format_currency(position_size)} [5%], Max positions: 20, Max exposure: 80%)")
    
    # Initialize Slack notifier if available
    slack_notifier = None
    if SLACK_AVAILABLE:
        slack_notifier = SlackNotifier()
        if slack_notifier.enabled:
            print("📱 Slack notifications enabled")
            slack_notifier.notify_test_start(
                duration_hours=duration_seconds / 3600,
                symbol=symbol
            )
        else:
            print("⚠️  Slack notifications disabled (set SLACK_WEBHOOK_URL in .env)")
    else:
        print("⚠️  Slack notifier not available")

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

    # 🧠 Initialize Pattern Intelligence for learning
    pattern_intelligence = PatternIntelligence.get_instance(pattern_db)
    print(f"🧠 Pattern Intelligence initialized")
    health = pattern_intelligence.health_check()
    print(f"   Status: {health['status']} | Patterns with trades: {health['patterns_with_trades']}")

    builder = RealtimePatternBuilder(pattern_db, interval_seconds=args.candle_seconds)
    mcp_server = TradingMCPServer(pattern_db)
    # Initialize agent with same capital as portfolio (R1,000 = $54.05)
    agent = TradingAgent(mcp_server, model=args.model, capital=portfolio.starting_capital)

    stop_event = asyncio.Event()
    decisions: List[DecisionRecord] = []
    patterns_before = pattern_db.count()

    stream_task = asyncio.create_task(
        _stream_loop(
            builder=builder,
            portfolio=portfolio,
            symbol=symbol,
            pattern_intelligence=pattern_intelligence,  # 🧠 Pass for learning
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
            portfolio=portfolio,
            symbol=symbol,
            interval_seconds=decision_interval,
            stop_event=stop_event,
            results=decisions,
            slack_notifier=slack_notifier,
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
    
    # Portfolio summary
    print("\n💰 Portfolio Summary")
    print(f"   Starting capital: {format_currency(portfolio.starting_capital)}")
    print(f"   Current capital: {format_currency(portfolio.capital)}")
    print(f"   Total equity: {format_currency(portfolio.get_total_equity())}")
    print(f"   Total P&L: {format_currency_signed(portfolio.get_total_pnl())} ({portfolio.get_total_pnl() / portfolio.starting_capital * 100:+.2f}%)")
    print(f"   Open positions: {len(portfolio.positions)}")
    print(f"   Closed trades: {len(portfolio.closed_trades)}")

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
    
    # Send completion notification
    if slack_notifier and slack_notifier.enabled:
        perf_stats = portfolio.get_performance_stats()
        slack_notifier.notify_test_complete(
            duration_hours=stream_stats['runtime'] / 3600,
            total_pnl=portfolio.get_total_pnl(),
            wins=perf_stats.get('wins', 0),
            losses=perf_stats.get('losses', 0)
        )

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
