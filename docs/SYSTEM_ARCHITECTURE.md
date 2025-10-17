# 🏗️ OZZY SIMPLE - SYSTEM ARCHITECTURE

**Version:** 1.0  
**Last Updated:** October 17, 2025  
**Status:** Phase 2 - Active Development

---

## 🎯 EXECUTIVE SUMMARY

OZZY is an AI-powered cryptocurrency day trading bot that uses GPT-4o-mini for decision-making, pattern recognition for intelligence, and quantitative risk management. The system operates on a self-aware architecture where the AI agent checks its own capabilities and demands the tools it needs before making trading decisions.

**Core Philosophy:** "I won't make decisions without the tools I need!"

---

## 📊 HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        OZZY TRADING BOT                         │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
            ┌───────▼──────┐         ┌───────▼──────┐
            │ CLI DASHBOARD│         │   STREAMLIT  │
            │  (Terminal)  │         │  (Web UI)    │
            └──────────────┘         └──────────────┘
                                             │
┌────────────────────────────────────────────┼─────────────────────┐
│                       CORE SYSTEM          │                     │
│                                            │                     │
│  ┌──────────────┐      ┌─────────────┐    │   ┌──────────────┐ │
│  │   Trading    │──────│     MCP     │────┼───│   Pattern    │ │
│  │    Agent     │      │   Server    │    │   │ Intelligence │ │
│  │  (GPT-4o)    │      │  (Context)  │    │   │  (ChromaDB)  │ │
│  └──────┬───────┘      └─────────────┘    │   └──────────────┘ │
│         │                                  │                     │
│         │              ┌─────────────┐    │                     │
│         └──────────────│   Safety    │────┘                     │
│                        │    Rails    │                          │
│                        └──────┬──────┘                          │
└───────────────────────────────┼─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
            ┌───────▼──────┐       ┌───────▼──────┐
            │   Paper      │       │  Realistic   │
            │  Trading     │       │   Mock       │
            │  Portfolio   │       │   Feed       │
            └──────────────┘       └──────────────┘
                    │                       │
                    └───────────┬───────────┘
                                │
                        ┌───────▼──────┐
                        │  Market Data │
                        │   (Simulated)│
                        └──────────────┘

DATA FLOW:
1. Mock Feed generates realistic price ticks
2. Trading Agent requests market context from MCP Server
3. MCP Server queries Pattern Intelligence for similar patterns
4. Agent calls GPT-4o-mini with enriched context
5. Safety Rails validate AI decision
6. Portfolio executes trade (paper trading)
7. Pattern Intelligence learns from outcomes
8. Dashboards display real-time status
```

---

## 🧩 CORE COMPONENTS

### 1. **Trading Agent** (`agent/trader.py`)

**Purpose:** Self-aware AI trading brain that orchestrates all decision-making.

**Key Responsibilities:**
- Demand required intelligence systems on startup
- Request market context from MCP server
- Call GPT-4o-mini for trading decisions
- Enforce safety rails before execution
- Track pattern performance for learning

**Critical Architecture Decision:**
```python
# ✅ Self-Aware Initialization
if not self.pattern_intelligence:
    logger.warning("⚠️ Pattern Intelligence NOT initialized! Bootstrapping...")
    # Agent KNOWS it needs this tool and demands it
```

**Input:**
- Symbol to analyze (e.g., "BTCUSDT")
- Current market state from MCP

**Output:**
```python
{
    "action": "BUY|SELL|SKIP",
    "confidence": 0.75,  # 0-1 scale
    "position_size": 500.0,  # ZAR
    "reasoning": "Strong bullish pattern with 65% historical win rate"
}
```

**Dependencies:**
- MCP Server (context provider)
- Pattern Intelligence (historical data)
- Safety Rails (validation)
- OpenAI API (GPT-4o-mini)

**Error Handling:**
- Timeout protection (90s max)
- Fallback to SKIP on any error
- Full exception logging
- Graceful degradation without pattern intelligence

---

### 2. **MCP Server** (`mcp/trading_server.py`)

**Purpose:** Model Context Protocol server that provides rich context to AI agent.

**Key Responsibilities:**
- Fetch current market state (price, RSI, EMA, volume)
- Query pattern database for similar historical situations
- Provide portfolio state (capital, positions, P&L)
- Validate risk limits before execution

**Critical Fix (Oct 17, 2025):**
```python
# ✅ Handle both PortfolioState and PaperTradingPortfolio
if hasattr(self.portfolio, 'open_positions'):
    open_count = len(self.portfolio.open_positions)
else:
    # PaperTradingPortfolio - count OPEN positions manually
    open_count = len([p for p in getattr(self.portfolio, 'positions', []) 
                      if p.get('status') == 'OPEN'])
```

**API Methods:**
- `get_market_state(symbol)` → Current market indicators
- `get_similar_patterns(market_state, top_k=10)` → Historical pattern matches
- `get_portfolio_state()` → Current portfolio snapshot
- `check_risk_limits(proposed_trade)` → Pre-trade validation

**Data Flow:**
```
Agent Request → MCP Server → Pattern DB Query → Enriched Response
                    ↓
              Portfolio Check → Risk Validation
```

---

### 3. **Pattern Intelligence** (`intelligence/pattern_intelligence.py`)

**Purpose:** Self-learning system that tracks pattern outcomes and calculates win rates.

**Key Capabilities:**
- Store patterns in ChromaDB vector database
- Calculate context-aware win rates (session, volatility, volume)
- Track pattern effectiveness over time
- Provide top-performing patterns to AI

**Pattern Structure:**
```python
{
    "pattern_id": "rsi_45_ema_1.02_vol_high",
    "market_state": {
        "rsi": 45,
        "ema_ratio": 1.02,
        "volume_change": 0.15
    },
    "outcome": "WIN|LOSS|NEUTRAL",
    "entry_price": 67500.0,
    "exit_price": 68500.0,
    "pnl_pct": 1.48,
    "session": "london",
    "timestamp": "2025-10-17T10:30:00Z"
}
```

**Intelligence Evolution:**
```
Phase 1: Bootstrap with labeled historical patterns (2,494 patterns)
Phase 2: Learn from live trades (track outcomes)
Phase 3: Context-aware intelligence (session-specific win rates)
Phase 4: Adaptive learning (adjust to market conditions)
```

**Current Status:**
- ✅ Pattern storage working (ChromaDB)
- ✅ Win rate calculation working
- ✅ Bootstrap labeling complete (2,494 patterns)
- ⏳ Context-aware learning in progress
- ⏳ Real trade tracking not yet active

---

### 4. **Safety Rails** (`agent/safety.py`)

**Purpose:** Deterministic guardrails that prevent AI from making dangerous trades.

**Validation Rules:**

| Check | Threshold | Reason |
|-------|-----------|--------|
| Confidence | ≥ 55% | AI must be reasonably confident |
| Pattern Win Rate | ≥ 40% | Historical evidence required (lowered for testing) |
| RSI Bounds | 30-70 | Avoid extreme overbought/oversold |
| Position Size | ≤ 5% capital | Prevent over-leverage |
| Max Positions | ≤ 20 | Limit simultaneous exposure |

**Critical Configuration:**
```python
@dataclass
class SafetyRailsConfig:
    capital: float = 5_000.0
    max_position_pct: float = 0.05  # 5% per trade
    min_confidence: float = 0.55    # 55% AI confidence minimum
    min_pattern_win_rate: float = 40.0  # 40% historical win rate (testing)
    rsi_bounds: Tuple[float, float] = (30.0, 70.0)
```

**Rejection Examples:**
```
❌ "Confidence 0.45 below 0.55 threshold"
❌ "Historical win rate 38% below 40%"
❌ "RSI 75 outside safe band 30-70"
❌ "Position size 550 exceeds 5% of capital"
❌ "Portfolio already at max positions"
```

---

See full document for remaining sections (Portfolio, Mock Feed, Workflows, Design Decisions, etc.)

---

**📞 SUPPORT:** See docs/TROUBLESHOOTING.md for common issues  
**🐛 BUGS:** See docs/BUG_HISTORY.md for known issues  
**✅ TESTING:** See docs/PRE_FLIGHT_CHECKLIST.md before running
