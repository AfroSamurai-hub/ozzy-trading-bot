"""
🎮 Realistic Mock Feed - Pattern-Based Market Simulation

This feed generates realistic price movements based on actual patterns stored
in ChromaDB. Instead of random data, it creates scenarios that match our
historical patterns, making tests more meaningful.

Features:
- Uses real patterns from ChromaDB
- Generates price movements matching pattern characteristics
- Includes volume surges, RSI divergences, EMA crossovers
- Context-aware (respects current session/regime)
- Configurable scenario generation
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from intelligence.rolling_window_db import RollingWindowPatternDB
from intelligence.market_context import get_session_detector

logger = logging.getLogger(__name__)


class RealisticMockFeed:
    """
    🎮 Generates realistic market data based on stored patterns.
    
    Instead of random walks, this creates market scenarios that actually
    match the patterns we've seen before, making tests more realistic.
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        base_price: float = 67000.0,
        pattern_db: Optional[RollingWindowPatternDB] = None
    ):
        """
        Initialize realistic mock feed.
        
        Args:
            symbol: Trading symbol
            base_price: Starting price
            pattern_db: Pattern database (will create if None)
        """
        self.symbol = symbol
        self.base_price = base_price
        self.current_price = base_price
        self.pattern_db = pattern_db or RollingWindowPatternDB()
        
        # Price history for technical indicators
        self.price_history: List[float] = [base_price]
        self.volume_history: List[float] = [1000000.0]  # Base volume
        
        # Pattern scenarios to cycle through
        self.scenarios = self._load_pattern_scenarios()
        self.current_scenario_index = 0
        
        logger.info(f"🎮 RealisticMockFeed initialized for {symbol}")
        logger.info(f"   Base price: ${base_price:,.2f}")
        logger.info(f"   Loaded {len(self.scenarios)} pattern scenarios")
    
    def _load_pattern_scenarios(self) -> List[Dict]:
        """
        Load pattern scenarios from database.
        
        Returns:
            List of scenario configurations based on real patterns
        """
        try:
            # Get all patterns from database
            collection_data = self.pattern_db.collection.get()
            all_metadatas = collection_data['metadatas']
            
            if not all_metadatas:
                return self._get_default_scenarios()
            
            # Create scenarios from actual patterns
            scenarios = []
            
            # Sample diverse patterns (max 20 scenarios)
            sample_size = min(20, len(all_metadatas))
            sampled_patterns = random.sample(all_metadatas, sample_size)
            
            for metadata in sampled_patterns:
                scenario = {
                    'name': metadata.get('pattern_type', 'unknown'),
                    'rsi': metadata.get('rsi', 50.0),
                    'ema_ratio': metadata.get('ema_ratio', 1.0),
                    'volume_change': metadata.get('volume_change', 1.0),
                    'price_change': metadata.get('price_change', 0.0),
                    'duration': random.randint(5, 15)  # How many ticks to sustain
                }
                scenarios.append(scenario)
            
            logger.info(f"📊 Created {len(scenarios)} scenarios from real patterns")
            return scenarios
            
        except Exception as e:
            logger.warning(f"Could not load patterns: {e}, using defaults")
            return self._get_default_scenarios()
    
    def _get_default_scenarios(self) -> List[Dict]:
        """Get default scenarios if database is empty"""
        return [
            {
                'name': 'bullish_momentum',
                'rsi': 65.0,
                'ema_ratio': 1.02,
                'volume_change': 1.8,
                'price_change': 0.015,
                'duration': 10
            },
            {
                'name': 'bearish_momentum',
                'rsi': 35.0,
                'ema_ratio': 0.98,
                'volume_change': 1.5,
                'price_change': -0.015,
                'duration': 8
            },
            {
                'name': 'oversold_bounce',
                'rsi': 25.0,
                'ema_ratio': 0.995,
                'volume_change': 2.0,
                'price_change': 0.025,
                'duration': 5
            },
            {
                'name': 'overbought_pullback',
                'rsi': 75.0,
                'ema_ratio': 1.005,
                'volume_change': 1.6,
                'price_change': -0.02,
                'duration': 6
            },
            {
                'name': 'sideways_consolidation',
                'rsi': 50.0,
                'ema_ratio': 1.0,
                'volume_change': 0.8,
                'price_change': 0.002,
                'duration': 12
            }
        ]
    
    async def get_ticker(self) -> Dict:
        """
        Get next realistic tick based on current scenario.
        
        Returns:
            Ticker data matching pattern characteristics
        """
        # Get current scenario
        scenario = self.scenarios[self.current_scenario_index]
        
        # Generate price movement based on scenario
        price_change_pct = scenario['price_change'] + random.uniform(-0.005, 0.005)
        new_price = self.current_price * (1 + price_change_pct)
        
        # Add some realistic noise
        noise = random.uniform(-0.001, 0.001)
        new_price *= (1 + noise)
        
        # Generate volume with surge patterns
        base_volume = 1000000.0
        volume_multiplier = scenario['volume_change'] + random.uniform(-0.2, 0.2)
        volume = base_volume * volume_multiplier
        
        # Update history
        self.price_history.append(new_price)
        self.volume_history.append(volume)
        
        # Keep last 100 candles
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]
            self.volume_history = self.volume_history[-100:]
        
        # Calculate technical indicators
        rsi = self._calculate_rsi(scenario['rsi'])
        ema_ratio = self._calculate_ema_ratio(scenario['ema_ratio'])
        
        # Build ticker
        ticker = {
            'symbol': self.symbol,
            'last_price': str(new_price),
            'price_24h_pcnt': str(price_change_pct * 100),
            'high_price_24h': str(new_price * 1.02),
            'low_price_24h': str(new_price * 0.98),
            'prev_price_24h': str(self.current_price),
            'volume_24h': str(volume),
            'turnover_24h': str(volume * new_price),
            
            # Simulated indicators
            'rsi': rsi,
            'ema_ratio': ema_ratio,
            'volume_change': scenario['volume_change'],
            
            # Metadata
            'scenario': scenario['name'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Update current price
        self.current_price = new_price
        
        # Move to next scenario every N ticks
        scenario['duration'] -= 1
        if scenario['duration'] <= 0:
            self._next_scenario()
        
        return ticker
    
    def _calculate_rsi(self, target_rsi: float) -> float:
        """Calculate realistic RSI with some variation"""
        variation = random.uniform(-5, 5)
        rsi = max(0, min(100, target_rsi + variation))
        return round(rsi, 2)
    
    def _calculate_ema_ratio(self, target_ratio: float) -> float:
        """Calculate realistic EMA ratio with some variation"""
        variation = random.uniform(-0.005, 0.005)
        ratio = target_ratio + variation
        return round(ratio, 4)
    
    def _next_scenario(self):
        """Move to next scenario"""
        # Reset current scenario duration
        self.scenarios[self.current_scenario_index]['duration'] = random.randint(5, 15)
        
        # Move to next scenario
        self.current_scenario_index = (self.current_scenario_index + 1) % len(self.scenarios)
        
        next_scenario = self.scenarios[self.current_scenario_index]
        logger.info(f"🎬 New scenario: {next_scenario['name']}")
    
    async def stream_ticks(self, duration_seconds: int = 3600, interval_seconds: int = 60):
        """
        Stream realistic ticks for a duration.
        
        Args:
            duration_seconds: How long to stream
            interval_seconds: Seconds between ticks
        """
        logger.info(f"🎮 Starting realistic tick stream")
        logger.info(f"   Duration: {duration_seconds}s ({duration_seconds/3600:.1f} hours)")
        logger.info(f"   Interval: {interval_seconds}s")
        logger.info(f"   Expected ticks: {duration_seconds // interval_seconds}")
        
        start_time = asyncio.get_event_loop().time()
        tick_count = 0
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            if elapsed >= duration_seconds:
                logger.info(f"✅ Stream complete! {tick_count} ticks generated")
                break
            
            # Generate tick
            ticker = await self.get_ticker()
            tick_count += 1
            
            # Log progress every 10 ticks
            if tick_count % 10 == 0:
                logger.info(f"📊 Tick {tick_count}: ${ticker['last_price']:.2f} | "
                           f"RSI: {ticker['rsi']:.1f} | Scenario: {ticker['scenario']}")
            
            # Wait for next tick
            await asyncio.sleep(interval_seconds)
    
    def get_current_state(self) -> Dict:
        """Get current market state for analysis"""
        if len(self.price_history) < 2:
            return {}
        
        recent_prices = self.price_history[-20:]
        recent_volumes = self.volume_history[-20:]
        
        return {
            'current_price': self.current_price,
            'price_change_1h': (self.current_price - recent_prices[0]) / recent_prices[0],
            'avg_volume': sum(recent_volumes) / len(recent_volumes),
            'volatility': np.std(recent_prices) / np.mean(recent_prices),
            'trend': 'up' if recent_prices[-1] > recent_prices[0] else 'down',
            'current_scenario': self.scenarios[self.current_scenario_index]['name']
        }


# Singleton instance
_realistic_feed: Optional[RealisticMockFeed] = None


def get_realistic_feed(
    symbol: str = "BTCUSDT",
    base_price: float = 67000.0
) -> RealisticMockFeed:
    """Get or create singleton realistic mock feed"""
    global _realistic_feed
    if _realistic_feed is None or _realistic_feed.symbol != symbol:
        _realistic_feed = RealisticMockFeed(symbol=symbol, base_price=base_price)
    return _realistic_feed


async def test_realistic_feed():
    """Test the realistic feed"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║       🎮 TESTING REALISTIC MOCK FEED 🎮                   ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    feed = get_realistic_feed()
    
    print(f"📊 Generating 10 realistic ticks...\n")
    
    for i in range(10):
        ticker = await feed.get_ticker()
        
        print(f"Tick {i+1}:")
        print(f"  Price: ${float(ticker['last_price']):,.2f}")
        print(f"  RSI: {ticker['rsi']:.1f}")
        print(f"  EMA Ratio: {ticker['ema_ratio']:.4f}")
        print(f"  Volume Change: {ticker['volume_change']:.2f}x")
        print(f"  Scenario: {ticker['scenario']}")
        print()
        
        await asyncio.sleep(0.5)
    
    state = feed.get_current_state()
    print(f"📈 Current Market State:")
    print(f"  Price: ${state['current_price']:,.2f}")
    print(f"  Trend: {state['trend'].upper()}")
    print(f"  Volatility: {state['volatility']:.2%}")
    print(f"  Active Scenario: {state['current_scenario']}")
    
    print("\n✅ Realistic feed test complete!")


if __name__ == "__main__":
    asyncio.run(test_realistic_feed())
