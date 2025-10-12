"""
External Market Data Adapter (Yahoo Finance public endpoints)

Provides candles and current price for FX/Gold to support monitor-only mode
when the primary venue lacks these instruments.

No API key required. For light monitoring only.
"""
from typing import Dict, List, Optional
from datetime import datetime
import requests


class ExternalMarketData:
    """Yahoo Finance-backed candles/price for FX/Gold."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def _map_symbol(self, symbol: str) -> Optional[str]:
        """Map internal symbols to Yahoo Finance tickers."""
        mapping = {
            'XAUUSDT': 'XAUUSD=X',
            'XAUUSD': 'XAUUSD=X',
            'EURUSD': 'EURUSD=X',
            'GBPUSD': 'GBPUSD=X',
            'USDJPY': 'USDJPY=X',
        }
        return mapping.get(symbol)

    def get_candles(self, symbol: str, interval: str = '15', limit: int = 100) -> Optional[List[Dict]]:
        ticker = self._map_symbol(symbol)
        if not ticker:
            return None

        # Map interval
        interval_map = {
            '1': '1m', '2': '2m', '5': '5m', '15': '15m', '30': '30m', '60': '60m', '90': '90m', '240': '1h', 'D': '1d'
        }
        yf_interval = interval_map.get(str(interval), '15m')
        # Yahoo chart API requires a range compatible with interval; use 5d for intraday
        rng = '5d' if yf_interval.endswith('m') or yf_interval.endswith('h') else '1mo'
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            'interval': yf_interval,
            'range': rng,
        }
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            result = (data.get('chart', {}).get('result') or [None])[0]
            if not result:
                return None
            ts = result.get('timestamp') or []
            quotes = (result.get('indicators', {}).get('quote') or [{}])[0]
            opens = quotes.get('open') or []
            highs = quotes.get('high') or []
            lows = quotes.get('low') or []
            closes = quotes.get('close') or []
            vols = quotes.get('volume') or []

            candles = []
            # Align arrays; skip None values
            n = min(len(ts), len(opens), len(highs), len(lows), len(closes), len(vols))
            # Keep only the most recent "limit" candles
            start = max(0, n - int(limit))
            for i in range(start, n):
                if ts[i] is None or closes[i] is None:
                    continue
                o = opens[i] if opens[i] is not None else closes[i]
                h = highs[i] if highs[i] is not None else closes[i]
                l = lows[i] if lows[i] is not None else closes[i]
                c = closes[i]
                v = vols[i] if vols[i] is not None else 0
                candles.append({
                    'timestamp': int(ts[i]) * 1000,
                    'open': float(o),
                    'high': float(h),
                    'low': float(l),
                    'close': float(c),
                    'volume': float(v),
                    'datetime': datetime.fromtimestamp(int(ts[i])).strftime('%Y-%m-%d %H:%M:%S')
                })
            return candles
        except Exception:
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        ticker = self._map_symbol(symbol)
        if not ticker:
            return None
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {'interval': '1m', 'range': '1d'}
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            result = (data.get('chart', {}).get('result') or [None])[0]
            if not result:
                return None
            closes = (result.get('indicators', {}).get('quote') or [{}])[0].get('close') or []
            if closes:
                return float(closes[-1])
        except Exception:
            return None
        return None
