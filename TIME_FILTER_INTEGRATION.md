# Time-of-Day Filter A/B Test - Integration Guide

## Overview
This A/B test framework allows you to test whether avoiding certain hours improves trading performance without breaking your existing bot.

## Files Created

1. **`scripts/test_time_filter.py`** - Main A/B test analysis tool
2. **`time_filter_wrapper.py`** - Integration wrapper for your bot
3. **`TIME_FILTER_INTEGRATION.md`** - This guide

## How It Works

### The Strategy
- **Control Group (50%)**: No time filter, trades 24/7
- **Test Group (50%)**: Avoids specific hours (default: 22:00-02:00 UTC)
- Both groups run simultaneously on the same bot
- After 50 trades per group, compare performance

### Why Test Time Filters?
Crypto markets have varying volatility throughout the day:
- **High Volatility**: Asian session (02:00-08:00 UTC), US session (14:00-20:00 UTC)
- **Low Volatility**: Late night UTC (22:00-02:00 UTC)
- **Question**: Does avoiding low-volatility hours improve win rate?

## Integration Steps

### Option 1: Quick Test (Non-Invasive)

Just run the test script to check current data:

```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status
```

### Option 2: Full Integration (Recommended)

Integrate into your bot for real A/B testing:

#### Step 1: Import the Wrapper

Add to `main.py` (near the top):

```python
from time_filter_wrapper import TimeFilterWrapper
```

#### Step 2: Initialize in `__init__`

In `TradingBot.__init__()`, add:

```python
# Time filter A/B test
self.time_filter = TimeFilterWrapper(
    test_name="time_filter_night",
    avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC
    enabled=True  # Set False to disable
)
```

#### Step 3: Apply Filter in `check_signal()`

Replace this code in `main.py` around line 215:

**BEFORE:**
```python
# Generate signal
signal = self.signal_generator.generate_signal(candles)
```

**AFTER:**
```python
# Generate signal
signal = self.signal_generator.generate_signal(candles)

# Apply time filter for A/B test
signal, test_group = self.time_filter.apply_filter(signal, symbol)
```

#### Step 4: Tag Trades in Database

When recording trade entry, modify `entry_reason`:

**BEFORE:**
```python
entry_reason = "rsi_oversold" or "ema_crossover" or whatever
```

**AFTER:**
```python
base_reason = "rsi_oversold"  # Your original reason
entry_reason = self.time_filter.format_entry_reason(base_reason, test_group)
# Result: "TEST_time_filter_night_control_rsi_oversold"
```

### Step 5: Restart Bot

```bash
pkill -f "python main.py"
cd ~/ozzy-simple
nohup python main.py > bot.log 2>&1 &
```

## Usage

### Check Test Status

```bash
./venv/bin/python scripts/test_time_filter.py --status
```

### Generate Full Report

```bash
./venv/bin/python scripts/test_time_filter.py --report
```

### Custom Configuration

```bash
# Test different hours (e.g., avoid 00:00-04:00)
./venv/bin/python scripts/test_time_filter.py \
    --test-name "time_filter_early_morning" \
    --avoid-start 0 \
    --avoid-end 4 \
    --trades 50 \
    --status
```

## What Happens

### Control Group (50% of signals)
1. Bot generates signal normally
2. No time filtering applied
3. Trades execute 24/7
4. Tagged as: `TEST_time_filter_night_control_...`

### Test Group (50% of signals)
1. Bot generates signal normally
2. Checks current hour (UTC)
3. If in avoid window (22:00-02:00):
   - Converts signal to HOLD
   - Logs: "Skipping signal - in avoid hours"
   - No trade executed
4. If outside avoid window:
   - Signal passes through unchanged
   - Trade executes normally
5. Tagged as: `TEST_time_filter_night_test_...`

## Reading Results

### Example Report

```
📊 PROGRESS
Control Group:       50/50 trades (100%)
Test Group:          50/50 trades (100%)

📈 RESULTS COMPARISON
Metric                    Control (24/7)       Test (Filtered)     
Win Rate                  58.0%                62.0%                
Total P&L                 R1,450.00            R1,860.00            
Avg P&L per Trade         R29.00               R37.20               

🎯 VERDICT
✅ WINNER: Time Filter
   Win rate improved by +4.0%
   Avg P&L improved by R+8.20
   Recommendation: Apply time filter to baseline
```

### Interpretation

**Winner (Test > Control + 2% win rate OR +R5 avg P&L):**
- Time filter improves performance
- Apply to baseline configuration
- Update config: `AVOID_HOURS = [(22, 2)]`

**Loser (Test < Control - 2% win rate OR -R5 avg P&L):**
- Time filter hurts performance
- Keep 24/7 trading
- Don't apply filter

**No Difference (within ±2% win rate AND ±R5 avg P&L):**
- No meaningful improvement
- Keep 24/7 trading (simpler)
- Try different hours or different test

## Timeline

Based on your baseline (444 trades, 58.1% win rate):

### With Current Bot Speed (~10-20 trades/day)
- Day 1-2: Collect 25-40 trades
- Day 3-4: Collect 50 trades control + 50 trades test
- Day 5: Generate final report and decision

### Expected Completion
**5-7 days** for 100 total trades (50 per group)

## Safety Features

### Non-Breaking Design
- ✅ Bot continues working if test disabled
- ✅ Control group always trades normally
- ✅ Only test group subject to filter
- ✅ Easy to disable: `enabled=False`

### Monitoring
```bash
# Watch bot logs for test activity
tail -f bot.log | grep -E "Test group|Control group|avoid window"

# Check test progress
watch -n 60 './venv/bin/python scripts/test_time_filter.py --status'
```

## Configuration Options

### Different Avoid Windows

**Avoid Early Morning (00:00-04:00):**
```python
TimeFilterWrapper(
    test_name="time_filter_early_morning",
    avoid_hours=[(0, 4)],
    enabled=True
)
```

**Avoid Multiple Windows:**
```python
TimeFilterWrapper(
    test_name="time_filter_dual",
    avoid_hours=[(22, 2), (12, 14)],  # Avoid night AND lunch
    enabled=True
)
```

**Avoid Entire Asian Session:**
```python
TimeFilterWrapper(
    test_name="time_filter_asian",
    avoid_hours=[(2, 8)],  # 02:00-08:00 UTC
    enabled=True
)
```

## Troubleshooting

### "No trades collecting"
- Check bot is running: `ps aux | grep main.py`
- Check logs: `tail -100 bot.log`
- Verify integration in code

### "Only control group has trades"
- Test group might be filtering too aggressively
- Check current hour: `date -u`
- Adjust avoid_hours to smaller window

### "No statistical significance"
- Need more trades (at least 50 per group)
- Let test run longer
- Consider 100 trades per group for better confidence

## Next Steps

1. ✅ **Integrate wrapper** into main.py
2. ✅ **Restart bot** with test enabled
3. ⏳ **Monitor daily** with `--status`
4. ⏳ **Wait 5-7 days** for 100 trades
5. ✅ **Generate report** and make decision
6. ✅ **Apply winner** to baseline config

## Related Files

- **Baseline Verification**: `scripts/verify_baseline.py`
- **Evolution Framework**: `STRATEGY_EVOLUTION_PLAN.md`
- **Test Results**: `test_results.json` (auto-created)

---

**Created:** October 11, 2025  
**Status:** ✅ Ready for Testing  
**Baseline:** 444 trades, 58.1% win rate  
**Target:** Test time filter impact on performance  
