# 🎯 QUICK REFERENCE CARD

**Status:** ✅ Environment Ready | ⏳ Waiting for API Credentials

---

## 📍 Where You Are

```
Location: /home/rick/ozzy-simple/rescue/
Status:   Virtual env created ✓
          Dependencies installed ✓
          .env file created ✓
          
Next:     Add Bybit testnet credentials
```

---

## 🔑 Get Credentials (15 minutes)

1. **Open browser:** https://testnet.bybit.com
2. **Create account** (free, instant)
3. **Navigate to:** API Management
4. **Create API Key:**
   - Name: "OZZY Simple Test"
   - Enable: "Derivatives V3" ✓
5. **Copy:** API Key + API Secret
6. **Edit .env:**
   ```bash
   nano .env
   ```
7. **Paste your credentials:**
   ```
   BYBIT_API_KEY=your_actual_key_here
   BYBIT_API_SECRET=your_actual_secret_here
   ```
8. **Save:** Ctrl+O, Enter, Ctrl+X

---

## 🚀 Run First Test

```bash
cd /home/rick/ozzy-simple/rescue
source venv/bin/activate
python main_simple.py
```

**What happens:**
- ✅ Connects to Bybit testnet
- ✅ Fetches 100 4-hour BTCUSDT candles
- ✅ Calculates RSI, EMA, Volume
- ✅ Generates signal (LONG/SHORT/SKIP)
- ✅ Logs decision to logs/trading.log
- ⏰ Waits 4 hours for next check

**Stop bot:** Press Ctrl+C

---

## 📊 Monitor Progress

```bash
# Watch logs in real-time
tail -f logs/trading.log

# Count total decisions
grep "DECISION #" logs/trading.log | wc -l

# See what signals generated
grep "Signal:" logs/trading.log

# Check for errors
grep "ERROR" logs/trading.log
```

---

## ⚙️ Adjust Settings (If Needed)

**If all signals are SKIP:**

```bash
nano config/config.py
```

**Change these values:**
```python
MIN_CONFIDENCE = 20.0  # Lower from 30.0
RSI_OVERSOLD = 30      # Lower from 35
RSI_OVERBOUGHT = 70    # Raise from 65
VOLUME_MULTIPLIER = 1.2  # Lower from 1.3
```

**Save and restart bot**

---

## 🎯 Success Criteria

### Day 1 (Today):
- [x] Environment setup
- [ ] Get API credentials ← YOU ARE HERE
- [ ] Run first test
- [ ] Generate 5 decisions

### Week 1:
- [ ] 30+ decisions collected
- [ ] 5+ tradeable signals (>40% confidence)
- [ ] System runs stable

---

## 🆘 Troubleshooting

### "Authentication failed"
→ Check API key has "Derivatives V3" enabled
→ Verify you copied entire key (no spaces)

### "Connection timeout"
→ Check internet connection
→ Try again in 1 minute

### "All signals are SKIP"
→ Lower thresholds (see "Adjust Settings" above)

### "Module not found"
→ Make sure virtual env is activated:
   `source venv/bin/activate`

---

## 📚 Reference Files

- **Setup Guide:** `README.md`
- **This Card:** `QUICK_REFERENCE.md`
- **Full Summary:** `../RADICAL_SIMPLIFICATION_COMPLETE.md`
- **Evidence:** `../BEFORE_AFTER_COMPARISON.md`
- **Action Plan:** `../START_HERE_NOW.md`

---

## 🚫 Remember The Rules

**FORBIDDEN until profitable:**
- ❌ Adding ML
- ❌ Adding patterns
- ❌ Building agents
- ❌ Any complexity

**ALLOWED:**
- ✅ Run the bot
- ✅ Fix bugs
- ✅ Adjust thresholds
- ✅ Track results

---

## 💡 Philosophy

> "Simple beats complex.  
>  Execution beats architecture.  
>  Profit beats sophistication."

**You have 918 lines of code.**  
**That's enough to make money.**  
**Prove it first. Then sophisticate.**

---

**Next Action:** Get testnet credentials (15 min) → Run first test (5 min)

🎯 **You're 20 minutes from seeing your first signal!**
