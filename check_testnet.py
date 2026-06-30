import os
from binance.client import Client
from dotenv import load_dotenv

load_dotenv(override=True)

# Determine the environment from the .env flag
is_testnet = os.getenv('HERMES_BINANCE_TESTNET', 'false').strip().lower() == 'true'

if is_testnet:
    print("🔌 Booting in TESTNET Sandbox...")
    api_key = os.getenv('BINANCE_TESTNET_API_KEY')
    api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
else:
    print("⚠️ Booting in LIVE MAINNET...")
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

# Initialize the Binance client with the testnet flag
client = Client(api_key, api_secret, testnet=is_testnet)

# Query the USDⓈ-M Futures Wallet
try:
    futures_account = client.futures_account()
    total_wallet_balance = futures_account.get('totalWalletBalance')
    print(f"✅ Success! Connected Wallet Balance: ${total_wallet_balance}")
except Exception as e:
    print(f"❌ Error fetching futures account: {e}")
