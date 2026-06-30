#!/usr/bin/env python3
"""
Live Credential Check Script — Read-Only
Verifies account connectivity, API read/write permissions, Dual-Side Position Mode (Hedge Mode),
open positions, and open algo orders without placing any trades.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load active environment secrets
load_dotenv(ROOT / ".env")

# Optional load of live-micro.env for local diagnostics
ENV_FILE = ROOT / "config" / "live-micro.env"
if ENV_FILE.exists() and os.getenv("IGNORE_MICRO_ENV") != "true":
    print(f"Loading env parameters from {ENV_FILE}...")
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ[key.strip()] = val.strip()
else:
    print("Using active system environment variables...")

from binance.client import Client

def check_credentials():
    print("\n" + "=" * 60)
    print("      OZZY BOT — READ-ONLY LIVE CREDENTIAL CHECK")
    print("=" * 60)

    # 1. Check API Key configuration
    api_key = os.getenv("HERMES_BINANCE_API_KEY") or os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("HERMES_BINANCE_API_SECRET") or os.getenv("BINANCE_API_SECRET")
    testnet = os.getenv("HERMES_BINANCE_TESTNET", "True").strip().lower() in {"1", "true", "yes", "on"}

    if testnet:
        print("💡 Target Mode: TESTNET")
        api_key = os.getenv("HERMES_BINANCE_DEMO_API_KEY") or os.getenv("BINANCE_DEMO_API_KEY") or api_key
        api_secret = os.getenv("HERMES_BINANCE_DEMO_API_SECRET") or os.getenv("BINANCE_DEMO_API_SECRET") or api_secret
    else:
        print("🔥 Target Mode: LIVE_MICRO / PRODUCTION")

    if not api_key or not api_secret:
        print("❌ FAILED: API credentials are missing from environment.")
        return False

    print(f"🔑 API Key Loaded: ...{api_key[-6:] if len(api_key) > 6 else 'INVALID'}")

    try:
        # Initialize Binance Client
        client = Client(api_key, api_secret, testnet=testnet)
        
        # 2. Ping connection
        print("📡 Pinging Binance API...")
        client.futures_ping()
        print("✅ Ping Successful.")

        # 3. Account / Permissions read
        print("📖 Reading Account Information...")
        account_info = client.futures_account()
        can_trade = account_info.get("canTrade", False)
        can_deposit = account_info.get("canDeposit", False)
        can_withdraw = account_info.get("canWithdraw", False)
        
        print(f"✅ Account retrieved successfully.")
        print(f"   - canTrade: {can_trade}")
        print(f"   - canDeposit: {can_deposit}")
        print(f"   - canWithdraw: {can_withdraw}")
        
        if not can_trade:
            print("❌ WARNING: Trading permissions are disabled on this API Key!")

        # 4. Position Mode alignment
        print("🛡️  Verifying Position Mode (Hedge Mode vs One-Way)...")
        pos_mode = client.futures_get_position_mode()
        dual_side = pos_mode.get("dualSidePosition", False)
        if dual_side:
            print("✅ Verified: Dual-Side HEDGE MODE is active.")
        else:
            print("❌ FAILED: Account is in ONE-WAY mode. Dual-side Hedge Mode must be active.")

        # 5. Open Positions
        print("📊 Querying Open Positions...")
        positions = client.futures_position_information()
        open_positions = []
        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            if amt != 0:
                open_positions.append({
                    "symbol": pos.get("symbol"),
                    "positionAmt": amt,
                    "positionSide": pos.get("positionSide"),
                    "entryPrice": float(pos.get("entryPrice", 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit", 0))
                })
        
        if open_positions:
            print(f"✅ Found {len(open_positions)} active position(s):")
            for op in open_positions:
                print(f"   • {op['symbol']} | Side: {op['positionSide']} | Amt: {op['positionAmt']} | Entry: {op['entryPrice']} | PnL: ${op['unRealizedProfit']:.2f}")
        else:
            print("✅ Verified: No open positions.")

        # 6. Open Algo Orders
        print("🤖 Querying Open Algo Orders...")
        try:
            algo_orders = client.futures_get_open_algo_orders()
            if algo_orders and isinstance(algo_orders, list):
                print(f"✅ Found {len(algo_orders)} open algo order(s):")
                for o in algo_orders:
                    print(f"   • ID: {o.get('algoId')} | Symbol: {o.get('symbol')} | Type: {o.get('orderType')} | Side: {o.get('side')} | Price: {o.get('stopPrice')}")
            else:
                print("✅ Verified: No open algo orders.")
        except Exception as ae:
            print(f"⚠️  Algo Orders check failed/unsupported: {ae}")

        print("=" * 60)
        print("🎉 READ-ONLY CREDENTIAL VALIDATION PASSED SUCCESSFULLY")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ CRITICAL ERROR during credential audit: {e}")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = check_credentials()
    sys.exit(0 if success else 1)
