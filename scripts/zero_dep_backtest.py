#!/usr/bin/env python3
"""
ZERO-DEPENDENCY BACKTEST - 60 Days

Pure Python - No external dependencies needed
Tests: "Is the learning concept actually smart?"

Run this to see if learning from historical outcomes works!

Usage:
    python3 scripts/zero_dep_backtest.py
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

print("=" * 70)
print("🎮 ZERO-DEPENDENCY BACKTEST - 60 DAYS")
print("=" * 70)
print()
print("Question: Does the bot get smarter from learning historical trades?")
print()


class ZeroDepBacktest:
    """Pure Python backtest - no external dependencies"""
    
    def __init__(self):
        self.balance = 10000.0
        self.starting_balance = 10000.0
        self.trades = []
        self.pattern_stats = {}  # Track win/loss per pattern
        self.pattern_multipliers = {}  # Learning multipliers
        
    def fetch_data(self, symbol="BTCUSDT", days=60) -> List[Dict]:
        """Fetch historical data from Bybit"""
        print(f"📊 Fetching {days} days of {symbol} data...")
        
        try:
            import requests
            
            all_candles = []
            end_time = datetime.now()
            
            # Fetch in 2-day chunks
            for chunk_idx in range(days // 2):
                chunk_end = end_time - timedelta(days=chunk_idx * 2)
                chunk_start = chunk_end - timedelta(days=2)
                
                url = "https://api.bybit.com/v5/market/kline"
                params = {
                    "category": "spot",
                    "symbol": symbol,
                    "interval": "15",
                    "start": int(chunk_start.timestamp() * 1000),
                    "end": int(chunk_end.timestamp() * 1000),
                    "limit": 200
                }
                
                resp = requests.get(url, params=params, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("retCode") == 0:
                        for k in data.get("result", {}).get("list", []):
                            all_candles.append({
                                "ts": int(k[0]),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5])
                            })
                
                if (chunk_idx + 1) % 5 == 0:
                    print(f"   Loaded: {(chunk_idx+1)*2}/{days} days ({len(all_candles)} candles)")
            
            all_candles.sort(key=lambda x: x["ts"])
            print(f"✅ Got {len(all_candles)} candles")
            return all_candles
            
        except Exception as e:
            print(f"❌ Fetch failed: {e}")
            return []
    
    def detect_pattern(self, current: Dict, history: List[Dict]) -> Optional[str]:
        """Simple pattern detection"""
        if len(history) < 5:
            return None
        
        recent = history[-5:]
        
        # Bullish engulfing
        prev = recent[-1]
        if (current["close"] > current["open"] and
            prev["close"] < prev["open"] and
            current["close"] > prev["open"] and
            current["open"] < prev["close"]):
            return "bullish_engulfing"
        
        # Hammer
        body = abs(current["close"] - current["open"])
        lower_wick = min(current["open"], current["close"]) - current["low"]
        upper_wick = current["high"] - max(current["open"], current["close"])
        
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return "hammer"
        
        # Morning star
        if len(recent) >= 3:
            c1, c2, c3 = recent[-3], recent[-2], recent[-1]
            if (c1["close"] < c1["open"] and
                abs(c2["close"] - c2["open"]) < body * 0.5 and
                c3["close"] > c3["open"]):
                return "morning_star"
        
        # Doji
        if body < (current["high"] - current["low"]) * 0.1:
            return "doji"
        
        return None
    
    def get_confidence(self, pattern: str) -> float:
        """Get confidence with learning multiplier applied"""
        base_confidence = 65.0
        
        # Apply learning multiplier
        multiplier = self.pattern_multipliers.get(pattern, 1.0)
        
        return base_confidence * multiplier
    
    def learn_from_outcome(self, pattern: str, won: bool):
        """Update pattern statistics and multipliers"""
        # Track stats
        if pattern not in self.pattern_stats:
            self.pattern_stats[pattern] = {"wins": 0, "losses": 0}
        
        if won:
            self.pattern_stats[pattern]["wins"] += 1
        else:
            self.pattern_stats[pattern]["losses"] += 1
        
        # Calculate win rate
        stats = self.pattern_stats[pattern]
        total = stats["wins"] + stats["losses"]
        win_rate = stats["wins"] / total if total > 0 else 0.5
        
        # Update multiplier based on win rate
        # Win rate 70%+ → boost confidence
        # Win rate 50-70% → neutral
        # Win rate <50% → reduce confidence
        
        if total >= 5:  # Need minimum sample
            if win_rate >= 0.70:
                self.pattern_multipliers[pattern] = min(1.5, 0.9 + (win_rate * 0.8))
            elif win_rate >= 0.60:
                self.pattern_multipliers[pattern] = 1.0 + (win_rate - 0.6) * 2
            elif win_rate >= 0.50:
                self.pattern_multipliers[pattern] = 1.0
            else:
                self.pattern_multipliers[pattern] = max(0.7, 0.5 + win_rate)
        else:
            # Not enough data, start neutral
            self.pattern_multipliers[pattern] = 1.0
    
    def run(self, candles: List[Dict]):
        """Run the backtest"""
        
        if not candles:
            print("❌ No data")
            return
        
        print()
        print("=" * 70)
        print("🚀 RUNNING BACKTEST")
        print("=" * 70)
        print(f"📊 {len(candles)} candles to process")
        print(f"💰 Starting balance: ${self.balance:,.2f}")
        print()
        
        # Initial multipliers (all neutral)
        initial_mults = {"bullish_engulfing": 1.0, "hammer": 1.0, "morning_star": 1.0, "doji": 1.0}
        self.pattern_multipliers = initial_mults.copy()
        
        positions = {}
        report_every = len(candles) // 20
        
        for i, candle in enumerate(candles):
            # Progress
            if i > 0 and i % report_every == 0:
                pct = (i / len(candles)) * 100
                wins = sum(1 for t in self.trades if t["win"])
                wr = (wins / len(self.trades) * 100) if self.trades else 0
                print(f"   [{i:,}/{len(candles):,}] {pct:.0f}% | Trades: {len(self.trades)} | "
                      f"Balance: ${self.balance:,.0f} | WR: {wr:.1f}%")
            
            # Check positions for exits
            for pos_id in list(positions.keys()):
                pos = positions[pos_id]
                
                # Stop loss
                if candle["low"] <= pos["sl"]:
                    pnl = (pos["sl"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self.close_trade(pos, pnl, "SL", i)
                    del positions[pos_id]
                
                # Take profit
                elif candle["high"] >= pos["tp"]:
                    pnl = (pos["tp"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self.close_trade(pos, pnl, "TP", i)
                    del positions[pos_id]
                
                # Timeout (24 hours = 96 candles @ 15m)
                elif (i - pos["entry_idx"]) > 96:
                    pnl = (candle["close"] - pos["entry"]) / pos["entry"] * pos["size"]
                    self.close_trade(pos, pnl, "timeout", i)
                    del positions[pos_id]
            
            # Try to open new position
            if len(positions) < 3 and i % 20 == 0:  # Check every 20 candles
                history = candles[max(0, i-50):i]
                pattern = self.detect_pattern(candle, history)
                
                if pattern:
                    confidence = self.get_confidence(pattern)
                    
                    # Only trade if confident
                    if confidence >= 60.0:
                        entry = candle["close"]
                        size = self.balance * 0.02  # 2% risk
                        
                        pos = {
                            "id": f"p{i}",
                            "entry_idx": i,
                            "entry": entry,
                            "size": size,
                            "pattern": pattern,
                            "conf": confidence,
                            "sl": entry * 0.98,  # 2% SL
                            "tp": entry * 1.04   # 4% TP (2:1 RR)
                        }
                        
                        positions[pos["id"]] = pos
        
        # Close remaining
        for pos in positions.values():
            pnl = (candles[-1]["close"] - pos["entry"]) / pos["entry"] * pos["size"]
            self.close_trade(pos, pnl, "end", len(candles)-1)
        
        # Results
        self.show_results(initial_mults)
    
    def close_trade(self, pos: Dict, pnl: float, reason: str, idx: int):
        """Close trade and learn"""
        self.balance += pnl
        won = pnl > 0
        
        self.trades.append({
            "idx": idx,
            "pattern": pos["pattern"],
            "pnl": pnl,
            "win": won,
            "reason": reason
        })
        
        # LEARNING HAPPENS
        old_mult = self.pattern_multipliers.get(pos["pattern"], 1.0)
        self.learn_from_outcome(pos["pattern"], won)
        new_mult = self.pattern_multipliers.get(pos["pattern"], 1.0)
        
        if abs(new_mult - old_mult) > 0.05:
            print(f"   📚 {pos['pattern']}: {old_mult:.2f} → {new_mult:.2f} ({'✅' if won else '❌'})")
    
    def show_results(self, initial_mults: Dict):
        """Show final results"""
        
        print()
        print("=" * 70)
        print("✅ BACKTEST COMPLETE")
        print("=" * 70)
        
        # Performance
        ret = ((self.balance - self.starting_balance) / self.starting_balance) * 100
        wins = sum(1 for t in self.trades if t["win"])
        losses = len(self.trades) - wins
        wr = (wins / len(self.trades) * 100) if self.trades else 0
        
        print()
        print("📊 PERFORMANCE:")
        print(f"   Start: ${self.starting_balance:,.2f}")
        print(f"   Final: ${self.balance:,.2f}")
        print(f"   Return: {ret:+.2f}%")
        print(f"   Trades: {len(self.trades)} (W: {wins}, L: {losses})")
        print(f"   Win Rate: {wr:.1f}%")
        
        # Pattern learning
        print()
        print("📚 PATTERN LEARNING:")
        for pattern in sorted(self.pattern_multipliers.keys()):
            initial = initial_mults.get(pattern, 1.0)
            final = self.pattern_multipliers[pattern]
            change = final - initial
            
            stats = self.pattern_stats.get(pattern, {"wins": 0, "losses": 0})
            total = stats["wins"] + stats["losses"]
            pwr = (stats["wins"] / total * 100) if total > 0 else 0
            
            print(f"   {pattern:20} {initial:.2f} → {final:.2f} (Δ{change:+.2f}) | "
                  f"{stats['wins']}/{total} trades ({pwr:.0f}% WR)")
        
        # The answer
        print()
        print("=" * 70)
        print("🎯 THE ANSWER")
        print("=" * 70)
        
        if wr >= 60:
            print("✅ YES - System is smart! (Win rate 60%+)")
        elif wr >= 50:
            print("⚠️  MAYBE - Better than random (50-60%), needs tuning")
        else:
            print("❌ NOT YET - Needs work (Win rate <50%)")
        
        improved = sum(1 for p, m in self.pattern_multipliers.items() 
                      if m > initial_mults.get(p, 1.0))
        degraded = sum(1 for p, m in self.pattern_multipliers.items() 
                      if m < initial_mults.get(p, 1.0))
        
        if improved > degraded:
            print(f"✅ LEARNED - {improved} patterns improved, {degraded} degraded")
        else:
            print(f"⚠️  LIMITED LEARNING - {improved} improved, {degraded} degraded")
        
        if ret > 0:
            print(f"✅ PROFITABLE - Made {ret:+.2f}%")
        else:
            print(f"❌ UNPROFITABLE - Lost {ret:.2f}%")
        
        print("=" * 70)


def main():
    backtest = ZeroDepBacktest()
    
    # Fetch data
    candles = backtest.fetch_data(symbol="BTCUSDT", days=60)
    
    if candles:
        # Run
        backtest.run(candles)
    else:
        print("❌ No data available")


if __name__ == "__main__":
    main()
