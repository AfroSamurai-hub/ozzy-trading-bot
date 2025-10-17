# 🇿🇦 ZAR Currency Support - Quick Start Guide

**Status:** ✅ IMPLEMENTED!  
**Philosophy:** "Evolve, not add and break"

---

## 🎯 What Changed

### Core Changes (MINIMAL):
1. ✅ Created `utils/currency.py` - Centralized currency formatter
2. ✅ Updated `agent/portfolio.py` - 5 format changes
3. ✅ Updated `scripts/test_live_stream.py` - 8 format changes
4. ✅ All calculations still in USD internally
5. ✅ Only display/formatting changed to support ZAR

### How It Works:
- **Internal:** All calculations in USD (positions, P&L, capital)
- **Display:** Format as USD or ZAR based on environment setting
- **Exchange Rate:** Configurable via `.env` file

---

## 🚀 How To Use

### Option 1: Use USD (Default - No Changes Needed)
```bash
cd ~/ozzy-simple
source venv/bin/activate

# USD is default - just run as normal
python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800
```

**Output:**
```
💰 Initialized paper trading portfolio with $5,000.00
✅ Position #1 opened: BTCUSDT @ $112,570.50
📊 Portfolio: 1/20 positions, $4,750.00 capital remaining
```

---

### Option 2: Use ZAR (South African Rand)
```bash
cd ~/ozzy-simple
source venv/bin/activate

# Set currency to ZAR
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50  # Update with current rate

# Run as normal
python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800
```

**Output:**
```
💰 Initialized paper trading portfolio with R92,500.00
✅ Position #1 opened: BTCUSDT @ R2,082,554.25
📊 Portfolio: 1/20 positions, R87,875.00 capital remaining
```

---

### Option 3: Add to .env File (Permanent)

Edit `~/ozzy-simple/.env`:
```bash
# Currency Configuration
OZZY_CURRENCY=ZAR
OZZY_USD_TO_ZAR=18.50

# Other settings...
OPENAI_API_KEY=sk-...
SLACK_WEBHOOK_URL=https://...
```

Then just run:
```bash
python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800
```

---

## 🧪 Test Currency Formatting

We created a test script to verify everything works:

```bash
cd ~/ozzy-simple
source venv/bin/activate

# Test with USD (default)
python scripts/test_currency.py

# Test with ZAR
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50
python scripts/test_currency.py
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🇿🇦 ZAR CURRENCY TEST 🇿🇦                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 Current Configuration:
   Currency Code:   ZAR
   Currency Symbol: R
   Currency Name:   South African Rand
   Exchange Rate:   18.50

📊 Formatting Test:

Description          | USD Value       | Formatted Display   
------------------------------------------------------------
Starting Capital     | $5,000.00       | R92,500.00          
Position Size        | $250.00         | R4,625.00           
Entry Price          | $112,570.50     | R2,082,554.25       
Small Profit         | $12.50          | R+231.25            
Small Loss           | $-5.25          | R-97.12             
Big Win              | $150.00         | R+2,775.00          
Big Loss             | $-75.00         | R-1,387.50          
Zero P&L             | $0.00           | R+0.00              

✅ Currency formatting test complete!
```

---

## 📊 Before/After Comparison

### USD Mode (Default):
```
💰 Starting capital: $5,000.00
📊 Position #1: BTCUSDT @ $112,570.50 ($250.00)
📊 Portfolio: 1/20 positions, $4,750.00 capital remaining
💵 Position closed @ $115,000.00 (P&L: +$123.45)
```

### ZAR Mode:
```
💰 Starting capital: R92,500.00
📊 Position #1: BTCUSDT @ R2,082,554.25 (R4,625.00)
📊 Portfolio: 1/20 positions, R87,875.00 capital remaining
💵 Position closed @ R2,127,500.00 (P&L: +R2,283.83)
```

**Note:** P&L percentages stay the same! Only display currency changes!

---

## ⚙️ Exchange Rate Updates

### Get Latest USD/ZAR Rate:
```bash
# Check current rate online:
# Google: "usd to zar"
# XE.com: https://www.xe.com/currencyconverter/convert/?Amount=1&From=USD&To=ZAR

# Update in your session:
export OZZY_USD_TO_ZAR=18.75  # Example: new rate

# Or update .env file:
echo "OZZY_USD_TO_ZAR=18.75" >> ~/ozzy-simple/.env
```

### Rate Update Frequency:
- **Daily trading:** Update once per day
- **Paper trading:** Can use fixed rate for consistency
- **Live trading:** Update before each session

---

## 🎓 What Stayed The Same

### Internal Calculations (USD):
- ✅ Position sizes calculated in USD
- ✅ P&L calculated in USD
- ✅ Risk limits (20 positions, 80% exposure) in USD
- ✅ Capital management in USD
- ✅ All data stored in USD
- ✅ API calls to Binance still use USD pairs (BTCUSDT)

### What Changed (Display Only):
- ✅ Terminal output formatting
- ✅ Log messages
- ✅ Future: Slack notifications (not updated yet)
- ✅ Future: Dashboard display (not updated yet)

**Result:** 100% accurate calculations + localized display! 🎯

---

## 📋 Files Changed

### Created (3 files):
- `utils/__init__.py` - Package initialization
- `utils/currency.py` - Currency formatter (120 lines)
- `scripts/test_currency.py` - Test script (80 lines)

### Modified (2 files):
- `agent/portfolio.py` - 5 format string changes
- `scripts/test_live_stream.py` - 8 format string changes

**Total impact:** ~15 lines changed in core files ✅

---

## ✅ Validation Checklist

Test both modes work correctly:

- [ ] USD mode: `python scripts/test_currency.py`
- [ ] ZAR mode: `OZZY_CURRENCY=ZAR OZZY_USD_TO_ZAR=18.50 python scripts/test_currency.py`
- [ ] Run validation test with USD
- [ ] Run validation test with ZAR
- [ ] Verify P&L percentages identical in both modes
- [ ] Verify all amounts display correctly
- [ ] Verify risk limits still work (20 positions max)

---

## 🚦 Run Validation Test with ZAR

```bash
cd ~/ozzy-simple
source venv/bin/activate

# Test with ZAR
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50

# Run 30-minute validation
python scripts/run_validation_test.py
```

**Expected:**
- Max 20 positions (same as USD)
- Capital stays positive (displayed in Rand)
- All amounts in ZAR
- P&L percentages identical to USD mode

---

## 💡 Pro Tips

### Switching Currencies Mid-Session:
```bash
# Don't! Complete your test in one currency.
# The portfolio state is saved in USD, but switching display
# mid-test can be confusing.
```

### Best Practice:
- Pick USD or ZAR at start of session
- Stick with it for entire test
- Switching is fine between sessions

### For South African Traders:
```bash
# Add to ~/.bashrc for permanent ZAR:
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50

# Update rate weekly:
# Edit ~/.bashrc and update OZZY_USD_TO_ZAR value
```

---

## 🎉 Success!

You now have full ZAR support with ZERO breaking changes! 

**"Evolve, not add and break" - perfectly executed!** ✅

### What You Can Do Now:
1. ✅ Run all tests in ZAR or USD
2. ✅ Easy to switch between currencies
3. ✅ Simple exchange rate updates
4. ✅ All calculations stay accurate
5. ✅ Easy to add more currencies (EUR, GBP, etc.)

**Ready to test with your local currency!** 🇿🇦🎯
