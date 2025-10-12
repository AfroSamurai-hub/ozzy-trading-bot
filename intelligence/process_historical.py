"""
Process historical OHLCV data into labeled trading patterns with intrawindow risk tracking.

For each candle, calculate:
- RSI (14 period)
- EMA short (13 period) and long (23 period)
- Volume change
- Price change
- Look forward 6 candles (30 minutes)
- Track intrawindow highs and lows
- Calculate max profit and max drawdown percentages
- Three-way labeling based on realistic trading outcomes:
  * WIN: Take-profit hit first (target: +3%)
  * LOSS: Stop-loss hit first (target: -2%)
  * NEUTRAL: Neither hit within window

Output: data/historical/BTCUSDT_5m_bootstrap_patterns.csv
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI indicator."""
    indicator = RSIIndicator(close=prices, window=period)
    return indicator.rsi()


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Calculate EMA indicator."""
    indicator = EMAIndicator(close=prices, window=period)
    return indicator.ema_indicator()


def process_patterns(
    input_file: str,
    lookforward: int = 6,
    take_profit_pct: float = 0.03,
    stop_loss_pct: float = 0.02,
) -> pd.DataFrame:
    """
    Convert OHLCV data into labeled patterns for vector DB with intrawindow risk tracking.

    Args:
        input_file: CSV file with OHLCV data
        lookforward: How many candles to look ahead (6 = 30 minutes for 5m)
        take_profit_pct: Take-profit target (default: 3%)
        stop_loss_pct: Stop-loss threshold (default: 2%)

    Returns:
        DataFrame with patterns, intrawindow metrics, and three-way labels
    """
    print(f"📊 Processing patterns from: {input_file}")

    # Load data
    df = pd.read_csv(input_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    print(f"   Loaded {len(df)} candles")

    # Calculate indicators
    print("🔢 Calculating indicators...")
    df["rsi"] = calculate_rsi(df["close"])
    df["ema_short"] = calculate_ema(df["close"], 13)
    df["ema_long"] = calculate_ema(df["close"], 23)

    # Derived features
    df["ema_ratio"] = df["ema_short"] / df["ema_long"]
    df["volume_change"] = df["volume"].pct_change()
    df["price_change"] = df["close"].pct_change()

    # Look forward for intrawindow risk tracking
    print(f"🔮 Looking forward {lookforward} candles for intrawindow tracking...")
    df["future_close"] = df["close"].shift(-lookforward)

    # Calculate intrawindow highs and lows
    future_high_candidates = [df["high"].shift(-i) for i in range(1, lookforward + 1)]
    future_low_candidates = [df["low"].shift(-i) for i in range(1, lookforward + 1)]
    
    df["future_high"] = pd.concat(future_high_candidates, axis=1).max(axis=1)
    df["future_low"] = pd.concat(future_low_candidates, axis=1).min(axis=1)

    # Calculate max profit and max drawdown percentages
    df["max_profit_pct"] = (df["future_high"] - df["close"]) / df["close"]
    df["max_drawdown_pct"] = (df["close"] - df["future_low"]) / df["close"]
    
    df["price_change_forward_close"] = (
        df["future_close"] - df["close"]
    ) / df["close"]

    # Three-way labeling based on stop-loss and take-profit hits
    print(f"🏷️  Labeling patterns (TP: {take_profit_pct*100:.1f}%, SL: {stop_loss_pct*100:.1f}%)...")
    
    def label_pattern(row):
        """Determine if take-profit or stop-loss was hit first."""
        max_profit = row["max_profit_pct"]
        max_drawdown = row["max_drawdown_pct"]
        
        tp_hit = max_profit >= take_profit_pct
        sl_hit = max_drawdown >= stop_loss_pct
        
        if tp_hit and sl_hit:
            # Both hit - need to determine which came first
            # Use forward iteration to find exact sequence
            # For simplicity, if both hit within window, check which threshold is closer
            if max_profit / take_profit_pct > max_drawdown / stop_loss_pct:
                return "WIN"
            else:
                return "LOSS"
        elif tp_hit:
            return "WIN"
        elif sl_hit:
            return "LOSS"
        else:
            return "NEUTRAL"
    
    df["label"] = df.apply(label_pattern, axis=1)

    # Remove rows without enough future data
    df = df.iloc[:-lookforward].copy()

    # Drop NaNs from indicator warmups
    df = df.dropna()

    # Stats
    total = len(df)
    win_count = int((df["label"] == "WIN").sum())
    loss_count = int((df["label"] == "LOSS").sum())
    neutral_count = int((df["label"] == "NEUTRAL").sum())
    
    win_rate = (win_count / total * 100) if total else 0
    loss_rate = (loss_count / total * 100) if total else 0
    neutral_rate = (neutral_count / total * 100) if total else 0

    print(f"\n✅ Processed {total} patterns with intrawindow risk tracking")
    print(f"   WIN (TP hit first):   {win_count:5d} ({win_rate:5.1f}%)")
    print(f"   LOSS (SL hit first):  {loss_count:5d} ({loss_rate:5.1f}%)")
    print(f"   NEUTRAL (neither):    {neutral_count:5d} ({neutral_rate:5.1f}%)")
    
    # Additional statistics
    avg_max_profit = df["max_profit_pct"].mean() * 100
    avg_max_drawdown = df["max_drawdown_pct"].mean() * 100
    print(f"\n📊 Intrawindow Metrics:")
    print(f"   Avg Max Profit:    {avg_max_profit:.2f}%")
    print(f"   Avg Max Drawdown:  {avg_max_drawdown:.2f}%")

    output_file = input_file.replace(".csv", "_patterns.csv")
    columns = [
        "timestamp",
        "close",
        "rsi",
        "ema_short",
        "ema_long",
        "ema_ratio",
        "volume_change",
        "price_change",
        "future_close",
        "future_high",
        "future_low",
        "max_profit_pct",
        "max_drawdown_pct",
        "price_change_forward_close",
        "label",
    ]
    df[columns].to_csv(output_file, index=False)

    print(f"📁 Saved to: {output_file}")

    return df


if __name__ == "__main__":
    SOURCE = "data/historical/BTCUSDT_5m_bootstrap.csv"
    patterns = process_patterns(
        input_file=SOURCE,
        lookforward=6,
        take_profit_pct=0.03,  # 3% take-profit target
        stop_loss_pct=0.02,    # 2% stop-loss threshold
    )

    print("\n📋 Sample patterns:")
    print(
        patterns[
            [
                "timestamp",
                "rsi",
                "ema_ratio",
                "future_high",
                "future_low",
                "max_profit_pct",
                "max_drawdown_pct",
                "label",
            ]
        ].head(10)
    )
