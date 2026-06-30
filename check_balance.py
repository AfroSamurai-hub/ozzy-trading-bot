import os
from binance.client import Client
from dotenv import load_dotenv

# 1. Load the environment variables from your .env file
load_dotenv()

api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

# 2. Initialize the Binance client
client = Client(api_key, api_secret)

# 3. Query the USDⓈ-M Futures Wallet
try:
    print("Connecting to Binance Futures...")
    futures_account = client.futures_account()
    
    total_wallet_balance = futures_account.get('totalWalletBalance')
    print(f"✅ Success! Futures Wallet Balance: ${total_wallet_balance}")
    
except Exception as e:
    print(f"❌ Error fetching futures account: {e}")
