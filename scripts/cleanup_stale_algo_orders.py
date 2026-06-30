#!/usr/bin/env python3
"""
Minimal script to cancel stale reduce-only Binance USD-M Futures algo orders.
Dry-run by default. Requires --execute to perform actual cancellation.
Only cancels orders for symbols explicitly passed via --symbols.
Only cancels stale reduce-only STOP_MARKET and TAKE_PROFIT_MARKET orders
when reconciliation confirms no exchange position and no DB open trade for that symbol.
Fails closed on any uncertainty.
"""

import argparse
import sys
import os
from typing import List, Dict, Any

# Add the project root to the sys.path so we can import the project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load live-micro.env environment variables if the file exists
def _load_env_file(path):
    from pathlib import Path
    env_path = Path(path)
    if env_path.is_file():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip("'").strip('"')

_load_env_file(os.path.join(os.path.dirname(__file__), '..', 'config', 'live-micro.env'))
#
# Import existing modules (do not modify them)
try:
    from binance_connector import (
        get_open_positions,
        get_open_orders,
        get_open_algo_orders,
    )
    from trade_db import (
        get_open_trades,
        get_binance_order_states,
    )
except ImportError as e:
    print(f"Error importing required modules: {e}", file=sys.stderr)
    sys.exit(1)


def _truthy(value) -> bool:
    """Return True if value is True or string 'true' (case-insensitive)."""
    return value is True or str(value).lower() == "true"


def _algo_order_type(order: dict) -> str:
    """Return normalized order type string."""
    return str(order.get("type") or order.get("orderType") or "").upper()


def _is_reduce_only_stop_or_tp(order: dict) -> bool:
    """
    Check if order is a reduce-only STOP_MARKET or TAKE_PROFIT_MARKET order.
    reduceOnly can be boolean True or string "true".
    closePosition can be boolean True or string "true".
    """
    order_type = _algo_order_type(order)
    if order_type not in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
        return False
    reduce_only = _truthy(order.get("reduceOnly"))
    close_position = _truthy(order.get("closePosition"))
    return reduce_only or close_position


def get_stale_algo_orders_for_symbol(
    symbol: str,
    positions: List[Dict],
    normal_orders: List[Dict],
    algo_orders: List[Dict],
    db_open_trades: List[Dict],
    order_states: List[Dict],
) -> List[Dict]:
    """Identify stale algo orders for a given symbol.
    Uses the exact same stale_algo_orders classification logic as live_reconcile.py.
    """
    from live_reconcile import reconcile_snapshot
    res = reconcile_snapshot(
        equity=0.0,
        positions=positions,
        normal_orders=normal_orders,
        algo_orders=algo_orders,
        db_open_trades=db_open_trades,
        order_states=order_states,
    )
    # Find matching stale orders in res["stale_algo_orders"]
    stale_detail_list = [
        o for o in res.get("stale_algo_orders", [])
        if o.get("symbol") == symbol
    ]
    
    # We must return the actual elements from algo_orders that match the stale_detail_list,
    # so that callers can access the full raw order information.
    stale_orders = []
    for detail in stale_detail_list:
        for order in algo_orders:
            if order.get("symbol") != symbol:
                continue
            # Match by algo_id or client_algo_id
            order_algo_id = order.get("algoId")
            order_client_algo_id = order.get("clientAlgoId")
            detail_algo_id = detail.get("algo_id")
            detail_client_algo_id = detail.get("client_algo_id")
            
            if (detail_algo_id is not None and str(order_algo_id) == str(detail_algo_id)) or \
               (detail_client_algo_id is not None and order_client_algo_id == detail_client_algo_id):
                stale_orders.append(order)
                break
    return stale_orders


def main():
    parser = argparse.ArgumentParser(
        description="Cancel stale Binance algo orders (dry-run by default)."
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated list of symbols to check (e.g., ETHUSDT,LINKUSDT)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually cancel orders (default: dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode (default)",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("Error: No symbols provided", file=sys.stderr)
        sys.exit(1)

    is_execute = args.execute and not args.dry_run

    # Fetch live reconcile state (our single source of truth for stale algo orders)
    from live_reconcile import reconcile_live_state
    try:
        reconcile_res = reconcile_live_state(dry_run=True)
        stale_algo_orders = reconcile_res.get("stale_algo_orders", [])
    except Exception as e:
        print(f"Error fetching live state from reconcile: {e}", file=sys.stderr)
        sys.exit(1)

    # Filter stale algo orders by symbols requested
    all_stale_orders = [
        order for order in stale_algo_orders
        if order.get("symbol") in symbols
    ]

    if not all_stale_orders:
        print("No stale algo orders found for the specified symbols.")
        return

    # Print the exact dry-run output matching the expected format exactly
    # "LINKUSDT TAKE_PROFIT_MARKET 4000001377468990"
    for order in all_stale_orders:
        symbol = order.get("symbol")
        order_type = order.get("order_type") or "UNKNOWN"
        algo_id = order.get("algo_id") or order.get("client_algo_id")
        print(f"{symbol:<8} {order_type:<18} {algo_id}")

    if not is_execute:
        print("\nDRY-RUN: No orders were cancelled. Use --execute to perform actual cancellation.")
        return

    # Execute cancellations
    from binance_connector import _get_client
    client = _get_client()
    cancelled_count = 0
    failed_count = 0
    for order in all_stale_orders:
        symbol = order.get("symbol")
        algo_id = order.get("algo_id")
        client_algo_id = order.get("client_algo_id")

        if not algo_id and not client_algo_id:
            print(
                f"Skipping cancellation for {symbol}: missing algo_id/client_algo_id",
                file=sys.stderr,
            )
            failed_count += 1
            continue

        try:
            # Binance USD-M Futures endpoint for cancel algo order
            if algo_id:
                result = client.futures_cancel_algo_order(symbol=symbol, algoId=int(algo_id))
            else:
                result = client.futures_cancel_algo_order(symbol=symbol, clientAlgoId=client_algo_id)
            print(f"Cancelled algo order {algo_id or client_algo_id} for {symbol}: {result}")
            cancelled_count += 1
        except Exception as e:
            print(
                f"Failed to cancel algo order {algo_id or client_algo_id} for {symbol}: {e}",
                file=sys.stderr,
            )
            failed_count += 1

    print(f"\nCancellation complete: {cancelled_count} cancelled, {failed_count} failed.")


if __name__ == "__main__":
    main()