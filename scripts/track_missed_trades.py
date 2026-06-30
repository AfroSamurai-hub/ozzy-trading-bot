#!/usr/bin/env python3
import requests
import sys
from datetime import datetime, UTC

def check_trade_performance(symbol, direction, entry_price, sl, tp, start_time_ms):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_time_ms,
        "limit": 1500
    }
    
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return None
        
    klines = resp.json()
    if not klines:
        return None
        
    highest_price = -1.0
    lowest_price = 99999999.0
    hit_sl = False
    hit_tp = False
    sl_time = None
    tp_time = None
    first_hit = None
    
    for k in klines:
        h = float(k[2])
        l = float(k[3])
        
        highest_price = max(highest_price, h)
        lowest_price = min(lowest_price, l)
        
        t_dt = datetime.fromtimestamp(k[0] / 1000, UTC).strftime("%H:%M:%S UTC")
        
        if direction == "BUY":
            if l <= sl and not hit_sl:
                hit_sl = True
                sl_time = t_dt
                if first_hit is None:
                    first_hit = "SL"
            if h >= tp and not hit_tp:
                hit_tp = True
                tp_time = t_dt
                if first_hit is None:
                    first_hit = "TP"
        else: # SELL
            if h >= sl and not hit_sl:
                hit_sl = True
                sl_time = t_dt
                if first_hit is None:
                    first_hit = "SL"
            if l <= tp and not hit_tp:
                hit_tp = True
                tp_time = t_dt
                if first_hit is None:
                    first_hit = "TP"
                    
    curr_resp = requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}")
    curr_price = float(curr_resp.json()["price"]) if curr_resp.status_code == 200 else float(klines[-1][4])
    
    pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0 if direction == "BUY" else ((entry_price - curr_price) / entry_price) * 100.0
    
    return {
        "symbol": symbol,
        "direction": direction,
        "entry": entry_price,
        "sl": sl,
        "tp": tp,
        "highest": highest_price,
        "lowest": lowest_price,
        "current": curr_price,
        "pnl_pct": pnl_pct,
        "first_hit": first_hit,
        "sl_time": sl_time,
        "tp_time": tp_time
    }

def main():
    # SOLUSDT: entry=86.55, sl=85.10, tp=89.45, timestamp=1779617104000 (12:05 SAST)
    sol = check_trade_performance("SOLUSDT", "BUY", 86.55, 85.10, 89.45, 1779617104000)
    # XAUUSDT: entry=4551.56, sl=4546.56, tp=4564.06, timestamp=1779613507000 (11:05 SAST)
    xau = check_trade_performance("XAUUSDT", "BUY", 4551.56, 4546.56, 4564.06, 1779613507000)

    print("\n" + "="*58)
    print("💎  OZZYBOT MISSED SIGNAL TRACKER  💎")
    print("="*58)
    
    for res in [sol, xau]:
        if not res:
            continue
        print(f"\n🏷️  Asset:  {res['symbol']} ({res['direction']})")
        print(f"  🔹 Entry Price:  ${res['entry']:.2f}")
        print(f"  🛡️ Stop Loss:    ${res['sl']:.2f}")
        print(f"  🎯 Take Profit:  ${res['tp']:.2f}")
        print(f"  " + "─"*30)
        print(f"  💵 Current:      ${res['current']:.2f}")
        print(f"  📈 Highest 1m:   ${res['highest']:.2f}")
        print(f"  📉 Lowest 1m:    ${res['lowest']:.2f}")
        
        pnl_val = res['pnl_pct']
        pnl_str = f"{pnl_val:+.2f}%"
        pnl_color = "\033[92m" if pnl_val >= 0 else "\033[91m"
        pnl_reset = "\033[0m"
        print(f"  📊 Performance:  {pnl_color}{pnl_str}{pnl_reset}")
        
        if res['first_hit']:
            status_text = f"CLOSED via {res['first_hit']} at {res['tp_time'] if res['first_hit'] == 'TP' else res['sl_time']}"
            color = "\033[92m🟢 " if res['first_hit'] == "TP" else "\033[91m🔴 "
            print(f"  ⚡ Status:       {color}{status_text}{pnl_reset}")
        else:
            print(f"  ⚡ Status:       \033[93m🟡 OPEN & ACTIVE\033[0m")
            
    print("\n" + "="*58 + "\n")

if __name__ == "__main__":
    main()
