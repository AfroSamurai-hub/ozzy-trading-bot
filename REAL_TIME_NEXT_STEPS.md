# 🚀 Real-Time Streaming System - Next Steps

**Prerequisites:** ✅ Intrawindow Risk Tracking Complete  
**Goal:** Build real-time pattern detection and AI decision-making system  
**Estimated Time:** ~6 hours  
**Target:** Fully operational by early next morning 🌅

---

## 📋 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    REAL-TIME TRADING SYSTEM                  │
└─────────────────────────────────────────────────────────────┘

1. WEBSOCKET STREAM        2. PATTERN BUILDER         3. VECTOR DB
┌─────────────────┐       ┌──────────────────┐      ┌─────────────┐
│   Market Ticks  │  →    │  Tick → Candles  │  →   │   Rolling   │
│   (BTC/ETH)     │       │  + Indicators    │      │   Window    │
│   Live Data     │       │  + Embeddings    │      │   Patterns  │
└─────────────────┘       └──────────────────┘      └─────────────┘
                                                            ↓
4. MCP SERVER              5. AI AGENT               6. DASHBOARD
┌─────────────────┐       ┌──────────────────┐      ┌─────────────┐
│   API Layer     │  ←    │   Decision       │  ←   │   Monitor   │
│   Query         │       │   Maker          │      │   & Alert   │
│   Endpoints     │       │   (Pattern AI)   │      │   System    │
└─────────────────┘       └──────────────────┘      └─────────────┘
```

---

## 🎯 Component Implementation Guide

### Component 1: WebSocket Stream (1.5 hours)

**File:** `stream/websocket_client.py`

**Requirements:**
```python
# Install websocket client
pip install websocket-client python-bybit
```

**Implementation Outline:**
```python
"""
Real-time WebSocket client for market data streaming.
"""
import asyncio
import json
from typing import Callable, Dict
from websocket import WebSocketApp

class BybitWebSocketClient:
    def __init__(self, symbols: list, on_tick: Callable):
        """
        Initialize WebSocket client.
        
        Args:
            symbols: List of trading symbols (e.g., ["BTCUSDT", "ETHUSDT"])
            on_tick: Callback function to handle incoming ticks
        """
        self.symbols = symbols
        self.on_tick = on_tick
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        
    async def connect(self):
        """Establish WebSocket connection."""
        pass
        
    async def subscribe(self):
        """Subscribe to tick data for symbols."""
        pass
        
    def on_message(self, ws, message):
        """Handle incoming tick messages."""
        data = json.loads(message)
        self.on_tick(data)
        
    def on_error(self, ws, error):
        """Handle connection errors."""
        print(f"WebSocket error: {error}")
        
    def on_close(self, ws):
        """Handle connection closure."""
        print("WebSocket connection closed")
        
    async def run(self):
        """Start the WebSocket stream."""
        pass
```

**Testing:**
```python
# Test with live data
async def test_stream():
    def handle_tick(data):
        print(f"Received tick: {data}")
    
    client = BybitWebSocketClient(
        symbols=["BTCUSDT", "ETHUSDT"],
        on_tick=handle_tick
    )
    await client.run()

# Run test
asyncio.run(test_stream())
```

---

### Component 2: Pattern Builder (2 hours)

**File:** `agent/pattern_builder.py` (Already exists - needs enhancement)

**Current State:** Basic structure exists  
**Needed Enhancements:**
1. ✅ Tick aggregation to 5-minute candles (exists)
2. ✅ RSI and EMA calculation (exists)
3. ⚠️  Need to integrate with WebSocket stream
4. ⚠️  Need to label patterns using intrawindow logic (forward-looking)

**Enhancement Plan:**
```python
# In pattern_builder.py

class RealtimePatternBuilder:
    def __init__(self, pattern_db: RollingWindowPatternDB):
        self.pattern_db = pattern_db
        self.interval_seconds = 300  # 5 minutes
        # ... existing code ...
    
    async def process_tick_from_stream(self, tick: Dict) -> None:
        """
        Process incoming tick from WebSocket.
        
        Args:
            tick: {'symbol': 'BTCUSDT', 'price': 50000, 'volume': 10, 'timestamp': ...}
        """
        await self.process_tick(tick)
        
    def _close_candle(self, symbol: str, candle: Dict) -> None:
        """
        Enhanced candle closure with pattern storage.
        Note: Live patterns won't have labels yet - label as "UNKNOWN"
        """
        # ... existing code ...
        
        metadata = {
            "timestamp": candle["end_ts"] / 1000,
            "label": "UNKNOWN",  # Can't know outcome until lookforward period passes
            "rsi": float(latest["rsi"] or 50),
            "ema_ratio": float(latest["ema_short"] / latest["ema_long"]),
            # Add these for future labeling
            "symbol": symbol,
            "close": candle["close"],
        }
        
        self.pattern_db.add_pattern(...)
```

**Integration Test:**
```python
# Test pattern builder with WebSocket stream
async def test_live_patterns():
    db = RollingWindowPatternDB(window_hours=48)
    builder = RealtimePatternBuilder(db)
    
    async def handle_tick(tick_data):
        await builder.process_tick_from_stream(tick_data)
        if db.count() % 10 == 0:
            print(f"Stored {db.count()} patterns")
    
    client = BybitWebSocketClient(
        symbols=["BTCUSDT"],
        on_tick=handle_tick
    )
    await client.run()
```

---

### Component 3: MCP Server (1.5 hours)

**File:** `mcp/trading_server.py` (Already exists - needs enhancement)

**Current State:** Basic MCP structure exists  
**Needed Features:**

1. **Pattern Query Endpoint**
```python
@server.tool()
async def query_similar_patterns(
    rsi: float,
    ema_ratio: float,
    volume_change: float,
    price_change: float,
    k: int = 5
) -> dict:
    """
    Find similar historical patterns.
    
    Returns top-k similar patterns with their outcomes.
    """
    embedding = [rsi/100, ema_ratio, volume_change, price_change]
    results = pattern_db.query(embedding, k=k)
    
    # Analyze outcomes
    labels = [m['label'] for m in results['metadatas'][0]]
    win_rate = labels.count('WIN') / len(labels) * 100
    loss_rate = labels.count('LOSS') / len(labels) * 100
    neutral_rate = labels.count('NEUTRAL') / len(labels) * 100
    
    return {
        "similar_patterns": len(labels),
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "neutral_rate": neutral_rate,
        "confidence": win_rate,  # Simple confidence metric
        "patterns": results['metadatas'][0]
    }
```

2. **Statistics Endpoint**
```python
@server.tool()
async def get_pattern_statistics() -> dict:
    """Get current pattern database statistics."""
    return pattern_db.get_stats()
```

3. **Current Price Endpoint**
```python
@server.tool()
async def get_current_market_state(symbol: str) -> dict:
    """Get latest pattern for a symbol."""
    # Query most recent pattern for symbol
    pass
```

**Testing:**
```python
# Test MCP server
python mcp/trading_server.py
```

---

### Component 4: AI Agent (1 hour)

**File:** `agent/decision_maker.py` (New file)

**Implementation:**
```python
"""
AI-powered trading decision maker using pattern similarity.
"""
from intelligence.rolling_window_db import RollingWindowPatternDB
from typing import Dict, Optional

class PatternBasedAgent:
    def __init__(self, pattern_db: RollingWindowPatternDB, min_confidence: float = 40.0):
        self.pattern_db = pattern_db
        self.min_confidence = min_confidence
        
    def generate_signal(self, current_pattern: Dict) -> Dict:
        """
        Generate trading signal based on pattern similarity.
        
        Args:
            current_pattern: {
                'rsi': float,
                'ema_ratio': float,
                'volume_change': float,
                'price_change': float,
            }
            
        Returns:
            {
                'signal': 'LONG' | 'SHORT' | 'HOLD',
                'confidence': float,
                'reason': str,
                'similar_patterns': int,
                'win_rate': float,
                'avg_max_profit': float,
                'avg_max_drawdown': float,
            }
        """
        # Create embedding
        embedding = [
            current_pattern['rsi'] / 100.0,
            current_pattern['ema_ratio'],
            current_pattern['volume_change'],
            current_pattern['price_change'],
        ]
        
        # Query similar patterns
        results = self.pattern_db.query(embedding, k=20)
        
        if not results['metadatas'][0]:
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'reason': 'No similar patterns found',
            }
        
        # Analyze outcomes
        metadatas = results['metadatas'][0]
        wins = sum(1 for m in metadatas if m['label'] == 'WIN')
        losses = sum(1 for m in metadatas if m['label'] == 'LOSS')
        neutrals = sum(1 for m in metadatas if m['label'] == 'NEUTRAL')
        total = len(metadatas)
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # Calculate average intrawindow metrics
        avg_profit = sum(m.get('max_profit_pct', 0) for m in metadatas) / total
        avg_drawdown = sum(m.get('max_drawdown_pct', 0) for m in metadatas) / total
        
        # Decision logic
        if win_rate >= self.min_confidence:
            signal = 'LONG'
            confidence = win_rate
            reason = f"Pattern has {win_rate:.1f}% win rate based on {total} similar patterns"
        else:
            signal = 'HOLD'
            confidence = win_rate
            reason = f"Win rate {win_rate:.1f}% below threshold {self.min_confidence}%"
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'similar_patterns': total,
            'win_rate': win_rate,
            'loss_rate': (losses / total * 100) if total > 0 else 0,
            'neutral_rate': (neutrals / total * 100) if total > 0 else 0,
            'avg_max_profit_pct': avg_profit * 100,
            'avg_max_drawdown_pct': avg_drawdown * 100,
        }
```

**Testing:**
```python
# Test agent
agent = PatternBasedAgent(pattern_db, min_confidence=35.0)

test_pattern = {
    'rsi': 45.0,
    'ema_ratio': 0.98,
    'volume_change': 0.05,
    'price_change': -0.002,
}

signal = agent.generate_signal(test_pattern)
print(f"Signal: {signal['signal']}")
print(f"Confidence: {signal['confidence']:.1f}%")
print(f"Reason: {signal['reason']}")
```

---

### Component 5: Dashboard (Optional, 1-2 hours)

**File:** `dashboard/live_monitor.py`

**Simple CLI Dashboard:**
```python
"""
Simple CLI dashboard for monitoring live patterns.
"""
import time
from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()

def create_dashboard(pattern_db, agent):
    """Create live dashboard display."""
    table = Table(title="Ozzy Live Trading Monitor")
    
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    stats = pattern_db.get_stats()
    
    table.add_row("Total Patterns", str(stats['total_patterns']))
    table.add_row("WIN Rate", f"{stats['win_rate']:.1f}%")
    table.add_row("LOSS Rate", f"{stats['loss_rate']:.1f}%")
    table.add_row("NEUTRAL Rate", f"{stats['neutral_rate']:.1f}%")
    table.add_row("Avg Max Profit", f"{stats['avg_max_profit_pct']:.2f}%")
    table.add_row("Avg Max Drawdown", f"{stats['avg_max_drawdown_pct']:.2f}%")
    
    return table

def run_dashboard(pattern_db, agent, refresh_seconds=5):
    """Run live dashboard with auto-refresh."""
    with Live(create_dashboard(pattern_db, agent), refresh_per_second=1) as live:
        while True:
            time.sleep(refresh_seconds)
            live.update(create_dashboard(pattern_db, agent))
```

---

## 🔧 Integration Flow

### End-to-End System

```python
"""
main_realtime.py - Complete real-time trading system
"""
import asyncio
from intelligence.rolling_window_db import RollingWindowPatternDB
from agent.pattern_builder import RealtimePatternBuilder
from agent.decision_maker import PatternBasedAgent
from stream.websocket_client import BybitWebSocketClient

async def main():
    # 1. Initialize pattern database
    print("🗄️  Initializing pattern database...")
    pattern_db = RollingWindowPatternDB(window_hours=48)
    
    # Load historical patterns for bootstrapping
    count = pattern_db.load_from_csv("data/historical/BTCUSDT_5m_bootstrap_patterns.csv")
    print(f"   ✓ Loaded {count} bootstrap patterns")
    
    # 2. Initialize pattern builder
    print("🔨 Initializing pattern builder...")
    pattern_builder = RealtimePatternBuilder(pattern_db)
    
    # 3. Initialize AI agent
    print("🤖 Initializing AI decision maker...")
    agent = PatternBasedAgent(pattern_db, min_confidence=35.0)
    
    # 4. Define tick handler
    async def handle_tick(tick_data):
        # Process tick into patterns
        await pattern_builder.process_tick_from_stream(tick_data)
        
        # Every 5 minutes, generate signal
        # (In practice, trigger on candle close)
        if should_generate_signal(tick_data):
            current_pattern = extract_current_pattern(tick_data)
            signal = agent.generate_signal(current_pattern)
            
            if signal['signal'] != 'HOLD':
                print(f"\n🚨 SIGNAL: {signal['signal']}")
                print(f"   Confidence: {signal['confidence']:.1f}%")
                print(f"   Reason: {signal['reason']}")
    
    # 5. Start WebSocket stream
    print("🌐 Starting WebSocket stream...")
    client = BybitWebSocketClient(
        symbols=["BTCUSDT", "ETHUSDT"],
        on_tick=handle_tick
    )
    
    print("✅ Real-time system operational!")
    print("📊 Monitoring live patterns...\n")
    
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## ✅ Completion Checklist

### Phase 1: WebSocket Stream
- [ ] Create `stream/websocket_client.py`
- [ ] Implement connection management
- [ ] Test with live BTC/ETH data
- [ ] Handle errors and reconnection

### Phase 2: Pattern Builder Enhancement
- [ ] Integrate with WebSocket stream
- [ ] Test real-time candle aggregation
- [ ] Verify pattern storage in DB
- [ ] Monitor memory usage

### Phase 3: MCP Server
- [ ] Add pattern query endpoint
- [ ] Add statistics endpoint
- [ ] Add current state endpoint
- [ ] Test with MCP client

### Phase 4: AI Agent
- [ ] Create `agent/decision_maker.py`
- [ ] Implement pattern-based signals
- [ ] Test with historical patterns
- [ ] Validate confidence scoring

### Phase 5: Integration
- [ ] Create `main_realtime.py`
- [ ] Connect all components
- [ ] End-to-end testing
- [ ] Performance monitoring

### Phase 6: Dashboard (Optional)
- [ ] Create CLI monitoring dashboard
- [ ] Add real-time statistics
- [ ] Add pattern visualization
- [ ] Test auto-refresh

---

## 🎯 Success Criteria

- ✅ WebSocket receives live ticks (>100 ticks/minute)
- ✅ Patterns stored in real-time (new pattern every 5 min)
- ✅ AI agent generates signals based on similarity
- ✅ Confidence scores use intrawindow metrics
- ✅ System runs continuously without errors
- ✅ Dashboard shows live statistics

---

## 🚨 Important Notes

1. **Pattern Labeling Delay**: Live patterns can't be labeled until the lookforward window (30 minutes) passes. Initially label as "UNKNOWN", then update later.

2. **Database Performance**: With 48-hour window, expect ~576 patterns (48h × 12 per hour). Monitor query performance.

3. **Risk Management**: AI agent generates signals, but integrate with existing risk manager before live trading.

4. **Testing**: Use paper trading mode initially. Verify all components work together before considering live trading.

5. **Monitoring**: Watch for:
   - WebSocket disconnections
   - Pattern storage errors
   - Memory leaks
   - Query latency

---

## 📚 Resources

- **Bybit WebSocket API**: https://bybit-exchange.github.io/docs/v5/ws/connect
- **ChromaDB Query API**: https://docs.trychroma.com/reference/query
- **MCP Protocol**: https://github.com/anthropics/model-context-protocol

---

## 🎉 Ready to Build!

All prerequisites are complete. Follow the component guides above to build the real-time system.

**Estimated completion:** 6 hours  
**Target:** Fully operational by early next morning 🌅

Let's build! 🚀
