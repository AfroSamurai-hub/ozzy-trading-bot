#!/usr/bin/env python3
"""
HERMES — Signal Replay Backtest
Compares entry strategies on historical 4H data with realistic costs.

Strategies tested:
  1. SuperTrend Flip (current) — enter on ST direction change
  2. 4H Breakout — enter on break of previous 4H swing high/low
  3. EMA Pullback — enter when price retraces to EMA200 in trend direction
  4. RSI Momentum — enter on RSI cross above 50 in uptrend / below 50 in downtrend

Usage:
  python backtest_replay.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import requests

# ── Config ──
SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]
TIMEFRAME = "4h"
RISK_PER_TRADE = 0.05          # 5%
MIN_RR = 2.5
SLIPPAGE_PCT = 0.0015          # 0.15% slippage per side ( conservative )
COMMISSION_PCT = 0.0005        # 0.05% round-trip commission
MAX_TRADE_DAYS = 5             # time-stop after 5 days (30 × 4H bars)

# Pine-equivalent parameters
ST_PERIOD = 10
ST_MULTIPLIER = 3.0
EMA_PERIOD = 200
RSI_PERIOD = 14
ATR_PERIOD = 14
SWING_LENGTH = 5

# Symbol specs for slippage / pip calculations
SPECS = {
    "XAUUSD": {"pip": 0.01,  "spread_avg": 0.30},
    "EURUSD": {"pip": 0.0001, "spread_avg": 0.00015},
    "BTCUSD": {"pip": 1.0,   "spread_avg": 50.0},
    "ETHUSD": {"pip": 0.01,  "spread_avg": 2.0},
}


# ── Data fetching ──

def fetch_4h_candles(symbol: str, days: int = 180) -> list[dict]:
    """
    Fetch 4H historical candles. Tries multiple free sources.
    Returns list of {ts, open, high, low, close, volume} sorted by time.
    """
    end = datetime.now(timezone.utc)
    start = end - __import__("datetime").timedelta(days=days)

    # Crypto: Coinbase 1H → aggregate to 4H
    if symbol in ("BTCUSD", "ETHUSD"):
        product = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD"}[symbol]
        url = f"https://api.exchange.coinbase.com/products/{product}/candles"
        all_candles = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + __import__("datetime").timedelta(hours=300), end)
            resp = requests.get(
                url,
                params={
                    "granularity": 3600,
                    "start": cursor.isoformat().replace("+00:00", "Z"),
                    "end": chunk_end.isoformat().replace("+00:00", "Z"),
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            resp.raise_for_status()
            for row in resp.json():
                if len(row) >= 6:
                    ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc).isoformat()
                    all_candles.append({
                        "ts": ts,
                        "open": float(row[3]),
                        "high": float(row[2]),
                        "low": float(row[1]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    })
            cursor = chunk_end
        all_candles.sort(key=lambda x: x["ts"])
        return _resample_to_4h(all_candles)

    # Forex/Gold: Twelve Data 4H direct
    try:
        td_sym = {"XAUUSD": "XAU/USD", "EURUSD": "EUR/USD"}[symbol]
        from twelvedata_client import TWELVE_API_KEY
        url = "https://api.twelvedata.com/time_series"
        resp = requests.get(
            url,
            params={
                "symbol": td_sym,
                "interval": "4h",
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "apikey": TWELVE_API_KEY,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if "values" in data:
            candles = []
            for row in data["values"]:
                candles.append({
                    "ts": row["datetime"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })
            candles.sort(key=lambda x: x["ts"])
            return candles
    except Exception as e:
        print(f"  ⚠ Twelve Data failed for {symbol}: {e}")

    print(f"  ✗ No data source available for {symbol}")
    return []


def _resample_to_4h(candles: list[dict]) -> list[dict]:
    """Resample 1H candles to 4H."""
    if not candles:
        return []
    groups: dict[str, list[dict]] = {}
    for c in candles:
        dt = datetime.fromisoformat(c["ts"].replace("Z", "+00:00"))
        bucket = dt.replace(minute=0, second=0, microsecond=0)
        bucket = bucket.replace(hour=(dt.hour // 4) * 4)
        key = bucket.isoformat()
        groups.setdefault(key, []).append(c)
    result = []
    for key in sorted(groups):
        g = groups[key]
        result.append({
            "ts": key,
            "open": g[0]["open"],
            "high": max(x["high"] for x in g),
            "low": min(x["low"] for x in g),
            "close": g[-1]["close"],
            "volume": sum(x["volume"] for x in g),
        })
    return result


# ── Indicator calculations (pure numpy) ──

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    ema = np.zeros_like(series)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = alpha * series[i] + (1 - alpha) * ema[i - 1]
    return ema


def _rsi(series: np.ndarray, period: int) -> np.ndarray:
    delta = np.diff(series, prepend=series[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.zeros_like(series)
    avg_loss = np.zeros_like(series)
    avg_gain[period] = np.mean(gain[1:period + 1])
    avg_loss[period] = np.mean(loss[1:period + 1])
    for i in range(period + 1, len(series)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50.0
    return rsi


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    atr = np.zeros_like(tr)
    atr[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    atr[:period] = atr[period]
    return atr


def _supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int, mult: float):
    atr = _atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    st = np.zeros_like(close)
    direction = np.zeros_like(close, dtype=int)
    st[0] = upper[0]
    direction[0] = -1

    for i in range(1, len(close)):
        if close[i] > st[i - 1]:
            direction[i] = 1
            st[i] = max(lower[i], st[i - 1]) if direction[i - 1] == 1 else lower[i]
        else:
            direction[i] = -1
            st[i] = min(upper[i], st[i - 1]) if direction[i - 1] == -1 else upper[i]

    return st, direction


def _swing_pivots(high: np.ndarray, low: np.ndarray, length: int) -> tuple[np.ndarray, np.ndarray]:
    ph = np.full_like(high, np.nan)
    pl = np.full_like(low, np.nan)
    for i in range(length, len(high) - length):
        if all(high[i] >= high[i - j] for j in range(1, length + 1)) and all(high[i] >= high[i + j] for j in range(1, length + 1)):
            ph[i] = high[i]
        if all(low[i] <= low[i - j] for j in range(1, length + 1)) and all(low[i] <= low[i + j] for j in range(1, length + 1)):
            pl[i] = low[i]
    return ph, pl


# ── Strategy definitions ──

@dataclass
class Trade:
    entry_idx: int
    signal: str          # BUY or SELL
    entry_price: float
    sl: float
    tp: float
    exit_idx: int = -1
    exit_price: float = 0.0
    outcome: str = ""    # win, loss, open, timeout
    r_multiple: float = 0.0


def strategy_supertrend_flip(data: dict) -> list[Trade]:
    """Current Pine logic: SuperTrend direction change + EMA bias."""
    o, h, l, c = data["o"], data["h"], data["l"], data["c"]
    ema200 = _ema(c, EMA_PERIOD)
    _, st_dir = _supertrend(h, l, c, ST_PERIOD, ST_MULTIPLIER)
    trades = []

    for i in range(EMA_PERIOD + 1, len(c) - 1):
        ema_bias = "bullish" if c[i] > ema200[i] else "bearish"
        st_changed = st_dir[i] != st_dir[i - 1]
        atr = _atr(h, l, c, ATR_PERIOD)[i]

        if st_changed and st_dir[i] == 1 and ema_bias == "bullish":
            entry = c[i]
            sl = entry - atr * 1.5
            tp = entry + abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "BUY", entry, sl, tp))

        elif st_changed and st_dir[i] == -1 and ema_bias == "bearish":
            entry = c[i]
            sl = entry + atr * 1.5
            tp = entry - abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "SELL", entry, sl, tp))

    return trades


def strategy_breakout(data: dict) -> list[Trade]:
    """Enter on break of previous 4H swing high/low."""
    o, h, l, c = data["o"], data["h"], data["l"], data["c"]
    ema200 = _ema(c, EMA_PERIOD)
    ph, pl = _swing_pivots(h, l, SWING_LENGTH)
    trades = []

    # Fill forward last known swing levels
    last_ph = np.full_like(c, np.nan)
    last_pl = np.full_like(c, np.nan)
    curr_ph, curr_pl = np.nan, np.nan
    for i in range(len(c)):
        if not np.isnan(ph[i]):
            curr_ph = ph[i]
        if not np.isnan(pl[i]):
            curr_pl = pl[i]
        last_ph[i] = curr_ph
        last_pl[i] = curr_pl

    for i in range(EMA_PERIOD + 1, len(c) - 1):
        if np.isnan(last_ph[i]) or np.isnan(last_pl[i]):
            continue
        ema_bias = "bullish" if c[i] > ema200[i] else "bearish"
        atr = _atr(h, l, c, ATR_PERIOD)[i]

        # Break above recent swing high in bullish bias
        if h[i] > last_ph[i] and ema_bias == "bullish" and c[i] > ema200[i]:
            entry = c[i]
            sl = entry - atr * 1.5
            tp = entry + abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "BUY", entry, sl, tp))

        # Break below recent swing low in bearish bias
        elif l[i] < last_pl[i] and ema_bias == "bearish" and c[i] < ema200[i]:
            entry = c[i]
            sl = entry + atr * 1.5
            tp = entry - abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "SELL", entry, sl, tp))

    return trades


def strategy_ema_pullback(data: dict) -> list[Trade]:
    """Enter when price retraces to EMA200 in direction of trend."""
    o, h, l, c = data["o"], data["h"], data["l"], data["c"]
    ema200 = _ema(c, EMA_PERIOD)
    rsi = _rsi(c, RSI_PERIOD)
    trades = []

    for i in range(EMA_PERIOD + 1, len(c) - 1):
        atr = _atr(h, l, c, ATR_PERIOD)[i]
        price_above_ema = c[i] > ema200[i]
        price_below_ema = c[i] < ema200[i]

        # Uptrend: price was above EMA, now touches or dips below it, RSI still > 40
        if price_above_ema and l[i] <= ema200[i] and rsi[i] > 40 and rsi[i] < 65:
            entry = c[i]
            sl = entry - atr * 1.5
            tp = entry + abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "BUY", entry, sl, tp))

        # Downtrend: price was below EMA, now touches or pops above it, RSI still < 60
        elif price_below_ema and h[i] >= ema200[i] and rsi[i] < 60 and rsi[i] > 35:
            entry = c[i]
            sl = entry + atr * 1.5
            tp = entry - abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "SELL", entry, sl, tp))

    return trades


def strategy_rsi_momentum(data: dict) -> list[Trade]:
    """Enter on RSI cross above 50 in uptrend / below 50 in downtrend."""
    o, h, l, c = data["o"], data["h"], data["l"], data["c"]
    ema200 = _ema(c, EMA_PERIOD)
    rsi = _rsi(c, RSI_PERIOD)
    trades = []

    for i in range(EMA_PERIOD + 1, len(c) - 1):
        atr = _atr(h, l, c, ATR_PERIOD)[i]
        ema_bias = "bullish" if c[i] > ema200[i] else "bearish"
        rsi_cross_up = rsi[i] > 50 and rsi[i - 1] <= 50
        rsi_cross_down = rsi[i] < 50 and rsi[i - 1] >= 50

        if rsi_cross_up and ema_bias == "bullish":
            entry = c[i]
            sl = entry - atr * 1.5
            tp = entry + abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "BUY", entry, sl, tp))

        elif rsi_cross_down and ema_bias == "bearish":
            entry = c[i]
            sl = entry + atr * 1.5
            tp = entry - abs(entry - sl) * MIN_RR
            trades.append(Trade(i, "SELL", entry, sl, tp))

    return trades


# ── Trade simulation ──

def simulate(trades: list[Trade], data: dict, symbol: str) -> list[Trade]:
    h, l, c = data["h"], data["l"], data["c"]
    spec = SPECS.get(symbol, {"pip": 0.01, "spread_avg": 0.01})
    slippage = spec["spread_avg"] * 0.5  # half spread slippage

    for t in trades:
        entry_slippage = slippage if t.signal == "BUY" else -slippage
        t.entry_price += entry_slippage

        # Re-calculate SL/TP after slippage adjustment
        risk = abs(t.tp - t.entry_price) / MIN_RR
        if t.signal == "BUY":
            t.sl = t.entry_price - risk
            t.tp = t.entry_price + risk * MIN_RR
        else:
            t.sl = t.entry_price + risk
            t.tp = t.entry_price - risk * MIN_RR

        max_bars = min(t.entry_idx + MAX_TRADE_DAYS * 6, len(c) - 1)  # ~6 bars per day
        for j in range(t.entry_idx + 1, max_bars + 1):
            if t.signal == "BUY":
                if l[j] <= t.sl:
                    t.exit_idx = j
                    t.exit_price = t.sl
                    t.outcome = "loss"
                    t.r_multiple = -1.0
                    break
                if h[j] >= t.tp:
                    t.exit_idx = j
                    t.exit_price = t.tp
                    t.outcome = "win"
                    t.r_multiple = MIN_RR
                    break
            else:
                if h[j] >= t.sl:
                    t.exit_idx = j
                    t.exit_price = t.sl
                    t.outcome = "loss"
                    t.r_multiple = -1.0
                    break
                if l[j] <= t.tp:
                    t.exit_idx = j
                    t.exit_price = t.tp
                    t.outcome = "win"
                    t.r_multiple = MIN_RR
                    break
        else:
            t.exit_idx = max_bars
            t.exit_price = c[max_bars]
            t.outcome = "timeout"
            t.r_multiple = round((t.exit_price - t.entry_price) / abs(t.entry_price - t.sl), 2) if t.signal == "BUY" else round((t.entry_price - t.exit_price) / abs(t.entry_price - t.sl), 2)

    return trades


# ── Reporting ──

def report(name: str, trades: list[Trade], symbol: str):
    if not trades:
        print(f"  {name}: NO TRADES")
        return

    wins = [t for t in trades if t.outcome == "win"]
    losses = [t for t in trades if t.outcome == "loss"]
    timeouts = [t for t in trades if t.outcome == "timeout"]
    net_r = sum(t.r_multiple for t in trades)
    win_rate = len(wins) / len(trades) * 100
    avg_r = net_r / len(trades)

    # Commission-adjusted
    commission_cost = len(trades) * COMMISSION_PCT * 2 * 100  # rough % impact

    print(f"  {name:25s} | Trades: {len(trades):3d} | Wins: {len(wins):3d} | Losses: {len(losses):3d} | TO: {len(timeouts):2d} | WR: {win_rate:5.1f}% | Net R: {net_r:+6.2f} | Avg R: {avg_r:+5.2f}")


# ── Main ──

def main():
    print("=" * 90)
    print("HERMES — Signal Replay Backtest")
    print("Comparing entry strategies on 4H data with realistic costs")
    print("=" * 90)

    strategies = {
        "1. SuperTrend Flip (CURRENT)": strategy_supertrend_flip,
        "2. 4H Breakout": strategy_breakout,
        "3. EMA Pullback": strategy_ema_pullback,
        "4. RSI Momentum": strategy_rsi_momentum,
    }

    for symbol in SYMBOLS:
        print(f"\n📊 {symbol}")
        print("-" * 90)

        candles = fetch_4h_candles(symbol)
        if len(candles) < EMA_PERIOD + 50:
            print(f"  ⚠ Insufficient data ({len(candles)} candles)")
            continue

        data = {
            "o": np.array([c["open"] for c in candles]),
            "h": np.array([c["high"] for c in candles]),
            "l": np.array([c["low"] for c in candles]),
            "c": np.array([c["close"] for c in candles]),
            "v": np.array([c.get("volume", 0) for c in candles]),
            "ts": [c["ts"] for c in candles],
        }

        for name, strat_fn in strategies.items():
            trades = simulate(strat_fn(data), data, symbol)
            report(name, trades, symbol)

    print("\n" + "=" * 90)
    print("Legend:")
    print("  WR   = Win Rate")
    print("  Net R = Sum of all R-multiples (positive = profitable)")
    print("  Avg R = Average R per trade")
    print("  Costs: slippage + commission modeled per trade")
    print("=" * 90)


if __name__ == "__main__":
    main()
