#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from binance_connector import (
    get_open_positions,
    get_open_orders,
    get_open_algo_orders,
)
import trade_db

def main():
    print("Fetching data for cleanup script...")
    
    positions = get_open_positions() or []
    print(f"Positions: {positions}")
    
    normal_orders = get_open_orders() or []
    print(f"Normal orders count: {len(normal_orders)}")
    
    algo_orders = get_open_algo_orders() or []
    print(f"Algo orders count: {len(algo_orders)}")
    for order in algo_orders:
        print(f"  Algo order: {order.get('symbol')} {order.get('type')} reduceOnly={order.get('reduceOnly')} closePosition={order.get('closePosition')} orderId={order.get('orderId')} algoId={order.get('algoId')}")
    
    db_open_trades = trade_db.get_open_trades() or []
    print(f"DB open trades: {db_open_trades}")
    
    order_states = trade_db.get_binance_order_states() or []
    print(f"Order states count: {len(order_states)}")
    
    # Now test the cleanup function for each symbol
    from scripts.cleanup_stale_algo_orders import get_stale_algo_orders_for_symbol, _is_reduce_only_stop_or_tp
    
    symbols = ["ETHUSDT", "LINKUSDT"]
    for symbol in symbols:
        print(f"\n--- Testing symbol {symbol} ---")
        stale = get_stale_algo_orders_for_symbol(
            symbol=symbol,
            positions=positions,
            normal_orders=normal_orders,
            algo_orders=algo_orders,
            db_open_trades=db_open_trades,
            order_states=order_states,
        )
        print(f"Stale orders found: {len(stale)}")
        for order in stale:
            print(f"  {order.get('symbol')} {order.get('type')} orderId={order.get('orderId')} algoId={order.get('algoId')}")

if __name__ == "__main__":
    main()