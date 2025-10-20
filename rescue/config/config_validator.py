"""
Configuration Validator - Sanity check before starting
"""
import os
from . import config

def validate_config():
    """Validate configuration before starting bot"""
    print("\n" + "="*60)
    print("🔍 VALIDATING CONFIGURATION")
    print("="*60)
    
    # Check required API credentials
    issues = []
    
    if not config.BYBIT_API_KEY or config.BYBIT_API_KEY == "your_testnet_api_key_here":
        issues.append("❌ BYBIT_API_KEY not set or still placeholder")
    else:
        print("✅ BYBIT_API_KEY configured")
    
    if not config.BYBIT_API_SECRET or config.BYBIT_API_SECRET == "your_testnet_api_secret_here":
        issues.append("❌ BYBIT_API_SECRET not set or still placeholder")
    else:
        print("✅ BYBIT_API_SECRET configured")
    
    # Check trading mode
    if config.TRADING_MODE == "PAPER":
        print(f"✅ Mode: PAPER TRADING (safe)")
    else:
        print(f"⚠️  Mode: LIVE TRADING (real money!)")
    
    # Check capital
    print(f"✅ Starting Capital: R{config.STARTING_CAPITAL:,.2f}")
    
    # Check thresholds
    print(f"✅ Min Confidence: {config.MIN_CONFIDENCE}%")
    print(f"✅ RSI Thresholds: {config.RSI_OVERSOLD}/{config.RSI_OVERBOUGHT}")
    print(f"✅ Volume Multiplier: {config.VOLUME_MULTIPLIER}x")
    print(f"✅ Timeframe: {config.TIMEFRAME}")
    
    # Check risk settings
    print(f"✅ Risk per Trade: {config.RISK_PER_TRADE*100:.1f}%")
    print(f"✅ Max Positions: {config.MAX_POSITIONS}")
    
    print("="*60)
    
    if issues:
        print("\n❌ CONFIGURATION ERRORS:")
        for issue in issues:
            print(f"   {issue}")
        print("\n⚠️  Fix these issues in .env file before continuing!")
        print("="*60 + "\n")
        return False
    
    print("✅ Configuration valid - ready to start!\n")
    return True
