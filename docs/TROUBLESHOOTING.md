# Troubleshooting Guide - Quick Fixes

**Purpose:** Fast solutions for common errors during development and testing

**Last Updated:** October 17, 2025

---

## 🚨 Quick Diagnostic Commands

```bash
# Check if test is running
ps aux | grep bulletproof_test

# Check recent errors
tail -100 /tmp/test_output.log | grep -i "error\|exception\|failed"

# Check pattern DB
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); print(f'Patterns: {db.collection.count()}')"

# Check portfolio connection
grep "portfolio=portfolio" scripts/bulletproof_test.py

# Check for syntax errors
python -m py_compile agent/*.py mcp/*.py scripts/*.py
```

---

## 🐛 Error: "All decisions SKIP"

### Symptom
```
AI Decision: SKIP
Reasoning: Historical win rate 45.3% below 60.0% threshold
```

Every decision is SKIP, no trades executed.

### Possible Causes & Fixes

#### Cause 1: Win rate threshold too high
**Check:**
```bash
grep "min_pattern_win_rate" agent/safety.py
```

**Should show:**
```python
min_pattern_win_rate: float = 40.0
```

**Fix:**
```bash
# Edit agent/safety.py line 23
min_pattern_win_rate: float = 40.0  # Lower to 40 for testing
```

#### Cause 2: No labeled patterns
**Check:**
```bash
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); r = db.query_patterns({'rsi': 50}, limit=1); print(f'Win rate: {r.get(\"win_rate\")}')"
```

**If shows "Win rate: None":**
```bash
cd intelligence
python process_historical.py  # Generate labeled patterns
```

#### Cause 3: Pattern query returns 0 results
**Check agent logs for:**
```
Similar patterns in database: 0
```

**Fix:** Lower similarity threshold or add more diverse patterns

---

## 🐛 Error: AttributeError 'PaperTradingPortfolio' object has no attribute...

### Common Variants
```
'PaperTradingPortfolio' object has no attribute 'open_positions'
'PaperTradingPortfolio' object has no attribute 'daily_pnl'
'PaperTradingPortfolio' object has no attribute 'as_dict'
```

### Root Cause
Code assumes `PortfolioState` attributes but got `PaperTradingPortfolio`.

### Attribute Comparison

| Attribute | PortfolioState | PaperTradingPortfolio |
|-----------|---------------|----------------------|
| `capital` | ✅ | ✅ |
| `open_positions` | ✅ (dict) | ❌ (use `positions` list) |
| `daily_pnl` | ✅ (float) | ❌ (calculate from `closed_trades`) |
| `positions` | ❌ | ✅ (list) |
| `closed_trades` | ❌ | ✅ (list) |
| `starting_capital` | ❌ | ✅ (float) |
| `as_dict()` | ✅ (method) | ❌ |

### Quick Fixes

#### Fix: Access open positions
```python
# ❌ WRONG
len(portfolio.open_positions)

# ✅ CORRECT
len([p for p in portfolio.positions if p.get('status') == 'OPEN'])
```

#### Fix: Get daily P&L
```python
# ❌ WRONG
portfolio.daily_pnl

# ✅ CORRECT
today = datetime.now().strftime('%Y-%m-%d')
daily_pnl = sum(
    p.get('realized_pnl', 0) 
    for p in portfolio.closed_trades 
    if p.get('exit_time', '').startswith(today)
)
```

#### Fix: Safe attribute access
```python
# Use hasattr() to check first
if hasattr(portfolio, 'open_positions'):
    count = len(portfolio.open_positions)
else:
    count = len([p for p in portfolio.positions if p.get('status') == 'OPEN'])
```

### Files to Check
1. `mcp/trading_server.py` - Methods: `get_portfolio_state()`, `check_risk_limits()`
2. `agent/safety.py` - Method: `validate_decision()`
3. `scripts/bulletproof_test.py` - Anywhere portfolio is accessed

---

## 🐛 Error: "Position size exceeds 5% of capital"

### Symptom
```
AI Decision: BUY, position_size: 500
Safety Rails: REJECTED
Reason: Position size 500 exceeds 5% of capital

[But you have R10,000 capital, so R500 = 5% should be OK!]
```

### Root Cause
MCP server has wrong portfolio (either own PortfolioState or disconnected)

### Check
```bash
# Verify portfolio passed to MCP
grep -A 2 "TradingMCPServer" scripts/bulletproof_test.py
```

### Should show
```python
mcp_server = TradingMCPServer(
    pattern_db,
    portfolio=portfolio  # ← MUST BE HERE
)
```

### Fix
**Edit scripts/bulletproof_test.py:**
```python
# Find the line creating MCP server (around line 199)
mcp_server = TradingMCPServer(
    pattern_db,
    portfolio=portfolio  # Add this parameter
)
```

### Verify Fix
```bash
python -c "
from agent.portfolio import PaperTradingPortfolio
from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer

portfolio = PaperTradingPortfolio(10000)
pattern_db = RollingWindowPatternDB()
mcp = TradingMCPServer(pattern_db, portfolio=portfolio)

assert mcp.portfolio is portfolio, 'MCP portfolio not connected!'
print('✅ Portfolio connection OK')
"
```

---

## 🐛 Error: SyntaxError or ImportError

### Symptom
```
SyntaxError: unterminated string literal (detected at line 521)
ImportError: cannot import name 'TradingAgent' from 'agent.trader'
```

### Quick Fix
```bash
# Check which file has syntax error
python -m py_compile agent/trader.py
python -m py_compile agent/portfolio.py
python -m py_compile agent/safety.py
python -m py_compile mcp/trading_server.py
```

### Common Causes
1. **Unterminated string** - Missing closing quote
2. **Mismatched brackets** - Check (), [], {}
3. **Wrong indentation** - Python is whitespace-sensitive
4. **Circular imports** - Module A imports B, B imports A

### Find Recent Changes
```bash
# Show files modified in last hour
find . -name "*.py" -mmin -60 -type f
```

### Rollback Strategy
```bash
# If you have git
git diff agent/trader.py  # See changes
git checkout agent/trader.py  # Undo changes
```

---

## 🐛 Error: AI makes BUY/SELL but no positions opened

### Symptom
```
AI Decision: BUY
Confidence: 78%
Position size: 450

[15 minutes later...]
Portfolio: Capital R10,000.00, Open Positions: 0
```

### Root Cause
Test script receives decision but doesn't execute it.

### Check
```bash
grep -n "open_position\|close_position" scripts/bulletproof_test.py
```

### Should show
```
362:            position = portfolio.open_position(
408:                portfolio.close_position(
```

### Fix
Add execution logic after decision:

```python
# In bulletproof_test.py, after getting AI decision
action = decision.get('action', 'SKIP').upper()

if action == "BUY":
    print(f"💰 EXECUTING BUY: {symbol} at {price}")
    position = portfolio.open_position(
        symbol=symbol,
        side="LONG",
        entry_price=price,
        size=decision.get('position_size', 0),
        confidence=decision.get('confidence', 0),
        reason=decision.get('reasoning', '')
    )
    if position:
        print(f"   ✅ Position opened: {position['id']}")
    else:
        print(f"   ❌ Position rejected by risk checks")

elif action == "SELL":
    print(f"💸 EXECUTING SELL: Closing all positions")
    open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']
    for pos in open_positions:
        portfolio.close_position(pos['symbol'], price, "AI SELL signal")
```

---

## 🐛 Error: Positions never close (no TP/SL)

### Symptom
Position opens but stays open forever, even when profitable or losing.

### Root Cause
No monitoring loop checking TP/SL conditions.

### Check
```bash
grep -n "TP HIT\|SL HIT" scripts/bulletproof_test.py
```

### Should show monitoring logic

### Fix
Add TP/SL monitoring after each decision:

```python
# After decision, in main loop
portfolio.update_positions({symbol: current_price})
open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']

print(f"\n🔍 Checking TP/SL conditions...")
for pos in open_positions:
    pnl_pct = pos.get('unrealized_pnl_pct', 0)
    
    # Take Profit: 2%
    if pnl_pct >= 2.0:
        print(f"   🎯 TP HIT: {pos['symbol']} at {pnl_pct:.2f}%")
        portfolio.close_position(
            pos['symbol'],
            current_price,
            f"TP hit at {pnl_pct:.2f}%"
        )
    
    # Stop Loss: -1%
    elif pnl_pct <= -1.0:
        print(f"   🛑 SL HIT: {pos['symbol']} at {pnl_pct:.2f}%")
        portfolio.close_position(
            pos['symbol'],
            current_price,
            f"SL hit at {pnl_pct:.2f}%"
        )
```

---

## 🐛 Error: Pattern DB empty or returns 0 patterns

### Symptom
```
Similar patterns in database: 0
Total patterns: 0
```

### Check DB File
```bash
ls -lh data/vector_db/chroma.sqlite3
```

**If file doesn't exist or is tiny (<100KB):** Database empty

### Fix
```bash
cd intelligence
python process_historical.py
```

This will:
1. Load historical data from CSV
2. Generate bootstrap patterns
3. Label them as WIN/LOSS/NEUTRAL
4. Store in ChromaDB

**Expected output:**
```
Processing historical data...
Generated 2,494 patterns
WIN: 831 (33.3%)
LOSS: 831 (33.3%)
NEUTRAL: 832 (33.3%)
✅ Patterns stored in database
```

### Verify
```bash
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); print(f'Patterns: {db.collection.count()}')"
```

**Should show:** `Patterns: 2494` (or similar)

---

## 🐛 Error: OpenAI API errors

### Variants
```
openai.APIConnectionError: Connection error
openai.RateLimitError: Rate limit exceeded
openai.AuthenticationError: Invalid API key
```

### Fix: Connection Error
**Check internet:**
```bash
ping -c 3 api.openai.com
```

**Check WARP VPN:**
```bash
warp-cli status
```

**If disconnected:**
```bash
warp-cli connect
```

### Fix: Rate Limit
**Wait 60 seconds, then retry**

Or increase interval between decisions:
```bash
# Use 20-minute intervals instead of 15
python bulletproof_test.py --interval 1200
```

### Fix: Invalid API Key
**Check .env file:**
```bash
grep OPENAI_API_KEY .env
```

**Should show:**
```
OPENAI_API_KEY=sk-proj-...
```

**Verify key works:**
```bash
python -c "
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
print('✅ API key valid')
"
```

---

## 🐛 Error: Test runs but makes no decisions

### Symptom
```
🚀 STARTING DECISION LOOP

[Nothing happens, no decisions printed]
```

### Possible Causes

#### Cause 1: Timeout too short
**Check:**
```python
# In bulletproof_test.py
timeout = 90  # Should be at least 60s
```

#### Cause 2: Async loop issue
**Try running without nohup:**
```bash
cd scripts
python bulletproof_test.py --duration 180 --interval 60 --capital 5000
```

Watch for errors in real-time.

#### Cause 3: Mock feed not generating data
**Check:**
```python
# In bulletproof_test.py, verify feed initialization
feed = RealisticMockFeed(symbol, initial_price=66000)
tick = feed.get_tick()
print(f"Feed price: {tick.price}")  # Should print a price
```

---

## 🐛 Dashboard shows no data

### Symptom
Dashboard runs but shows empty or stale data.

### Check Portfolio State File
```bash
ls -lh logs/portfolio_state.json
stat logs/portfolio_state.json
```

**Check last modified time** - should update when positions change.

### Check Dashboard Logs
```bash
tail -50 logs/cli_dashboard_*.log
tail -50 logs/streamlit_dashboard.log
```

### Restart Dashboards
```bash
# Kill old processes
pkill -f cli_monitor
pkill -f streamlit

# Start fresh
cd dashboard
nohup python cli_monitor.py > ../logs/cli_dashboard.log 2>&1 &

cd ../scripts
nohup streamlit run live_dashboard.py --server.port 8501 > ../logs/streamlit_dashboard.log 2>&1 &
```

### Verify Portfolio State Updates
```bash
# Run test for 3 minutes
cd scripts
python quick_validation.py --duration 180 --interval 60 --capital 5000

# Check if state file updated
stat logs/portfolio_state.json
```

---

## 🛠️ Recovery Commands

### Kill All Tests
```bash
pkill -f bulletproof_test
pkill -f quick_validation
```

### Clean Logs
```bash
rm -f logs/*.log
rm -f /tmp/test_output.log
```

### Reset Pattern DB (nuclear option)
```bash
rm -rf data/vector_db/
cd intelligence
python process_historical.py  # Rebuild from scratch
```

### Reset Portfolio State
```bash
rm -f logs/portfolio_state.json
rm -f logs/decisions.json
```

### Full Reset (start completely fresh)
```bash
# Kill all processes
pkill -f bulletproof_test
pkill -f cli_monitor
pkill -f streamlit

# Clean logs
rm -f logs/*.log

# Reset portfolio
rm -f logs/portfolio_state.json
rm -f logs/decisions.json

# Verify pattern DB
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); print(f'Patterns: {db.collection.count()}')"

# Run pre-flight check
bash docs/pre_flight_check.sh  # If you create this script
```

---

## 🔍 Debug Mode

### Enable Detailed Logging
```python
# Add to top of bulletproof_test.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Print All AI Context
```python
# In trader.py, before calling OpenAI
print("=== MARKET STATE ===")
print(json.dumps(market_state, indent=2))
print("=== PATTERNS ===")
print(json.dumps(patterns, indent=2))
print("=== PORTFOLIO ===")
print(json.dumps(portfolio, indent=2))
```

### Dry Run (No Real Decisions)
```python
# In bulletproof_test.py, replace agent call with:
decision = {
    'action': 'SKIP',
    'confidence': 0.5,
    'reasoning': 'DRY RUN MODE'
}
```

---

## 📞 When All Else Fails

### Checklist
1. ✅ Run pre-flight checklist (`docs/PRE_FLIGHT_CHECKLIST.md`)
2. ✅ Check recent git changes: `git diff`
3. ✅ Read bug history: `docs/BUG_HISTORY.md`
4. ✅ Check system architecture: `docs/SYSTEM_ARCHITECTURE.md`
5. ✅ Restart from last known good state

### Get Help
Document your issue with:
- Exact error message
- Command you ran
- Output of pre-flight checks
- Recent changes made

---

**Last Updated:** October 17, 2025  
**Covers:** 90% of common errors encountered during development
