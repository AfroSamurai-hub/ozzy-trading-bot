"""
Optimized Bybit client wrapper with batching, caching, and rate limiting.
Wraps the existing BybitClient to maintain compatibility while cutting API calls.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Dict, Optional, Tuple, List
from loguru import logger

from bybit_client import BybitClient


class RateLimiter:
    """Prevent API rate limit violations"""
    def __init__(self, max_calls: int = 100, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()

    def wait_if_needed(self) -> None:
        now = time.time()
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            oldest = self.calls[0]
            wait_time = self.time_window - (now - oldest)
            if wait_time > 0:
                logger.warning(f"⏳ Rate limit protection: waiting {wait_time:.1f}s")
                time.sleep(wait_time + 0.05)
        self.calls.append(time.time())


class CachedBybitClient:
    """Compatibility-preserving client with caching/batching/rate limiting."""

    def __init__(self, *, paper_trading: Optional[bool] = None, testnet: Optional[bool] = None):
        # Underlying client (reuse requests logic we already have)
        self._client = BybitClient(paper_trading=paper_trading, testnet=testnet)

        # Caches (symbol -> (value, ts))
        self._price_cache: Dict[str, tuple] = {}
        self._ticker_cache: Dict[str, tuple] = {}
        self._cache_ttl = 5  # seconds

        # Batch fetch settings
        self._last_batch_fetch = 0.0
        self._batch_interval = 10  # seconds

        # Rate limiter
        self._rl = RateLimiter(max_calls=100, time_window=60)

        # Stats (optional)
        self._api_calls = 0
        self._cache_hits = 0

    # -------------------- Helpers --------------------
    def _now(self) -> float:
        return time.time()

    def _is_fresh(self, ts: float, ttl: Optional[int] = None) -> bool:
        return (self._now() - ts) < (ttl or self._cache_ttl)

    def _batch_fetch_all_tickers_if_needed(self) -> None:
        now = self._now()
        if now - self._last_batch_fetch < self._batch_interval:
            return

        # Perform single public tickers call to hydrate caches for many symbols
        try:
            # Guard with rate limiter
            self._rl.wait_if_needed()

            # Reuse the underlying client's request method
            # Endpoint mirrors get_current_price fallback ticker call
            resp = self._client._make_request(
                "GET", 
                "/v5/market/tickers", 
                params={"category": "spot"}, 
                authenticated=False
            )
            self._api_calls += 1

            if resp.get('retCode') == 0:
                lst = resp.get('result', {}).get('list', []) or []
                hydrated = 0
                for t in lst:
                    try:
                        sym = t.get('symbol')
                        lp = t.get('lastPrice') or t.get('last')
                        if sym and lp is not None:
                            ts = self._now()
                            self._price_cache[sym] = (float(lp), ts)
                            self._ticker_cache[sym] = (t, ts)
                            hydrated += 1
                    except Exception:
                        continue
                self._last_batch_fetch = now
                logger.debug(f"📊 Batch cached {hydrated} tickers")
        except Exception as e:
            logger.debug(f"Batch fetch tickers failed: {e}")

    # -------------------- Public API (compat) --------------------
    def get_current_price(self, symbol: str) -> Optional[float]:
        # Try to serve from batch-cache first
        self._batch_fetch_all_tickers_if_needed()

        cached = self._price_cache.get(symbol)
        if cached and self._is_fresh(cached[1]):
            self._cache_hits += 1
            return float(cached[0])

        # Fallback to underlying method with rate limiting
        self._rl.wait_if_needed()
        self._api_calls += 1
        price = self._client.get_current_price(symbol)
        if price is not None:
            self._price_cache[symbol] = (float(price), self._now())
        return price

    def get_candles(self, symbol: str, interval: str = "15", limit: int = 100) -> Optional[List[Dict]]:
        # Candle history is less bursty; still protect
        self._rl.wait_if_needed()
        self._api_calls += 1
        return self._client.get_candles(symbol, interval=interval, limit=limit)

    def get_bid_ask(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        # Serve from ticker cache if fresh
        self._batch_fetch_all_tickers_if_needed()
        t_cached = self._ticker_cache.get(symbol)
        if t_cached and self._is_fresh(t_cached[1]):
            t = t_cached[0]
            try:
                ask = t.get('askPrice') or t.get('ask') or t.get('bestAskPrice')
                bid = t.get('bidPrice') or t.get('bid') or t.get('bestBidPrice')
                return (float(bid) if bid is not None else None, float(ask) if ask is not None else None)
            except Exception:
                pass

        # Fallback
        self._rl.wait_if_needed()
        self._api_calls += 1
        return self._client.get_bid_ask(symbol)

    def get_balance(self) -> Optional[float]:
        # Balance calls can be expensive; keep as-is but rate limit
        self._rl.wait_if_needed()
        self._api_calls += 1
        return self._client.get_balance()

    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "Market",
                    price: Optional[float] = None, stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None) -> Dict:
        # Trade ops protected by limiter
        self._rl.wait_if_needed()
        self._api_calls += 1
        return self._client.place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    # Optional: expose efficiency metrics
    def get_api_stats(self) -> Dict[str, float]:
        total = self._api_calls + self._cache_hits
        hit_rate = (self._cache_hits / total * 100.0) if total else 0.0
        return {
            'api_calls': float(self._api_calls),
            'cache_hits': float(self._cache_hits),
            'cache_hit_rate_pct': hit_rate
        }
