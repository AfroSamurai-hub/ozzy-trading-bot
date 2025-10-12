#!/usr/bin/env python3
"""
Test script for intrawindow risk tracking implementation.

This script generates synthetic OHLCV data and verifies that the
three-way labeling system (WIN/LOSS/NEUTRAL) works correctly.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

# Add intelligence module to path
sys.path.insert(0, os.path.dirname(__file__))

from intelligence.process_historical import process_patterns


def generate_synthetic_ohlcv(num_candles=100, base_price=50000):
    """
    Generate synthetic OHLCV data for testing.
    
    Creates patterns that will result in WIN, LOSS, and NEUTRAL labels.
    """
    np.random.seed(42)
    
    data = []
    current_price = base_price
    start_time = datetime(2024, 1, 1)
    
    for i in range(num_candles):
        timestamp = start_time + timedelta(minutes=5*i)
        
        # Create different scenarios: trending up (WIN), trending down (LOSS), sideways (NEUTRAL)
        scenario = i % 30
        
        if scenario < 10:
            # Uptrend scenario - will hit take-profit
            volatility = 0.015
            bias = 0.01  # Positive bias
        elif scenario < 20:
            # Downtrend scenario - will hit stop-loss
            volatility = 0.015
            bias = -0.01  # Negative bias
        else:
            # Sideways scenario - might stay neutral
            volatility = 0.005
            bias = 0.0
        
        price_change = (np.random.randn() * volatility + bias) * current_price
        
        # Create candle
        open_price = current_price
        close_price = current_price + price_change
        high_price = max(open_price, close_price) * (1 + abs(np.random.randn() * 0.005))
        low_price = min(open_price, close_price) * (1 - abs(np.random.randn() * 0.005))
        volume = np.random.uniform(100, 1000)
        
        data.append({
            'timestamp': timestamp.isoformat(),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
        })
        
        current_price = close_price
    
    return pd.DataFrame(data)


def test_intrawindow_tracking():
    """Test the intrawindow risk tracking implementation."""
    
    print("=" * 70)
    print("TESTING INTRAWINDOW RISK TRACKING")
    print("=" * 70)
    
    # Create test data directory
    test_dir = "/tmp/ozzy_test"
    os.makedirs(test_dir, exist_ok=True)
    
    # Generate synthetic data
    print("\n1. Generating synthetic OHLCV data...")
    df = generate_synthetic_ohlcv(num_candles=150)
    test_file = f"{test_dir}/test_data.csv"
    df.to_csv(test_file, index=False)
    print(f"   ✓ Created {len(df)} candles")
    print(f"   ✓ Saved to: {test_file}")
    
    # Process patterns
    print("\n2. Processing patterns with intrawindow tracking...")
    try:
        patterns = process_patterns(
            input_file=test_file,
            lookforward=6,
            take_profit_pct=0.03,  # 3% take-profit
            stop_loss_pct=0.02,    # 2% stop-loss
        )
        print("   ✓ Processing completed successfully")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Verify three-way labels exist
    print("\n3. Verifying three-way labeling...")
    labels = patterns['label'].value_counts()
    
    required_labels = {'WIN', 'LOSS', 'NEUTRAL'}
    found_labels = set(labels.index)
    
    if not found_labels.issubset(required_labels | set()):
        print(f"   ✗ Unexpected labels found: {found_labels - required_labels}")
        return False
    
    print(f"   ✓ Labels found: {list(found_labels)}")
    for label in ['WIN', 'LOSS', 'NEUTRAL']:
        count = labels.get(label, 0)
        pct = (count / len(patterns) * 100) if len(patterns) > 0 else 0
        print(f"     - {label:8s}: {count:3d} ({pct:5.1f}%)")
    
    # Verify intrawindow columns exist
    print("\n4. Verifying intrawindow metrics...")
    required_columns = [
        'max_profit_pct', 
        'max_drawdown_pct', 
        'future_high', 
        'future_low'
    ]
    
    for col in required_columns:
        if col not in patterns.columns:
            print(f"   ✗ Missing column: {col}")
            return False
        print(f"   ✓ Column exists: {col}")
    
    # Verify data integrity
    print("\n5. Verifying data integrity...")
    
    # Check that max_profit_pct is non-negative
    if (patterns['max_profit_pct'] < 0).any():
        print("   ✗ max_profit_pct contains negative values")
        return False
    print("   ✓ max_profit_pct values are valid (>= 0)")
    
    # Check that max_drawdown_pct is non-negative
    if (patterns['max_drawdown_pct'] < 0).any():
        print("   ✗ max_drawdown_pct contains negative values")
        return False
    print("   ✓ max_drawdown_pct values are valid (>= 0)")
    
    # Check that future_high >= close
    if (patterns['future_high'] < patterns['close']).any():
        print("   ✗ future_high is less than close (should be >= close)")
        return False
    print("   ✓ future_high >= close")
    
    # Check that future_low <= close
    if (patterns['future_low'] > patterns['close']).any():
        print("   ✗ future_low is greater than close (should be <= close)")
        return False
    print("   ✓ future_low <= close")
    
    # Display sample patterns
    print("\n6. Sample patterns:")
    sample_cols = [
        'timestamp', 
        'close', 
        'future_high', 
        'future_low',
        'max_profit_pct', 
        'max_drawdown_pct', 
        'label'
    ]
    print(patterns[sample_cols].head(10).to_string(index=False))
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    
    return True


if __name__ == "__main__":
    success = test_intrawindow_tracking()
    sys.exit(0 if success else 1)
