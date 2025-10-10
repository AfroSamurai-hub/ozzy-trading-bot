"""
OZZY SIMPLE - Bybit API Client
Handles all communication with Bybit exchange
"""

import requests
import time
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from loguru import logger
import config


class BybitClient:
    """
    Bybit API Client for fetching market data and executing trades.
    Supports both testnet (paper trading) and live trading.
    """
    
    def __init__(self):
        """Initialize the Bybit client with configuration"""
        self.api_key = config.BYBIT_API_KEY
        self.api_secret = config.BYBIT_API_SECRET
        self.testnet = config.BYBIT_TESTNET
        self.paper_trading = config.PAPER_TRADING
        
        # Set base URL based on testnet/live
        if self.testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
        
        # Paper trading state (simulated balance and positions)
        self.paper_balance = config.STARTING_CAPITAL if self.paper_trading else 0
        self.paper_positions = {}  # {symbol: {'size': float, 'entry_price': float}}

        logger.info("BybitClient initialized", 
                    mode='PAPER TRADING' if self.paper_trading else 'LIVE TRADING',
                    network='TESTNET' if self.testnet else 'MAINNET')
        if self.paper_trading:
            logger.info(f"Paper Balance: R{self.paper_balance:,.2f}")
    
    
    def _generate_signature(self, params: Dict) -> str:
        """
        Generate HMAC SHA256 signature for authenticated requests
        
        Args:
            params: Request parameters
            
        Returns:
            Signature string
        """
        # Sort parameters alphabetically
        sorted_params = sorted(params.items())
        param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
        
        # Generate signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     authenticated: bool = False) -> Dict:
        """
        Make HTTP request to Bybit API
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Request parameters
            authenticated: Whether request requires authentication
            
        Returns:
            Response dictionary
        """
        # Avoid mutating the caller's dict
        request_params = params.copy() if params else {}
        
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        # Add authentication if required
        if authenticated:
            timestamp = str(int(time.time() * 1000))
            request_params['api_key'] = self.api_key
            request_params['timestamp'] = timestamp
            request_params['sign'] = self._generate_signature(request_params)
        
        try:
            if method == "GET":
                response = requests.get(url, params=request_params, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=request_params, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {endpoint}", error=str(e), exc_info=True)
            return {"retCode": -1, "retMsg": str(e)}
    
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            
        Returns:
            Current price or None if failed
        """
        if self.paper_trading:
            # In paper trading, fetch real price but don't use authenticated API
            endpoint = "/v5/market/tickers"
            params = {"category": "spot", "symbol": symbol}
            response = self._make_request("GET", endpoint, params, authenticated=False)
            
            if response.get("retCode") == 0:
                tickers = response.get("result", {}).get("list", [])
                if tickers:
                    price = float(tickers[0].get("lastPrice", 0))
                    logger.debug(f"{symbol} price: ${price:,.2f}")
                    return price
            
            logger.warning(f"Failed to fetch price for {symbol}", response_code=response.get("retCode"))
            return None
        
        else:
            # Live trading - use same endpoint
            endpoint = "/v5/market/tickers"
            params = {"category": "spot", "symbol": symbol}
            response = self._make_request("GET", endpoint, params, authenticated=False)
            
            if response.get("retCode") == 0:
                tickers = response.get("result", {}).get("list", [])
                if tickers:
                    return float(tickers[0].get("lastPrice", 0))
            
            return None
    
    
    def get_candles(self, symbol: str, interval: str = "15", limit: int = 100) -> Optional[List[Dict]]:
        """
        Get historical candlestick data
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candle interval in minutes ('1', '5', '15', '60', '240', 'D')
            limit: Number of candles to fetch (max 200)
            
        Returns:
            List of candle dictionaries with OHLCV data, or None if failed
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        response = self._make_request("GET", endpoint, params, authenticated=False)
        
        if response.get("retCode") == 0:
            candles_raw = response.get("result", {}).get("list", [])
            
            # Convert to more readable format
            candles = []
            for candle in candles_raw:
                candles.append({
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                    "datetime": datetime.fromtimestamp(int(candle[0]) / 1000).strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Reverse to get chronological order (API returns newest first)
            candles.reverse()
            
            logger.debug(f"Fetched {len(candles)} candles for {symbol}", interval=f"{interval}m")
            return candles
        
        logger.warning(f"Failed to fetch candles for {symbol}", error=response.get('retMsg'))
        return None


    def get_bid_ask(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Get current best bid and ask for a symbol (public endpoint)

        Returns:
            (bid, ask) as floats or (None, None) if unavailable
        """
        endpoint = "/v5/market/tickers"
        params = {"category": "spot", "symbol": symbol}
        response = self._make_request("GET", endpoint, params, authenticated=False)

        if response.get("retCode") == 0:
            tickers = response.get("result", {}).get("list", [])
            if tickers:
                t = tickers[0]
                # Common fields
                ask = t.get('askPrice') or t.get('ask') or t.get('bestAskPrice')
                bid = t.get('bidPrice') or t.get('bid') or t.get('bestBidPrice')
                try:
                    ask = float(ask) if ask is not None else None
                except Exception:
                    ask = None
                try:
                    bid = float(bid) if bid is not None else None
                except Exception:
                    bid = None

                return bid, ask

        return None, None
    
    
    def get_balance(self) -> Optional[float]:
        """
        Get account balance (USDT)
        
        Returns:
            Balance in USDT or None if failed
        """
        if self.paper_trading:
            logger.debug(f"Paper balance: R{self.paper_balance:,.2f}")
            return self.paper_balance
        
        else:
            # Live trading - fetch real balance
            endpoint = "/v5/account/wallet-balance"
            params = {"accountType": "UNIFIED"}
            response = self._make_request("GET", endpoint, params, authenticated=True)
            
            if response.get("retCode") == 0:
                accounts = response.get("result", {}).get("list", [])
                if accounts:
                    coins = accounts[0].get("coin", [])
                    for coin in coins:
                        if coin.get("coin") == "USDT":
                            balance = float(coin.get("walletBalance", 0))
                            logger.info(f"Live balance: ${balance:,.2f} USDT")
                            return balance
            
            logger.error(f"Failed to fetch balance", error=response.get('retMsg'))
            return None
    
    
    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "Market",
                   price: Optional[float] = None, stop_loss: Optional[float] = None,
                   take_profit: Optional[float] = None) -> Dict:
        """
        Place an order (paper or live)
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'Buy' or 'Sell'
            qty: Order quantity
            order_type: 'Market' or 'Limit'
            price: Limit price (only for Limit orders)
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Order result dictionary
        """
        if self.paper_trading:
            # Simulate order execution with improved short support
            current_price = self.get_current_price(symbol)
            if current_price is None:
                return {"success": False, "message": "Failed to get current price"}

            # Notional (full position value at market price)
            notional = qty * current_price

            # BUY side: either close SHORT (buy-to-cover) or open LONG
            if side == "Buy":
                # If there's a short, close (or partially close) it
                if symbol in self.paper_positions and self.paper_positions[symbol].get('side') == 'short':
                    position = self.paper_positions[symbol]
                    pos_qty = position.get('qty', 0)
                    close_qty = min(qty, pos_qty)

                    # PnL for short (profit when price falls): (entry_price - exit_price) * closed_qty
                    entry_price = position.get('entry_price', 0)
                    exit_value = close_qty * current_price
                    entry_value = close_qty * entry_price
                    pnl = entry_value - exit_value

                    # Return proportionate margin + pnl
                    margin_total = position.get('margin', position.get('notional', position.get('value', 0)) * config.SHORT_MARGIN)
                    margin_return = margin_total * (close_qty / pos_qty) if pos_qty > 0 else margin_total
                    self.paper_balance += margin_return + pnl

                    # Adjust or remove position
                    remaining_qty = pos_qty - close_qty
                    if remaining_qty > 0:
                        # shrink notional and margin proportionally
                        position['qty'] = remaining_qty
                        position['notional'] = position.get('notional', position.get('value', 0)) - entry_value
                        position['margin'] = margin_total - margin_return
                        self.paper_positions[symbol] = position
                    else:
                        del self.paper_positions[symbol]

                    logger.info(f"Paper SHORT closed: Buy {close_qty} {symbol} @ ${current_price:,.2f}",
                               pnl=f"${pnl:,.2f}", margin_returned=f"${margin_return:,.2f}")
                    result = {
                        "success": True,
                        "order_id": f"PAPER_{int(time.time())}",
                        "symbol": symbol,
                        "side": side,
                        "qty": close_qty,
                        "price": current_price,
                        "pnl": pnl,
                        "margin_returned": margin_return,
                        "order_type": "Market",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    logger.info(f"Paper order executed: {side} {close_qty} {symbol} @ ${current_price:,.2f}")
                    return result

                # No short exists -> open a LONG position (spot buy)
                if notional > self.paper_balance:
                    return {"success": False, "message": "Insufficient balance to open LONG"}

                self.paper_balance -= notional
                self.paper_positions[symbol] = {
                    "qty": qty,
                    "entry_price": current_price,
                    "side": 'long',
                    "value": notional,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }

                logger.info(f"Paper LONG opened: Buy {qty} {symbol} @ ${current_price:,.2f}",
                           notional=f"${notional:,.2f}")
                result = {
                    "success": True,
                    "order_id": f"PAPER_{int(time.time())}",
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": current_price,
                    "order_type": "Market",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                logger.info(f"Paper order executed: {side} {qty} {symbol} @ ${current_price:,.2f}")
                return result

            # SELL side: either close LONG or open SHORT
            else:  # Sell
                # If there's a long, close (or partially close) it
                if symbol in self.paper_positions and self.paper_positions[symbol].get('side') == 'long':
                    position = self.paper_positions[symbol]
                    pos_qty = position.get('qty', 0)
                    close_qty = min(qty, pos_qty)

                    exit_value = close_qty * current_price
                    pnl = (current_price - position.get('entry_price')) * close_qty

                    # Release proceeds back to balance (spot sell)
                    self.paper_balance += exit_value

                    remaining_qty = pos_qty - close_qty
                    if remaining_qty > 0:
                        position['qty'] = remaining_qty
                        position['value'] = position.get('value', 0) - (close_qty * position.get('entry_price'))
                        self.paper_positions[symbol] = position
                    else:
                        del self.paper_positions[symbol]

                    logger.info(f"Paper LONG closed: Sell {close_qty} {symbol} @ ${current_price:,.2f}",
                               pnl=f"${pnl:,.2f}")
                    result = {
                        "success": True,
                        "order_id": f"PAPER_{int(time.time())}",
                        "symbol": symbol,
                        "side": side,
                        "qty": close_qty,
                        "price": current_price,
                        "pnl": pnl,
                        "order_type": "Market",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    logger.info(f"Paper order executed: {side} {close_qty} {symbol} @ ${current_price:,.2f}")
                    return result

                # No long exists -> open a SHORT (use margin)
                margin_required = notional * getattr(config, 'SHORT_MARGIN', 0.10)
                if margin_required > self.paper_balance:
                    return {"success": False, "message": "Insufficient balance to post SHORT margin"}

                # Deduct margin from balance and record short position
                self.paper_balance -= margin_required
                self.paper_positions[symbol] = {
                    'qty': qty,
                    'entry_price': current_price,
                    'side': 'short',
                    'notional': notional,
                    'margin': margin_required,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                }

                logger.info(f"Paper SHORT opened: Sell {qty} {symbol} @ ${current_price:,.2f}",
                           notional=f"${notional:,.2f}", margin=f"${margin_required:,.2f}")
                result = {
                    "success": True,
                    "order_id": f"PAPER_{int(time.time())}",
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": current_price,
                    "margin": margin_required,
                    "order_type": "Market",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                logger.info(f"Paper order executed: {side} {qty} {symbol} @ ${current_price:,.2f}")
                return result
        
        else:
            # Live trading - place real order
            endpoint = "/v5/order/create"
            params = {
                "category": "spot",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty)
            }
            
            if order_type == "Limit" and price:
                params["price"] = str(price)
            
            if stop_loss:
                params["stopLoss"] = str(stop_loss)
            
            if take_profit:
                params["takeProfit"] = str(take_profit)
            
            response = self._make_request("POST", endpoint, params, authenticated=True)
            
            if response.get("retCode") == 0:
                order_id = response.get("result", {}).get("orderId")
                return {
                    "success": True,
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "order_type": order_type
                }
            else:
                return {
                    "success": False,
                    "message": response.get("retMsg", "Unknown error")
                }


def test_client():
    """Test the Bybit client with basic operations"""
    logger.info("=" * 60)
    logger.info("TESTING BYBIT CLIENT")
    logger.info("=" * 60)
    
    client = BybitClient()
    
    # Test 1: Get BTC price
    logger.info("[TEST 1] Fetching BTC price...")
    btc_price = client.get_current_price("BTCUSDT")
    if btc_price:
        logger.info(f"✅ TEST 1 PASSED: BTC price = ${btc_price:,.2f}")
    else:
        logger.error("❌ TEST 1 FAILED: Could not fetch BTC price")
    
    # Test 2: Get candle data
    logger.info("[TEST 2] Fetching BTC candles (15m, last 10)...")
    candles = client.get_candles("BTCUSDT", interval="15", limit=10)
    if candles and len(candles) > 0:
        logger.info(f"✅ TEST 2 PASSED: Fetched {len(candles)} candles")
        logger.debug(f"  Latest candle: {candles[-1]}")
    else:
        logger.error("❌ TEST 2 FAILED: Could not fetch candles")
    
    # Test 3: Get balance
    logger.info("[TEST 3] Getting account balance...")
    balance = client.get_balance()
    if balance is not None:
        logger.info(f"✅ TEST 3 PASSED: Balance = R{balance:,.2f}")
    else:
        logger.error("❌ TEST 3 FAILED: Could not fetch balance")
    
    logger.info("=" * 60)
    logger.info("TESTING COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_client()
