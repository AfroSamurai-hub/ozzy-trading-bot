#!/usr/bin/env python3
"""Test if prices are actually changing"""
import time
from bybit_client import BybitClient
from datetime import datetime

client = BybitClient()

print("🔍 Testing Live Price Updates...")
print("=" * 60)

previous_prices = {}
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

for i in range(10):
    print(f"\n[Check #{i+1} - {datetime.now().strftime('%H:%M:%S')}]")
    
    for symbol in symbols:
        current_price = client.get_current_price(symbol)
        
        if current_price is None:
            print(f"{symbol}: ❌ Failed to get price")
            continue
        
        if symbol in previous_prices:
            change = current_price - previous_prices[symbol]
            try:
                pct_change = (change / previous_prices[symbol]) * 100
            except (ZeroDivisionError, TypeError):
                pct_change = 0.0
            
            if abs(change) < 0.01:
                status = "⏸️ FROZEN"
            elif change > 0:
                status = f"📈 +${change:.2f} (+{pct_change:.3f}%)"
            else:
                status = f"📉 ${change:.2f} ({pct_change:.3f}%)"
            
            print(f"{symbol}: ${current_price:,.2f} {status}")
        else:
            print(f"{symbol}: ${current_price:,.2f} (baseline)")
        
        previous_prices[symbol] = current_price
    
    if i < 9:
        time.sleep(3)

print("\n" + "=" * 60)
print("✅ Test complete!")
