"""
OZZY SIMPLE - Configuration
All settings for the trading bot
"""

# ============================================================================
# TRADING PARAMETERS
# ============================================================================

# Trading symbols to monitor
# Expanded for Phase 2 data collection
TRADING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

# Trading schedule
CHECK_INTERVAL_MINUTES = 1   # How often to check for signals (minutes) - temporarily lowered for Phase 2 rapid data collection
TRADING_START_HOUR = 9       # Start trading at 9:00 AM SAST
TRADING_END_HOUR = 21        # Stop trading at 9:00 PM SAST
CLOSE_POSITIONS_EOD = True   # Close all positions at end of day

# Capital and risk management
STARTING_CAPITAL = 10000     # Starting capital in ZAR
RISK_PER_TRADE = 2.0         # Risk per trade as % of capital
MAX_DAILY_LOSS = 5.0         # Maximum daily loss as % of capital (stop trading if hit)
MAX_POSITIONS = 3            # Maximum number of open positions

# Trade parameters
RSI_OVERBOUGHT = 57
RSI_OVERSOLD = 43
STOP_LOSS_PCT = 2.0          # Stop loss percentage
TAKE_PROFIT_PCT = 3.0        # Take profit percentage
MIN_CONFIDENCE = 30.0        # Minimum signal confidence to trade (%) (AGGRESSIVE MODE - collect data)

# Margin requirement for opening shorts (fraction of notional). Example: 0.1 = 10% margin
SHORT_MARGIN = 0.10

# ============================================================================
# BROKER SETTINGS
# ============================================================================

# Bybit API credentials (REPLACE WITH YOUR REAL KEYS FOR LIVE TRADING)
BYBIT_API_KEY = "your_api_key_here"
BYBIT_API_SECRET = "your_api_secret_here"

# Trading mode
BYBIT_TESTNET = True         # True = testnet (practice), False = mainnet (real money)
PAPER_TRADING = True         # True = simulate trades, False = real trades

# ============================================================================
# TARGET AND GOALS
# ============================================================================

WEEKLY_TARGET = 5000         # Weekly profit target in ZAR

# ============================================================================
# DISPLAY CONFIGURATION
# ============================================================================

# Backwards-compatible aliases (some modules expect these names)
STOP_LOSS_PERCENT = STOP_LOSS_PCT
TAKE_PROFIT_PERCENT = TAKE_PROFIT_PCT

if __name__ == "__main__":
    print("\n" + "="*50)
    print("           OZZY SIMPLE - CONFIG           ")
    print("="*50)
    print(f"\nMode: {'PAPER TRADING' if PAPER_TRADING else 'LIVE TRADING'}")
    print(f"Capital: R{STARTING_CAPITAL:,.0f}")
    print(f"Weekly Target: R{WEEKLY_TARGET:,.0f}")
    print(f"Trading Hours: {TRADING_START_HOUR}:00-{TRADING_END_HOUR}:00 SAST")
    print(f"Check Interval: {CHECK_INTERVAL_MINUTES} minutes")
    print(f"Risk Per Trade: {RISK_PER_TRADE}%")
    print(f"Max Daily Loss: {MAX_DAILY_LOSS}%")
    print(f"Symbols: {', '.join(TRADING_SYMBOLS)}")
    print("="*50 + "\n")
