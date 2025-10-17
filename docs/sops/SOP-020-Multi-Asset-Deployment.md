# 📊 SOP-020: Multi-Asset Deployment

**Purpose:** Add additional crypto pairs to diversify income streams  
**Applies To:** Phase 1.5 - Asset Scaling  
**Author:** OZZY Trading Bot Development  
**Date:** October 17, 2025  

---

## 🎯 GOAL

**Expand from BTC-only to 3-5 crypto pairs trading simultaneously**

**Why:**
- Diversify income (don't rely on single asset)
- Capture opportunities across multiple markets
- Smooth out volatility (correlation management)
- Scale to R10k+/week combined profit

**Current:** BTC only  
**Target:** BTC + ETH + SOL + (2 more pairs)  

---

## 📋 PREREQUISITES

**Before adding ANY new pair:**

✅ **Phase 1 COMPLETE**
- BTC trading profitable (R5k/week minimum)
- System stable (24/7 uptime)
- Win rate >50%
- Confidence levels working (>40%)

✅ **Infrastructure Ready**
- Master control (ozzy.py) operational
- Monitoring dashboard working
- Portfolio tracking accurate
- Sufficient processing power

✅ **Risk Management**
- Capital allocation plan defined
- Position sizing rules clear
- Correlation analysis prepared

---

## 🧪 TESTING PROTOCOL (Per New Pair)

### **Step 1: Historical Data Validation**

**Purpose:** Verify strategy works on new asset

```bash
# 1. Download historical data for new pair
cd ~/ozzy-simple/scripts
python download_historical.py --symbol ETHUSDT --days 90

# 2. Run backtesting
python backtest_strategy.py --symbol ETHUSDT --days 30

# 3. Check results:
# - Win rate >45% minimum
# - Confidence levels >40% for 50%+ of signals
# - Drawdown <20%
# - Positive P&L overall
```

**Success Criteria:**
- ✅ Win rate: >45%
- ✅ High confidence signals: >50%
- ✅ Drawdown: <20%
- ✅ Net positive P&L

**If FAILS:** Asset not suitable, try different pair

### **Step 2: Paper Trading Validation**

**Purpose:** Test in real-time market conditions

```bash
# 1. Add symbol to test config
# Edit bulletproof_test.py or create multi_asset_test.py

# 2. Run parallel paper trading (3-7 days minimum)
python multi_asset_test.py --symbols BTCUSDT,ETHUSDT --duration 259200

# 3. Monitor both pairs:
./ozzy.py status --multi

# 4. Compare profitability
python compare_asset_performance.py --symbols BTCUSDT,ETHUSDT
```

**Success Criteria:**
- ✅ New pair profitable independently
- ✅ Combined P&L > BTC alone
- ✅ Correlation not >0.9 (diversification benefit)
- ✅ No system crashes with 2 pairs

**If FAILS:** Troubleshoot or skip this pair

### **Step 3: Live Deployment (Small Capital)**

**Purpose:** Validate profitability in live trading

```bash
# 1. Allocate 20% of capital to new pair
# If R10k total → R2k for ETH, R8k stays in BTC

# 2. Deploy live
python live_trader.py --symbols BTCUSDT,ETHUSDT --capital-btc 8000 --capital-eth 2000

# 3. Monitor for 1 week minimum
./ozzy.py portfolio --breakdown

# 4. Track individual pair P&L
python asset_performance.py --days 7
```

**Success Criteria:**
- ✅ New pair profitable after 1 week
- ✅ Combined profit > BTC-only baseline
- ✅ System stable (no crashes)
- ✅ Monitoring tools accurate

**If FAILS:** Reduce allocation or remove pair

### **Step 4: Scale Capital Allocation**

**Purpose:** Optimize capital distribution

```bash
# After 2 weeks of successful trading:

# 1. Analyze optimal allocation
python optimize_allocation.py --symbols BTCUSDT,ETHUSDT --history 14

# 2. Rebalance based on performance
# Example output: BTC 60%, ETH 40%

# 3. Update live allocation
# Keep monitoring for another week

# 4. Finalize allocation if stable
```

**Success Criteria:**
- ✅ Allocation maximizes combined profit
- ✅ Risk balanced across pairs
- ✅ No single pair >60% of capital

---

## 🔄 ADDING ADDITIONAL PAIRS

**Order of Priority:**

### **Tier 1: High Priority (Add First)**
1. **ETHUSDT** - 2nd largest, high liquidity
2. **SOLUSDT** - High volatility, good opportunities

### **Tier 2: Medium Priority (Add After Tier 1 Stable)**
3. **ADAUSDT** - Stable, good volume
4. **MATICUSDT** - Strong fundamentals
5. **DOGEUSDT** - High volatility (use cautiously)

### **Tier 3: Advanced (Phase 2+)**
6. **AVAXUSDT**
7. **LINKUSDT**
8. **DOTUSDT**

**MAX in Phase 1.5:** 5 pairs total

---

## 💰 CAPITAL ALLOCATION STRATEGY

### **Starting Allocation (BTC + ETH)**

```
Total Capital: R10,000

Initial Split:
- BTC: R7,000 (70%) - Proven performer
- ETH: R3,000 (30%) - New pair, conservative
```

### **After ETH Proven (BTC + ETH + SOL)**

```
Total Capital: R10,000

Optimized Split:
- BTC: R5,000 (50%)
- ETH: R3,000 (30%)
- SOL: R2,000 (20%)
```

### **Full Phase 1.5 (5 Pairs)**

```
Total Capital: R20,000 (scaled from profits!)

Optimized Split:
- BTC: R8,000 (40%)
- ETH: R6,000 (30%)
- SOL: R3,000 (15%)
- ADA: R2,000 (10%)
- MATIC: R1,000 (5%)
```

**Rule:** No single pair >50% of total capital

---

## 🔍 MONITORING MULTI-ASSET PORTFOLIO

### **Daily Checks**

```bash
# 1. Overall status
./ozzy.py status --multi

# 2. Individual pair performance
./ozzy.py portfolio --breakdown

# 3. Correlation check
python check_correlation.py --days 7
```

**Watch For:**
- Pairs moving together (high correlation = less diversification)
- One pair consistently losing (consider removing)
- Total capital drifting (rebalance if needed)

### **Weekly Analysis**

```bash
# Generate weekly report
python weekly_multi_asset_report.py

# Check:
# - Per-pair P&L
# - Combined P&L vs BTC-only baseline
# - Win rates per pair
# - Optimal allocation suggestions
```

---

## ⚠️ RISK MANAGEMENT

### **Correlation Limits**

```python
# Check correlation between pairs
correlation_matrix = calculate_correlation(['BTC', 'ETH', 'SOL'])

# Rule: If correlation >0.8 between 2 pairs, reduce allocation
# Why: Not true diversification if moving together
```

### **Drawdown Limits**

```python
# Per-pair max drawdown: 20%
# Total portfolio max drawdown: 15%

# If exceeded:
# 1. Reduce allocation to that pair
# 2. Increase cash reserves
# 3. Review strategy effectiveness
```

### **Position Size Limits**

```python
# Per trade:
# - BTC: Max 10% of BTC allocation
# - ETH: Max 10% of ETH allocation
# - SOL: Max 8% of SOL allocation (more volatile)

# Why: No single trade should risk >2% of TOTAL capital
```

---

## 🚨 TROUBLESHOOTING

### **Issue: New Pair Constantly Losing**

**Symptoms:**
- Win rate <40% on new pair
- Negative P&L after 2 weeks
- Confidence levels low

**Solution:**
```bash
# 1. Check if pair suitable
python analyze_pair_suitability.py --symbol ETHUSDT

# 2. Review strategy parameters
# May need pair-specific tuning

# 3. If still unprofitable after 1 month:
# → REMOVE the pair, stick with winners
```

### **Issue: All Pairs Moving Together (High Correlation)**

**Symptoms:**
- Correlation >0.9 between pairs
- All pairs profit/loss same days
- No diversification benefit

**Solution:**
```bash
# 1. Check correlation
python check_correlation.py

# 2. If >0.8, reduce overlapping pairs
# Example: If BTC and ETH correlated, keep BTC, add different pair

# 3. Consider non-crypto assets (Phase 3+)
```

### **Issue: System Can't Handle Multiple Pairs**

**Symptoms:**
- Crashes when running 3+ pairs
- Slow execution
- Memory issues

**Solution:**
```bash
# 1. Check system resources
top
df -h

# 2. May need hardware upgrade (Milestone 1.5.5)
# 3. Optimize code (parallel processing)
# 4. Reduce number of pairs until hardware ready
```

---

## ✅ SUCCESS CRITERIA (Per Pair)

**Before marking milestone complete:**

| Metric | Target | How to Check |
|--------|--------|--------------|
| **Win Rate** | >45% | `python analyze_pair.py --symbol X` |
| **Profitability** | Positive P&L over 2 weeks | `./ozzy.py portfolio --breakdown` |
| **Confidence** | >40% for 50%+ of signals | Review decision logs |
| **Stability** | 0 crashes | `./ozzy.py status` |
| **Correlation** | <0.8 with existing pairs | `python check_correlation.py` |

---

## 📈 MILESTONE COMPLETION

### **1.5.1: Add ETH Trading**

```bash
# When ETH profitable for 2 weeks:
python3 MASTER_PLANNER.py complete 1.5.1
```

### **1.5.2: Add SOL Trading**

```bash
# When SOL profitable for 2 weeks:
python3 MASTER_PLANNER.py complete 1.5.2
```

### **1.5.6: Add 2 More Pairs**

```bash
# When 5 pairs all profitable:
python3 MASTER_PLANNER.py complete 1.5.6
```

---

## 📚 RELATED DOCUMENTATION

- **SOP-002-Testing-Protocol.md** - Testing procedures
- **SOP-021-Portfolio-Allocation.md** - Capital management
- **TRACKING_GUIDE.md** - Portfolio tracking
- **ARCHITECTURE.md** - System design

---

## 🎯 THE VISION

**Phase 1:** BTC only → R5k/week  
**Phase 1.5:** 5 pairs → R10k+/week  
**Phase 2+:** Optimized → R20k+/week  
**End Game:** Professional operation → R100k+/week  

**Each pair is a new income stream. Diversify. Scale. Dominate.** 💰

---

**Last Updated:** October 17, 2025  
**Status:** ACTIVE  
**Next:** Add ETH (Milestone 1.5.1)
