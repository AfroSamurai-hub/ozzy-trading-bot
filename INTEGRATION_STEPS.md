# Time Filter Integration - Step-by-Step Instructions

## ⚠️ Important: Make a Backup First

```bash
cd ~/ozzy-simple
cp main.py main.py.backup
cp config.py config.py.backup
```

## Step 1: Stop the Bot

```bash
pkill -f "python main.py"
# Wait 3 seconds
sleep 3
# Verify it stopped
ps aux | grep main.py
```

## Step 2: Edit `main.py` - Add Import

**Location:** Top of file, around line 15-19 (after other imports)

**Find this section:**
```python
from bybit_client import BybitClient
from signal_generator import SignalGenerator
from risk_manager import RiskManager
from position_tracker import PositionTracker
from logger_config import setup_logger
import db
```

**Add this line after `import db`:**
```python
from time_filter_wrapper import TimeFilterWrapper
```

**Result:**
```python
from bybit_client import BybitClient
from signal_generator import SignalGenerator
from risk_manager import RiskManager
from position_tracker import PositionTracker
from logger_config import setup_logger
import db
from time_filter_wrapper import TimeFilterWrapper
```

## Step 3: Edit `main.py` - Initialize Wrapper

**Location:** In `__init__` method, around line 60-62 (after `self.max_backoff = 300`)

**Find this section:**
```python
        # Resilience and logging
        self.backoff_seconds = 1
        self.max_backoff = 300
        self.api_error_count = 0
```

**Add these lines after `self.api_error_count = 0`:**
```python
        
        # Time filter A/B test
        self.time_filter = TimeFilterWrapper(
            test_name="time_filter_night",
            avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC (low volatility)
            enabled=True  # Set to False to disable test
        )
        logger.info(f"🧪 Time filter A/B test enabled: avoiding {self.time_filter.avoid_hours}")
```

## Step 4: Edit `main.py` - Apply Filter in check_signal()

**Location:** In `check_signal()` method, around line 216 (after signal generation)

**Find this section:**
```python
        # Generate signal
        signal = self.signal_generator.generate_signal(candles)
        
        # Log signal summary
        signal_emoji = "🟢" if signal["signal"] == "LONG" else "🔴" if signal["signal"] == "SHORT" else "⚪"
```

**Replace with:**
```python
        # Generate signal
        signal = self.signal_generator.generate_signal(candles)
        
        # Apply time filter for A/B test
        signal, test_group = self.time_filter.apply_filter(signal, symbol)
        
        # Log signal summary
        signal_emoji = "🟢" if signal["signal"] == "LONG" else "🔴" if signal["signal"] == "SHORT" else "⚪"
```

## Step 5: Edit `main.py` - Tag Trades in Database

**Location:** In `execute_trade()` method, around line 327 (where DB trade is logged)

**Find this section:**
```python
            db_id = db.log_trade_open({
                'entry_timestamp': self.open_positions[symbol]['entry_time'].strftime("%Y-%m-%d %H:%M:%S"),
                'symbol': symbol,
                'side': signal["signal"],
                'entry_price': signal["entry_price"],
                'position_size': position_size,
                'position_value': position_value,
                'quality': signal.get('quality', ''),
                'confidence': signal.get('confidence', 0.0),
                'entry_reason': signal.get('reason', '')
            })
```

**Replace the `'entry_reason'` line with:**
```python
                'entry_reason': self.time_filter.format_entry_reason(
                    signal.get('reason', ''),
                    test_group
                )
```

**Final result:**
```python
            db_id = db.log_trade_open({
                'entry_timestamp': self.open_positions[symbol]['entry_time'].strftime("%Y-%m-%d %H:%M:%S"),
                'symbol': symbol,
                'side': signal["signal"],
                'entry_price': signal["entry_price"],
                'position_size': position_size,
                'position_value': position_value,
                'quality': signal.get('quality', ''),
                'confidence': signal.get('confidence', 0.0),
                'entry_reason': self.time_filter.format_entry_reason(
                    signal.get('reason', ''),
                    test_group
                )
            })
```

**⚠️ Important:** You must pass `test_group` to the `format_entry_reason()` call. The `test_group` variable was created in Step 4 when you called `apply_filter()`.

## Step 6: Verify Changes

```bash
cd ~/ozzy-simple

# Check syntax
python -c "import main; print('✅ Syntax OK')"

# Should print: ✅ Syntax OK
```

If you see any errors, review the changes or restore from backup.

## Step 7: Restart Bot

```bash
cd ~/ozzy-simple
nohup python main.py > bot.log 2>&1 &

# Save the PID
echo $! > bot.pid

# Check it's running
sleep 3
tail -50 bot.log
```

**Expected output in log:**
```
🤖 OZZY SIMPLE - AUTOMATED TRADING BOT
...
✅ Bot initialized successfully!
🧪 Time filter A/B test enabled: avoiding [(22, 2)]
```

## Step 8: Monitor Test Progress

### Watch Logs in Real-Time

```bash
tail -f ~/ozzy-simple/bot.log | grep -E "Test group|Control group|avoid window"
```

### Check Test Status (Every Hour)

```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status
```

**Expected output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      Time-of-Day Filter A/B Test - Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Test Name: time_filter_night
Avoid Hours (Test): 22:00-02:00 UTC
Target Trades: 50 per group

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Status: In Progress (34%)
Control Group:      17/50 trades (34%)
Test Group:         17/50 trades (34%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Verdict: INCOMPLETE - Need more trades
(Run with --report for detailed statistics)
```

### Daily Check (Run Once Per Day)

```bash
cd ~/ozzy-simple
./venv/bin/python scripts/quick_status.py
./venv/bin/python scripts/test_time_filter.py --status
```

## Step 9: Generate Report (When Complete)

After 50 trades per group are collected:

```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --report
```

## Troubleshooting

### Bot Won't Start

```bash
# Check syntax errors
cd ~/ozzy-simple
python main.py

# If errors, restore backup
cp main.py.backup main.py
```

### No Trades Collecting

```bash
# Check bot is running
ps aux | grep main.py

# Check recent logs
tail -100 ~/ozzy-simple/bot.log

# Check for errors
grep -i error ~/ozzy-simple/bot.log | tail -20
```

### Only Control Group Has Trades

This is normal if:
- Current time is in avoid window (22:00-02:00 UTC)
- Test group signals being filtered

Check current hour:
```bash
date -u  # Should show UTC time
```

If it's between 22:00-02:00 UTC, test group SHOULD be empty.

### Verify Test Group Assignment

```bash
# Check database for test tags
cd ~/ozzy-simple
sqlite3 ozzy_simple.db "SELECT entry_reason FROM trades WHERE entry_reason LIKE '%TEST_%' ORDER BY id DESC LIMIT 10;"
```

Should see entries like:
```
TEST_time_filter_night_control_rsi_oversold
TEST_time_filter_night_test_ema_crossover
```

## Disable Test (If Needed)

### Temporary (Without Code Change)

Not possible with current implementation. Must edit code.

### Permanent (Edit Code)

In `main.py`, change:
```python
        self.time_filter = TimeFilterWrapper(
            test_name="time_filter_night",
            avoid_hours=[(22, 2)],
            enabled=False  # ← Change to False
        )
```

Then restart bot.

## What Success Looks Like

After 5-7 days, you should have:

- ✅ 50 control group trades (24/7 trading)
- ✅ 50 test group trades (avoid 22:00-02:00)
- ✅ Clear winner based on win rate and avg P&L
- ✅ Decision: apply filter or keep 24/7

## Next Steps After Test Complete

1. Generate final report
2. If test wins: Update config to use filter permanently
3. If test loses: Keep 24/7 trading
4. Move to next evolution test (confidence thresholds, RSI levels, etc.)

---

**Created:** October 11, 2025  
**Integration Time:** ~10-15 minutes  
**Data Collection:** 5-7 days  
**Files Modified:** main.py (3 changes)  
