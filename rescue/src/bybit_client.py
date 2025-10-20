"""
Simplified Bybit API Client - V5 API Only
Stripped down to ONLY what we need: get candles, place orders, check balance.
"""
from __future__ import annotations
import time
import hmac
import hashlib
import json
import logging
from typing import Dict, List, Optional
from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

class BybitClient:
    """
    Minimal Bybit V5 API wrapper.
    No fancy features, just the basics that work.
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Initialize Bybit client
        
        Args:
            api_key: Your Bybit API key
            api_secret: Your Bybit API secret
            testnet: True for testnet, False for live (DEFAULT: True for safety)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Initialize pybit HTTP client
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )
        
        logger.info(f"✅ Bybit client initialized ({'TESTNET' if testnet else 'LIVE'})")
    
    def get_candles(self, symbol: str = "BTCUSDT", interval: str = "240", limit: int = 100) -> List[Dict]:
        """
        Get historical candles (klines)
        
        Args:
            symbol: Trading pair (default: BTCUSDT)
            interval: Timeframe in minutes - "240" = 4H (default)
            limit: Number of candles (max 200)
        
        Returns:
            List of candle dicts with: timestamp, open, high, low, close, volume
        """
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response['retCode'] != 0:
                logger.error(f"Bybit API error: {response['retMsg']}")
                return []
            
            # Parse candles into simple format
            candles = []
            for kline in response['result']['list']:
                candles.append({
                    'timestamp': int(kline[0]),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),  # Volume in base currency (BTC)
                    'turnover': float(kline[6]) if len(kline) > 6 else 0  # Volume in quote currency (USDT)
                })
            
            # Bybit returns newest first, we want oldest first
            candles.reverse()
            
            logger.info(f"📊 Fetched {len(candles)} candles for {symbol} ({interval}m)")
            if candles:
                logger.debug(f"   Sample candle - Volume: {candles[-1]['volume']:.2f}, Turnover: {candles[-1].get('turnover', 0):.2f}")
            return candles
            
        except Exception as e:
            logger.error(f"❌ Failed to get candles: {e}")
            return []
    
    def get_balance(self) -> Dict:
        """
        Get USDT balance
        
        Returns:
            {'total': float, 'available': float}
        """
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED"  # V5 API uses unified account
            )
            
            if response['retCode'] != 0:
                logger.error(f"Bybit API error: {response['retMsg']}")
                return {'total': 0.0, 'available': 0.0}
            
            # Extract USDT balance
            coins = response['result']['list'][0]['coin']
            usdt_balance = next((c for c in coins if c['coin'] == 'USDT'), None)
            
            if not usdt_balance:
                return {'total': 0.0, 'available': 0.0}
            
            return {
                'total': float(usdt_balance['walletBalance']),
                'available': float(usdt_balance['availableToWithdraw'])
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get balance: {e}")
            return {'total': 0.0, 'available': 0.0}
    
    def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict:
        """
        Place a market order with stop loss and take profit
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "LONG" or "SHORT"
            size: Position size (in coin, e.g., 0.001 BTC)
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
        
        Returns:
            Order details dict
        """
        try:
            # Convert LONG/SHORT to Buy/Sell
            order_side = "Buy" if side == "LONG" else "Sell"
            
            # Place market order with DCP support
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": order_side,
                "orderType": "Market",
                "qty": str(size),
                "timeInForce": "GTC",  # CRITICAL: DCP protection (40-second window)
            }
            
            # Add stop loss if provided
            if stop_loss:
                order_params["stopLoss"] = str(stop_loss)
            
            # Add take profit if provided
            if take_profit:
                order_params["takeProfit"] = str(take_profit)
            
            response = self.session.place_order(**order_params)
            
            if response['retCode'] != 0:
                logger.error(f"❌ Order failed: {response['retMsg']}")
                return {'success': False, 'error': response['retMsg']}
            
            order_id = response['result']['orderId']
            logger.info(f"✅ Order placed: {order_id} ({side} {size} {symbol})")
            
            return {
                'success': True,
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'size': size,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to place order: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_open_positions(self, symbol: str = "BTCUSDT") -> List[Dict]:
        """
        Get current open positions
        
        Returns:
            List of position dicts
        """
        try:
            response = self.session.get_positions(
                category="linear",
                symbol=symbol
            )
            
            if response['retCode'] != 0:
                logger.error(f"Bybit API error: {response['retMsg']}")
                return []
            
            positions = []
            for pos in response['result']['list']:
                if float(pos['size']) > 0:  # Only active positions
                    positions.append({
                        'symbol': pos['symbol'],
                        'side': pos['side'],
                        'size': float(pos['size']),
                        'entry_price': float(pos['avgPrice']),
                        'unrealized_pnl': float(pos['unrealisedPnl']),
                        'leverage': float(pos['leverage'])
                    })
            
            return positions
            
        except Exception as e:
            logger.error(f"❌ Failed to get positions: {e}")
            return []
    
    def close_position(self, symbol: str, side: str) -> Dict:
        """
        Close an open position
        
        Args:
            symbol: Trading pair
            side: "Buy" to close short, "Sell" to close long
        """
        try:
            # Get current position size
            positions = self.get_open_positions(symbol)
            if not positions:
                return {'success': False, 'error': 'No position to close'}
            
            position = positions[0]
            
            # Place closing order (opposite side)
            close_side = "Sell" if position['side'] == "Buy" else "Buy"
            
            response = self.session.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(position['size']),
                timeInForce="GTC",
                reduceOnly=True  # Important: only close, don't open opposite
            )
            
            if response['retCode'] != 0:
                logger.error(f"❌ Close failed: {response['retMsg']}")
                return {'success': False, 'error': response['retMsg']}
            
            logger.info(f"✅ Position closed: {symbol}")
            return {'success': True, 'pnl': position['unrealized_pnl']}
            
        except Exception as e:
            logger.error(f"❌ Failed to close position: {e}")
            return {'success': False, 'error': str(e)}
