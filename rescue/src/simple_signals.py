"""
SIMPLE Signal Generation - The ONLY Strategy We Need
RSI + EMA + Volume ONLY. No complex patterns, no ML, no agents.
"""
from __future__ import annotations
import logging
import numpy as np
from typing import Dict, List, Optional

class SimpleSignalGenerator:
    """
    Dead simple trading strategy:
    1. RSI for momentum (oversold/overbought)
    2. EMA crossover for trend direction
    3. Volume spike for confirmation
    
    That's literally it. Nothing else.
    """
    
    def __init__(self, config):
        self.rsi_period = config.RSI_PERIOD
        self.rsi_oversold = config.RSI_OVERSOLD
        self.rsi_overbought = config.RSI_OVERBOUGHT
        self.ema_short = config.EMA_SHORT
        self.ema_long = config.EMA_LONG
        self.volume_mult = config.VOLUME_MULTIPLIER
        self.min_confidence = config.MIN_CONFIDENCE
    
    def calculate_rsi(self, prices: List[float]) -> float:
        """Calculate RSI - the most battle-tested momentum indicator"""
        if len(prices) < self.rsi_period + 1:
            return 50.0  # Neutral if insufficient data
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return np.mean(prices)  # Fall back to SMA if insufficient data
        
        prices_array = np.array(prices)
        ema = prices_array[0]
        alpha = 2 / (period + 1)
        
        for price in prices_array[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    def calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """Average True Range for stop loss placement"""
        if len(candles) < period + 1:
            # If not enough data, use 2% of price as default
            return candles[-1]['close'] * 0.02
        
        # Only calculate ATR over the last 'period' candles  
        recent_candles = candles[-(period + 1):]
        
        tr_list = []
        for i in range(1, len(recent_candles)):
            high = recent_candles[i]['high']
            low = recent_candles[i]['low']
            prev_close = recent_candles[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)
        
        atr = np.mean(tr_list)
        
        # Sanity check: ATR should be 0.5% - 10% of price for crypto
        current_price = candles[-1]['close']
        logger = logging.getLogger(__name__)
        
        if atr < current_price * 0.005:  # Less than 0.5%
            logger.warning(f"⚠️  ATR ({atr:.2f}) < 0.5% of price ({current_price:.2f}), using 1% default")
            return current_price * 0.01
        elif atr > current_price * 0.10:  # More than 10%
            logger.warning(f"⚠️  ATR ({atr:.2f}) > 10% of price ({current_price:.2f}), using 2% default")
            return current_price * 0.02
        
        return atr
    
    def generate_signal(self, candles: List[Dict]) -> Dict:
        """
        Generate ONE simple signal.
        
        Returns:
            {'signal': 'LONG'|'SHORT'|'SKIP', 'confidence': 0-100, ...}
        """
        # Need enough data for all indicators
        min_candles = max(self.rsi_period, self.ema_long) + 10
        if len(candles) < min_candles:
            return self._skip_signal(f"Need {min_candles} candles, got {len(candles)}")
        
        # Extract price and volume data
        closes = [c['close'] for c in candles]
        volumes = [c['volume'] for c in candles]
        current_price = closes[-1]
        
        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        ema_short = self.calculate_ema(closes, self.ema_short)
        ema_long = self.calculate_ema(closes, self.ema_long)
        avg_volume = np.mean(volumes[-20:])
        current_volume = volumes[-1]
        atr = self.calculate_atr(candles)
        
        # Debug: Check if there's anomalous volume data
        logger = logging.getLogger(__name__)
        logger.info(f"📊 Volume Raw Data Check:")
        logger.info(f"   Total candles: {len(volumes)}")
        logger.info(f"   Last 20 volumes: {[f'{v:.2f}' for v in volumes[-20:]]}")
        logger.info(f"   Max volume in last 20: {max(volumes[-20:]):.2f}")
        logger.info(f"   Min volume in last 20: {min(volumes[-20:]):.2f}")
        logger.info(f"   Sum of last 20: {sum(volumes[-20:]):.2f}")
        logger.info(f"   Calculated avg: {avg_volume:.2f}")
        
        # Debug logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 ATR Debug:")
        logger.info(f"   Current price: ${current_price:.2f}")
        logger.info(f"   ATR value: ${atr:.2f}")
        logger.info(f"   ATR as % of price: {(atr/current_price)*100:.2f}%")
        logger.info(f"   Recent high: ${candles[-1]['high']:.2f}")
        logger.info(f"   Recent low: ${candles[-1]['low']:.2f}")
        logger.info(f"   Recent range: ${candles[-1]['high'] - candles[-1]['low']:.2f}")
        
        # Volume confirmation
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        volume_confirmed = volume_ratio > self.volume_mult
        
        # Debug volume data
        logger.info(f"📊 Volume Debug:")
        logger.info(f"   Latest volume: {current_volume:.2f}")
        logger.info(f"   Recent volumes: {volumes[-5:]}")
        logger.info(f"   Avg volume (20): {avg_volume:.2f}")
        logger.info(f"   Volume ratio: {volume_ratio:.2f}x")
        logger.info(f"   Volume confirmed: {volume_confirmed}")
        
        # LONG signal conditions
        long_conditions = [
            rsi < self.rsi_oversold,  # Oversold
            ema_short > ema_long,  # Uptrend (short EMA above long)
            current_price > ema_short,  # Price above short-term trend
            volume_confirmed  # Volume spike
        ]
        
        # SHORT signal conditions  
        short_conditions = [
            rsi > self.rsi_overbought,  # Overbought
            ema_short < ema_long,  # Downtrend
            current_price < ema_short,  # Price below short-term trend
            volume_confirmed  # Volume spike
        ]
        
        # Calculate confidence (simple percentage of conditions met)
        long_score = sum(long_conditions) / len(long_conditions) * 100
        short_score = sum(short_conditions) / len(short_conditions) * 100
        
        # Decision logic
        if long_score >= self.min_confidence and long_score > short_score:
            signal = "LONG"
            confidence = long_score
        elif short_score >= self.min_confidence and short_score > long_score:
            signal = "SHORT"
            confidence = short_score
        else:
            return self._skip_signal(
                f"No clear signal (LONG:{long_score:.0f}% SHORT:{short_score:.0f}%)"
            )
        
        # Calculate risk management levels
        stop_loss = self._calculate_stop(current_price, signal, atr)
        take_profit = self._calculate_target(current_price, signal, stop_loss)
        
        return {
            'signal': signal,
            'confidence': confidence,
            'entry': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rsi': rsi,
            'ema_short': ema_short,
            'ema_long': ema_long,
            'volume_ratio': volume_ratio,
            'atr': atr,
            'conditions_met': sum(long_conditions if signal == "LONG" else short_conditions),
            'timestamp': candles[-1]['timestamp']
        }
    
    def _calculate_stop(self, price: float, signal: str, atr: float) -> float:
        """ATR-based stop loss (1.5x ATR from entry)"""
        stop_distance = atr * 1.5
        
        if signal == "LONG":
            return price - stop_distance
        else:
            return price + stop_distance
    
    def _calculate_target(self, entry: float, signal: str, stop: float) -> float:
        """2:1 Risk/Reward target"""
        risk = abs(entry - stop)
        
        if signal == "LONG":
            return entry + (risk * 2)
        else:
            return entry - (risk * 2)
    
    def _filter_volume_outliers(self, volumes: List[float]) -> List[float]:
        """Remove volume outliers using IQR method"""
        if len(volumes) < 5:
            return volumes
        
        volumes_arr = np.array(volumes)
        q1 = np.percentile(volumes_arr, 25)
        q3 = np.percentile(volumes_arr, 75)
        iqr = q3 - q1
        
        # Remove values beyond 3*IQR (extreme outliers)
        lower_bound = q1 - 3 * iqr
        upper_bound = q3 + 3 * iqr
        
        filtered = volumes_arr[(volumes_arr >= lower_bound) & (volumes_arr <= upper_bound)]
        
        if len(filtered) < 5:
            # If we filtered too much, use median filter instead
            median = np.median(volumes_arr)
            mad = np.median(np.abs(volumes_arr - median))
            filtered = volumes_arr[np.abs(volumes_arr - median) < 5 * mad]
        
        return filtered.tolist() if len(filtered) > 0 else volumes
    
    def _skip_signal(self, reason: str) -> Dict:
        """Return SKIP signal with reason"""
        return {
            'signal': 'SKIP',
            'confidence': 0.0,
            'reason': reason,
            'timestamp': None
        }
