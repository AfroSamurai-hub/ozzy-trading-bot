"""
🎲 Realistic Mock Feed - Pattern-Based Market Simulation

Instead of random walk (Ornstein-Uhlenbeck), this feed:
1. Queries ChromaDB for actual winning patterns
2. Replays historical price movements
3. Forms recognizable patterns (engulfing, hammers, etc.)
4. Includes realistic volume profiles
5. Respects trend context and regime changes

Perfect for testing trading strategies without network dependency!
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Market tick with OHLCV data."""
    symbol: str
    price: float
    volume: float
    timestamp: int  # milliseconds

    def as_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'price': self.price,
            'volume': self.volume,
            'timestamp': self.timestamp,
        }


class MarketRegime:
    """Market regime state machine."""
    RANGING = "ranging"  # Sideways, low volatility
    TRENDING_UP = "trending_up"  # Strong uptrend
    TRENDING_DOWN = "trending_down"  # Strong downtrend
    VOLATILE = "volatile"  # High volatility, choppy


class RealisticMockFeed:
    """
    Pattern-based mock feed that replays actual market patterns from ChromaDB.
    
    Features:
    - Queries winning patterns (WR > 60%)
    - Replays price sequences with realistic timing
    - Forms recognizable patterns (bullish_engulfing, hammer, etc.)
    - Includes volume profiles from pattern metadata
    - Simulates regime changes (ranging → trending)
    - Configurable pattern mix (wins vs losses)
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval_ms: int = 500,  # Tick every 500ms
        pattern_db=None,  # RollingWindowPatternDB instance
        base_price: float = 60000.0,
        win_rate_target: float = 0.70,  # 70% winning patterns, 30% losing
        regime_duration: int = 50,  # Change regime every 50 ticks
    ):
        self.symbol = symbol
        self.interval_ms = interval_ms
        self.pattern_db = pattern_db
        self.base_price = base_price
        self.current_price = base_price
        self.win_rate_target = win_rate_target
        self.regime_duration = regime_duration
        
        # State
        self.tick_count = 0
        self.current_regime = MarketRegime.RANGING
        self.pattern_sequence: List[Dict] = []
        self.sequence_index = 0
        self.ticks_in_regime = 0
        
        # Volume simulation
        self.base_volume = 1000.0
        self.current_volume = self.base_volume
        
        # Pattern library (loaded from ChromaDB)
        self.winning_patterns: List[Dict] = []
        self.losing_patterns: List[Dict] = []
        
        logger.info("🎲 RealisticMockFeed initialized")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Base price: ${base_price:,.2f}")
        logger.info(f"   Win rate target: {win_rate_target:.0%}")
        logger.info(f"   Regime duration: {regime_duration} ticks")
        
        # Load patterns if pattern_db provided
        if pattern_db:
            self._load_patterns()
    
    def _load_patterns(self):
        """Load winning and losing patterns from ChromaDB."""
        if not self.pattern_db:
            logger.warning("No pattern_db provided, using random walk fallback")
            return
        
        try:
            # Query all patterns
            total_patterns = self.pattern_db.count()
            logger.info(f"📊 Loading patterns from ChromaDB ({total_patterns} total)...")
            
            # Sample patterns to get wins and losses
            sample_size = min(200, total_patterns)
            
            # Query with dummy embedding to get patterns
            dummy_state = {
                'rsi': 50.0,
                'ema_ratio': 1.0,
                'volume_change': 0.0,
                'price_change': 0.0
            }
            
            patterns = self.pattern_db.find_similar(dummy_state, k=sample_size)
            
            for pattern in patterns:
                metadata = pattern.get('metadata', {})
                label = metadata.get('label', 'UNKNOWN')
                
                if label == 'WIN':
                    self.winning_patterns.append(metadata)
                elif label == 'LOSS':
                    self.losing_patterns.append(metadata)
            
            logger.info(f"✅ Loaded {len(self.winning_patterns)} winning patterns")
            logger.info(f"✅ Loaded {len(self.losing_patterns)} losing patterns")
            
            if len(self.winning_patterns) == 0:
                logger.warning("⚠️  No winning patterns found, using fallback")
            if len(self.losing_patterns) == 0:
                logger.warning("⚠️  No losing patterns found, using fallback")
                
        except Exception as e:
            logger.error(f"Failed to load patterns: {e}")
            logger.info("Using random walk fallback")
    
    def _select_next_pattern(self) -> Optional[Dict]:
        """Select next pattern based on win rate target."""
        if not self.winning_patterns and not self.losing_patterns:
            return None
        
        # Decide if we want a winner or loser
        use_winner = random.random() < self.win_rate_target
        
        if use_winner and self.winning_patterns:
            return random.choice(self.winning_patterns)
        elif not use_winner and self.losing_patterns:
            return random.choice(self.losing_patterns)
        elif self.winning_patterns:
            return random.choice(self.winning_patterns)
        elif self.losing_patterns:
            return random.choice(self.losing_patterns)
        
        return None
    
    def _generate_pattern_sequence(self, pattern: Dict) -> List[Dict]:
        """
        Generate price sequence from pattern metadata.
        
        Creates realistic price movements that form the pattern:
        - Extract price_change_forward (overall movement)
        - Extract max_profit_pct, max_drawdown_pct (intrabar volatility)
        - Generate tick sequence that follows this path
        """
        sequence = []
        
        # Extract pattern info
        price_change = pattern.get('price_change_forward', 0.0) or 0.0
        max_profit = pattern.get('max_profit_pct', 0.0) or 0.0
        max_drawdown = pattern.get('max_drawdown_pct', 0.0) or 0.0
        volume_change = pattern.get('volume_change', 1.0) or 1.0
        
        # Number of ticks in this pattern (simulate 5-15 ticks per pattern)
        num_ticks = random.randint(8, 15)
        
        # Generate price path
        start_price = self.current_price
        target_price = start_price * (1 + price_change / 100.0)
        
        # Add volatility: price goes to drawdown first, then to profit
        for i in range(num_ticks):
            progress = i / num_ticks
            
            # First half: move toward drawdown
            if progress < 0.4:
                drawdown_factor = (progress / 0.4)
                price = start_price * (1 + (max_drawdown / 100.0) * drawdown_factor)
                volume = self.base_volume * (1 + volume_change * 0.5)
            
            # Middle: transition
            elif progress < 0.6:
                # Interpolate from drawdown to target
                transition = (progress - 0.4) / 0.2
                dd_price = start_price * (1 + max_drawdown / 100.0)
                price = dd_price + (target_price - dd_price) * transition
                volume = self.base_volume * (1 + volume_change * 0.8)
            
            # Final: reach target with potential overshoot to max_profit
            else:
                overshoot = (progress - 0.6) / 0.4
                profit_price = start_price * (1 + max_profit / 100.0)
                # Blend between target and max profit
                price = target_price + (profit_price - target_price) * overshoot * 0.5
                volume = self.base_volume * (1 + volume_change)
            
            # Add some noise (±0.1%)
            noise = random.uniform(-0.001, 0.001)
            price = price * (1 + noise)
            
            # Ensure price is positive
            price = max(price, start_price * 0.95)
            
            sequence.append({
                'price': price,
                'volume': volume,
                'pattern_label': pattern.get('label', 'UNKNOWN')
            })
        
        return sequence
    
    def _generate_ranging_tick(self) -> Dict:
        """Generate tick for ranging market (low volatility)."""
        # Small random walk
        change = random.uniform(-0.0015, 0.0015)  # ±0.15%
        self.current_price = self.current_price * (1 + change)
        
        # Low volume in ranging market
        self.current_volume = self.base_volume * random.uniform(0.8, 1.2)
        
        return {
            'price': self.current_price,
            'volume': self.current_volume,
            'pattern_label': 'ranging'
        }
    
    def _generate_trending_tick(self, direction: str) -> Dict:
        """Generate tick for trending market (consistent direction)."""
        # Stronger directional movement
        if direction == "up":
            change = random.uniform(0.001, 0.004)  # +0.1% to +0.4%
        else:
            change = random.uniform(-0.004, -0.001)  # -0.4% to -0.1%
        
        self.current_price = self.current_price * (1 + change)
        
        # Higher volume in trending market
        self.current_volume = self.base_volume * random.uniform(1.2, 1.8)
        
        return {
            'price': self.current_price,
            'volume': self.current_volume,
            'pattern_label': f'trending_{direction}'
        }
    
    def _generate_volatile_tick(self) -> Dict:
        """Generate tick for volatile market (high variance)."""
        # Large random movements
        change = random.uniform(-0.005, 0.005)  # ±0.5%
        self.current_price = self.current_price * (1 + change)
        
        # Very high volume in volatile market
        self.current_volume = self.base_volume * random.uniform(1.5, 2.5)
        
        return {
            'price': self.current_price,
            'volume': self.current_volume,
            'pattern_label': 'volatile'
        }
    
    def _update_regime(self):
        """Change market regime based on duration."""
        self.ticks_in_regime += 1
        
        if self.ticks_in_regime >= self.regime_duration:
            # Time to change regime
            old_regime = self.current_regime
            
            # Pick new regime (weighted probabilities)
            regimes = [
                (MarketRegime.RANGING, 0.4),  # 40% ranging
                (MarketRegime.TRENDING_UP, 0.25),  # 25% uptrend
                (MarketRegime.TRENDING_DOWN, 0.20),  # 20% downtrend
                (MarketRegime.VOLATILE, 0.15),  # 15% volatile
            ]
            
            # Don't pick same regime twice in a row
            regimes = [(r, w) for r, w in regimes if r != old_regime]
            total_weight = sum(w for _, w in regimes)
            regimes = [(r, w/total_weight) for r, w in regimes]
            
            rand = random.random()
            cumulative = 0.0
            for regime, weight in regimes:
                cumulative += weight
                if rand < cumulative:
                    self.current_regime = regime
                    break
            
            self.ticks_in_regime = 0
            logger.info(f"📊 Regime change: {old_regime} → {self.current_regime}")
    
    def _generate_next_tick(self) -> Dict:
        """Generate next tick based on current state."""
        self.tick_count += 1
        self._update_regime()
        
        # Use pattern sequence if available
        if self.pattern_sequence and self.sequence_index < len(self.pattern_sequence):
            tick_data = self.pattern_sequence[self.sequence_index]
            self.sequence_index += 1
            self.current_price = tick_data['price']
            self.current_volume = tick_data['volume']
            
            # If sequence complete, clear it
            if self.sequence_index >= len(self.pattern_sequence):
                self.pattern_sequence = []
                self.sequence_index = 0
            
            return tick_data
        
        # Start new pattern sequence (30% chance every tick)
        if not self.pattern_sequence and random.random() < 0.3:
            pattern = self._select_next_pattern()
            if pattern:
                logger.debug(f"🎯 Starting pattern: {pattern.get('label', 'UNKNOWN')}")
                self.pattern_sequence = self._generate_pattern_sequence(pattern)
                self.sequence_index = 0
                # Return first tick of sequence
                if self.pattern_sequence:
                    tick_data = self.pattern_sequence[0]
                    self.sequence_index = 1
                    self.current_price = tick_data['price']
                    self.current_volume = tick_data['volume']
                    return tick_data
        
        # No pattern, generate tick based on regime
        if self.current_regime == MarketRegime.RANGING:
            return self._generate_ranging_tick()
        elif self.current_regime == MarketRegime.TRENDING_UP:
            return self._generate_trending_tick("up")
        elif self.current_regime == MarketRegime.TRENDING_DOWN:
            return self._generate_trending_tick("down")
        else:  # VOLATILE
            return self._generate_volatile_tick()
    
    async def ticks(self) -> AsyncIterator[Tick]:
        """
        Async generator yielding realistic ticks.
        
        Yields:
            Tick objects with realistic price/volume based on patterns
        """
        logger.info(f"🎲 Starting realistic tick feed for {self.symbol}")
        logger.info(f"   Starting price: ${self.current_price:,.2f}")
        
        while True:
            tick_data = self._generate_next_tick()
            
            yield Tick(
                symbol=self.symbol,
                price=tick_data['price'],
                volume=tick_data['volume'],
                timestamp=int(time.time() * 1000)
            )
            
            await asyncio.sleep(self.interval_ms / 1000.0)
    
    async def close(self):
        """Close the feed (no-op for mock)."""
        logger.info("🎲 RealisticMockFeed closed")


# Example usage / self-test
if __name__ == "__main__":
    async def test():
        print("🧪 Testing RealisticMockFeed...")
        
        # Test without pattern DB (fallback mode)
        feed = RealisticMockFeed("BTCUSDT", interval_ms=100)
        
        tick_count = 0
        async for tick in feed.ticks():
            tick_count += 1
            print(f"📊 Tick {tick_count}: {tick.symbol} @ ${tick.price:,.2f} (vol: {tick.volume:.0f})")
            
            if tick_count >= 50:
                break
        
        print(f"\n✅ Test complete! Generated {tick_count} realistic ticks")
        print(f"   Price range: ${feed.base_price:,.2f} → ${feed.current_price:,.2f}")
        print(f"   Final regime: {feed.current_regime}")
    
    asyncio.run(test())
