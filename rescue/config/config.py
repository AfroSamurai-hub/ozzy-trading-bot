"""
OZZY SIMPLE - Minimalist Configuration
NO COMPLEXITY, NO BELLS & WHISTLES
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============= TRADING SETTINGS =============
TRADING_MODE = "PAPER"  # PAPER or LIVE
STARTING_CAPITAL = 5000.00  # Start with R5k (keep R5k in reserve)
SYMBOLS = ["BTCUSDT"]  # ONE symbol only

# ============= STRATEGY SETTINGS (TESTING - Relaxed) =============
RSI_PERIOD = 14
RSI_OVERSOLD = 40  # Testing: More lenient (was 35)
RSI_OVERBOUGHT = 60  # Testing: More lenient (was 65)

EMA_SHORT = 20
EMA_LONG = 50

VOLUME_MULTIPLIER = 1.2  # Testing: Very lenient (was 1.3)

MIN_CONFIDENCE = 30.0  # 30% minimum to generate signal

# ============= RISK SETTINGS =============
RISK_PER_TRADE = 0.01  # 1% risk per trade
MAX_POSITIONS = 2  # Start with 2 max
MAX_PORTFOLIO_HEAT = 0.06  # 6% total exposure max
DAILY_LOSS_LIMIT = 0.03  # Stop trading if down 3% in one day

# ============= TIMEFRAME (CRITICAL!) =============
TIMEFRAME = "4h"  # 4-hour candles (NOT 15m - fees will destroy you)
CHECK_INTERVAL = 14400  # 4 hours in seconds (check once per candle close)

# ============= BYBIT API CREDENTIALS =============
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = True  # Start on testnet

# ============= LOGGING =============
LOG_LEVEL = "INFO"
LOG_FILE = "logs/trading.log"

# Validation
if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    print("⚠️  WARNING: API credentials not found in .env file")
    print("   Create a .env file with:")
    print("   BYBIT_API_KEY=your_key_here")
    print("   BYBIT_API_SECRET=your_secret_here")

print(f"""
╔══════════════════════════════════════════╗
║     OZZY SIMPLE - CONFIGURATION         ║
╠══════════════════════════════════════════╣
║ Mode: {TRADING_MODE:8s}                         ║
║ Capital: R{STARTING_CAPITAL:,.2f}                    ║
║ Symbols: {', '.join(SYMBOLS):25s}   ║
║ Timeframe: {TIMEFRAME:4s}                        ║
║ Risk/Trade: {RISK_PER_TRADE*100:.1f}%                       ║
║ Check Interval: Every {CHECK_INTERVAL//3600} hours           ║
╚══════════════════════════════════════════╝
""")
