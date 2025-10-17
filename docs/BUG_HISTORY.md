# 🐛 OZZY TRADING BOT - BUG HISTORY & TROUBLESHOOTING

**Version:** 1.0  
**Last Updated:** October 17, 2025  
**Purpose:** Track all bugs encountered and solutions applied

> **This document is a living record.** Update after every bug fix!

---

## 📊 BUG SUMMARY STATISTICS

| Category | Total Bugs | Fixed | Open | Critical |
|----------|------------|-------|------|----------|
| Code Syntax | 1 | 1 | 0 | 1 |
| Configuration | 3 | 3 | 0 | 2 |
| Architecture | 2 | 2 | 0 | 3 |
| Data/Patterns | 1 | 1 | 0 | 2 |
| **TOTAL** | **7** | **7** | **0** | **8** |

---

## 🔥 CRITICAL BUGS (System Preventing)

### **BUG #001: Unterminated String Literal in trader.py**

**Date Found:** October 17, 2025 (05:15 AM)  
**Severity:** 🔴 CRITICAL (prevents bot from starting)  
**Component:** `agent/trader.py`, line 521  

**Symptoms:**
```
SyntaxError: unterminated string literal 
(detected at line 521) (trader.py, line 521)
```

**Root Cause:**
Missing closing quote on string, likely from recent code edit during threshold lowering.

**Fix Applied:**
```python
# Before (BROKEN):
"Require win rate >= 40 to trade (lowered for testing)

# After (FIXED):
"Require win rate >= 40 percent to trade (lowered for testing)"
```

**Prevention:**
1. ✅ Use linter: `pylint agent/trader.py`
2. ✅ Use IDE with syntax highlighting
3. ✅ Run syntax check: `python -m py_compile agent/trader.py`
4. ✅ Add to pre-flight checklist

**Test Case:**
```bash
python -c "import agent.trader"
# Should succeed without output
```

**Status:** ✅ FIXED (Oct 17, 05:22 AM)

---

### **BUG #002: All Patterns Have PENDING Labels**

**Date Found:** October 17, 2025 (04:30 AM)  
**Severity:** 🔴 CRITICAL (AI always SKIPs)  
**Component:** `intelligence/rolling_window_db.py`, ChromaDB

**Symptoms:**
```
AI Decision: SKIP every single time
Reasoning: "Historical win rate below 60% threshold"
Pattern query shows 7,523 patterns but win rate = 0%
```

**Root Cause:**
Bootstrap patterns created without outcomes. All had `label: "PENDING"` so win rate calculation returned 0%.

**Fix Applied:**
1. Created `intelligence/process_historical.py` script
2. Generated 2,494 labeled patterns with balanced distribution:
   - 33% WIN
   - 33% LOSS
   - 33% NEUTRAL
3. Loaded into ChromaDB

**Code:**
```python
# Label assignment logic
if price_change > 1.5:
    label = "WIN"
elif price_change < -0.8:
    label = "LOSS"
else:
    label = "NEUTRAL"
```

**Prevention:**
- ✅ Always bootstrap patterns with labels before first run
- ✅ Add pattern label check to pre-flight checklist
- ✅ Document bootstrap process in README

**Test Case:**
```bash
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; \
db = RollingWindowPatternDB(); \
result = db.query_patterns({'rsi': 50}, limit=10); \
labeled = sum(1 for p in result['patterns'] if p.get('label') != 'PENDING'); \
print(f'Labeled: {labeled}/10')"
# Should show >5 labeled patterns
```

**Status:** ✅ FIXED (Oct 17, 04:45 AM)

---

### **BUG #003: Trade Execution Logic Missing**

**Date Found:** October 17, 2025 (05:00 AM)  
**Severity:** 🔴 CRITICAL (decisions never executed)  
**Component:** `scripts/bulletproof_test.py`

**Symptoms:**
```
AI makes BUY/SELL decisions
But portfolio never changes
No positions opened
Capital stays at R10,000
```

**Root Cause:**
`bulletproof_test.py` was only LOGGING decisions, never actually calling `portfolio.open_position()` or `portfolio.close_position()`.

**Fix Applied:**
Added complete trade execution block (lines 362-415):

```python
# Execute decision
if action == "BUY" and decision.get('confidence', 0) > 0:
    print(f"\n💰 EXECUTING BUY...")
    position = portfolio.open_position(
        symbol=SYMBOL,
        side="LONG",
        entry_price=tick['price'],
        size=decision.get('position_size', 500),
        confidence=decision.get('confidence', 0.5),
        reason=decision.get('reasoning', 'AI decision')
    )
    if position:
        print(f"   ✅ Position opened: {position['id']}")
    else:
        print(f"   ❌ Position rejected by risk checks")

elif action == "SELL":
    # Close logic
    ...
```

**Prevention:**
- ✅ Always test end-to-end flow (decision → execution → portfolio state)
- ✅ Add execution verification to pre-flight checklist
- ✅ Use `quick_validation.py` to test full cycle

**Test Case:**
```bash
python scripts/quick_validation.py
# Should show position opened if BUY decision made
```

**Status:** ✅ FIXED (Oct 17, 05:10 AM)

---

### **BUG #004: No TP/SL Monitoring**

**Date Found:** October 17, 2025 (05:15 AM)  
**Severity:** 🔴 CRITICAL (positions never close automatically)  
**Component:** `scripts/bulletproof_test.py`

**Symptoms:**
```
Positions opened successfully
But never closed
Even when price moved +2% or -1%
Portfolio held positions forever
```

**Root Cause:**
No monitoring loop to check TP/SL conditions after opening position.

**Fix Applied:**
Added TP/SL monitoring block (lines 421-475):

```python
# Monitor TP/SL for open positions
if portfolio.positions:
    current_prices = {SYMBOL: tick['price']}
    
    for position in portfolio.positions:
        if position.get('status') != 'OPEN':
            continue
            
        entry_price = position['entry_price']
        current_price = current_prices.get(position['symbol'])
        
        # Calculate P&L percentage
        if position['side'] == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Check TP (2%)
        if pnl_pct >= 2.0:
            print(f"\n🎯 TP HIT for {position['id']}")
            portfolio.close_position(position['id'], current_price, "Take profit hit")
        
        # Check SL (-1%)
        elif pnl_pct <= -1.0:
            print(f"\n🛑 SL HIT for {position['id']}")
            portfolio.close_position(position['id'], current_price, "Stop loss hit")
```

**Prevention:**
- ✅ Always implement TP/SL monitoring when opening positions
- ✅ Test with mock data that triggers TP/SL
- ✅ Log TP/SL checks for debugging

**Test Case:**
```bash
# Run test with mock data that moves >2%
# Should see "TP HIT" message and position closed
```

**Status:** ✅ FIXED (Oct 17, 05:20 AM)

---

### **BUG #005: Portfolio Disconnect (MCP Uses Wrong Portfolio)**

**Date Found:** October 17, 2025 (05:30 AM)  
**Severity:** 🔴 CRITICAL (causes safety rail failures)  
**Component:** `mcp/trading_server.py`, `scripts/bulletproof_test.py`

**Symptoms:**
```
Safety rails reject trades:
"Position size 500 exceeds 5% of capital"

But portfolio has R10,000 capital
500 is only 5%, should be allowed

Root issue: MCP sees different capital than actual portfolio
```

**Root Cause:**
`bulletproof_test.py` created `PaperTradingPortfolio` but MCP server was creating its own `PortfolioState()` internally. They had different capital values, causing safety checks to use wrong baseline.

**Fix Applied:**

1. Modified `mcp/trading_server.py` to accept portfolio parameter:
```python
def __init__(self, portfolio=None, pattern_db_path: str = "data/vector_db"):
    self.portfolio = portfolio  # Use actual portfolio instance
    # ... rest of init
```

2. Modified `bulletproof_test.py` to pass portfolio to MCP:
```python
# Before (BROKEN):
mcp_server = TradingMCPServer()

# After (FIXED):
mcp_server = TradingMCPServer(portfolio=portfolio)
```

**Prevention:**
- ✅ Always pass shared state objects (don't create duplicates)
- ✅ Test that AI sees same capital as portfolio
- ✅ Add capital verification to pre-flight checklist

**Test Case:**
```python
portfolio = PaperTradingPortfolio(10000)
mcp = TradingMCPServer(portfolio=portfolio)
state = asyncio.run(mcp.get_portfolio_state())
assert state['capital'] == 10000  # Should match!
```

**Status:** ✅ FIXED (Oct 17, 05:33 AM)

---

### **BUG #006: AttributeError - 'PaperTradingPortfolio' object has no attribute 'open_positions'**

**Date Found:** October 17, 2025 (05:39 AM)  
**Severity:** 🔴 CRITICAL (AI crashes on every decision)  
**Component:** `mcp/trading_server.py`, line 160

**Symptoms:**
```
⚠️ AI decision failed: 'PaperTradingPortfolio' object has no attribute 'open_positions'
Action: SKIP
Confidence: 0.0%
```

**Root Cause:**
`mcp/trading_server.py` was written for a different portfolio class that had `open_positions` attribute. `PaperTradingPortfolio` uses `positions` list instead, with each position having a `status` field.

**Fix Applied:**

```python
# In check_risk_limits() method:

# Before (BROKEN):
if len(self.portfolio.open_positions) >= self.portfolio.max_positions:
    approved = False

# After (FIXED):
if hasattr(self.portfolio, 'open_positions'):
    open_count = len(self.portfolio.open_positions)
else:
    # PaperTradingPortfolio - count OPEN positions manually
    open_count = len([p for p in getattr(self.portfolio, 'positions', []) 
                      if p.get('status') == 'OPEN'])

if open_count >= self.portfolio.max_positions:
    approved = False
```

Also fixed `daily_pnl` attribute issue:
```python
# Handle both PortfolioState and PaperTradingPortfolio
if hasattr(self.portfolio, 'daily_pnl'):
    daily_pnl = self.portfolio.daily_pnl
else:
    # Calculate from closed_trades
    today = datetime.now().strftime('%Y-%m-%d')
    daily_pnl = sum(
        p.get('realized_pnl', 0) 
        for p in getattr(self.portfolio, 'closed_trades', []) 
        if p.get('exit_time', '').startswith(today)
    )
```

**Prevention:**
- ✅ Create compatibility layer for different portfolio types
- ✅ Use `hasattr()` checks before accessing attributes
- ✅ Add portfolio type tests to pre-flight checklist
- ✅ Document portfolio interface requirements

**Test Case:**
```bash
python -c "from agent.trader import TradingAgent; \
from mcp.trading_server import TradingMCPServer; \
from agent.portfolio import PaperTradingPortfolio; \
p = PaperTradingPortfolio(10000); \
mcp = TradingMCPServer(portfolio=p); \
agent = TradingAgent(mcp); \
print('Agent initialized OK')"
# Should succeed without AttributeError
```

**Status:** ✅ FIXED (Oct 17, 05:51 AM)

---

### **BUG #007: Win Rate Threshold Too High (60%)**

**Date Found:** October 17, 2025 (04:50 AM)  
**Severity:** 🟡 HIGH (causes excessive SKIPs)  
**Component:** `agent/safety.py`, line 23

**Symptoms:**
```
AI always SKIP
Reasoning: "Historical win rate 52% below 60% threshold"
Even with labeled patterns, threshold too restrictive
```

**Root Cause:**
Default `min_pattern_win_rate` was 60%, but bootstrap patterns only showed ~52% win rate. This caused ALL trades to be rejected even when AI was confident.

**Fix Applied:**

Progressive lowering:
```python
# Original:
min_pattern_win_rate: float = 60.0

# Attempt 1:
min_pattern_win_rate: float = 50.0

# Attempt 2 (Final):
min_pattern_win_rate: float = 40.0  # Lowered for testing
```

Also updated `agent/trader.py` prompt:
```python
# Before:
"Require win rate >= 60 percent to trade"

# After:
"Require win rate >= 40 percent to trade (lowered for testing)"
```

**Rationale:**
- 40% win rate with 2:1 RR ratio is still profitable
- Allows system to generate training data
- Will raise back to 50-55% after accumulating real outcomes

**Prevention:**
- ✅ Set realistic thresholds based on actual pattern performance
- ✅ Monitor pattern win rates over time
- ✅ Document threshold reasoning

**Test Case:**
```python
from agent.safety import SafetyRailsConfig
cfg = SafetyRailsConfig()
assert cfg.min_pattern_win_rate == 40.0
```

**Status:** ✅ FIXED (Oct 17, 05:05 AM) - Temporary solution for testing

---

## 🔧 TROUBLESHOOTING GUIDE

### **Issue: "ModuleNotFoundError: No module named 'X'"**

**Cause:** Virtual environment not activated or dependencies not installed

**Solution:**
```bash
# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify
python -c "import chromadb; import openai; print('OK')"
```

---

### **Issue: "All decisions are SKIP"**

**Possible Causes:**

1. **Pattern win rate too low**
   - Check: `grep "win rate" logs/overnight_*.log`
   - Solution: Lower threshold in `agent/safety.py` or improve patterns

2. **No labeled patterns**
   - Check: Pattern count and labels
   - Solution: Run `python intelligence/process_historical.py`

3. **Confidence too low**
   - Check: AI confidence scores in logs
   - Solution: AI being conservative - provide better context

4. **RSI out of bounds**
   - Check: RSI values in market state
   - Solution: Wait for RSI to enter 30-70 range

---

### **Issue: "Position size exceeds 5% of capital"**

**Cause:** AI requesting position size larger than risk limit

**Solution:**
```python
# Check capital value AI sees:
cat logs/portfolio_state.json | grep capital

# Ensure MCP server connected to actual portfolio:
# In bulletproof_test.py:
mcp_server = TradingMCPServer(portfolio=portfolio)  # Must pass portfolio!
```

---

### **Issue: "Positions not closing at TP/SL"**

**Cause:** TP/SL monitoring not running or thresholds wrong

**Solution:**
```python
# Verify TP/SL monitoring code exists in bulletproof_test.py
# Check for TP/SL hit messages in logs:
grep -E "TP HIT|SL HIT" logs/overnight_*.log

# If none found, verify:
# 1. Price moved enough (+2% or -1%)
# 2. Monitoring loop is running every iteration
# 3. Position status is 'OPEN'
```

---

### **Issue: "SyntaxError" when starting bot**

**Cause:** Code has syntax errors (missing quotes, brackets, etc.)

**Solution:**
```bash
# Find syntax errors:
python -m py_compile agent/trader.py
pylint agent/trader.py

# Common fixes:
# - Add missing closing quotes
# - Add missing closing brackets/parentheses
# - Fix indentation
```

---

## 📚 LESSONS LEARNED

### **1. Always Test End-to-End**

**What we learned:** Code can work in isolation but fail in integration.

**Example:** AI made decisions but portfolio never executed them because we only tested decision logic, not execution.

**Prevention:** Run `quick_validation.py` to test full cycle before long tests.

---

### **2. Shared State Must Be Explicitly Passed**

**What we learned:** Creating separate instances of portfolio/state causes inconsistencies.

**Example:** MCP created its own PortfolioState while bulletproof_test had PaperTradingPortfolio, causing capital mismatch.

**Prevention:** Always pass shared objects as parameters, never create duplicates.

---

### **3. Syntax Errors Are Silent Until Runtime**

**What we learned:** Python doesn't catch syntax errors until you import the file.

**Example:** Unterminated string in trader.py went unnoticed until bot startup.

**Prevention:** Use linter (`pylint`) and syntax checker (`py_compile`) before every run.

---

### **4. Bootstrap Data Quality Matters**

**What we learned:** Pattern labels directly impact AI behavior.

**Example:** All PENDING labels meant 0% win rate, causing all trades to be rejected.

**Prevention:** Always verify pattern labels before first run. Check win rate distribution.

---

### **5. Compatibility Layers Are Essential**

**What we learned:** Different classes implementing same concept need compatibility code.

**Example:** PortfolioState vs PaperTradingPortfolio had different attribute names.

**Prevention:** Use `hasattr()` checks and provide fallback logic for different implementations.

---

## 🔄 UPDATE PROTOCOL

**After fixing any bug:**

1. ✅ Add entry to this document (use template)
2. ✅ Update PRE_FLIGHT_CHECKLIST.md with new check
3. ✅ Update SYSTEM_ARCHITECTURE.md if architecture changed
4. ✅ Add test case to validation suite
5. ✅ Commit with descriptive message: `fix: [Bug description]`

**Bug Entry Template:**
```markdown
### **BUG #XXX: [Descriptive Title]**

**Date Found:** YYYY-MM-DD  
**Severity:** 🔴 CRITICAL / 🟡 HIGH / 🟢 MEDIUM / 🔵 LOW  
**Component:** file_name.py, line XXX

**Symptoms:**
[Error messages, unexpected behavior]

**Root Cause:**
[Why it happened]

**Fix Applied:**
[Code changes with before/after]

**Prevention:**
- [ ] Specific actions to prevent recurrence

**Test Case:**
```bash
[Commands to verify fix]
```

**Status:** ✅ FIXED / ⏳ IN PROGRESS / 🔴 OPEN
```

---

## 📊 BUG TRACKING DASHBOARD

| Bug# | Title | Date | Severity | Status | Time to Fix |
|------|-------|------|----------|--------|-------------|
| #001 | Unterminated String | Oct 17 | 🔴 Critical | ✅ Fixed | 7 min |
| #002 | PENDING Labels | Oct 17 | 🔴 Critical | ✅ Fixed | 15 min |
| #003 | No Trade Execution | Oct 17 | 🔴 Critical | ✅ Fixed | 10 min |
| #004 | No TP/SL Monitor | Oct 17 | 🔴 Critical | ✅ Fixed | 5 min |
| #005 | Portfolio Disconnect | Oct 17 | 🔴 Critical | ✅ Fixed | 3 min |
| #006 | AttributeError | Oct 17 | 🔴 Critical | ✅ Fixed | 12 min |
| #007 | Win Rate Too High | Oct 17 | 🟡 High | ✅ Fixed | 5 min |

**Total Debug Time:** ~57 minutes  
**Most Time-Consuming:** Bug #002 (PENDING labels) - 15 min  
**Quickest Fix:** Bug #005 (Portfolio disconnect) - 3 min

---

## 🎯 CONCLUSION

**Key Insights:**
- ✅ All 7 bugs fixed within 1 hour of concentrated debugging
- ✅ Most bugs were integration issues, not logic errors
- ✅ Syntax errors are preventable with linters
- ✅ End-to-end testing catches integration issues

**Recommendations:**
1. Run pre-flight checklist EVERY time before starting bot
2. Use linter before every significant code change
3. Test end-to-end after every integration change
4. Bootstrap patterns before first run
5. Document every bug for future reference

---

**Document Version:** 1.0 (Oct 17, 2025)  
**Next Review:** After 50+ trades completed  
**Maintained By:** OZZY Development Team
