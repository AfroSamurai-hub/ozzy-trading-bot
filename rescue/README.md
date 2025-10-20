# OZZY SIMPLE - The Rescue Plan

## 🚨 What Happened?

We over-engineered to the point of paralysis:
- **25,083 Python files** (should be ~5)
- **324 Markdown docs** (should be ~1)
- Hedge fund infrastructure for R10K capital
- Agent councils before first profitable trade

## ✅ The Fix

Radical simplification. **5 files. <1000 lines total.**

## 📁 Project Structure

```
rescue/
├── config/
│   └── config.py          # Settings (100 lines)
├── src/
│   ├── simple_signals.py  # RSI+EMA+Volume strategy (180 lines)
│   ├── simple_risk.py     # 1% risk management (150 lines)
│   └── bybit_client.py    # Bybit V5 API wrapper (200 lines)
├── logs/                  # Trading logs (auto-created)
├── main_simple.py         # Main bot (200 lines)
├── requirements.txt       # 4 dependencies only
├── .env.example           # API credentials template
└── README.md              # This file
```

**Total: ~830 lines of code**

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (4 packages only!)
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env and add your Bybit testnet API keys
```

### 2. Get Testnet Credentials

1. Go to https://testnet.bybit.com
2. Create account (free)
3. Go to API Management
4. Create new API key with "Derivatives V3" permissions
5. Add your IP to whitelist
6. Copy API key and secret to `.env`

### 3. Run First Test

```bash
python main_simple.py
```

**Expected output:**
- Connects to Bybit testnet ✅
- Fetches 100 candles ✅
- Generates signal (LONG/SHORT/SKIP) ✅
- Logs decision ✅
- Waits 4 hours for next check ✅

## 🎯 Strategy Explained

### Simple RSI + EMA + Volume

**LONG Signal (Buy):**
- RSI < 35 (oversold)
- EMA(20) > EMA(50) (uptrend)
- Price > EMA(20) (above short-term trend)
- Volume > 1.3× average (spike)

**SHORT Signal (Sell):**
- RSI > 65 (overbought)
- EMA(20) < EMA(50) (downtrend)
- Price < EMA(20) (below short-term trend)
- Volume > 1.3× average (spike)

**Risk Management:**
- 1% risk per trade
- Stop loss: 1.5× ATR from entry
- Take profit: 2:1 risk/reward
- Max 2 positions open
- 3% daily loss limit

## 📊 Configuration

Edit `config/config.py` to adjust:

```python
RSI_OVERSOLD = 35        # Lower = more aggressive
RSI_OVERBOUGHT = 65      # Higher = more aggressive
MIN_CONFIDENCE = 30.0    # Lower = more signals
VOLUME_MULTIPLIER = 1.3  # Lower = more signals
TIMEFRAME = "4h"         # 4-hour candles (recommended)
CHECK_INTERVAL = 14400   # 4 hours in seconds
```

## 🎓 The 7-Day Challenge

### Day 1 (Today):
- ✅ Setup environment
- ✅ Test Bybit connection
- ✅ Get first 5 decisions

### Day 2:
- Run 24-hour test
- Collect 10+ decisions
- Verify signals make sense

### Day 3-4:
- Analyze decisions
- Adjust thresholds if needed
- Fix any bugs

### Day 5-7:
- Run 3-day continuous test
- Target: 30+ decisions
- Success: 5+ tradeable signals (40%+ confidence)

## ⚠️ Rules to Live By

### ✅ DO:
- Execute trades
- Track results
- Fix what breaks
- Stay simple

### ❌ DON'T:
- Add ML "to improve"
- Add more indicators "to filter"
- Read about agent councils
- Build fancy infrastructure

### 🎯 Goal Hierarchy:

1. **Month 1:** Get system running → 10+ trades
2. **Month 2:** Get 100 decisions → Analyze
3. **Month 3:** Get 50%+ win rate → Consistency
4. **Month 4-6:** Get R5K/week → Prove edge
5. **Month 7-12:** Scale capital → R50K
6. **Year 2:** THEN add complexity if needed

## 📈 When to Add Features

**Priority 1 (Fix First):**
- API connection issues
- Signal generation bugs
- Position sizing errors

**Priority 2 (After 100 Decisions):**
- Optimize thresholds from data
- Add trailing stop loss
- Better logging/CSV tracking

**Priority 3 (After Profitable):**
- Add 2nd symbol (ETHUSDT)
- Add 2nd timeframe (1H)
- Improve risk correlation

**Priority 4 (After 6 Months Profitable):**
- Revisit complex features in archive/
- Consider if ML helps
- Look at agent councils

## 🔧 Troubleshooting

### "No API credentials"
→ Create `.env` file with your Bybit keys

### "All signals are SKIP"
→ Lower `MIN_CONFIDENCE` to 20%
→ Adjust RSI thresholds (30/70 instead of 35/65)

### "401 Authentication error"
→ Check API key permissions (need "Derivatives V3")
→ Check IP whitelist on Bybit

### "No candle data"
→ Check internet connection
→ Verify Bybit testnet is up

## 📚 What About The Complex Stuff?

All the complex code (25K+ files) is still in the parent directory.

**It's archived, not deleted.**

Once you're profitable with this simple system for 6 months, you can revisit:
- Machine learning features
- Pattern intelligence
- Agent councils
- Institutional infrastructure

But NOT before.

## 🏁 Success Criteria

**Week 1:**
- Bot runs without crashing ✅
- Generates 30+ decisions ✅
- At least 5 tradeable signals (>40% confidence) ✅

**Month 1:**
- 100+ decisions collected
- System stable 99%+ uptime
- Signals make logical sense

**Month 3:**
- Win rate ≥ 45%
- Positive net P&L
- Ready for live trading with R2K

**Month 6:**
- R5K/week profit target hit
- System runs autonomously
- Time to scale or sophisticate

## 💡 Philosophy

> "Complexity is the enemy of execution."

You don't need neural networks to make money.

You need:
1. A simple edge (RSI+EMA+Volume)
2. Proper risk management (1% rule)
3. Consistent execution (no emotions)
4. Time to compound (patience)

That's it.

---

**Remember:** Renaissance Technologies didn't start with 150 PhDs. They started simple and scaled over 30 years.

You're on Day 0. Act like it. 🚀
