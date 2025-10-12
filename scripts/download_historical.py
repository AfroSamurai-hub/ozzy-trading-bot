"""
Lean historical downloader for bootstrap pattern learning.

Usage:
    python3 scripts/download_historical.py \
        --symbol BTCUSDT \
        --interval 5 \
        --days 7

Default behaviour pulls just the last 7 days of 5-minute candles
(~2,000 rows) to seed the vector database quickly.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta
from typing import List

import pandas as pd
from pybit.unified_trading import HTTP

BATCH_LIMIT = 200
RATE_LIMIT_DELAY = 0.2  # seconds (5 requests/sec)


def _format_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def download_bootstrap_data(symbol: str, interval: str = "5", days: int = 7) -> pd.DataFrame:
    """Download recent OHLCV data from Bybit (linear contracts)."""

    client = HTTP(testnet=False)

    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"📊 Downloading {symbol} {interval}m candles for last {days} days...")
    print(f"   Start target: {_format_time(start_time)}")
    print(f"   End target:   {_format_time(end_time)}")

    all_candles: List[List[str]] = []
    current_end = end_time
    batch_num = 0

    while current_end > start_time:
        batch_num += 1
        print(f"\n⏳ Batch {batch_num}: requesting up to {BATCH_LIMIT} candles ending {_format_time(current_end)}")

        response = client.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            end=current_end,
            limit=BATCH_LIMIT,
        )

        if response["retCode"] != 0:
            raise RuntimeError(f"Bybit error {response['retCode']}: {response['retMsg']}")

        candles = response["result"].get("list", [])

        if not candles:
            print("✅ No more data available")
            break

        all_candles.extend(candles)

        oldest_timestamp = int(candles[-1][0])
        print(f"   Received: {len(candles)} candles (total {len(all_candles)})")
        print(f"   Oldest candle in batch: {_format_time(oldest_timestamp)}")

        if oldest_timestamp <= start_time:
            print("✅ Reached requested start window")
            break

        current_end = oldest_timestamp - 1
        time.sleep(RATE_LIMIT_DELAY)

    if not all_candles:
        raise RuntimeError("No candles retrieved from Bybit. Check symbol/interval parameters.")

    df = pd.DataFrame(
        all_candles,
        columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
    numeric_cols = ["open", "high", "low", "close", "volume", "turnover"]
    for col in numeric_cols:
        df[col] = df[col].astype(float)

    df = df.sort_values("timestamp").reset_index(drop=True)

    output_file = os.path.join("data", "historical", f"{symbol}_{interval}m_bootstrap.csv")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=False)

    file_size_mb = os.path.getsize(output_file) / 1024 / 1024

    print("\n✅ Download complete")
    print(f"📁 Saved to: {output_file}")
    print(f"� Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"🔢 Rows: {len(df)}")
    print(f"💾 File size: {file_size_mb:.2f} MB")

    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download recent Bybit OHLCV data for bootstrap training",
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading symbol (default: BTCUSDT)")
    parser.add_argument("--interval", default="5", help="Candle interval in minutes (default: 5)")
    parser.add_argument(
        "--days",
        type=lambda v: max(1, int(v)),
        default=7,
        help="Days of history to download (default: 7)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    download_bootstrap_data(symbol=args.symbol, interval=args.interval, days=args.days)
