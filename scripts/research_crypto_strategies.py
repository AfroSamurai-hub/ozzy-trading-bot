#!/usr/bin/env python3
"""Research multiple Binance USD-M crypto strategy hypotheses.

This script is read-only against Binance. It does not place orders.
It fetches recent futures candles, runs simple strategy variants, and writes a
ranked JSON report to reports/.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import talib

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
FAPI = "https://fapi.binance.com"
FEE_RATE = 0.0004
INITIAL_EQUITY = 10_000.0
RISK_PCT = 0.01


@dataclass(frozen=True)
class StrategySpec:
    """Strategy settings for a single hypothesis."""

    name: str
    timeframe: str
    days: int
    st_len: int
    st_factor: float
    ema_len: int
    rsi_min: float
    rsi_max: float
    volume_min: float
    atr_sl_mult: float
    rr: float
    max_bars: int
    mode: str
    eth_short_only: bool = True
    side_mode: str = "both"  # both | long | short


SPECS = [
    StrategySpec(
        name="generator_grade_b_1h",
        timeframe="1h",
        days=180,
        st_len=10,
        st_factor=3.0,
        ema_len=200,
        rsi_min=30,
        rsi_max=70,
        volume_min=0.75,
        atr_sl_mult=2.0,
        rr=2.5,
        max_bars=24,
        mode="trend_pullback",
    ),
    StrategySpec(
        name="momentum_volume_1h",
        timeframe="1h",
        days=180,
        st_len=10,
        st_factor=3.0,
        ema_len=200,
        rsi_min=35,
        rsi_max=78,
        volume_min=1.10,
        atr_sl_mult=1.5,
        rr=2.5,
        max_bars=18,
        mode="momentum",
    ),
    StrategySpec(
        name="fast_breakout_15m",
        timeframe="15m",
        days=90,
        st_len=7,
        st_factor=2.2,
        ema_len=100,
        rsi_min=35,
        rsi_max=75,
        volume_min=1.20,
        atr_sl_mult=1.2,
        rr=2.0,
        max_bars=16,
        mode="momentum",
    ),
    StrategySpec(
        name="mean_revert_trend_15m",
        timeframe="15m",
        days=90,
        st_len=10,
        st_factor=3.0,
        ema_len=200,
        rsi_min=40,
        rsi_max=60,
        volume_min=0.80,
        atr_sl_mult=0.9,
        rr=1.8,
        max_bars=16,
        mode="pullback_reclaim",
    ),
]


def fetch_klines(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Fetch futures klines from Binance."""
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    start_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        resp = requests.get(
            f"{FAPI}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "startTime": cursor, "endTime": end_ms, "limit": 1500},
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.05)

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_base",
            "taker_quote",
            "ignore",
        ],
    )
    for col in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def supertrend(df: pd.DataFrame, length: int, factor: float) -> pd.Series:
    """Return SuperTrend direction as long/short."""
    atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=length).bfill()
    hl2 = (df["high"] + df["low"]) / 2.0
    upper = hl2 + factor * atr
    lower = hl2 - factor * atr
    line = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=object)
    line.iloc[0] = lower.iloc[0]
    direction.iloc[0] = "long" if df["close"].iloc[0] > line.iloc[0] else "short"
    for i in range(1, len(df)):
        close = df["close"].iloc[i]
        prev_line = line.iloc[i - 1]
        if close > prev_line:
            line.iloc[i] = max(lower.iloc[i], prev_line)
            direction.iloc[i] = "long"
        else:
            line.iloc[i] = min(upper.iloc[i], prev_line)
            direction.iloc[i] = "short"
    return direction


def with_indicators(df: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    """Add indicators needed by a strategy spec."""
    data = df.copy()
    data["ema"] = talib.EMA(data["close"], timeperiod=spec.ema_len)
    data["ema_fast"] = talib.EMA(data["close"], timeperiod=20)
    data["rsi"] = talib.RSI(data["close"], timeperiod=14)
    data["atr"] = talib.ATR(data["high"], data["low"], data["close"], timeperiod=14)
    data["volume_avg20"] = data["volume"].rolling(20).mean()
    data["volume_ratio"] = data["volume"] / data["volume_avg20"]
    data["st_dir"] = supertrend(data, spec.st_len, spec.st_factor)
    return data


def signal_for_row(symbol: str, data: pd.DataFrame, i: int, spec: StrategySpec) -> str | None:
    """Return BUY/SELL/None for a row."""
    row = data.iloc[i]
    prev = data.iloc[i - 1]
    if any(pd.isna(row[col]) for col in ("ema", "rsi", "atr", "volume_ratio")):
        return None
    if row["volume_ratio"] < spec.volume_min or not (spec.rsi_min < row["rsi"] < spec.rsi_max):
        return None

    if spec.mode == "trend_pullback":
        long_ok = row["close"] > row["ema"] and row["st_dir"] == "long" and abs(row["close"] / row["ema"] - 1) <= 0.04
        short_ok = row["close"] < row["ema"] and row["st_dir"] == "short" and abs(row["close"] / row["ema"] - 1) <= 0.04
    elif spec.mode == "momentum":
        long_ok = (
            row["close"] > row["ema"]
            and row["st_dir"] == "long"
            and row["close"] > prev["high"]
            and row["volume_ratio"] >= spec.volume_min
        )
        short_ok = (
            row["close"] < row["ema"]
            and row["st_dir"] == "short"
            and row["close"] < prev["low"]
            and row["volume_ratio"] >= spec.volume_min
        )
    else:
        long_ok = row["st_dir"] == "long" and row["low"] < row["ema_fast"] < row["close"] and row["close"] > row["ema"]
        short_ok = row["st_dir"] == "short" and row["high"] > row["ema_fast"] > row["close"] and row["close"] < row["ema"]

    if spec.eth_short_only and symbol == "ETHUSDT":
        long_ok = False
    if spec.side_mode == "long":
        short_ok = False
    elif spec.side_mode == "short":
        long_ok = False
    if long_ok and not short_ok:
        return "BUY"
    if short_ok and not long_ok:
        return "SELL"
    return None


def run_strategy(symbol: str, candles: pd.DataFrame, spec: StrategySpec) -> dict:
    """Backtest one strategy against one symbol."""
    data = with_indicators(candles, spec)
    equity = INITIAL_EQUITY
    equity_peak = equity
    max_dd = 0.0
    trades = []
    in_trade = None
    start = max(spec.ema_len + 20, 220)

    for i in range(start, len(data) - 1):
        row = data.iloc[i]
        next_open = float(data.iloc[i + 1]["open"])

        if in_trade is None:
            side = signal_for_row(symbol, data, i, spec)
            if not side:
                continue
            sl_dist = float(row["atr"]) * spec.atr_sl_mult
            if not math.isfinite(sl_dist) or sl_dist <= 0:
                continue
            qty = (equity * RISK_PCT) / sl_dist
            in_trade = {
                "side": side,
                "entry": next_open,
                "qty": qty,
                "sl_dist": sl_dist,
                "entry_i": i + 1,
                "entry_time": data.iloc[i + 1]["date"].isoformat(),
            }
            continue

        side = in_trade["side"]
        entry = in_trade["entry"]
        qty = in_trade["qty"]
        sl_dist = in_trade["sl_dist"]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        bars = i - in_trade["entry_i"]
        if side == "BUY":
            sl = entry - sl_dist
            tp = entry + sl_dist * spec.rr
            hit_sl = low <= sl
            hit_tp = high >= tp
        else:
            sl = entry + sl_dist
            tp = entry - sl_dist * spec.rr
            hit_sl = high >= sl
            hit_tp = low <= tp

        exit_price = None
        reason = None
        if hit_sl and hit_tp:
            exit_price = sl
            reason = "same_bar_sl_first"
        elif hit_sl:
            exit_price = sl
            reason = "sl"
        elif hit_tp:
            exit_price = tp
            reason = "tp"
        elif bars >= spec.max_bars:
            exit_price = close
            reason = "time"

        if exit_price is None:
            continue

        gross = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
        fees = (entry * qty * FEE_RATE) + (exit_price * qty * FEE_RATE)
        pnl = gross - fees
        equity += pnl
        equity_peak = max(equity_peak, equity)
        max_dd = max(max_dd, (equity_peak - equity) / equity_peak * 100)
        r_mult = pnl / (INITIAL_EQUITY * RISK_PCT)
        trades.append(
            {
                "side": side,
                "entry_time": in_trade["entry_time"],
                "exit_time": row["date"].isoformat(),
                "entry": round(entry, 8),
                "exit": round(exit_price, 8),
                "reason": reason,
                "pnl": round(pnl, 2),
                "r": round(r_mult, 3),
                "bars": bars,
            }
        )
        in_trade = None

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = gross_win / gross_loss if gross_loss else (999.0 if gross_win else 0.0)
    return {
        "symbol": symbol,
        "strategy": spec.name,
        "timeframe": spec.timeframe,
        "days": spec.days,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "net_pnl": round(sum(t["pnl"] for t in trades), 2),
        "return_pct": round((equity / INITIAL_EQUITY - 1) * 100, 2),
        "profit_factor": round(pf, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_r": round(sum(t["r"] for t in trades) / len(trades), 3) if trades else 0,
        "exit_counts": {reason: sum(1 for t in trades if t["reason"] == reason) for reason in sorted({t["reason"] for t in trades})},
        "sample_trades": trades[-5:],
    }


def main() -> None:
    """Run the research sweep."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="ETHUSDT,LINKUSDT,SOLUSDT,SUIUSDT,HYPEUSDT")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    cache: dict[tuple[str, str, int], pd.DataFrame] = {}
    results = []
    for spec in SPECS:
        for symbol in symbols:
            key = (symbol, spec.timeframe, spec.days)
            if key not in cache:
                print(f"Fetching {symbol} {spec.timeframe} {spec.days}d")
                cache[key] = fetch_klines(symbol, spec.timeframe, spec.days)
            print(f"Testing {symbol} {spec.name}")
            results.append(run_strategy(symbol, cache[key], spec))

    ranked = sorted(
        results,
        key=lambda r: (r["profit_factor"], r["return_pct"], r["trades"]),
        reverse=True,
    )
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"strategy_research_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    payload = {"generated_at": datetime.now(UTC).isoformat(), "results": ranked}
    path.write_text(json.dumps(payload, indent=2))

    print("\nTop results")
    print("symbol strategy trades win_rate pf return max_dd")
    for row in ranked[:12]:
        print(
            row["symbol"],
            row["strategy"],
            row["trades"],
            row["win_rate"],
            row["profit_factor"],
            row["return_pct"],
            row["max_drawdown_pct"],
        )
    print(f"\nReport: {path}")


if __name__ == "__main__":
    main()
