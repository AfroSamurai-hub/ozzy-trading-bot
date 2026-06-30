#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Load the live micro env to get the right config
from pathlib import Path
ROOT = Path(__file__).resolve().parents[0]
LIVE_ENV = ROOT / "config" / "live-micro.env"
if LIVE_ENV.exists():
    for raw in LIVE_ENV.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'").strip('"')

from live_reconcile import reconcile_snapshot
from binance_connector import (
    get_balance,
    get_open_positions,
    get_open_orders,
    get_open_algo_orders,
)
import trade_db

def main():
    print("Fetching live data...")
    
    balance = get_balance()
    print(f"Balance: {balance}")
    
    positions = get_open_positions()
    print(f"Positions count: {len(positions) if positions else 0}")
    if positions:
        for p in positions[:3]:  # Show first 3
            print(f"  Position: {p}")
    
    normal_orders = get_open_orders()
    print(f"Normal orders count: {len(normal_orders) if normal_orders else 0}")
    if normal_orders:
        for o in normal_orders[:3]:  # Show first 3
            print(f"  Normal order: {o}")
    
    algo_orders = get_open_algo_orders()
    print(f"Algo orders count: {len(algo_orders) if algo_orders else 0}")
    if algo_orders:
        for o in algo_orders[:5]:  # Show first 5
            print(f"  Algo order: {o}")
    
    db_open_trades = trade_db.get_open_trades()
    print(f"DB open trades count: {len(db_open_trades) if db_open_trades else 0}")
    if db_open_trades:
        for t in db_open_trades[:3]:  # Show first 3
            print(f"  DB trade: {t}")
    
    order_states = trade_db.get_binance_order_states()
    print(f"Order states count: {len(order_states) if order_states else 0}")
    if order_states:
        for s in order_states[:3]:  # Show first 3
            print(f"  Order state: {s}")
    
    # Now run the reconciliation snapshot
    print("\nRunning reconciliation snapshot...")
    result = reconcile_snapshot(
        equity=float(balance.get("equity", 0) or 0),
        positions=positions or [],
        normal_orders=normal_orders or [],
        algo_orders=algo_orders or [],
        db_open_trades=db_open_trades or [],
        order_states=order_states or [],
    )
    
    print(f"Healthy: {result['healthy']}")
    print(f"Stale algo order count: {result['stale_algo_order_count']}")
    print(f"Stale algo orders: {result['stale_algo_orders']}")

if __name__ == "__main__":
    main()