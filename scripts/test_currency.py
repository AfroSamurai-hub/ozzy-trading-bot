#!/usr/bin/env python3
"""
Test ZAR Currency Formatting

Quick test to verify ZAR currency support is working
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.currency import (
    format_currency,
    format_currency_signed,
    get_currency_code,
    get_currency_symbol,
    get_currency_name,
    get_exchange_rate
)

def test_currency_formatting():
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "🇿🇦 ZAR CURRENCY TEST 🇿🇦" + " " * 32 + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    # Show current configuration
    print("📋 Current Configuration:")
    print(f"   Currency Code:   {get_currency_code()}")
    print(f"   Currency Symbol: {get_currency_symbol()}")
    print(f"   Currency Name:   {get_currency_name()}")
    print(f"   Exchange Rate:   {get_exchange_rate():.2f}")
    print()
    
    # Test amounts
    test_amounts = [
        ("Starting Capital", 5000.00),
        ("Position Size", 250.00),
        ("Entry Price", 112570.50),
        ("Small Profit", 12.50),
        ("Small Loss", -5.25),
        ("Big Win", 150.00),
        ("Big Loss", -75.00),
        ("Zero P&L", 0.00),
    ]
    
    print("📊 Formatting Test:")
    print()
    print(f"{'Description':<20} | {'USD Value':<15} | {'Formatted Display':<20}")
    print("-" * 60)
    
    for desc, amount in test_amounts:
        if amount >= 0:
            formatted = format_currency(amount)
        else:
            formatted = format_currency_signed(amount)
        
        print(f"{desc:<20} | ${amount:<14,.2f} | {formatted:<20}")
    
    print()
    print("✅ Currency formatting test complete!")
    print()
    
    # Show how to switch currencies
    current = get_currency_code()
    other = "ZAR" if current == "USD" else "USD"
    
    print("💡 To switch currencies, set environment variables:")
    print()
    print(f"   # Switch to {other}:")
    print(f"   export OZZY_CURRENCY={other}")
    if other == "ZAR":
        print(f"   export OZZY_USD_TO_ZAR=18.50  # Update with current rate")
    print()
    print("   # Run your script:")
    print("   python scripts/test_live_stream.py --symbol BTCUSDT --duration 1800")
    print()

if __name__ == "__main__":
    test_currency_formatting()
