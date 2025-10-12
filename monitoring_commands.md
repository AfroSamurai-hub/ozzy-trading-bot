# 📊 PHASE 1 MONITORING COMMANDS
# Copy/paste these commands in separate terminals to watch your bot

## 🔴 TERMINAL 1: Live Activity Log
```bash
cd /home/rick/ozzy-simple
tail -f logs/phase1_monitor.log
```
**What you'll see**: Real-time signal generation, confidence scores, RSI values, LONG/SHORT decisions

---

## **TERMINAL 2** - Quick Status (Run Every Few Hours):
```bash
cd /home/rick/ozzy-simple
/home/rick/ozzy-simple/venv/bin/python monitor_phase1.py
```

## **TERMINAL 3** - Learning Analysis (2x Daily):
```bash
cd /home/rick/ozzy-simple
/home/rick/ozzy-simple/venv/bin/python learning_analysis.py
```

---

## 🟡 TERMINAL 3: Learning Analysis (Run 2x Daily)
```bash
cd /home/rick/ozzy-simple
python learning_analysis.py
```
**What you'll see**: Confidence improvements, pattern recognition, correlation analysis

---

## 🔵 TERMINAL 4: Signal Statistics (Quick SQL Queries)

### Check if bot is running:
```bash
ps aux | grep main.py | grep -v grep
```

### Today's signal count:
```bash
cd /home/rick/ozzy-simple
sqlite3 ozzy_simple.db "SELECT COUNT(*) as today_signals FROM signals WHERE DATE(timestamp) = DATE('now')"
```

### Signal breakdown by type:
```bash
sqlite3 ozzy_simple.db "
SELECT signal, COUNT(*) as count 
FROM signals 
WHERE DATE(timestamp) = DATE('now') 
GROUP BY signal"
```

### Signal breakdown by symbol:
```bash
sqlite3 ozzy_simple.db "
SELECT symbol, signal, COUNT(*) as count 
FROM signals 
WHERE DATE(timestamp) = DATE('now') 
GROUP BY symbol, signal 
ORDER BY symbol, signal"
```

### Average confidence by hour:
```bash
sqlite3 ozzy_simple.db "
SELECT strftime('%H', timestamp) as hour, 
       COUNT(*) as signals,
       ROUND(AVG(confidence), 1) as avg_confidence
FROM signals 
WHERE DATE(timestamp) = DATE('now') 
GROUP BY hour 
ORDER BY hour"
```

### Recent high-confidence signals:
```bash
sqlite3 ozzy_simple.db "
SELECT timestamp, symbol, signal, confidence 
FROM signals 
WHERE confidence > 45 
  AND DATE(timestamp) = DATE('now')
ORDER BY timestamp DESC 
LIMIT 10"
```

---

## ⚫ TERMINAL 5: Log File Management

### Check log file size:
```bash
ls -lh /home/rick/ozzy-simple/logs/phase1_monitor.log
```

### Count error lines (excluding balance errors):
```bash
grep "ERROR" /home/rick/ozzy-simple/logs/phase1_monitor.log | grep -v "Failed to fetch balance" | wc -l
```

### Show recent errors (if any):
```bash
grep "ERROR" /home/rick/ozzy-simple/logs/phase1_monitor.log | grep -v "Failed to fetch balance" | tail -5
```

### Archive log if it gets too big (>100MB):
```bash
# Only run if log is huge:
mv logs/phase1_monitor.log logs/phase1_monitor_$(date +%Y%m%d).log
# Bot will create new log automatically
```

---

## 🚨 EMERGENCY COMMANDS

### Stop the bot:
```bash
pkill -f main.py
```

### Restart the bot:
```bash
cd /home/rick/ozzy-simple
nohup bash -c 'echo "yes" | venv/bin/python main.py' > logs/phase1_monitor.log 2>&1 &
```

### Check if restart worked:
```bash
ps aux | grep main.py | grep -v grep
```

---

## 📅 DAILY ROUTINE

### Morning Check (30 seconds):
```bash
cd /home/rick/ozzy-simple
python monitor_phase1.py
```

### Evening Check (1 minute):
```bash
cd /home/rick/ozzy-simple
python monitor_phase1.py
python learning_analysis.py
```

### Weekend Check (2 minutes):
```bash
cd /home/rick/ozzy-simple
python monitor_phase1.py
python learning_analysis.py

# Check total signals collected
sqlite3 ozzy_simple.db "
SELECT 
    COUNT(*) as total_signals,
    SUM(CASE WHEN signal = 'LONG' THEN 1 ELSE 0 END) as long_signals,
    SUM(CASE WHEN signal = 'SHORT' THEN 1 ELSE 0 END) as short_signals,
    SUM(CASE WHEN signal = 'HOLD' THEN 1 ELSE 0 END) as hold_signals,
    ROUND(AVG(confidence), 1) as avg_confidence
FROM signals 
WHERE DATE(timestamp) >= DATE('now', '-3 days')"
```

---

## 🎯 MONDAY ANALYSIS (End of Phase 1)

### Run full Phase 1 analysis:
```bash
cd /home/rick/ozzy-simple
python phase1_analysis.py
```

### Manual analysis:
```bash
sqlite3 ozzy_simple.db "
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as signals,
    SUM(CASE WHEN signal != 'HOLD' THEN 1 ELSE 0 END) as actionable,
    ROUND(AVG(confidence), 1) as avg_conf
FROM signals 
WHERE DATE(timestamp) >= '2025-10-11'
GROUP BY DATE(timestamp)
ORDER BY date"
```

---

## 💡 WHAT TO WATCH FOR

### ✅ Good Signs:
- Bot status: RUNNING
- 20+ signals per day
- Both LONG and SHORT signals
- Confidence scores 25-50%
- No critical errors
- Learning correlation > 0.5

### ⚠️ Warning Signs:
- Bot stops running
- No signals for 2+ hours
- Only HOLD signals
- Critical errors in log
- Confidence stuck at same level

### 🚨 Action Needed:
- "Process not found" → Restart bot
- Log file >500MB → Archive old log
- No signals all day → Check config/API keys

---

## 📱 QUICK REFERENCE CARD

**Check Status**: `python monitor_phase1.py`
**Live Feed**: `tail -f logs/phase1_monitor.log`  
**Learning**: `python learning_analysis.py`
**Restart**: `pkill -f main.py && nohup bash -c 'echo "yes" | venv/bin/python main.py' > logs/phase1_monitor.log 2>&1 &`

**Current Status**: ✅ RUNNING (started 18:04 Oct 11)
**Target End**: Monday Oct 14 
**Expected Signals**: 3,000+ total

---

## 🏆 SUCCESS CRITERIA FOR MONDAY

- [ ] 60+ total signals (you'll have 3,000+!)
- [ ] All 5 symbols represented  
- [ ] Both LONG and SHORT signals
- [ ] 72+ hours runtime
- [ ] Confidence range 25-50%
- [ ] Strong learning correlation

**You're already crushing these targets!** 🚀

---

*Save this file for easy reference over the weekend!*