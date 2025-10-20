#!/usr/bin/env python3
"""
Production Learning Backtest - 60 Days

Tests if the learning system actually makes the bot smarter over time.

This will:
1. Fetch 2 months of real historical data
2. Simulate trading through it sequentially
3. Let the bot learn from outcomes in real-time
4. Show if system improves or not

Usage:
    python3 scripts/production_backtest.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging first
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Now import our modules
from mcp.trading_server import TradingMCPServer
from scripts.track_trade_outcomes import TradeOutcomeTracker
from scripts.learning_engine import LearningEngine


class ProductionBacktest:
    """
    Real backtest using actual system components.
    
    This answers: "Is the system actually as smart as we thought?"
    """
    
    def __init__(self, symbol: str = "BTCUSDT", days: int = 60):
        """Initialize backtest with real components"""
        self.symbol = symbol
        self.days = days
        self.interval_minutes = 240  # 4-hour candles for swing trading
        
        # Real components
        self.mcp_server = TradingMCPServer()
        self.tracker = TradeOutcomeTracker()
        self.engine = LearningEngine()
        
        # Backtest state
        self.historical_data = []
        self.positions = {}  # Open positions
        self.closed_trades = []
        self.balance = 10000.0
        self.starting_balance = 10000.0
        
        # Performance tracking
        self.trades_by_period = []  # Split into 10-day periods
        self.learning_events = []
        
        logger.info("🎮 Production Backtest Initialized")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Period: {days} days")
        logger.info(f"   Starting Balance: ${self.balance:,.2f}")
    
    async def load_historical_data(self):
        """Fetch historical candles from MCP server"""
        logger.info(f"\n📊 Loading {self.days} days of historical data...")
        
        try:
            # Use MCP server to fetch historical data
            # This matches how the real system works
            end_time = datetime.now()
            start_time = end_time - timedelta(days=self.days)
            
            logger.info(f"   From: {start_time.strftime('%Y-%m-%d')}")
            logger.info(f"   To: {end_time.strftime('%Y-%m-%d')}")
            logger.info(f"   Fetching...")
            
            # Fetch in chunks (API limits)
            all_candles = []
            chunk_size = 2  # Days per chunk
            current_end = end_time
            
            while (current_end - start_time).days > 0:
                chunk_start = max(start_time, current_end - timedelta(days=chunk_size))
                
                # Fetch chunk
                candles = await self._fetch_chunk(chunk_start, current_end)
                if candles:
                    all_candles = candles + all_candles
                
                days_loaded = (end_time - chunk_start).days
                logger.info(f"   Progress: {days_loaded}/{self.days} days ({len(all_candles)} candles)")
                
                current_end = chunk_start
                
                if current_end <= start_time:
                    break
            
            self.historical_data = all_candles
            
            if self.historical_data:
                logger.info(f"✅ Loaded {len(self.historical_data)} candles")
                logger.info(f"   First: {self.historical_data[0].get('timestamp', 'unknown')}")
                logger.info(f"   Last: {self.historical_data[-1].get('timestamp', 'unknown')}")
                return True
            else:
                logger.error("❌ No data loaded")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to load data: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _fetch_chunk(self, start: datetime, end: datetime) -> List[Dict]:
        """Fetch a chunk of historical data"""
        try:
            # Use the stream module which has data fetching
            from stream.bybit_websocket import BybitWebSocket
            
            ws = BybitWebSocket()
            
            # Fetch klines
            start_ts = int(start.timestamp() * 1000)
            end_ts = int(end.timestamp() * 1000)
            
            candles = []
            
            # Bybit kline endpoint
            import requests
            url = "https://api.bybit.com/v5/market/kline"
            params = {
                "category": "spot",
                "symbol": self.symbol,
                "interval": str(self.interval_minutes),
                "start": start_ts,
                "end": end_ts,
                "limit": 200
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("retCode") == 0:
                    klines = data.get("result", {}).get("list", [])
                    
                    for k in klines:
                        candles.append({
                            "timestamp": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "datetime": datetime.fromtimestamp(int(k[0])/1000).strftime("%Y-%m-%d %H:%M:%S")
                        })
                    
                    # Reverse for chronological order
                    candles.reverse()
            
            return candles
            
        except Exception as e:
            logger.warning(f"⚠️  Chunk fetch error: {e}")
            return []
    
    async def run(self):
        """Main backtest execution"""
        
        if not self.historical_data:
            logger.error("❌ No data to backtest. Call load_historical_data() first.")
            return
        
        logger.info("\n" + "=" * 70)
        logger.info("🚀 STARTING PRODUCTION BACKTEST")
        logger.info("=" * 70)
        logger.info(f"📊 Processing {len(self.historical_data)} candles...")
        logger.info(f"💰 Starting Balance: ${self.balance:,.2f}")
        logger.info("")
        
        # Initialize learning multipliers
        initial_multipliers = self._get_current_multipliers()
        logger.info("📚 Initial Learning Multipliers:")
        for pattern, mult in list(initial_multipliers.items())[:5]:
            logger.info(f"   {pattern}: {mult:.3f}")
        logger.info("")
        
        # Process candles
        total = len(self.historical_data)
        report_interval = max(100, total // 20)  # Report ~20 times
        
        for i, candle in enumerate(self.historical_data):
            # Progress
            if i % report_interval == 0 and i > 0:
                pct = (i / total) * 100
                win_rate = self._calculate_win_rate()
                logger.info(f"   [{i:,}/{total:,}] {pct:.1f}% | Trades: {len(self.closed_trades)} | "
                          f"Balance: ${self.balance:,.0f} | Win Rate: {win_rate:.1f}%")
            
            # Check/close existing positions
            await self._check_positions(i, candle)
            
            # Make new decision if room
            if len(self.positions) < 3:  # Max 3 concurrent
                await self._make_decision(i, candle)
        
        # Close remaining positions
        await self._close_all_positions(len(self.historical_data) - 1)
        
        # Generate report
        await self._generate_report(initial_multipliers)
    
    async def _make_decision(self, candle_index: int, candle: Dict):
        """Simulate a trading decision"""
        try:
            # Build market state from candle
            lookback = 100
            start_idx = max(0, candle_index - lookback)
            history = self.historical_data[start_idx:candle_index + 1]
            
            if len(history) < 20:
                return  # Not enough data
            
            # Create market state
            market_state = {
                "symbol": self.symbol,
                "price": candle["close"],
                "timestamp": candle.get("timestamp"),
                "candles": history
            }
            
            # Get similar patterns from vector DB
            try:
                patterns = await self.mcp_server.get_similar_patterns(market_state, top_k=10)
            except:
                patterns = {"count": 0, "win_rate": None}
            
            # Simple decision logic (can enhance with AI later)
            # For now, use pattern matching
            from intelligence.pattern_library import find_matching_patterns
            
            cheat_matches = find_matching_patterns(market_state)
            
            if cheat_matches and len(cheat_matches) > 0:
                pattern = cheat_matches[0]
                
                # Get learning multiplier
                multipliers = self._get_current_multipliers()
                confidence_mult = multipliers.get(pattern.name, 1.0)
                
                # Calculate confidence
                base_confidence = pattern.confidence
                adjusted_confidence = base_confidence * confidence_mult
                
                # Only trade if confidence high enough
                if adjusted_confidence >= 60.0:
                    # Open position
                    decision = {
                        "action": "buy",  # Simplified
                        "detected_pattern": pattern.name,
                        "confidence": adjusted_confidence,
                        "reasoning": f"Pattern: {pattern.name}",
                    }
                    
                    await self._open_position(candle_index, decision, candle)
        
        except Exception as e:
            logger.debug(f"Decision error at {candle_index}: {e}")
    
    async def _open_position(self, candle_index: int, decision: Dict, candle: Dict):
        """Open a trading position"""
        entry_price = candle["close"]
        
        # Position sizing (2% risk)
        risk_amount = self.balance * 0.02
        stop_distance = entry_price * 0.02  # 2% stop loss
        position_size = risk_amount / stop_distance
        
        # Calculate levels
        stop_loss = entry_price * 0.98  # 2% below
        take_profit = entry_price * 1.04  # 4% above (2:1 RR)
        
        position = {
            "id": f"pos_{candle_index}",
            "entry_candle": candle_index,
            "entry_time": candle.get("datetime"),
            "entry_price": entry_price,
            "size": position_size,
            "decision": decision,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "max_hold_candles": 96  # 24 hours for 15m candles
        }
        
        self.positions[position["id"]] = position
        
        logger.debug(f"📈 Position: {decision.get('detected_pattern')} @ ${entry_price:,.2f} "
                    f"(conf: {decision.get('confidence', 0):.1f}%)")
    
    async def _check_positions(self, candle_index: int, candle: Dict):
        """Check if positions should close"""
        for pos_id in list(self.positions.keys()):
            position = self.positions[pos_id]
            
            outcome = self._should_close(position, candle_index, candle)
            
            if outcome:
                await self._close_position(position, outcome, candle_index)
                del self.positions[pos_id]
    
    def _should_close(self, position: Dict, candle_index: int, candle: Dict) -> Optional[Dict]:
        """Check if position should close"""
        current_price = candle["close"]
        entry_price = position["entry_price"]
        
        # Calculate P&L
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        pnl_dollars = (pnl_pct / 100) * (position["size"] * entry_price)
        
        # Check exits
        exit_reason = None
        
        # Stop loss
        if current_price <= position["stop_loss"]:
            exit_reason = "stop_loss"
        
        # Take profit
        elif current_price >= position["take_profit"]:
            exit_reason = "take_profit"
        
        # Timeout
        elif (candle_index - position["entry_candle"]) >= position["max_hold_candles"]:
            exit_reason = "timeout"
        
        if exit_reason:
            return {
                "exit_candle": candle_index,
                "exit_time": candle.get("datetime"),
                "exit_price": current_price,
                "exit_reason": exit_reason,
                "pnl_pct": pnl_pct,
                "pnl_dollars": pnl_dollars,
                "candles_held": candle_index - position["entry_candle"]
            }
        
        return None
    
    async def _close_position(self, position: Dict, outcome: Dict, candle_index: int):
        """Close position and learn from outcome"""
        decision = position["decision"]
        pnl = outcome["pnl_dollars"]
        
        # Update balance
        self.balance += pnl
        
        # Track trade
        is_win = pnl > 0
        self.closed_trades.append({
            "candle_index": candle_index,
            "time": outcome["exit_time"],
            "pattern": decision.get("detected_pattern"),
            "pnl": pnl,
            "pnl_pct": outcome["pnl_pct"],
            "win": is_win,
            "exit_reason": outcome["exit_reason"],
            "balance_after": self.balance
        })
        
        # LEARNING HAPPENS HERE
        try:
            # Capture before state
            before_mults = self._get_current_multipliers()
            pattern = decision.get("detected_pattern")
            before_mult = before_mults.get(pattern, 1.0)
            
            # Feed to learning system
            self.tracker.track_outcome(
                decision=decision,
                actual_outcome=pnl,
                confidence=decision.get("confidence", 50.0)
            )
            
            # Update multipliers
            self.engine.update_multipliers()
            
            # Check if changed
            after_mults = self._get_current_multipliers()
            after_mult = after_mults.get(pattern, 1.0)
            
            if abs(after_mult - before_mult) > 0.01:
                self.learning_events.append({
                    "candle_index": candle_index,
                    "pattern": pattern,
                    "before": before_mult,
                    "after": after_mult,
                    "change": after_mult - before_mult,
                    "outcome": "WIN" if is_win else "LOSS"
                })
                
                logger.info(f"   📚 LEARNED! {pattern}: {before_mult:.3f} → {after_mult:.3f} "
                          f"({'✅' if is_win else '❌'} {pnl:+.0f})")
        
        except Exception as e:
            logger.warning(f"Learning error: {e}")
        
        # Log result
        symbol = "✅" if is_win else "❌"
        logger.debug(f"   {symbol} {outcome['exit_reason']}: {pnl:+.2f} ({outcome['pnl_pct']:+.2f}%) "
                    f"| Balance: ${self.balance:,.0f}")
    
    async def _close_all_positions(self, final_candle_index: int):
        """Close remaining positions at end"""
        if not self.positions:
            return
        
        logger.info(f"\n🔚 Closing {len(self.positions)} remaining positions...")
        
        final_candle = self.historical_data[final_candle_index]
        
        for pos_id in list(self.positions.keys()):
            position = self.positions[pos_id]
            
            outcome = {
                "exit_candle": final_candle_index,
                "exit_time": final_candle.get("datetime"),
                "exit_price": final_candle["close"],
                "exit_reason": "end_of_backtest",
                "pnl_pct": ((final_candle["close"] - position["entry_price"]) / position["entry_price"]) * 100,
                "pnl_dollars": 0,  # Simplified
                "candles_held": final_candle_index - position["entry_candle"]
            }
            
            await self._close_position(position, outcome, final_candle_index)
    
    def _get_current_multipliers(self) -> Dict[str, float]:
        """Get current learning multipliers"""
        try:
            mult_file = Path("data/learning/confidence_multipliers.json")
            if mult_file.exists():
                with open(mult_file) as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def _calculate_win_rate(self) -> float:
        """Calculate current win rate"""
        if not self.closed_trades:
            return 0.0
        wins = sum(1 for t in self.closed_trades if t["win"])
        return (wins / len(self.closed_trades)) * 100
    
    async def _generate_report(self, initial_multipliers: Dict):
        """Generate comprehensive results"""
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ BACKTEST COMPLETE - THE MOMENT OF TRUTH!")
        logger.info("=" * 70)
        
        # Performance
        total_return = ((self.balance - self.starting_balance) / self.starting_balance) * 100
        wins = sum(1 for t in self.closed_trades if t["win"])
        losses = len(self.closed_trades) - wins
        win_rate = (wins / len(self.closed_trades) * 100) if self.closed_trades else 0
        
        logger.info("\n📊 OVERALL PERFORMANCE:")
        logger.info(f"   Starting Balance: ${self.starting_balance:,.2f}")
        logger.info(f"   Final Balance: ${self.balance:,.2f}")
        logger.info(f"   Total Return: {total_return:+.2f}%")
        logger.info(f"   Total Trades: {len(self.closed_trades)}")
        logger.info(f"   Wins: {wins} | Losses: {losses}")
        logger.info(f"   Win Rate: {win_rate:.1f}%")
        
        # Learning progression
        if self.learning_events:
            logger.info(f"\n📚 LEARNING EVENTS: {len(self.learning_events)}")
            logger.info("   Top Pattern Changes:")
            
            # Aggregate by pattern
            pattern_changes = {}
            for event in self.learning_events:
                p = event["pattern"]
                if p not in pattern_changes:
                    pattern_changes[p] = {
                        "initial": initial_multipliers.get(p, 1.0),
                        "final": event["after"],
                        "events": 0
                    }
                pattern_changes[p]["final"] = event["after"]
                pattern_changes[p]["events"] += 1
            
            for pattern, data in sorted(pattern_changes.items(), 
                                       key=lambda x: abs(x[1]["final"] - x[1]["initial"]), 
                                       reverse=True)[:10]:
                change = data["final"] - data["initial"]
                logger.info(f"   • {pattern:25} {data['initial']:.3f} → {data['final']:.3f} "
                          f"(Δ{change:+.3f}) | {data['events']} updates")
        
        # Answer the key question
        logger.info("\n" + "=" * 70)
        logger.info("🎯 THE ANSWER: IS THE SYSTEM ACTUALLY SMART?")
        logger.info("=" * 70)
        
        if win_rate >= 60:
            logger.info("✅ YES! Win rate 60%+. System shows intelligence.")
        elif win_rate >= 50:
            logger.info("⚠️  MAYBE. Win rate 50-60%. Better than random but needs work.")
        else:
            logger.info("❌ NO. Win rate <50%. System needs significant improvement.")
        
        if len(self.learning_events) >= 5:
            logger.info("✅ YES! System learned and adapted patterns.")
        else:
            logger.info("⚠️  Limited learning events. May need more data or tuning.")
        
        logger.info("=" * 70)
        
        # Save report
        report_file = Path(f"data/backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w') as f:
            json.dump({
                "config": {
                    "symbol": self.symbol,
                    "days": self.days,
                    "candles": len(self.historical_data)
                },
                "performance": {
                    "starting_balance": self.starting_balance,
                    "final_balance": self.balance,
                    "total_return_pct": total_return,
                    "total_trades": len(self.closed_trades),
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate
                },
                "learning_events": self.learning_events,
                "trades": self.closed_trades
            }, f, indent=2)
        
        logger.info(f"\n📄 Full report saved: {report_file}")
        logger.info("")


async def main():
    """Entry point"""
    logger.info("=" * 70)
    logger.info("🎮 PRODUCTION BACKTEST - 60 DAYS")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Testing: Is the learning system actually as smart as we thought?")
    logger.info("")
    
    backtest = ProductionBacktest(symbol="BTCUSDT", days=60)
    
    # Load data
    success = await backtest.load_historical_data()
    
    if success:
        # Run backtest
        await backtest.run()
    else:
        logger.error("❌ Could not load data. Check connection.")


if __name__ == "__main__":
    asyncio.run(main())
