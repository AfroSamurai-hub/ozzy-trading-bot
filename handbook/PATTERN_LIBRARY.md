# PATTERN LIBRARY - Validated Patterns Only

**Philosophy:** Only trade patterns with documented evidence.  
**Source:** Our backtests + academic research + altFINS studies  
**Update Frequency:** After every 50 trades or major market shift

---

## 🟢 HIGH-CONFIDENCE PATTERNS (Use These)

### Bullish Engulfing
**Expected Win Rate:** 60-65% (with confirmations)  
**Our Experience:** Not yet tested (0 trades in Oct 2025 backtest)  
**Status:** APPROVED for use

**Definition:**
- Previous candle: Red (close < open)
- Current candle: Green (close > open)
- Current open < previous close
- Current close > previous open
- Body of current completely engulfs previous body

**Confirmation Required:**
1. ✅ Volume on engulfing candle > 1.5x average
2. ✅ Occurs at support level or after downtrend
3. ✅ Price above 50-day EMA (trend context)
4. ✅ RSI > 40 (not oversold, has momentum)

**Entry:** Close of engulfing candle (wait for confirmation)  
**Stop:** Below low of engulfing candle  
**Target:** 2:1 R/R minimum (if 2% stop, aim for 4% profit)

**Failure Mode:** Fails in strong downtrends (check 200MA)

---

### Hammer
**Expected Win Rate:** 55-60% (with confirmations)  
**Our Experience:** 40% WR in Oct 2025 backtest (NO CONFIRMATIONS!)  
**Status:** ⚠️ CONDITIONAL - Requires ALL confirmations

**Definition:**
- Lower wick > 2x body size
- Upper wick < 0.5x body size
- Close > open (green hammer stronger)
- Appears after downtrend

**Confirmation Required:**
1. ✅ Volume spike (>1.5x average)
2. ✅ At support level (previous swing low, MA, psychological level)
3. ✅ Next candle closes above hammer high
4. ✅ RSI < 40 (oversold bounce)

**Entry:** Break above hammer high + volume  
**Stop:** Below hammer low  
**Target:** 2:1 R/R minimum

**Failure Mode:** 
- Without confirmations: 40% WR (our backtest proved this!)
- In strong downtrends (momentum too strong)

**LESSON LEARNED:** Never trade hammer without ALL confirmations!

---

### Morning Star
**Expected Win Rate:** 60-70% (with confirmations)  
**Our Experience:** 40% WR in Oct 2025 backtest (NO CONFIRMATIONS!)  
**Status:** ⚠️ CONDITIONAL - Requires ALL confirmations

**Definition:**
- 3-candle pattern
- Candle 1: Large red body (downtrend)
- Candle 2: Small body (doji or spinning top) - indecision
- Candle 3: Large green body (reversal)
- Candle 3 closes above midpoint of Candle 1

**Confirmation Required:**
1. ✅ Volume increasing on Candle 3 (>1.5x average)
2. ✅ At support level
3. ✅ Gap down on Candle 2 (shows exhaustion)
4. ✅ Next candle confirms (closes above morning star high)

**Entry:** Close of confirmation candle  
**Stop:** Below low of pattern  
**Target:** 2:1 R/R minimum

**Failure Mode:**
- Without confirmations: 40% WR (our backtest!)
- Becomes triple bottom (extended basing)

**LESSON LEARNED:** Patient! Wait for confirmation candle!

---

## 🟡 MEDIUM-CONFIDENCE PATTERNS (Use with Caution)

### Doji
**Expected Win Rate:** 50-55%  
**Our Experience:** 46% WR in Oct 2025 backtest  
**Status:** ⚠️ USE SPARINGLY - Barely better than coin flip

**Definition:**
- Open ≈ Close (body < 10% of high-low range)
- Shows indecision

**Confirmation Required:**
1. ✅ Strong volume (>2x average - show significance)
2. ✅ At support/resistance (meaningful location)
3. ✅ Next 2 candles confirm direction
4. ✅ Trend context (reversal doji vs continuation doji)

**Entry:** ONLY after 2-candle confirmation  
**Stop:** Tight (1.5% max)  
**Target:** 2:1 R/R minimum

**Failure Mode:**
- Too common (appears every few candles)
- Low win rate even with confirmations (46% in our backtest)

**RECOMMENDATION:** Use only in combination with other signals!

---

## 🔴 RETIRED PATTERNS (Don't Trade These - Yet)

### Pennants
**Expected Win Rate:** 52-56% (academic studies)  
**Our Experience:** Not tested yet  
**Status:** ⛔ RETIRED - Too many false breakouts

**Reason for Retirement:**
- Barely better than coin flip
- Requires perfect trending market
- High false breakout rate

**Reinstatement Criteria:**
- Must backtest at >60% WR with confirmations
- Must have clear rules for validation

---

### Flags
**Expected Win Rate:** 54-58%  
**Status:** ⛔ RETIRED - Trend-dependent

**Reason:**
- Only works in strong trends
- Too context-dependent

**Possible Future Use:**
- ONLY in confirmed trending regimes (ADX > 25)
- With volume confirmation

---

## 📊 PATTERN TESTING PROTOCOL

Before adding any pattern to HIGH-CONFIDENCE:
1. Backtest on 60+ days of data
2. Achieve >60% WR with confirmations
3. Document failure modes
4. Test in multiple market regimes
5. Peer review by system

---

## 🔄 UPDATE LOG

**Oct 17, 2025:**
- Initial library created
- Added backtest results (Oct 2025, 60 days, BTCUSDT)
- Identified that patterns without confirmations fail (<45% WR)
- Set conditional status for hammer, morning_star, doji
- Approved bullish_engulfing (pending test)

**Next Update:** After implementing full confirmation filters + retest

---

## 🎯 KEY LESSON FROM OCT 2025 BACKTEST

**"A pattern is NOT a signal. A pattern + confirmations = signal."**

- Pattern alone: 40-46% WR ❌
- Pattern + volume + trend + support/resistance: Expected 60-65% WR ✅

**Every pattern in this library must have ALL confirmations checked before entry!**
