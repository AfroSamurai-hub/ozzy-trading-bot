# 🇿🇦 ZAR Currency Support Implementation Plan

**Philosophy:** "Evolve, not add and break" ✅  
**Goal:** Add South African Rand (ZAR) support with minimal changes  
**Approach:** Centralized currency formatting + configuration

---

## 📋 Overview

**Current State:** All amounts hardcoded with `$` (USD)  
**Target State:** Configurable currency display (USD or ZAR)  
**Impact:** ~100 string formatting changes across 8 files

---

## 🎯 Strategy: Centralized Currency Formatter

### Step 1: Create Currency Utility Module (NEW FILE)
**File:** `utils/currency.py`

```python
"""
Centralized currency formatting for the trading system
"""
import os
from typing import Union

class CurrencyFormatter:
    """Format amounts in user's preferred currency"""
    
    def __init__(self):
        # Read from environment or default to USD
        self.currency = os.getenv("OZZY_CURRENCY", "USD").upper()
        self.usd_to_zar = float(os.getenv("OZZY_USD_TO_ZAR", "18.50"))
        
        self.symbols = {
            "USD": "$",
            "ZAR": "R"
        }
    
    def format(self, usd_amount: Union[float, int], decimals: int = 2) -> str:
        """
        Format amount in configured currency
        
        Args:
            usd_amount: Amount in USD (base currency)
            decimals: Decimal places (default: 2)
        
        Returns:
            Formatted string like "$1,234.56" or "R22,839.36"
        """
        if self.currency == "ZAR":
            amount = usd_amount * self.usd_to_zar
            symbol = "R"
        else:
            amount = usd_amount
            symbol = "$"
        
        return f"{symbol}{amount:,.{decimals}f}"
    
    def format_signed(self, usd_amount: Union[float, int], decimals: int = 2) -> str:
        """Format with + or - sign for P&L"""
        if self.currency == "ZAR":
            amount = usd_amount * self.usd_to_zar
            symbol = "R"
        else:
            amount = usd_amount
            symbol = "$"
        
        return f"{symbol}{amount:+,.{decimals}f}"

# Global instance
_formatter = CurrencyFormatter()

def format_currency(usd_amount: Union[float, int], decimals: int = 2) -> str:
    """Format amount in user's currency"""
    return _formatter.format(usd_amount, decimals)

def format_currency_signed(usd_amount: Union[float, int], decimals: int = 2) -> str:
    """Format amount with +/- sign"""
    return _formatter.format_signed(usd_amount, decimals)

def get_currency_code() -> str:
    """Get current currency code"""
    return _formatter.currency

def get_currency_symbol() -> str:
    """Get current currency symbol"""
    return _formatter.symbols.get(_formatter.currency, "$")
```

**Why this works:**
- ✅ All calculations stay in USD internally
- ✅ Only formatting changes to display layer
- ✅ Single place to update exchange rate
- ✅ Easy to add more currencies later
- ✅ Environment-based configuration

---

## 🔧 Step 2: Update Files (Surgical Changes)

### Files to Modify (8 files):

1. **agent/portfolio.py** (~10 changes)
   - Import: `from utils.currency import format_currency, format_currency_signed`
   - Replace: `f"${value:,.2f}"` → `format_currency(value)`
   - Replace: `f"${value:+.2f}"` → `format_currency_signed(value)`

2. **scripts/test_live_stream.py** (~15 changes)
   - Same pattern as above

3. **notifications/slack_notifier.py** (~15 changes)
   - All Slack message formatting

4. **dashboard/cli_monitor.py** (~20 changes)
   - Replace existing `format_currency()` function
   - Use new centralized version

5. **agent/trader.py** (~5 changes)
   - Logging statements

6. **scripts/test_pipeline.py** (~3 changes)
   - Output formatting

7. **scripts/quick_analysis.py** (~5 changes) - if exists
   - Output formatting

8. **scripts/run_validation_test.py** (~3 changes) - if exists
   - Output formatting

---

## 🚀 Implementation Steps

### Phase 1: Create Foundation (5 minutes)

```bash
cd ~/ozzy-simple
mkdir -p utils
touch utils/__init__.py
```

Create `utils/currency.py` with code above.

### Phase 2: Update Core Files (30 minutes)

**Strategy:**
1. Start with `agent/portfolio.py` (most critical)
2. Then `scripts/test_live_stream.py` (main script)
3. Then notifications and dashboard
4. Test after each file

### Phase 3: Configuration (2 minutes)

Add to `.env` or set environment:

```bash
# For USD (default)
export OZZY_CURRENCY=USD

# For ZAR
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50  # Update with current rate
```

### Phase 4: Test (10 minutes)

```bash
# Test USD (current behavior)
export OZZY_CURRENCY=USD
python scripts/test_pipeline.py --symbol BTCUSDT

# Test ZAR (new behavior)
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50
python scripts/test_pipeline.py --symbol BTCUSDT
```

---

## 📊 Before/After Examples

### USD Mode (Default):
```
💰 Starting capital: $5,000.00
📊 Position #1: BTCUSDT @ $112,570.50
💵 P&L: +$123.45 (+2.47%)
```

### ZAR Mode:
```
💰 Starting capital: R92,500.00
📊 Position #1: BTCUSDT @ R2,082,554.25
💵 P&L: +R2,283.83 (+2.47%)
```

---

## ⚠️ Important Notes

### What Stays in USD:
- ✅ All internal calculations
- ✅ Position sizes stored in portfolio
- ✅ Historical data
- ✅ API calls to Binance (they use USD pairs)

### What Changes to ZAR:
- ✅ Display in terminal
- ✅ Slack notifications
- ✅ Dashboard formatting
- ✅ Log files (human-readable parts)

### Exchange Rate Updates:
```python
# Option 1: Manual update in .env
OZZY_USD_TO_ZAR=18.50

# Option 2: Fetch from API (future enhancement)
# Add to utils/currency.py:
def update_exchange_rate():
    """Fetch latest USD/ZAR rate from API"""
    # Call exchange rate API
    # Update self.usd_to_zar
    pass
```

---

## 🎓 Why This Approach Works

### Follows "Evolve Not Add" Philosophy:
1. ✅ **Minimal changes:** Only formatting layer
2. ✅ **No breaking changes:** Internal calculations unchanged
3. ✅ **Single responsibility:** Currency logic in one place
4. ✅ **Easy rollback:** Remove import, revert formatting
5. ✅ **Extensible:** Easy to add EUR, GBP, etc.

### Benefits:
- 🎯 All calculations stay accurate (USD internally)
- 🎯 Easy to switch currencies (environment variable)
- 🎯 Consistent formatting across entire app
- 🎯 Simple to maintain and update exchange rates
- 🎯 No database or API changes needed

---

## 📝 Implementation Checklist

- [ ] Create `utils/__init__.py`
- [ ] Create `utils/currency.py` with formatter
- [ ] Test formatter standalone
- [ ] Update `agent/portfolio.py`
- [ ] Update `scripts/test_live_stream.py`
- [ ] Update `notifications/slack_notifier.py`
- [ ] Update `dashboard/cli_monitor.py`
- [ ] Update `agent/trader.py`
- [ ] Update `scripts/test_pipeline.py`
- [ ] Update `scripts/quick_analysis.py` (if exists)
- [ ] Update `scripts/run_validation_test.py` (if exists)
- [ ] Add `.env` configuration
- [ ] Test with USD (should work exactly as before)
- [ ] Test with ZAR (should show Rand amounts)
- [ ] Update README.md with currency configuration
- [ ] Run validation test with ZAR mode

---

## 🚦 Ready to Implement?

**Time Estimate:** 1 hour total
- 5 min: Create currency utility
- 30 min: Update 8 files
- 15 min: Testing
- 10 min: Documentation

**Risk Level:** LOW ✅
- No calculation changes
- Easy to rollback
- Backward compatible (defaults to USD)

---

## 🔥 Quick Start Command

Once implemented, switch currencies with:

```bash
# Use ZAR
export OZZY_CURRENCY=ZAR
export OZZY_USD_TO_ZAR=18.50
python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800

# Back to USD
export OZZY_CURRENCY=USD
python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800
```

**Both modes will produce identical P&L results, just different display!** 🎯
