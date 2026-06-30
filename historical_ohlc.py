from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable
import requests

RELIABLE_PROVIDERS = {
    "BTCUSD": {"provider": "coinbase", "product": "BTC-USD", "interval": 60},
    "ETHUSD": {"provider": "coinbase", "product": "ETH-USD", "interval": 60},
    "BTCUSDT": {"provider": "binance", "symbol": "BTCUSDT", "interval": "1m"},
    "ETHUSDT": {"provider": "binance", "symbol": "ETHUSDT", "interval": "1m"},
    # Forex/Gold via Twelve Data
    "XAUUSD": {"provider": "twelvedata", "symbol": "XAU/USD", "interval": "1h"},
    "EURUSD": {"provider": "twelvedata", "symbol": "EUR/USD", "interval": "1h"},
    "GBPUSD": {"provider": "twelvedata", "symbol": "GBP/USD", "interval": "1h"},
    "USDJPY": {"provider": "twelvedata", "symbol": "USD/JPY", "interval": "1h"},
}

UNRELIABLE_REASON = "No verified real OHLC provider wired in this environment for this symbol"


def provider_reliability_map(symbols: Iterable[str]) -> dict[str, dict]:
    result = {}
    for symbol in symbols:
        provider = RELIABLE_PROVIDERS.get(symbol)
        result[symbol] = {
            "reliable": provider is not None,
            "provider": provider["provider"] if provider else None,
            "reason": None if provider else UNRELIABLE_REASON,
        }
    return result


def _iso8601_utc(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_coinbase(candles: list[list]) -> list[dict]:
    parsed = []
    for row in candles:
        if len(row) < 6:
            continue
        start, low, high, open_, close, volume = row[:6]
        parsed.append({
            "ts": datetime.fromtimestamp(int(start), tz=timezone.utc).isoformat(),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        })
    parsed.sort(key=lambda x: x["ts"])
    return parsed


def _parse_binance(candles: list[list]) -> list[dict]:
    parsed = []
    for row in candles:
        if len(row) < 6:
            continue
        parsed.append({
            "ts": datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).isoformat(),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    parsed.sort(key=lambda x: x["ts"])
    return parsed


def fetch_candles(symbol: str, start_ts: str, end_ts: str | None = None) -> tuple[list[dict], dict]:
    provider = RELIABLE_PROVIDERS.get(symbol)
    if not provider:
        return [], {"reliable": False, "reason": UNRELIABLE_REASON, "provider": None}

    start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
    # Ensure timezone-aware for comparisons
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    if end_ts:
        end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = start_dt + timedelta(days=7)

    if provider["provider"] == "coinbase":
        url = f"https://api.exchange.coinbase.com/products/{provider['product']}/candles"
        cursor = start_dt
        parsed: list[dict] = []
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(minutes=300), end_dt)
            response = requests.get(
                url,
                params={
                    "granularity": provider["interval"],
                    "start": _iso8601_utc(cursor),
                    "end": _iso8601_utc(chunk_end),
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            response.raise_for_status()
            parsed.extend(_parse_coinbase(response.json()))
            cursor = chunk_end
        deduped = {row["ts"]: row for row in parsed}
        return [deduped[key] for key in sorted(deduped)], {"reliable": True, "provider": "coinbase", "timeframe": "1m"}

    if provider["provider"] == "twelvedata":
        return _fetch_twelvedata(provider["symbol"], start_dt, end_dt, provider["interval"])

    url = "https://api.binance.com/api/v3/klines"
    cursor = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    parsed: list[dict] = []
    while cursor < end_ms:
        response = requests.get(
            url,
            params={
                "symbol": provider["symbol"],
                "interval": provider["interval"],
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        chunk = response.json()
        if not chunk:
            break
        parsed.extend(_parse_binance(chunk))
        cursor = int(chunk[-1][6]) + 1
    deduped = {row["ts"]: row for row in parsed}
    return [deduped[key] for key in sorted(deduped)], {"reliable": True, "provider": "binance", "timeframe": "1m"}


def _parse_twelvedata(candles: list[dict]) -> list[dict]:
    """Parse Twelve Data time_series response."""
    parsed = []
    for row in candles:
        parsed.append({
            "ts": row["datetime"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })
    parsed.sort(key=lambda x: x["ts"])
    return parsed


def _fetch_twelvedata(symbol: str, start_dt: datetime, end_dt: datetime, interval: str) -> tuple[list[dict], dict]:
    """Fetch candles from Twelve Data."""
    from twelvedata_client import TWELVE_API_KEY
    
    url = "https://api.twelvedata.com/time_series"
    parsed: list[dict] = []
    
    # Twelve Data has rate limits, so we fetch in one request
    # Format: start_date and end_date as YYYY-MM-DD
    response = requests.get(
        url,
        params={
            "symbol": symbol,
            "interval": interval,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "apikey": TWELVE_API_KEY,
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    
    if "values" in data:
        parsed = _parse_twelvedata(data["values"])
    
    deduped = {row["ts"]: row for row in parsed}
    return [deduped[key] for key in sorted(deduped)], {"reliable": True, "provider": "twelvedata", "timeframe": interval}


def evaluate_outcome_from_candles(signal: str, entry: float, sl: float, tp: float, candles: list[dict], entry_ts: Optional[str] = None) -> dict:
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 4) if risk > 0 else None

    for candle in candles:
        high = float(candle["high"])
        low = float(candle["low"])
        candle_ts = candle["ts"]
        
        # BUG FIX: Only check candles AFTER entry time
        if entry_ts and candle_ts < entry_ts:
            continue

        if signal == "BUY":
            sl_hit = low <= sl
            tp_hit = high >= tp
        else:
            sl_hit = high >= sl
            tp_hit = low <= tp

        if sl_hit and tp_hit:
            return {
                "outcome": "ambiguous",
                "outcome_status": "ambiguous",
                "exit_reason": "same_candle_both_hit",
                "exit_ts": candle_ts,
                "r_multiple": None,
            }
        if tp_hit:
            return {
                "outcome": "win",
                "outcome_status": "resolved",
                "exit_reason": "tp_hit",
                "exit_ts": candle_ts,
                "r_multiple": round(rr, 4) if rr is not None else None,
            }
        if sl_hit:
            return {
                "outcome": "loss",
                "outcome_status": "resolved",
                "exit_reason": "sl_hit",
                "exit_ts": candle_ts,
                "r_multiple": -1.0,
            }

    return {
        "outcome": None,
        "outcome_status": "pending",
        "exit_reason": None,
        "exit_ts": None,
        "r_multiple": None,
    }
