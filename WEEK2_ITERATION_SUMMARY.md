# Week 2 Validation - Iteration Summary

## Overview
Testing 4-hour timeframe pivot with pattern-based trading strategy on 366 days of BTC/USDT data (Oct 2024 - Oct 2025).

**Target Metrics:**
- Trading Frequency: 10-15 trades/month
- Win Rate: ≥50%
- Monthly Fees: <$400
- Positive returns

## Iteration Results

### Iteration 1: Too Conservative
**Configuration:**
- Pattern Detection: Strict (pattern + trend + volume required)
- No RSI filters
- No cooldown

**Results:**
- Trades: 2 in 366 days (0.2/month)
- Win Rate: 0% (both timeout)
- Monthly Fees: $0.07
- Return: -0.01%

**Verdict:** ❌ Too strict - barely any trades

---

### Iteration 2: Too Aggressive
**Configuration:**
- Pattern Detection: Relaxed (added pullback to SMA10, removed volume requirement)
- No RSI filters
- No cooldown

**Results:**
- Trades: 419 in 366 days (34.3/month)
- Win Rate: 42%
- Monthly Fees: $5,582
- Return: +341,249% (unrealistic due to compounding bug)
- Avg Win/Loss: 2.33:1

**Verdict:** ❌ Overtrading - 14x over fee target

---

### Iteration 3A: Too Strict with Optimizations
**Configuration:**
- Cooldown: 3 candles (12 hours)
- RSI Oversold: < 40
- RSI Overbought: > 60
- Min ATR: > 1.0%
- Fixed position sizing (2% of initial capital)

**Results:**
- Trades: 0 in 366 days
- Win Rate: N/A
- Monthly Fees: $0
- Return: 0%

**Verdict:** ❌ Filters too strict - no trades executed

---

### Iteration 3B: Relaxed Optimizations
**Configuration:**
- Cooldown: 3 candles (12 hours)
- RSI Oversold: < 45
- RSI Overbought: > 55
- Min ATR: > 0.5%
- Fixed position sizing

**Results:**
- Trades: 7 in 366 days (0.6/month)
- Win Rate: 14.3%
- Monthly Fees: $0.24
- Return: +14.69%
- Avg Win/Loss: 1.21:1

**Verdict:** ❌ Still undertrading - 17x below target frequency

---

### Iteration 3C: Very Relaxed Optimizations (BEST SO FAR)
**Configuration:**
- Cooldown: 1 candle (4 hours)
- RSI Oversold: < 50
- RSI Overbought: > 50
- Min ATR: > 0.3%
- Fixed position sizing

**Results:**
- Trades: 27 in 366 days (2.2/month)
- Win Rate: 44.4%
- Monthly Fees: $1.15
- Return: +70.31%
- Avg Win/Loss: 1.31:1
- Exit breakdown: 74% timeout, 22% SL, 4% TP

**Verdict:** ⚠️ Getting closer but still 5x below target frequency

---

## Key Findings

### What Works ✅
1. **4H timeframe is viable** - All profitable iterations showed positive returns
2. **Risk parameters are good** - TP 6%, SL 3% appropriate for 4H volatility
3. **Fees under control** - Even with relaxed filters, monthly fees stay well under $400
4. **Pattern detection identifies real opportunities** - When trades execute, they're logical
5. **Fixed position sizing** - Prevents unrealistic compounding

### What Doesn't Work ❌
1. **Pattern-based approach too selective** - Candlestick patterns rare on 4H timeframe
2. **Trend-following (SMA10 pullback) not enough** - Even relaxed, only 2.2 trades/month
3. **RSI filters further reduce frequency** - Helpful for quality but hurts quantity
4. **74% timeout rate** - Most trades don't reach TP/SL, suggesting parameters may be too wide

### Root Cause Analysis

**Why Pattern Detection Fails on 4H:**
- Candlestick patterns (engulfing, hammer, shooting star) are visual compression artifacts
- On 4H timeframes, single candles represent 4 hours of price action
- True patterns are rarer than on lower timeframes
- Need ~50-75 pattern occurrences per year to hit 10-15 trades/month (accounting for filters)
- Current approach only finding ~10-30 patterns per year

**Trade Frequency Math:**
- Target: 10-15 trades/month = 120-180 trades/year
- Best result: 27 trades/year = 2.2/month
- Gap: **5x-7x too few trades**

---

## Recommendations

### Option A: Remove Pattern Detection (RECOMMENDED)
**Approach:** Pure trend-following on 4H timeframe
- Entry: Pullback to SMA10 in uptrend, Bounce to SMA10 in downtrend
- Remove candlestick pattern requirements entirely
- Keep RSI for momentum confirmation (but relax to 50 neutral)
- Keep minimal ATR filter (0.3%)
- Expected: 50-100 trades/year (4-8/month)

**Pros:**
- Simpler strategy
- More consistent entries
- Better suited for 4H timeframe
- Still trend-following (proven effective)

**Cons:**
- May still undertrade (4-8 vs 10-15 target)
- Less "smart" entries (no pattern confirmation)

---

### Option B: Hybrid Approach
**Approach:** Primary trend-following + opportunistic patterns
- Entry: Always allow SMA10 pullback/bounce (primary)
- Entry: Add pattern signals as bonus (secondary)
- Weight: 80% trend-following, 20% patterns
- Expected: 80-120 trades/year (7-10/month)

**Pros:**
- Gets closer to target frequency
- Keeps pattern logic for high-conviction setups
- More diversified entry reasons

**Cons:**
- More complex to tune
- Still may undertrade

---

### Option C: Reduce Timeframe to 2H
**Approach:** Compromise between 15-min and 4H
- Interval: 2 hours (7200 seconds)
- Decisions per day: 12 (vs 6 for 4H, vs 96 for 15-min)
- Expected patterns: 2-3x more than 4H
- Expected fees: Still 75% reduction vs 15-min
- Expected: 100-150 trades/year (8-12/month)

**Pros:**
- Hits target frequency more easily
- Still achieves major fee reduction
- Pattern detection more effective
- Better balance of opportunity vs noise

**Cons:**
- Not as dramatic fee reduction as 4H
- More decisions to process
- Need to recalibrate TP/SL for 2H volatility

---

### Option D: Accept Lower Frequency (FALLBACK)
**Approach:** Optimize for quality over quantity
- Target: 5-7 trades/month (instead of 10-15)
- Focus: High win rate (55%+) and win/loss ratio (2:1+)
- Philosophy: Fewer, better trades on 4H
- Expected fees: $50-150/month (still 70-90% reduction)

**Pros:**
- Works with current pattern approach
- Achieves major fee reduction
- Higher quality setups
- Less overfitting risk

**Cons:**
- Slower capital growth
- Longer periods between trades
- May not feel "active" enough

---

## Next Steps

### Immediate (Required before Week 3)
1. **Choose strategy approach** (A, B, C, or D)
2. **Implement chosen approach**
3. **Run final validation backtest**
4. **Document validated parameters**
5. **Make go/no-go decision for Week 3**

### If Proceeding with Option A (Recommended)
1. Remove all pattern detection from `check_entry_signal()`
2. Keep only trend-following (SMA10 pullback/bounce)
3. Set RSI neutral (50/50) or remove entirely
4. Set minimal ATR (0.3% or remove)
5. Remove or minimize cooldown (1 candle max)
6. Run backtest - expect 4-8 trades/month
7. If still low, consider Option C (2H timeframe)

### If Proceeding with Option C (2H Timeframe)
1. Update `.env`: `DECISION_INTERVAL=7200`
2. Download 2H historical data (4,400 candles for 1 year)
3. Recalibrate TP/SL for 2H volatility (analyze percentile ranges)
4. Run backtest with pattern detection
5. Expect 8-12 trades/month naturally

---

## Milestone 1.2.7 Status

**Completed (8/14 tasks):**
- ✅ Configuration updated to 4H (DECISION_INTERVAL=14400)
- ✅ 7 Python scripts updated
- ✅ Historical data downloaded (2,200 4H candles)
- ✅ API verified (V5)
- ✅ Risk parameters calibrated (TP 6%, SL 3%)
- ✅ Week 2 validation framework created
- ✅ Multiple iterations tested (1, 2, 3A, 3B, 3C)
- ✅ Problems identified and documented

**Pending (6/14 tasks):**
- ⏳ Choose final strategy approach
- ⏳ Complete final validation backtest
- ⏳ Achieve target metrics OR adjust targets
- ⏳ Update documentation (bulk replace 15-min→4H)
- ⏳ Run 24-hour live test
- ⏳ Make go/no-go decision for Week 3 (signal calibration)

**Timeline:**
- Week 2 target completion: October 26, 2025 (7 days remaining)
- Current progress: ~65% complete
- Decision required: Which strategy approach to pursue?

---

## Technical Notes

**Position Sizing Bug Fixed:**
- Old: `size = self.capital * 0.02` (compounding, caused 341,249% return)
- New: `size = self.initial_capital * 0.02` (fixed, realistic returns)
- Impact: More realistic P&L, prevents exponential growth

**Indicator Calculations Verified:**
- RSI (14-period): Working correctly
- ATR (14-period): Working correctly
- ATR percentage: (ATR / close) * 100
- Trend: SMA10 vs SMA20 crossover

**Exit Analysis:**
- 74% timeout (6 candles = 24 hours) - Suggests TP/SL may be too wide for 4H
- 22% stop loss - Normal defensive exits
- 4% take profit - Very few winners hit target
- Recommendation: Consider tighter TP (4-5%) or longer timeout (12 candles = 48 hours)

