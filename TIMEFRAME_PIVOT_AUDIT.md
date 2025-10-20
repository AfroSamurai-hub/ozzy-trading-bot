# ⏱️ TIMEFRAME PIVOT AUDIT - 15-Minute → 4-Hour+ Migration

**Date:** October 18, 2025  
**Priority:** CRITICAL  
**Status:** Initial audit complete

## 🚨 CRITICAL FINDING

Current system is configured for **15-minute trading** which research shows is **financially unviable** for R5K-R10K accounts due to 16% monthly fee burn.

**Action Required:** Migrate all timeframe references from 15-minute to 4-hour+ intervals.

---

## 📋 AUDIT RESULTS

### ✅ Files Searched
- Total workspace files: 500+
- Pattern matches found: 200+
- Critical files identified: 12

### 🔍 Current State Analysis

**1. Decision Intervals (PRIMARY CONCERN)**
- `scripts/test_live_stream.py` line 759: `--decision-interval` default (needs verification)
- `scripts/bulletproof_test.py` line 684: Default = 900s (15 minutes) ❌
- `scripts/quick_validation.py` line 146: Default = 60s (1 minute) ❌
- `.env` line 14: `DECISION_INTERVAL=60` ❌
- Documentation references: 900s (15 minutes) throughout

**2. Candle Intervals**
- `scripts/download_historical.py` line 118: Default = 5 minutes
- `scripts/backtest_with_learning.py` line 54: Default = "15" minutes ❌
- `scripts/production_backtest.py` line 54: `self.interval_minutes = 15` ❌
- `scripts/backtest_with_confirmations.py` line 90: interval = "15" ❌

**3. Research/Documentation References**
- `RESEARCH_IMPROVEMENTS_IMPLEMENTED.txt`: Multiple 15-min references
- `OVERNIGHT_TEST_STARTED.txt`: "Research-Optimal: 15-Minute Decision Interval"
- `R10K_VALIDATION_TEST_STARTED.md`: 900s (15 minutes)
- Research document: 60+ references to "15-minute trading"

**4. Comments/Constants**
- `scripts/test_live_stream.py` line 179: "Confidence Threshold for 15-min timeframe"
- `scripts/test_live_stream.py` line 332: "Take profit at +3.5% (adjusted for 15-min timeframe)"
- `RESEARCH_FINDINGS_CRYPTOCURRENCY_TRADING.md`: "15-minute trading is FINANCIALLY UNVIABLE"
- `ozzy.py` line 325: `interval_mins = 15  # 15-minute intervals`

---

## 🎯 RECOMMENDED CHANGES

### Phase 1: Core Configuration (IMMEDIATE)

1. **`.env` File**
   ```bash
   # OLD: DECISION_INTERVAL=60
   # NEW: DECISION_INTERVAL=14400  # 4 hours
   ```

2. **`scripts/bulletproof_test.py`**
   ```python
   # Line 684: OLD
   parser.add_argument('--interval', type=int, default=900, help='Decision interval in seconds (default: 900 = 15 minutes, less noisy)')
   
   # Line 684: NEW
   parser.add_argument('--interval', type=int, default=14400, help='Decision interval in seconds (default: 14400 = 4 hours, optimal for small accounts)')
   ```

3. **`scripts/quick_validation.py`**
   ```python
   # Line 146: OLD
   parser.add_argument("--interval", type=int, default=60, help="Decision interval in seconds (default 60 -> 1m timeframe)")
   
   # Line 146: NEW
   parser.add_argument("--interval", type=int, default=14400, help="Decision interval in seconds (default 14400 -> 4h timeframe)")
   ```

4. **`scripts/backtest_with_learning.py`**
   ```python
   # Line 54: OLD
   def __init__(self, symbol: str, start_date: str, end_date: str, interval: str = "15"):
   
   # Line 54: NEW
   def __init__(self, symbol: str, start_date: str, end_date: str, interval: str = "240"):  # 240 minutes = 4 hours
   ```

5. **`scripts/production_backtest.py`**
   ```python
   # Line 54: OLD
   self.interval_minutes = 15
   
   # Line 54: NEW
   self.interval_minutes = 240  # 4 hours
   ```

6. **`scripts/backtest_with_confirmations.py`**
   ```python
   # Line 90: OLD
   "interval": "15",
   
   # Line 90: NEW
   "interval": "240",  # 4 hours
   ```

### Phase 2: Strategic Constants (HIGH PRIORITY)

7. **`ozzy.py`**
   ```python
   # Line 325: OLD
   interval_mins = 15  # 15-minute intervals
   
   # Line 325: NEW
   interval_mins = 240  # 4-hour intervals (swing trading)
   ```

8. **`scripts/test_live_stream.py`**
   - Line 179: Update comment from "15-min timeframe" to "4-hour timeframe"
   - Line 332: Update TP percentage (currently 3.5% for 15-min, may need adjustment for 4H)

### Phase 3: Documentation Updates (MEDIUM PRIORITY)

9. **Update All Documentation Files**
   - `RESEARCH_IMPROVEMENTS_IMPLEMENTED.txt`
   - `OVERNIGHT_TEST_STARTED.txt`
   - `R10K_VALIDATION_TEST_STARTED.md`
   - `ALL_FIXES_COMPLETE.md`
   - `WEBSOCKET_FIXED_READY.md`
   - `OVERNIGHT_TEST_RUNNING.md`
   - `DEPLOYMENT_GUIDE.md`
   - `DUAL_TIMEFRAME_SETUP.md`

   Replace references to:
   - "15-minute trading" → "4-hour swing trading"
   - "900 seconds" → "14400 seconds"
   - "15-min intervals" → "4-hour intervals"

10. **Update Master Planner**
    - Already contains research findings ✅
    - Add implementation task tracking

---

## 📊 IMPACT ANALYSIS

### Trading Frequency
```
BEFORE (15-minute):
- Decisions per day: 96
- Trades per month (30% signal rate): ~864
- Estimated executions: 80-100/month
- Monthly fees @ 0.20%: R1,600 (16% of R10K)

AFTER (4-hour):
- Decisions per day: 6
- Trades per month (30% signal rate): ~54
- Estimated executions: 10-15/month
- Monthly fees @ 0.20%: R200-400 (2-4% of R10K)

FEE REDUCTION: 87.5% 🎯
```

### Win Rate Requirements
```
BEFORE (15-minute):
- Required WR to break even: 65-70%
- Current baseline: 51.2%
- Monthly outcome: GUARANTEED LOSS

AFTER (4-hour):
- Required WR to break even: 50-55%
- Current baseline: 51.2%
- Monthly outcome: VIABLE PATH TO PROFIT ✅
```

### Confirmation Check Timing
```
BEFORE (15-minute):
- Pattern formation: 5-10 ticks
- Average hold time: 1-3 hours
- TP target: +3.5%

AFTER (4-hour):
- Pattern formation: 5-10 ticks (same)
- Average hold time: 1-5 days (longer swing)
- TP target: TBD (may increase to +5-10%)
```

---

## ⚠️ CRITICAL CONSIDERATIONS

### 1. Take Profit / Stop Loss Adjustments
**Current settings calibrated for 15-minute volatility:**
- TP: +3.5% (designed for quick scalps)
- SL: -1.5% (tight stops)

**Need to adjust for 4-hour swings:**
- TP: +5-10% (allow longer moves)
- SL: -3-5% (wider stops for volatility)
- Trailing stop: Consider 15-20% trailing (Kaminski & Lo research)

**Action:** Create new risk parameters for 4H timeframe

### 2. Pattern Recognition
**15-minute patterns vs 4-hour patterns:**
- Same technical patterns (engulfing, hammer, etc.)
- But different scale and confirmation requirements
- May need longer lookback periods

**Action:** Test pattern performance on 4H data

### 3. Confirmation Checks
**Current checks may need recalibration:**
- Volume confirmation thresholds
- RSI oversold/overbought levels (more time to develop)
- Trend alignment (higher timeframe more reliable)
- Support/resistance levels (stronger on 4H)

**Action:** Run backtest on 4H data to validate checks

### 4. Backtesting Strategy
**Need historical 4-hour data:**
- Currently testing on 15-minute data
- Need to download 4H candles from Bybit
- Minimum 90 days (540 4H candles)
- Ideal: 1 year (2,190 4H candles)

**Action:** Update download scripts to fetch 4H candles

---

## 🔧 IMPLEMENTATION PLAN

### Week 1: Data & Configuration
- [ ] Update `.env` to 14400s interval
- [ ] Update all script defaults to 4H
- [ ] Download 1 year of 4H historical data
- [ ] Update backtest scripts to use 4H candles

### Week 2: Risk Parameter Calibration
- [ ] Research 4H volatility patterns
- [ ] Calculate appropriate TP/SL for 4H swings
- [ ] Update `scripts/test_live_stream.py` risk params
- [ ] Test new parameters in backtest

### Week 3: Confirmation Validation
- [ ] Run full backtest on 4H data (90 days)
- [ ] Analyze confirmation check performance
- [ ] Adjust volume/RSI thresholds if needed
- [ ] Calculate new baseline WR on 4H

### Week 4: Integration & Testing
- [ ] Update all documentation
- [ ] Run 24-hour live test with 4H intervals
- [ ] Verify fee calculations correct
- [ ] Confirm trade frequency ~2-3 per week

---

## 📁 FILES REQUIRING CHANGES

### CRITICAL (Must Change)
1. `.env` - DECISION_INTERVAL
2. `scripts/bulletproof_test.py` - default interval
3. `scripts/quick_validation.py` - default interval
4. `scripts/backtest_with_learning.py` - candle interval
5. `scripts/production_backtest.py` - interval_minutes
6. `scripts/backtest_with_confirmations.py` - interval
7. `ozzy.py` - interval_mins constant
8. `scripts/test_live_stream.py` - comments and TP percentage

### HIGH PRIORITY (Should Change)
9. `MASTER_PLANNER.py` - already has research findings, add implementation tasks
10. `scripts/download_historical.py` - add 4H interval option
11. `agent/pattern_builder.py` - verify interval_seconds handling
12. `stream/realistic_mock_feed.py` - verify tick generation for 4H patterns

### MEDIUM PRIORITY (Nice to Have)
13-30. All documentation files with 15-min references

---

## ✅ VALIDATION CRITERIA

**Before declaring pivot complete:**

1. ✅ All core scripts default to 14400s (4H)
2. ✅ All backtests running on 4H candles
3. ✅ Risk parameters calibrated for 4H volatility
4. ✅ Confirmation checks validated on 4H data
5. ✅ Baseline WR calculated on 4H timeframe
6. ✅ Trade frequency ~2-3 per week confirmed
7. ✅ Fee burn reduced to <R500/month
8. ✅ Documentation updated with new timeframe
9. ✅ Live test successful (24 hours, 4H intervals)
10. ✅ Master planner milestone 1.2.7 complete

---

## 🎯 SUCCESS METRICS

**3-Month Target (4H Timeframe):**
- Trades per month: 10-15
- Win rate: >52% (above current 51.2% baseline)
- Monthly fees: <R400 (4% of account)
- Sharpe ratio: >0.5
- Max drawdown: <15%
- Monthly return: 3-5% (R300-500 on R10K)

**If we achieve 55% WR on 4H:**
- 55% × 15 trades = 8.25 wins
- 45% × 15 trades = 6.75 losses
- Assume +7% avg win, -4% avg loss
- Gross: (8.25 × 7%) - (6.75 × 4%) = 57.75% - 27% = 30.75% monthly ❌ (unrealistic)
- More realistic: +5% avg win, -3% avg loss
- Gross: (8.25 × 5%) - (6.75 × 3%) = 41.25% - 20.25% = 21% monthly
- Less fees (R400 = 4%): 21% - 4% = 17% monthly ✅ INCREDIBLE
- Conservative estimate: 5-10% monthly realistic

---

## 📝 NEXT STEPS

1. **Get User Approval** - Confirm 4H+ timeframe pivot
2. **Start with Backtest** - Download 4H data, run backtest
3. **Calibrate Risk Params** - Adjust TP/SL for 4H volatility
4. **Update Core Scripts** - Change all defaults to 14400s
5. **Validate Performance** - Ensure >50% WR on 4H data
6. **Update Documentation** - Comprehensive timeframe references
7. **Live Test** - 24-hour test with 4H intervals
8. **Paper Trading** - 1 week on 4H to confirm viability

**Status:** ⏳ Awaiting user decision to proceed with pivot

