#!/usr/bin/env python3
"""
Standalone Learning Backtest - 60 Days

NO DEPENDENCIES VERSION - Tests the core learning concept

This will tell us: "Is the system actually as smart as we thought?"

Usage:
    python3 scripts/standalone_backtest.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

print("=" * 70)
print("🎮 STANDALONE LEARNING BACKTEST - 60 DAYS")
print("=" * 70)
print()
print("Testing: Does the bot actually get smarter from learning?")
print()

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only what we absolutely need
try:
    # Disable ChromaDB check temporarily
    import os
    os.environ['SKIP_CHROMADB_CHECK'] = '1'
    
    from scripts.track_trade_outcomes import TradeOutcomeTracker
    from scripts.learning_engine import LearningEngine
    LEARNING_AVAILABLE = True
    print("✅ Learning system modules loaded")
except Exception as e:
    print(f"⚠️  Learning modules not available: {e}")
    LEARNING_AVAILABLE = False

print()


class StandaloneBacktest:
    """Minimal backtest to test learning"""
    
    def __init__(self, symbol="BTCUSDT", days=60):
        self.symbol = symbol
        self.days = days
        self.balance = 10000.0
        self.starting_balance = 10000.0
        
        # Learning system
        if LEARNING_AVAILABLE:
            self.tracker = TradeOutcomeTracker()
            self.engine = LearningEngine()
        
        # State
        self.trades = []
        self.learning_events = []
        self.multipliers_history = []
        
    def fetch_historical_data(self) -> List[Dict]:
        """Fetch real historical data"""
        print(f"📊 Fetching {self.days} days of historical data...")
        
        try:
            import requests
            
            all_candles = []
            end_time = datetime.now()
            
            # Fetch in chunks
            for chunk in range(self.days // 2):  # 2 days per chunk
                chunk_end = end_time - timedelta(days=chunk * 2)
                chunk_start = chunk_end - timedelta(days=2)
                
                start_ts = int(chunk_start.timestamp() * 1000)
                end_ts = int(chunk_end.timestamp() * 1000)
                
                url = "https://api.bybit.com/v5/market/kline"
                params = {
                    "category": "spot",
                    "symbol": self.symbol,
                    "interval": "15",
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
                            all_candles.append({
                                "timestamp": int(k[0]),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                                "time": datetime.fromtimestamp(int(k[0])/1000).strftime("%Y-%m-%d %H:%M:%S")
                            })
                
                # Progress
                days_so_far = (chunk + 1) * 2
                print(f"   Loaded: {days_so_far}/{self.days} days ({len(all_candles)} candles)")
            
            # Sort chronologically
            all_candles.sort(key=lambda x: x["timestamp"])
            
            print(f"✅ Got {len(all_candles)} candles from {all_candles[0]['time']} to {all_candles[-1]['time']}")
            
            return all_candles
            
        except Exception as e:
            print(f"❌ Failed to fetch data: {e}")
            return []
    
    def run(self, candles: List[Dict]):
        """Run the backtest"""
        
        if not candles:
            print("❌ No data to backtest")
            return
        
        print()
        print("=" * 70)
        print("🚀 STARTING BACKTEST")
        print("=" * 70)
        print(f"📊 Processing {len(candles)} candles...")
        print(f"💰 Starting Balance: ${self.balance:,.2f}")
        print()
        
        # Get initial multipliers
        initial_mults = self._get_multipliers()
        print("📚 Initial Multipliers (top 5):")
        for pattern, mult in list(initial_mults.items())[:5]:
            print(f"   {pattern}: {mult:.3f}")
        print()
        
        # Simulate trading
        positions = {}
        report_every = len(candles) // 20  # 20 progress updates
        
        for i, candle in enumerate(candles):
            # Progress
            if i % report_every == 0 and i > 0:
                pct = (i / len(candles)) * 100
                win_rate = self._win_rate()
                print(f"   [{i:,}/{len(candles):,}] {pct:.0f}% | Trades: {len(self.trades)} | "
                      f"Balance: ${self.balance:,.0f} | Win Rate: {win_rate:.1f}%")
            
            # Close positions if SL/TP hit
            for pos_id in list(positions.keys()):
                pos = positions[pos_id]
                
                # Check if should close
                if candle["low"] <= pos["stop_loss"]:
                    # Stop loss hit
                    pnl = (pos["stop_loss"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self._close_trade(pos, pnl, "stop_loss", i)
                    del positions[pos_id]
                
                elif candle["high"] >= pos["take_profit"]:
                    # Take profit hit
                    pnl = (pos["take_profit"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self._close_trade(pos, pnl, "take_profit", i)
                    del positions[pos_id]
                
                elif (i - pos["entry_candle"]) > 96:  # 24 hours timeout
                    # Timeout
                    pnl = (candle["close"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self._close_trade(pos, pnl, "timeout", i)
                    del positions[pos_id]
            
            # Simple pattern detection (simulated)
            # In real version, this would use PatternIntelligence
            if len(positions) < 3 and i % 20 == 0:  # Try every 20 candles
                pattern = self._detect_pattern(candle, candles[max(0,i-50):i])
                
                if pattern:
                    # Get learning multiplier
                    mults = self._get_multipliers()
                    confidence_mult = mults.get(pattern, 1.0)
                    
                    base_conf = 65.0
                    adjusted_conf = base_conf * confidence_mult
                    
                    # Trade if confident enough
                    if adjusted_conf >= 60.0:
                        # Open position
                        entry_price = candle["close"]
                        position_size = self.balance * 0.02  # 2% risk
                        
                        pos = {
                            "id": f"pos_{i}",
                            "entry_candle": i,
                            "entry": entry_price,
                            "size": position_size,
                            "pattern": pattern,
                            "confidence": adjusted_conf,
                            "stop_loss": entry_price * 0.98,  # 2% SL
                            "take_profit": entry_price * 1.04  # 4% TP (2:1 RR)
                        }
                        
                        positions[pos["id"]] = pos
        
        # Close remaining
        for pos in positions.values():
            pnl = (candles[-1]["close"] - pos["entry"]) / pos["entry"] * pos["size"]
            self._close_trade(pos, pnl, "end", len(candles)-1)
        
        # Results
        self._show_results(initial_mults)
    
    def _detect_pattern(self, candle: Dict, history: List[Dict]) -> Optional[str]:
        """Simple pattern detection (simulated)"""
        if not history or len(history) < 5:
            return None
        
        # Simplified pattern detection
        recent = history[-5:]
        
        # Bullish engulfing
        if (candle["close"] > candle["open"] and 
            recent[-1]["close"] < recent[-1]["open"] and
            candle["close"] > recent[-1]["open"]):
            return "bullish_engulfing"
        
        # Hammer
        body = abs(candle["close"] - candle["open"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        if lower_wick > body * 2 and candle["close"] > candle["open"]:
            return "hammer"
        
        # Morning star (3 candles)
        if len(recent) >= 3:
            c1, c2, c3 = recent[-3], recent[-2], recent[-1]
            if (c1["close"] < c1["open"] and  # Down candle
                abs(c2["close"] - c2["open"]) < body and  # Doji
                c3["close"] > c3["open"]):  # Up candle
                return "morning_star"
        
        return None
    
    def _close_trade(self, pos: Dict, pnl: float, reason: str, candle_idx: int):
        """Close trade and learn"""
        self.balance += pnl
        is_win = pnl > 0
        
        trade = {
            "candle": candle_idx,
            "pattern": pos["pattern"],
            "pnl": pnl,
            "win": is_win,
            "reason": reason,
            "balance": self.balance
        }
        
        self.trades.append(trade)
        
        # LEARNING
        if LEARNING_AVAILABLE:
            try:
                # Before state
                before_mults = self._get_multipliers()
                before = before_mults.get(pos["pattern"], 1.0)
                
                # Learn
                decision = {
                    "action": "buy",
                    "detected_pattern": pos["pattern"],
                    "confidence": pos["confidence"],
                    "reasoning": f"Pattern: {pos['pattern']}"
                }
                
                self.tracker.track_outcome(
                    decision=decision,
                    actual_outcome=pnl,
                    confidence=pos["confidence"]
                )
                
                self.engine.update_multipliers()
                
                # After state
                after_mults = self._get_multipliers()
                after = after_mults.get(pos["pattern"], 1.0)
                
                # Track if changed
                if abs(after - before) > 0.01:
                    self.learning_events.append({
                        "candle": candle_idx,
                        "pattern": pos["pattern"],
                        "before": before,
                        "after": after,
                        "change": after - before,
                        "outcome": "WIN" if is_win else "LOSS"
                    })
                    
                    print(f"   📚 LEARNED! {pos['pattern']}: {before:.3f} → {after:.3f} "
                          f"({'✅' if is_win else '❌'})")
            
            except Exception as e:
                print(f"   ⚠️  Learning error: {e}")
    
    def _get_multipliers(self) -> Dict[str, float]:
        """Get current multipliers"""
        try:
            mult_file = Path("data/learning/confidence_multipliers.json")
            if mult_file.exists():
                with open(mult_file) as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def _win_rate(self) -> float:
        """Calculate win rate"""
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t["win"])
        return (wins / len(self.trades)) * 100
    
    def _show_results(self, initial_mults: Dict):
        """Show final results"""
        
        print()
        print("=" * 70)
        print("✅ BACKTEST COMPLETE - THE VERDICT")
        print("=" * 70)
        
        # Performance
        total_return = ((self.balance - self.starting_balance) / self.starting_balance) * 100
        wins = sum(1 for t in self.trades if t["win"])
        losses = len(self.trades) - wins
        win_rate = self._win_rate()
        
        print()
        print("📊 PERFORMANCE:")
        print(f"   Starting: ${self.starting_balance:,.2f}")
        print(f"   Final: ${self.balance:,.2f}")
        print(f"   Return: {total_return:+.2f}%")
        print(f"   Trades: {len(self.trades)} (W: {wins}, L: {losses})")
        print(f"   Win Rate: {win_rate:.1f}%")
        
        # Learning
        if self.learning_events:
            print()
            print(f"📚 LEARNING: {len(self.learning_events)} events")
            
            # Aggregate
            pattern_changes = {}
            for event in self.learning_events:
                p = event["pattern"]
                if p not in pattern_changes:
                    pattern_changes[p] = {
                        "initial": initial_mults.get(p, 1.0),
                        "final": event["after"],
                        "count": 0
                    }
                pattern_changes[p]["final"] = event["after"]
                pattern_changes[p]["count"] += 1
            
            print("   Pattern Evolution:")
            for pattern, data in sorted(pattern_changes.items(),
                                       key=lambda x: abs(x[1]["final"] - x[1]["initial"]),
                                       reverse=True):
                change = data["final"] - data["initial"]
                print(f"   • {pattern:20} {data['initial']:.3f} → {data['final']:.3f} "
                      f"(Δ{change:+.3f}) [{data['count']} updates]")
        
        # THE ANSWER
        print()
        print("=" * 70)
        print("🎯 IS THE SYSTEM ACTUALLY SMART?")
        print("=" * 70)
        
        if win_rate >= 60:
            print("✅ YES! Win rate 60%+. System demonstrates intelligence.")
        elif win_rate >= 50:
            print("⚠️  MAYBE. Win rate 50-60%. Better than random, needs tuning.")
        else:
            print("❌ NOT YET. Win rate <50%. Needs significant work.")
        
        if len(self.learning_events) >= 5:
            print("✅ YES! System learned and adapted ({} events).".format(len(self.learning_events)))
        else:
            print("⚠️  Limited learning. Only {} events.".format(len(self.learning_events)))
        
        if total_return > 0:
            print(f"✅ PROFITABLE! Made {total_return:+.2f}% in backtest.")
        else:
            print(f"❌ UNPROFITABLE. Lost {total_return:.2f}%.")
        
        print("=" * 70)
        print()


def main():
    """Run it"""
    backtest = StandaloneBacktest(symbol="BTCUSDT", days=60)
    
    # Fetch data
    candles = backtest.fetch_historical_data()
    
    if candles:
        # Run backtest
        backtest.run(candles)
    else:
        print("❌ No data available")


if __name__ == "__main__":
    main()
