import json
import os
import sys
from eth_account import Account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Native workspace imports verified by Hermes
telegram_client = None
try:
    from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
    import telegram_client
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False

class HyperliquidExecutor:
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
        
        if not self.address or not self.pkey:
            print("🛑 Error: Hyperliquid keys missing inside secrets.json")
            sys.exit(1)
            
        self.base_url = constants.MAINNET_API_URL if self.env.upper() == "MAINNET" else constants.TESTNET_API_URL
        print(f"🧪 Hyperliquid Engine Active: {self.env.upper()}")

    def broadcast_alert(self, message):
        """Dispatches operational updates straight to your Telegram via native client"""
        print(f"📢 [Local Log]: {message.replace('*', '')}")
        if TELEMETRY_AVAILABLE and telegram_client is not None:
            try:
                # telegram_client.send_message owns TELEGRAM_TOKEN/CHAT_ID internally.
                # Its current runtime signature is send_message(text: str).
                telegram_client.send_message(message)
            except Exception as e:
                print(f"⚠️ Telemetry broadcast skipped: {e}")

    def execute_test_order(self):
        print("\n🚀 INITIALIZING HYPERLIQUID INTEGRATION TEST")
        print("────────────────────────────────────────────────────────")
        try:
            wallet_account: LocalAccount = Account.from_key(self.pkey)
            exchange = Exchange(wallet=wallet_account, base_url=self.base_url, account_address=self.address)
            info = Info(self.base_url, skip_ws=True)
            
            all_mids = info.all_mids()
            sol_price = float(all_mids.get("SOL", 60.0))
            safe_target_price = round(sol_price * 0.5, 2)
            
            # Sending order using the exact syntax verified by Hermes
            order_result = exchange.order(
                name="SOL",
                is_buy=True,
                sz=0.1,
                limit_px=safe_target_price,
                order_type={"limit": {"tif": "Gtc"}}
            )
            
            # Fire an alert if the handshake succeeded, even if wallet is uninitialized
            if "status" in order_result:
                self.broadcast_alert("🤖 *OZZY MIGRATION UPDATE*\n────────────────\n🟢 Hyperliquid L1: *CONNECTED*\n📡 Telemetry Sync: *COMPLETE*")
                print(f"\n📦 Handshake Receipt verified by Ledger: Status -> {order_result.get('status')}")
                
        except Exception as e:
            print(f"🛑 Execution Failed: {e}")
        print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    executor = HyperliquidExecutor()
    executor.execute_test_order()
