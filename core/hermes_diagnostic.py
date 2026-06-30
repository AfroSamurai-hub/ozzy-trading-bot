import os
import sys
from binance.client import Client

try:
    import config
    print("✅ Hermes: System dependencies parsed successfully.")
except ImportError:
    print("🛑 Hermes: Master config missing or path unaligned.")
    sys.exit(1)

def run_hermes_audit():
    print("\n🔍 RUNNING HERMES INTERFACE EXCAVATION")
    print("────────────────────────────────────────────────────────")
    
    # Resolve exact env variable bindings
    api_key = getattr(config, 'BINANCE_API_KEY', os.getenv('BINANCE_API_KEY'))
    api_secret = getattr(config, 'BINANCE_SECRET_KEY', os.getenv('BINANCE_SECRET_KEY')) or getattr(config, 'BINANCE_API_SECRET', os.getenv('BINANCE_API_SECRET'))

    client = Client(api_key, api_secret)

    try:
        # 1. Fetch RAW account asset breakdown
        account_status = client.futures_account()
        
        print("⚙️ Account Modes:")
        print(f"   • Multi-Assets Mode Active: {account_status.get('multiAssetsMargin')}")
        print(f"   • Can Deposit Margin:       {account_status.get('canDeposit')}")
        print(f"   • Can Withdraw Funds:       {account_status.get('canWithdraw')}")
        
        print("\n💰 Asset Ledger Audit:")
        assets_found = False
        for asset in account_status.get('assets', []):
            wallet_bal = float(asset.get('walletBalance', 0.0))
            margin_bal = float(asset.get('marginBalance', 0.0))
            if wallet_bal > 0 or margin_bal > 0:
                assets_found = True
                print(f"   • [{asset.get('asset')}] Wallet: ${wallet_bal:,.2f} | Margin: ${margin_bal:,.2f}")
                
        if not assets_found:
            print("   ⚠️ No positive balances detected across standard crypto collateral arrays.")

        # 2. Check for Unified Portfolio Margin flag
        print("\n🔀 Portfolio Routing Verification:")
        try:
            # If this endpoint triggers or throws specific codes, portfolio margin is active
            pm_status = client.request_api('GET', '/v1/portfolio/account', signed=True)
            print("   • Status: Portfolio Margin configuration detected.")
        except Exception:
            print("   • Status: Standard separate Futures Account routing active.")

    except Exception as e:
        print(f"🛑 Hermes API Read Exception: {e}")
    print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    run_hermes_audit()
