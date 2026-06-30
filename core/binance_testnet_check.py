import os
import sys
import time

try:
    import config
    from binance.client import Client
    print("✅ System modules parsed for Binance Staging Environment.")
except ImportError as e:
    print(f"🛑 Configuration Dependency Error: {e}")
    sys.exit(1)

def run_testnet_diagnostics():
    print("\n🧪 INITIALIZING BINANCE FUTURES TESTNET HANDSHAKE")
    print("────────────────────────────────────────────────────────")
    
    # Extract keys from your native environment variables
    api_key = getattr(config, 'BINANCE_API_KEY', os.getenv('BINANCE_API_KEY'))
    api_secret = getattr(config, 'BINANCE_SECRET_KEY', os.getenv('BINANCE_SECRET_KEY'))

    try:
        # Forcing python-binance client straight into the Testnet network gate
        client = Client(api_key, api_secret, testnet=True)
        
        server_time = client.futures_time()
        latency = int(time.time() * 1000) - server_time['serverTime']
        print(f"🟢 Testnet API Connection Status: ONLINE (Latency: {latency}ms)")
        
        # Pull mock staging account capital metrics
        account_info = client.futures_account()
        total_wallet_balance = float(account_info.get('totalWalletBalance', 0.0))
        total_unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0.0))
        margin_balance = float(account_info.get('totalMarginBalance', 0.0))
        
        print("\n💰 Mock Testnet Vault Status:")
        print(f"   • Staging Wallet Balance: ${total_wallet_balance:,.2f} USDT")
        print(f"   • Floating Staging PnL:   ${total_unrealized_pnl:,.2f} USDT")
        print(f"   • Total Staging Equity:   ${margin_balance:,.2f} USDT")
        
        positions = client.futures_position_information()
        active_legs = [pos for pos in positions if float(pos.get('positionAmt', 0.0)) != 0.0]
        
        print(f"\n📡 Active Testnet Risk Tracker: {len(active_legs)} Mock Positions Active")
        print("────────────────────────────────────────────────────────")
        
        print("\n🏁 Verdict: Testnet environment validation complete.")
        
    except Exception as e:
        print(f"🛑 Testnet Handshake Rejected by Sandbox: {e}")
        print("💡 Tip: Ensure your Testnet-specific API keys are loaded into your system files.")
    print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    run_testnet_diagnostics()
