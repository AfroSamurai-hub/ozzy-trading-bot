# 🗄️ Vector Database System Overview

## Yes, the VectorDB is ACTIVELY USED! ✅

### 📊 Current Status:
- **Database**: ChromaDB (v0.5.3+)
- **Patterns Stored**: **5,029 patterns** 🎉
- **Location**: `data/vector_db/`
- **Type**: PersistentClient (survives restarts)

---

## 🔄 How It Works in Your AI Trading System:

### 1️⃣ **Pattern Storage** (`intelligence/rolling_window_db.py`)
```python
class RollingWindowPatternDB:
    - Stores market patterns with embeddings
    - Auto-flushes when reaching capacity (10,000 max)
    - Each pattern has: RSI, EMA ratio, price change, volume, label (WIN/LOSS)
```

### 2️⃣ **MCP Server Integration** (`mcp/trading_server.py`)
```python
TradingMCPServer:
    - get_market_state() → Gets latest pattern from DB
    - get_similar_patterns() → Vector similarity search
    - Calculates win rates from historical patterns
```

### 3️⃣ **AI Decision Process** (`agent/trader.py`)
```python
async def analyze_and_decide():
    1. Get current market state from DB
    2. Find similar patterns (vector similarity search)
    3. Calculate win rate from similar patterns
    4. Send to OpenAI with historical context
    5. Apply safety rails based on pattern win rates
```

---

## 🎯 What the VectorDB Does:

### **Vector Similarity Search**
- Current market: RSI=56, EMA=1.02, Price Change=2%
- **VectorDB finds**: 10 most similar historical patterns
- **Returns**: Win rate (e.g., "60% of similar patterns were profitable")
- **AI uses this**: To make informed decisions

### **Example from Your AI Test:**
```
🔍 Analyzing BTCUSDT...
   RSI: 56.19 | EMA ratio: 1.02 | Price Δ: 2.3%
   Pattern cheatsheet matches: none
   Patterns found: 10 | Win rate: 63.5%  ← FROM VECTORDB!
   
🤖 AI Decision: SKIP
   Reasoning: "While win rate is 63%, RSI shows overbought..."
```

---

## 📂 Database Structure:

### **Embedding Vector** (6 dimensions):
1. RSI (normalized 0-1)
2. EMA ratio (normalized)
3. Price change % (normalized)
4. Volume change % (normalized)
5. Hour of day (normalized)
6. Day of week (normalized)

### **Metadata** (stored with each pattern):
- `symbol`: BTCUSDT
- `timestamp`: Unix timestamp
- `price`: Current price
- `label`: WIN, LOSS, or UNKNOWN
- `hit_takeprofit`: boolean
- `hit_stoploss`: boolean
- `rsi`, `ema_ratio`, `price_change`, `volume_change`

---

## 🔧 Auto-Flush System:

**Capacity Management:**
- **Max capacity**: 10,000 patterns
- **Flush trigger**: 80% full (8,000 patterns)
- **Flush amount**: Remove oldest 20% (2,000 patterns)
- **Current**: 5,029 patterns (50% capacity) ✅

**Why flush?**
- Keeps recent patterns (more relevant)
- Prevents database bloat
- Maintains performance

---

## 🚀 How Patterns Get Added:

### **Bootstrap (Initial Load):**
```bash
python intelligence/process_historical.py
# Loads historical data from CSVs
# Creates embeddings for each pattern
# Populates ChromaDB
```

### **Live Trading:**
```python
When you close a trade:
1. Calculate outcome (WIN/LOSS)
2. Create pattern embedding
3. Add to ChromaDB
4. Now available for future AI decisions!
```

---

## 💡 Why This Matters:

### **Without VectorDB:**
```
AI: "I see RSI=56. Should I trade?"
Result: Random guess based on general knowledge
```

### **With VectorDB:**
```
AI: "I see RSI=56. Let me check..."
VectorDB: "I found 10 similar situations. 6 won, 4 lost = 60% win rate"
AI: "Based on 60% historical win rate, I'll SKIP because confidence is low"
Result: Data-driven decision! 🎯
```

---

## 🔍 How to Check VectorDB Health:

### **Pattern Count:**
```bash
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); print(f'Patterns: {db.count()}')"
```

### **Check Win Rates:**
```python
from intelligence.rolling_window_db import RollingWindowPatternDB

db = RollingWindowPatternDB()
current_state = {"rsi": 56, "ema_ratio": 1.02, "price_change": 0.02}
patterns = db.find_similar(current_state, k=10)

wins = sum(1 for p in patterns if p["metadata"].get("label") == "WIN")
print(f"Win rate: {wins/len(patterns)*100:.1f}%")
```

### **Clear and Rebuild:**
```bash
# If database gets corrupted
rm -rf data/vector_db/*
python intelligence/process_historical.py
```

---

## 📈 Your Current System Flow:

```
1. Market Data (Mock/Real)
   ↓
2. Create Embedding [RSI, EMA, Price Δ, Volume Δ, Time]
   ↓
3. VectorDB Similarity Search → Find 10 similar patterns
   ↓
4. Calculate Win Rate from similar patterns
   ↓
5. Send to OpenAI with context:
   - Current market state
   - 10 similar historical patterns
   - Win rate: 63.5%
   ↓
6. OpenAI Decision (BUY/SELL/SKIP)
   ↓
7. Safety Rails (check win rate, confidence, risk)
   ↓
8. Execute or Skip
```

---

## 🎉 Summary:

✅ **YES, VectorDB is ACTIVELY used**
✅ **5,029 patterns** ready for similarity search
✅ **ChromaDB** (persistent, survives restarts)
✅ **Integrated into every AI decision**
✅ **Provides historical win rates** for informed trading
✅ **Auto-flushes** to keep recent patterns relevant

**Your overnight AI test is using VectorDB right now!** Every decision the AI makes queries the database for similar patterns and win rates. 🚀

---

## 📝 Files Involved:

1. `intelligence/rolling_window_db.py` - Database wrapper
2. `mcp/trading_server.py` - MCP server with DB queries
3. `agent/trader.py` - AI agent using DB for decisions
4. `data/vector_db/` - ChromaDB storage directory
5. `intelligence/process_historical.py` - Bootstrap loader

---

**Last Updated**: October 16, 2025, 22:03
**Patterns**: 5,029 / 10,000 (50% capacity)
**Status**: ✅ Operational
