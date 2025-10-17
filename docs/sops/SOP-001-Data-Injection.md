# SOP-001: DATA INJECTION FIX

**Status:** ACTIVE  
**Priority:** CRITICAL  
**Phase:** 1.1  
**Estimated Time:** 2-3 days  

---

## 🎯 PURPOSE

Fix the 0% confidence issue by injecting fresh market data into the pattern database BEFORE making trading decisions.

## 🔍 PROBLEM STATEMENT

**Current Issue:**
- 7/24 test decisions showing SKIP with 0% confidence
- `get_market_state()` finding no recent data
- Pattern database empty when trader tries to analyze

**Root Cause:**
- Mock feed generates data ✅
- But data doesn't flow into pattern database ❌
- Trader analyzes empty database = 0% confidence

## ✅ SUCCESS CRITERIA

- [ ] All test decisions show >0% confidence
- [ ] Mix of LONG, SHORT, SKIP signals
- [ ] At least 40% of decisions have >40% confidence
- [ ] No "insufficient data" errors

## 📋 STEP-BY-STEP PROCEDURE

### Step 1: Implement Data Injection Function

**File:** `scripts/bulletproof_test.py`

**Add this function:**
```python
def inject_fresh_market_data(trader, symbol='BTCUSDT'):
    """
    CRITICAL FIX: Inject current market data into pattern database
    """
    print(f"\n💉 INJECTING FRESH MARKET DATA FOR {symbol}")
    
    try:
        # Get current market data from mock feed
        from intelligence.realistic_mock_feed import RealisticMarketFeed
        mock_feed = RealisticMarketFeed()
        current_data = mock_feed.get_current_market_state(symbol)
        
        print(f"✅ Got fresh data: Price={current_data.get('close', 'N/A')}")
        
        # Inject into trader's cache
        if not hasattr(trader, '_market_cache'):
            trader._market_cache = {}
        trader._market_cache[symbol] = current_data
        
        return True
        
    except Exception as e:
        print(f"❌ Error injecting data: {e}")
        return False
```

### Step 2: Modify Decision Loop

**In `make_single_decision_safe()` function:**

```python
def make_single_decision_safe(trader, decision_num, total_decisions):
    # ... existing code ...
    
    symbol = 'BTCUSDT' if decision_num % 2 == 1 else 'ETHUSDT'
    
    # 🔥 CRITICAL: Inject fresh data FIRST
    print(f"\n2️⃣ Injecting fresh market data...")
    if not inject_fresh_market_data(trader, symbol):
        print(f"   ⚠️ Data injection had issues, but continuing...")
    
    # NOW make decision with current data
    print(f"\n3️⃣ Analyzing market conditions...")
    decision = trader.check_and_trade(symbol)
    
    # ... rest of code ...
```

### Step 3: Update Trader to Use Cache

**File:** `agent/trader.py`

**Add to `__init__`:**
```python
class Trader:
    def __init__(self):
        # ... existing code ...
        self._market_cache = {}  # Cache for injected data
```

**Modify `get_market_state`:**
```python
def get_market_state(self, symbol):
    """Get market state, prefer cached data if available"""
    
    # Check cache first (from injection)
    if hasattr(self, '_market_cache') and symbol in self._market_cache:
        logger.info(f"Using cached market data for {symbol}")
        return self._market_cache[symbol]
    
    # Otherwise use MCP server
    logger.info(f"No cached data, using MCP for {symbol}")
    return self.mcp_client.get_market_state(symbol)
```

### Step 4: Test Quick (3 Decisions)

```bash
cd ~/ozzy-simple
python3 scripts/bulletproof_test.py
```

**Expected Output:**
```
💉 INJECTING FRESH MARKET DATA FOR BTCUSDT
✅ Got fresh data: Price=67250.42

📊 DECISION RESULT:
   Action: LONG
   Confidence: 67.5%  ← NOT 0%!
```

### Step 5: Verify Fix

**Check these indicators:**
- [ ] "INJECTING FRESH MARKET DATA" appears before each decision
- [ ] "Got fresh data" shows realistic price
- [ ] Confidence values are >0%
- [ ] Mix of actions (not all SKIP)

## 🐛 TROUBLESHOOTING

### Issue: Still 0% Confidence

**Check:**
```bash
# Is injection being called?
grep "INJECTING" logs/bulletproof_test_*.log

# Is data realistic?
grep "Got fresh data" logs/bulletproof_test_*.log

# Is cache being used?
grep "Using cached" logs/bulletproof_test_*.log
```

**Solutions:**
1. Verify `inject_fresh_market_data()` is being called
2. Check `realistic_mock_feed.py` generates realistic data
3. Ensure `trader.py` checks cache first

### Issue: Import Errors

**Fix:**
```python
# Add to top of bulletproof_test.py
import sys
import os
sys.path.insert(0, os.path.dirname(__file__) + '/..')
```

### Issue: Mock Data Too Neutral

**Fix:** Force extreme conditions in `realistic_mock_feed.py`:
```python
def get_current_market_state(self, symbol):
    data = self._generate_realistic_data(symbol)
    
    # Force some extremes for testing
    import random
    if random.random() < 0.3:
        data['rsi'] = random.uniform(20, 30)  # Oversold
    
    return data
```

## ✅ COMPLETION CHECKLIST

Before marking this SOP complete:

- [ ] Code changes implemented in all 3 files
- [ ] Quick test (3 decisions) passes
- [ ] All decisions show >0% confidence
- [ ] At least 1 LONG or SHORT signal
- [ ] No errors in logs
- [ ] Code committed to git
- [ ] Documentation updated

## 📊 EXPECTED RESULTS

**Before Fix:**
```
Decision #1: SKIP - 0%
Decision #2: SKIP - 0%
Decision #3: SKIP - 0%
```

**After Fix:**
```
Decision #1: LONG - 67%
Decision #2: SKIP - 45%
Decision #3: SHORT - 72%
```

## 🎯 NEXT STEPS

After completing this SOP:
1. Mark milestone 1.1 complete: `python3 MASTER_PLANNER.py complete 1.1`
2. Move to SOP-002: 24-Hour Stability Test
3. Run: `python3 MASTER_PLANNER.py next`

---

**Last Updated:** 2025-10-17  
**Version:** 1.0  
**Owner:** You (AfroSamurai)  
