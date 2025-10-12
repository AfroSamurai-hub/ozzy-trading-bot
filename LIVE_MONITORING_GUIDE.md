# 📺 LIVE MONITORING GUIDE

## 🎯 Quick Commands

### Option 1: Rich Live Dashboard (RECOMMENDED)
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/live_dashboard.py
```
**Features:**
- ✅ Full-screen live dashboard
- ✅ Auto-refreshes every 10 seconds
- ✅ Shows progress, stats, recent trades
- ✅ Color-coded performance
- ✅ Professional layout

**Controls:**
- Press `Ctrl+C` to exit

---

### Option 2: Watch Command (Simple)
```bash
# Updates every 30 seconds
watch -n 30 'cd ~/ozzy-simple && ./venv/bin/python scripts/test_time_filter.py --status'
```

---

### Option 3: Live Log Streaming
```bash
# See trades as they happen
tail -f ~/ozzy-simple/bot.log | grep --color=always -E "A/B Test|CONTROL|TEST|executed"
```

---

### Option 4: Live Dashboard (Faster Refresh)
```bash
# Update every 5 seconds (more frequent)
cd ~/ozzy-simple
./venv/bin/python scripts/live_dashboard.py --refresh 5
```

---

### Option 5: Custom One-Liner
```bash
# Quick status check in loop
while true; do clear; date; echo ""; cd ~/ozzy-simple && ./venv/bin/python scripts/test_time_filter.py --status | head -30; sleep 15; done
```

---

## 📊 What You'll See

### Live Dashboard Display:
```
╔══════════════════════════════════════════════════════════════════╗
║        🧪 TIME FILTER A/B TEST - LIVE DASHBOARD 🧪              ║
╚══════════════════════════════════════════════════════════════════╝

┌─────────────────────┐ ┌─────────────────────┐
│  📊 Progress        │ │  📋 Recent Trades   │
│                     │ │                     │
│  Control: 12/50     │ │  10:45  BTCUSDT  🟢 │
│  Test:    15/50     │ │         R42.50  CTRL│
│  Total:   27/100    │ │                     │
│                     │ │  10:43  ETHUSDT  🔴 │
│  📈 Performance     │ │         R-15.20 TEST│
│                     │ │                     │
│  Metric   Ctrl Test │ │  ... more trades    │
│  Win Rate 58%  63%  │ │                     │
│  Avg P&L  R29  R37  │ │                     │
└─────────────────────┘ └─────────────────────┘

🕐 2025-10-11 10:47:23 | Open: 3 | Ctrl+C to exit
```

---

## 🎨 Dashboard Features

### Progress Section
- Shows Control group: X/50 trades
- Shows Test group: X/50 trades  
- Progress percentage
- Remaining trades needed

### Performance Section
- Win rate comparison (Control vs Test)
- Average P&L per trade
- Total P&L accumulated
- Difference highlighting

### Recent Trades
- Last 10 completed trades
- Symbol, side (LONG/SHORT), P&L
- Which group (CTRL or TEST)
- Timestamp
- Color-coded: Green = profit, Red = loss

### Footer
- Current time (UTC)
- Open positions count
- Instructions

---

## 🔧 Dashboard Options

### Change Refresh Rate
```bash
# Refresh every 5 seconds (fast)
./venv/bin/python scripts/live_dashboard.py --refresh 5

# Refresh every 30 seconds (slow, saves CPU)
./venv/bin/python scripts/live_dashboard.py --refresh 30

# Default is 10 seconds
./venv/bin/python scripts/live_dashboard.py
```

### Monitor Different Test
```bash
# If you run multiple tests
./venv/bin/python scripts/live_dashboard.py --test-name "confidence_test"
```

---

## 💡 Pro Tips

### Tip 1: Use tmux/screen for Persistent Dashboard
```bash
# Install tmux if not installed
sudo apt install tmux

# Start tmux session
tmux new -s dashboard

# Run dashboard
cd ~/ozzy-simple
./venv/bin/python scripts/live_dashboard.py

# Detach: Press Ctrl+B, then D
# Re-attach later: tmux attach -t dashboard
```

### Tip 2: Multiple Monitors
```bash
# Terminal 1: Live dashboard
./venv/bin/python scripts/live_dashboard.py

# Terminal 2: Live logs
tail -f bot.log | grep --color=always "A/B Test"

# Terminal 3: Bot status
watch -n 60 'ps aux | grep main.py'
```

### Tip 3: Save Dashboard Output
```bash
# Capture screenshot every minute
while true; do 
    ./venv/bin/python scripts/test_time_filter.py --status > status_$(date +%Y%m%d_%H%M).txt
    sleep 60
done
```

---

## 🚨 Troubleshooting

### Dashboard Shows 0 Trades
**Cause:** Trades haven't closed yet (just opened)  
**Solution:** Wait 15-30 minutes for first trades to close

### Rich Display Not Working
**Cause:** Rich library might not be installed  
**Solution:** Dashboard auto-falls back to simple text display

### High CPU Usage
**Cause:** Refresh rate too fast  
**Solution:** Increase refresh interval:
```bash
./venv/bin/python scripts/live_dashboard.py --refresh 30
```

### Dashboard Freezes
**Cause:** Database locked or bot crashed  
**Solution:** 
1. Press Ctrl+C to exit dashboard
2. Check bot: `ps aux | grep main.py`
3. Check logs: `tail -50 bot.log`

---

## 📱 Remote Monitoring

### SSH from Another Machine
```bash
# From your laptop/phone
ssh rick@your-server-ip

# Run dashboard
cd ~/ozzy-simple
./venv/bin/python scripts/live_dashboard.py
```

### Quick Status via SSH
```bash
# One-liner for quick check
ssh rick@server "cd ~/ozzy-simple && ./venv/bin/python scripts/test_time_filter.py --status"
```

---

## 🎯 Recommended Setup

### Daily Monitoring (Casual)
```bash
# Check once in the morning
./venv/bin/python scripts/test_time_filter.py --status
```

### Active Monitoring (Day Trader)
```bash
# Live dashboard while working
./venv/bin/python scripts/live_dashboard.py --refresh 10
```

### Intensive Monitoring (Testing Phase)
```bash
# Terminal 1: Dashboard
./venv/bin/python scripts/live_dashboard.py --refresh 5

# Terminal 2: Live logs
tail -f bot.log | grep -E "A/B Test|executed|P&L"
```

---

## 📊 Understanding the Numbers

### Win Rate
- **Control:** Your baseline (24/7 trading)
- **Test:** With time filter applied
- **Goal:** Test > Control by at least 2%

### Avg P&L
- Average profit/loss per trade
- **Control:** Your baseline (R29.65)
- **Test:** With time filter
- **Goal:** Test > Control by at least R5

### Progress
- Need 50 trades per group (100 total)
- At ~10-20 trades/day → 4-5 days
- Dashboard shows % complete

---

## 🎓 Quick Reference

| Command | Purpose | Refresh |
|---------|---------|---------|
| `live_dashboard.py` | Full dashboard | 10s |
| `live_dashboard.py --refresh 5` | Fast dashboard | 5s |
| `watch -n 30 ...` | Simple status | 30s |
| `tail -f bot.log` | Live logs | Real-time |
| `test_time_filter.py --status` | One-time check | Manual |

---

**Created:** October 11, 2025  
**Best Option:** `./venv/bin/python scripts/live_dashboard.py`  
**Press:** `Ctrl+C` to exit any live view  
