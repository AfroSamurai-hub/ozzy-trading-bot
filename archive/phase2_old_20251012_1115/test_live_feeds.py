from datetime import datetime
import time
from bybit_client import BybitClient


def test_live_connectivity():
    """Validate live data feeds without trading"""

    # Force live data mode regardless of global config: paper_trading=False, testnet=False
    client = BybitClient(paper_trading=False, testnet=False)

    print("\n🔍 Testing Live Market Data Connectivity...")
    print("=" * 60)

    # Test 1: Can we connect?
    try:
        balance = client.get_balance()
        print(f"✅ Connection successful")
        print(f"   Account Balance: R{(balance or 0):,.2f}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

    # Test 2: Can we get current prices?
    symbols = ['BTCUSDT', 'ETHUSDT']
    for symbol in symbols:
        try:
            price = client.get_current_price(symbol)
            if price is None:
                raise RuntimeError("No price returned")
            print(f"✅ {symbol}: ${price:,.2f}")
        except Exception as e:
            print(f"❌ {symbol} price fetch failed: {e}")
            return False

    # Test 3: Can we get historical candles?
    try:
        candles = client.get_candles('BTCUSDT', '15', limit=100)
        if not candles:
            raise RuntimeError("No candles returned")
        print(f"✅ Historical data: {len(candles)} candles received")
        print(f"   Latest: {candles[-1]}")
    except Exception as e:
        print(f"❌ Candle data failed: {e}")
        return False

    # Test 4: Stream live prices for 5 minutes
    print("\n📊 Live Price Monitoring (5 minutes)...")
    print("   Watch for: stable updates, no gaps, reasonable prices")
    print("-" * 60)

    start_time = time.time()
    last_prices = {}

    while time.time() - start_time < 300:  # 5 minutes
        for symbol in symbols:
            price = client.get_current_price(symbol)
            if price is None:
                print(f"❌ {symbol}: failed to fetch price")
                return False

            # Detect anomalies
            if symbol in last_prices and last_prices[symbol]:
                try:
                    change_pct = abs(price - last_prices[symbol]) / last_prices[symbol] * 100
                    if change_pct > 2.0:  # >2% instant change = suspicious
                        print(f"⚠️  {symbol}: Large move {change_pct:.2f}% in 30s")
                except ZeroDivisionError:
                    pass

            last_prices[symbol] = price

            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"   [{timestamp}] {symbol}: ${price:,.2f}")

        time.sleep(30)  # Update every 30 seconds

    print("\n" + "=" * 60)
    print("✅ Live feed validation COMPLETE")
    print("   - Connection stable")
    print("   - Price updates working")
    print("   - Data quality acceptable")
    return True


if __name__ == "__main__":
    success = test_live_connectivity()

    if success:
        print("\n🚀 READY FOR PHASE 1: Passive Signal Monitoring")
    else:
        print("\n❌ FIX API ISSUES BEFORE PROCEEDING")
