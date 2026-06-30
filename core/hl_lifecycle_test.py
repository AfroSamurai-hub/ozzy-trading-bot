import json
import os
import sys
import time
from eth_account import Account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

try:
    import telegram_client
    TELEMETRY_AVAILABLE = True
    print("✅ Telegram Client bound successfully.")
except ImportError:
    TELEMETRY_AVAILABLE = False
    print("⚠️ Telegram Client module not found.")

class HyperliquidLifecycleTester:
    def __init__(self):
        self.secrets_path = os.path.expanduser("~/ozzy-bot/config/secrets.json")
        self.load_credentials()
        
    def load_credentials(self):
        if not os.path.exists(self.secrets_path):
            print(f"🛑 Error: Secrets file missing at {self.secrets_path}")
            sys.exit(1)
            
        with open(self.secrets_path, 'r') as f:
            data = json.load(f)
            
        hl_secrets = data.get("hyperliquid", {})
        self.address = hl_secrets.get("account_address")
        self.pkey = hl_secrets.get("private_key") or hl_secrets.get("secret_private_key")
        self.env = hl_secrets.get("environment", "TESTNET")
        
        if self.env.upper() == "MAINNET":
            self.base_url = constants.MAINNET_API_URL
            print("⚠️ WARNING: MAINNET RUNTIME DETECTED.")
        else:
            self.base_url = constants.TESTNET_API_URL
            print("🧪 RUNTIME: STAGING TESTNET ACTIVE")

    def broadcast_alert(self, message):
        print(f"📢 [Local Log]: {message.replace('*', '')}")
        if TELEMETRY_AVAILABLE:
            try:
                # Utilizing Hermes' fixed signature layout perfectly
                telegram_client.send_message(message)
            except Exception as e:
                print(f"⚠️ Telegram notification skipped: {e}")

    def run_lifecycle(self):
        print("\n⚡ STARTING PRODUCTION-GRADE LIFECYCLE AUDIT")
        print("────────────────────────────────────────────────────────")
        try:
            wallet_account: LocalAccount = Account.from_key(self.pkey)
            exchange = Exchange(wallet=wallet_account, base_url=self.base_url, account_address=self.address)
            info = Info(self.base_url, skip_ws=True)
            
            # Step 1: Verify Funded State
            print("1️⃣ Checking L1 clearinghouse vault balance...")
            user_state = info.user_state(self.address)
            margin_summary = user_state.get('marginSummary', {})
            account_value = float(margin_summary.get('accountValue', 0.0))
            print(f"   • Active Account Equity: {account_value} USDC")
            
            if account_value == 0.0:
                print("🛑 Lifecycle Halted: Wallet has 0.0 USDC. Please run Step 1 (Faucet Onboarding) first.")
                return

            # Step 2: Fetch Mid-Price for Target Asset
            all_mids = info.all_mids()
            sol_price = float(all_mids.get("SOL", 60.0))
            safe_target_price = round(sol_price * 0.5, 2)
            print(f"2️⃣ Market State: SOL Mid is ${sol_price}. Protected Limit Price set to ${safe_target_price}")

            # Step 3: Broadcast Order (The Handshake)
            print("3️⃣ Broadcasting Signed Placement Frame to L1 Engine...")
            order_result = exchange.order(
                "SOL",
                True,
                0.1,
                safe_target_price,
                {"limit": {"tif": "Gtc"}}
            )
            
            print(f"   • Placement Response JSON:\n{json.dumps(order_result, indent=2)}")
            
            if order_result.get("status") != "ok":
                print("❌ Placement Failed: L1 Engine rejected order properties.")
                return
                
            # Extract internal tracking ID from the response array
            order_status = order_result["response"]["statuses"][0]
            if "resting" in order_status:
                oid = order_status["resting"]["oid"]
            elif "filled" in order_status:
                oid = order_status["filled"]["oid"]
                print("⚠️ Warning: Safe protective order filled instantly. Check market parameters.")
            else:
                print("❌ Failed to resolve order ID from receipt status.")
                return
                
            print(f"🟢 PLACEMENT SUCCESS: Active Order Tracking ID -> {oid}")
            time.sleep(1.5)  # Let the block settle on the L1 chain
            
            # Step 4: Cancel Order (The Clean Up)
            print(f"4️⃣ Initiating Cryptographic Revocation for Order ID: {oid}...")
            cancel_result = exchange.cancel("SOL", oid)
            print(f"   • Revocation Response JSON:\n{json.dumps(cancel_result, indent=2)}")
            
            if cancel_result.get("status") == "ok":
                print("🟢 CANCELLATION SUCCESS: Order cleared safely from ledger.")
                self.broadcast_alert("🤖 *OZZY LIFECYCLE SUCCESS*\n────────────────\n🟢 Hyperliquid L1: *VERIFIED*\n💼 Order Execution: *SUCCESSFUL*\n🗑️ Order Cleanup: *CLEAN*")
            else:
                print("❌ Revocation Failed: Order might be dangling on the book!")
                
        except Exception as e:
            print(f"🛑 Lifecycle Audit Failed: {e}")
        print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    tester = HyperliquidLifecycleTester()
    tester.run_lifecycle()
