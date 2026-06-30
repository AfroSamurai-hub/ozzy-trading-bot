import os
import sys
import time

try:
    import config
    from binance.client import Client
    print("✅ System modules and config environment parsed.")
except ImportError as e:
    print(f"🛑 Configuration Dependency Error: {e}")
    sys.exit(1)

def run_live_diagnostics():
    print("\n📊 INITIALIZING LIVE MULTI-ASSET PRODUCTION HANDSHAKE")
    print("────────────────────────────────────────────────────────")
    
    api_key = getattr(config, 'BINANCE_API_KEY', None) or os.getenv('BINANCE_API_KEY')
    api_secret = getattr(config, 'BINANCE_SECRET_KEY', None) or getattr(config, 'BINANCE_API_SECRET', None) or os.getenv('BINANCE_SECRET_KEY')

    if not api_key or not api_secret:
        print("🛑 Configuration Error: Your setup could not resolve API Key variables.")
        sys.exit(1)

    try:
        client = Client(api_key, api_secret, testnet=False)
        account_info = client.futures_account()
        
        # Pull global cross-wallet multi-asset tracking matrix metrics
        total_wallet_usd = float(account_info.get('totalWalletBalance', 0.0))
        total_unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0.0))
        total_margin_balance = float(account_info.get('totalMarginBalance', 0.0))
        available_balance = float(account_info.get('availableBalance', 0.0))
        
        print("💼 Global Portfolio Summary (Cross-Margin USD Value):")
        print(f"   • Aggregated Wallet Balance: ${total_wallet_usd:,.2f} USD")
        print(f"   • Active Floating PnL:       ${total_unrealized_pnl:,.2f} USD")
        print(f"   • Total Account Equity:      ${total_margin_balance:,.2f} USD")
        print(f"   • Available Free Margin:     ${available_balance:,.2f} USD")
        
        print("\n💰 Breakdown of Contributing Collateral Assets:")
        assets_found = 0
        for asset in account_info.get('assets', []):
            wb = float(asset.get('walletBalance', 0.0))
            unpnl = float(asset.get('unrealizedProfit', 0.0))
            if wb != 0.0 or unpnl != 0.0:
                assets_found += 1
                print(f"   • [{asset.get('asset')}] Wallet: ${wb:,.2f} | Open PnL: ${unpnl:,.2f}")
        
        # 3. Scanning for live positions across all active symbols
        positions = client.futures_position_information()
        active_legs = [pos for pos in positions if float(pos.get('positionAmt', 0.0)) != 0.0]
        
        print(f"\n📡 Active Risk Tracking Engine: {len(active_legs)} Live Positions Found")
        print("────────────────────────────────────────────────────────")
        
        for leg in active_legs:
            symbol = leg.get('symbol')
            side = "LONG 🟢" if float(leg.get('positionAmt')) > 0 else "SHORT 🔴"
            size = abs(float(leg.get('positionAmt')))
            entry = float(leg.get('entryPrice', 0.0))
            mark = float(leg.get('markPrice', 0.0))
            pnl = float(leg.get('unrealizedProfit', 0.0))
            leverage = leg.get('leverage')
            
            print(f"   • Asset: {symbol} [{side} x{leverage}]")
            print(f"     Size: {size} | Entry: ${entry:,.4f} | Mark: ${mark:,.4f}")
            print(f"     Floating PnL: ${pnl:,.2f} USDT")
            print("   ──────────────────────────────────────────────────")
            
        print("\n🏁 Verdict: Matrix integration verified. Production tracking active.")
        
    except Exception as e:
        print(f"🛑 Live Handshake Blocked by Exchange: {e}")
    print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    run_live_diagnostics()
