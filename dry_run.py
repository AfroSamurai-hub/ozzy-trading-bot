from core.setup_detector import SetupDetector
from core.position_manager import PositionManager
from data.ohlcv_fetcher import OHLCVFetcher

import json
import sys

def main():
    try:
        with open('config/symbols.json') as f:
            symbols = json.load(f)
    except Exception as e:
        print(f"Error loading symbols: {e}")
        sys.exit(1)

    fetcher = OHLCVFetcher()
    detector = SetupDetector(symbols)
    pm = PositionManager(account_balance=10000)

    print("Fetching market data...")
    data = fetcher.fetch_all()
    
    print("Detecting setups...")
    setups = detector.detect_all(data)

    print(f"Found {len(setups)} setups\n")

    for setup in setups:
        print(f"Executing Setup: {setup.setup_type.value.upper()} on {setup.symbol}")
        result = pm.execute(setup, dry_run=True)
        print('-' * 50)

if __name__ == "__main__":
    main()
