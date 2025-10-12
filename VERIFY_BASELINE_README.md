# Baseline Verification Script

## Overview
The `verify_baseline.py` script provides a comprehensive analysis of your trading bot's performance, helping you verify that your baseline strategy is stable before proceeding with optimizations.

## Location
```
~/ozzy-simple/scripts/verify_baseline.py
```

## Usage

### Basic Usage
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/verify_baseline.py
```

### What It Shows

1. **Overall Statistics**
   - Total number of trades
   - Baseline vs Test trade counts
   - Win rate with win/loss breakdown
   - Average P&L per trade
   - Total cumulative P&L
   - Best and worst trades
   - Profit factor (avg win / avg loss)

2. **Verification Status**
   - ✅ Confirms you have minimum 100 trades for baseline
   - ✅ Validates win rate is in healthy range (55-70%)
   - ✅ Ready/Not Ready status for optimization

3. **Performance Breakdown**
   - Separate stats for baseline trades
   - Separate stats for test trades (if any)
   - Comparison between baseline and test performance

4. **Last 10 Trades**
   - Recent trade history
   - Symbol, side, P&L, type, exit time
   - Color-coded P&L (green=profit, red=loss)

5. **Symbol Breakdown**
   - Performance by trading pair
   - Win rate per symbol
   - Total P&L per symbol

6. **Recent Performance**
   - Daily statistics for last 7 days
   - Trades per day
   - Win rate per day
   - P&L per day

## Current Baseline Status

**✅ VERIFIED AND READY!**

Based on latest run:
- **444 baseline trades** (well above 100 minimum)
- **58.1% win rate** (within target 55-70%)
- **R29.65 average P&L** per trade
- **R13,165 total P&L**
- **1.69x profit factor**

### Symbol Performance
| Symbol | Trades | Win Rate | Total P&L |
|--------|--------|----------|-----------|
| BTCUSDT | 150 | 58.7% | R3,845.41 |
| BNBUSDT | 94 | 59.6% | R3,424.63 |
| SOLUSDT | 93 | 58.1% | R2,777.99 |
| XRPUSDT | 88 | 58.0% | R2,776.14 |
| ETHUSDT | 19 | 47.4% | R340.84 |

## Exit Codes

- **0**: Baseline verified and ready for optimization
- **1**: Not ready (need more trades or win rate outside range)

## Integration with Evolution Framework

This script should be run:
1. **Before starting optimization** - Verify baseline is stable
2. **After collecting 100+ trades** - Confirm statistical significance
3. **Periodically during testing** - Monitor ongoing performance
4. **Before going live** - Final verification

## Next Steps

Since your baseline is verified:
1. ✅ You can proceed with systematic optimization
2. ✅ Run evolution tests (one variable at a time)
3. ✅ Use this report as your control group reference

## Example Workflow

```bash
# Step 1: Verify baseline
./venv/bin/python scripts/verify_baseline.py

# Step 2: If verified (exit code 0), start first test
./venv/bin/python scripts/evolution_tester.py \
    --test-name "confidence_15" \
    --param MIN_CONFIDENCE \
    --baseline 10 \
    --test 15 \
    --trades 50

# Step 3: Compare test results against this baseline
./venv/bin/python scripts/verify_baseline.py
```

## Troubleshooting

### "Database not found"
- Ensure you're running from ~/ozzy-simple directory
- Check that ozzy_simple.db exists

### "Not ready - Need more trades"
- Let bot run longer to collect 100+ baseline trades
- Check that bot is running: `ps aux | grep main.py`

### "Win rate outside normal range"
- If <55%: Review strategy, may need adjustment
- If >70%: Great! But verify data isn't overfitted

## Color Coding

- 🟢 **Green**: Profitable trades, win rate >60%
- 🟡 **Yellow**: Break-even, win rate 50-60%
- 🔴 **Red**: Losing trades, win rate <50%

---

**Created:** October 11, 2025
**Status:** ✅ Production Ready
**Baseline:** 444 trades, 58.1% win rate, Ready for optimization
