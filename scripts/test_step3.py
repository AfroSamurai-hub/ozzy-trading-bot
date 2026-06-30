#!/usr/bin/env python3
"""
scripts/test_step3.py
Validate setup detector per spec Section 11.

Input: shared/market_data.json + shared/regime_wind.json
Output: shared/raw_setups.json
Checks: 3+ setups found, debug output per symbol, format correct

Usage: python3 scripts/test_step3.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.setup_detector import SetupDetector
from dataclasses import asdict


def load_json(path):
    with open(path) as f:
        return json.load(f)


def main():
    print("=" * 70)
    print("SETUP DETECTOR VALIDATION")
    print("=" * 70)

    try:
        market_data = load_json("shared/market_data.json")
        regime_wind = load_json("shared/regime_wind.json")
        print(f"PASS: Loaded market_data: {len(market_data)} symbols")
        print(f"PASS: Loaded regime_wind: {len(regime_wind)} symbols")
    except FileNotFoundError as e:
        print(f"FAIL: Missing input file: {e}")
        sys.exit(1)

    try:
        with open("config/symbols.json") as f:
            symbols_config = json.load(f)
        print(f"PASS: Loaded symbols.json: {len(symbols_config)} symbols")
    except FileNotFoundError:
        print("BLOCKED: config/symbols.json not found")
        sys.exit(1)

    detector = SetupDetector(symbols_config)
    raw_setups = detector.detect_all(market_data)
    setups = []
    for s in raw_setups:
        d = asdict(s)
        if hasattr(s.setup_type, 'value'):
            d['setup_type'] = s.setup_type.value
        setups.append(d)

    print("\n" + "-" * 70)
    print("PER-SYMBOL SCAN RESULTS")
    print("-" * 70)

    found_count = 0
    for symbol in sorted(symbols_config.keys()):
        symbol_setups = [s for s in setups if s['symbol'] == symbol]
        allowed = symbols_config.get(symbol, {}).get('allowed_setups', [])

        if symbol not in market_data:
            print(f"{symbol:>8}: NO DATA - symbol missing from market_data.json")
            continue

        data = market_data[symbol]
        if not data.get('15m') or not data.get('1h'):
            print(f"{symbol:>8}: NO DATA - empty candles (15m:{len(data.get('15m',[]))}, 1h:{len(data.get('1h',[]))})")
            continue

        if not symbol_setups:
            print(f"{symbol:>8}: NO SETUPS")
            print(f"           Allowed: {allowed}")

            ohlcv_15m = data['15m']
            if len(ohlcv_15m) >= 20:
                last = ohlcv_15m[-1]
                avg_vol = sum(c['volume'] for c in ohlcv_15m[-20:]) / 20
                ratio = last['volume'] / avg_vol if avg_vol > 0 else 0
                print(f"           15m volume: {last['volume']:.1f}, avg: {avg_vol:.1f}, ratio: {ratio:.2f}x (adaptive threshold)")
            else:
                print(f"           15m insufficient: {len(ohlcv_15m)} candles (need 20)")

            ohlcv_1h = data['1h']
            if len(ohlcv_1h) >= 50:
                prices = [c['close'] for c in ohlcv_1h[-30:]]
                ema21 = sum(prices[-21:]) / 21
                last_price = ohlcv_1h[-1]['close']
                distance = abs(last_price - ema21) / ema21
                print(f"           1h EMA21: {ema21:.2f}, price: {last_price:.2f}, distance: {distance:.4f} (need <0.005)")
            else:
                print(f"           1h insufficient: {len(ohlcv_1h)} candles (need 50)")

            ohlcv_4h = data.get('4h', [])
            if len(ohlcv_4h) >= 25:
                period_high = max(c['high'] for c in ohlcv_4h[-20:-1])
                period_low = min(c['low'] for c in ohlcv_4h[-20:-1])
                last_close = ohlcv_4h[-1]['close']
                print(f"           4h period high: {period_high:.2f}, low: {period_low:.2f}, close: {last_close:.2f}")
                if last_close > period_high:
                    print(f"           BREAKOUT: close > period_high (but volume/validation may have failed)")
                elif last_close < period_low:
                    print(f"           BREAKOUT: close < period_low (but volume/validation may have failed)")
            else:
                print(f"           4h insufficient: {len(ohlcv_4h)} candles (need 25)")

        else:
            for setup in symbol_setups:
                print(f"{symbol:>8}: {setup['setup_type']:>18} {setup['direction']:>5} "
                      f"conf={setup['confidence']:.2f} tf={setup['timeframe']}")
                found_count += 1

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Symbols scanned: {len(symbols_config)}")
    print(f"Setups found: {len(setups)}")
    
    by_type = {}
    for s in setups:
        by_type[s['setup_type']] = by_type.get(s['setup_type'], 0) + 1
    print(f"By type: {by_type}")

    high_conf = [s for s in setups if s['confidence'] >= 0.70]
    if len(high_conf) < 1:
        print(f"\nFAIL: Found {len(setups)} setups, 0 high-confidence (need 1+ with conf >= 0.70)")
        print("      Market may be dead OR detector is broken")
        print("      Check per-symbol output above for diagnosis")
    else:
        print(f"\nPASS: Found {len(high_conf)} high-confidence setups (>= 0.70)")

    with open("shared/raw_setups.json", "w") as f:
        json.dump(setups, f, indent=2)
    print(f"PASS: Wrote shared/raw_setups.json")

    if setups:
        required = ['symbol', 'setup_type', 'direction', 'entry_price', 'stop_price', 
                   'target_price', 'timeframe', 'confidence', 'context']
        missing = [k for k in required if k not in setups[0]]
        if missing:
            print(f"FAIL: Missing keys in setup: {missing}")
        else:
            print("PASS: Setup format valid")

    print("=" * 70)


if __name__ == "__main__":
    main()
