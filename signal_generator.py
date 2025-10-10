"""
OZZY SIMPLE - Signal Generator
The brain of the bot - analyzes market data and generates trading signals
"""

from statistics import mean, stdev
from typing import Dict, List, Optional
from datetime import datetime
import config
from bybit_client import BybitClient


class SignalGenerator:
    """
    Generates trading signals based on technical analysis.
    Uses RSI, EMA, and volume analysis to identify trading opportunities.
    """
    
    def __init__(self):
        """Initialize the signal generator with configuration"""
        self.rsi_period = 14
        # Read RSI thresholds from config if present (optimizer may update these)
        # Defaults chosen for Phase 2 aggressive data collection
        self.rsi_oversold = getattr(config, 'RSI_OVERSOLD', 45)
        self.rsi_overbought = getattr(config, 'RSI_OVERBOUGHT', 55)

        self.ema_short = 9
        self.ema_long = 21

        # Aggressive: volume confirmation effectively disabled (1.0 = current >= avg)
        self.volume_multiplier = 1.0  # Volume must be 1.0x average to confirm signal

        print("[SignalGenerator] Initialized")
        print("  RSI Period:", self.rsi_period)
        print(f"  RSI Oversold: {self.rsi_oversold} | Overbought: {self.rsi_overbought}")
        print(f"  EMA Short: {self.ema_short} | Long: {self.ema_long}")
        print("  Volume Multiplier:", f"{self.volume_multiplier}x")
    
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            prices: List of closing prices (most recent last)
            period: RSI period (default 14)
            
        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral RSI if insufficient data

        # Calculate price changes (deltas)
        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]

        # Separate gains and losses
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        # Safe mean helper
        def safe_mean(arr):
            return mean(arr) if len(arr) > 0 else 0.0

        # Calculate average gains and losses over the last `period` deltas
        avg_gain = safe_mean(gains[-period:])
        avg_loss = safe_mean(losses[-period:])

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        return rsi
    
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average (EMA)
        
        Args:
            prices: List of closing prices (most recent last)
            period: EMA period
            
        Returns:
            EMA value
        """
        if len(prices) < period:
            return mean(prices)  # Use simple average if insufficient data

        # Calculate multiplier
        multiplier = 2.0 / (period + 1)

        # Start with simple moving average for the first 'period' values
        ema = mean(prices[:period])

        # Calculate EMA for remaining prices
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1.0 - multiplier))

        return ema
    
    
    def analyze_volume(self, volumes: List[float]) -> Dict:
        """
        Analyze volume patterns
        
        Args:
            volumes: List of volume values (most recent last)
            
        Returns:
            Dictionary with volume analysis
        """
        if len(volumes) < 2:
            current = volumes[-1] if volumes else 0.0
            return {
                "current_volume": current,
                "avg_volume": current,
                "volume_ratio": 1.0,
                "high_volume": False
            }

        current_volume = volumes[-1]
        avg_volume = mean(volumes[:-1]) if len(volumes[:-1]) > 0 else 0.0

        # Avoid division by zero
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 1.0

        high_volume = volume_ratio >= self.volume_multiplier

        return {
            "current_volume": current_volume,
            "avg_volume": avg_volume,
            "volume_ratio": volume_ratio,
            "high_volume": high_volume
        }
    
    
    def calculate_confidence(self, rsi: float, ema_signal: str, volume_analysis: Dict,
                           price_momentum: float) -> float:
        """
        Calculate confidence score for the signal (0-100%)
        
        Args:
            rsi: RSI value
            ema_signal: EMA signal ('BULLISH', 'BEARISH', 'NEUTRAL')
            volume_analysis: Volume analysis dictionary
            price_momentum: Recent price momentum percentage
            
        Returns:
            Confidence score (0-100)
        """
        confidence = 0.0
        
        # RSI contribution (0-35 points)
        if rsi < self.rsi_oversold:
            # Strong oversold = high confidence for LONG
            confidence += 35 * (1 - (rsi / self.rsi_oversold))
        elif rsi > self.rsi_overbought:
            # Strong overbought = high confidence for SHORT
            confidence += 35 * ((rsi - self.rsi_overbought) / (100 - self.rsi_overbought))
        else:
            # Moderate RSI = lower confidence
            confidence += 10
        
        # EMA contribution (0-30 points)
        if ema_signal == "BULLISH":
            confidence += 30
        elif ema_signal == "BEARISH":
            confidence += 30
        else:
            confidence += 10
        
        # Volume contribution (0-20 points)
        if volume_analysis["high_volume"]:
            confidence += 20
        else:
            confidence += 5
        
        # Momentum contribution (0-15 points)
        momentum_strength = abs(price_momentum)
        confidence += min(momentum_strength * 3, 15)
        
        # Cap at 100
        confidence = min(confidence, 100.0)
        
        return round(confidence, 2)
    
    
    def generate_signal(self, candles: List[Dict]) -> Dict:
        """
        Generate trading signal from candle data
        
        Args:
            candles: List of candle dictionaries with OHLCV data
            
        Returns:
            Signal dictionary with recommendation and details
        """
        if len(candles) < 30:
            return {
                "signal": "HOLD",
                "confidence": 0,
                "reason": "Insufficient data (need 30+ candles)",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # Extract price and volume data
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        current_price = closes[-1]
        
        # Calculate technical indicators
        rsi = self.calculate_rsi(closes, self.rsi_period)
        ema_short = self.calculate_ema(closes, self.ema_short)
        ema_long = self.calculate_ema(closes, self.ema_long)
        volume_analysis = self.analyze_volume(volumes)

    # Volatility: ATR (14) and standard deviation of returns
        atr = None
        atr_pct = None
        stddev_returns = None
        try:
            tr_list = []
            if len(candles) >= 2:
                for i in range(1, len(candles)):
                    high = candles[i]["high"]
                    low = candles[i]["low"]
                    prev_close = candles[i-1]["close"]
                    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                    tr_list.append(tr)

            atr_period = 14
            if len(tr_list) >= atr_period:
                atr = sum(tr_list[-atr_period:]) / atr_period
                atr_pct = (atr / current_price) * 100 if current_price else None

            # Std dev of returns (percentage) over last 14 closes
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] != 0:
                    returns.append((closes[i] - closes[i-1]) / closes[i-1] * 100)
            if len(returns) >= 2:
                stddev_returns = stdev(returns[-14:])
        except Exception:
            atr = None
            atr_pct = None
            stddev_returns = None
        
        # Calculate price momentum (last 5 candles)
        price_5_ago = closes[-6]
        price_momentum = ((current_price - price_5_ago) / price_5_ago) * 100
        
        # Determine EMA signal
        if ema_short > ema_long * 1.002:  # 0.2% above
            ema_signal = "BULLISH"
        elif ema_short < ema_long * 0.998:  # 0.2% below
            ema_signal = "BEARISH"
        else:
            ema_signal = "NEUTRAL"
        
        # Generate signal
        signal = "HOLD"
        reason_parts = []
        
        # LONG signal conditions
        if rsi < self.rsi_oversold and ema_signal == "BULLISH":
            signal = "LONG"
            reason_parts.append(f"RSI oversold ({rsi:.1f})")
            reason_parts.append("EMA bullish crossover")
            
            if volume_analysis["high_volume"]:
                reason_parts.append(f"High volume ({volume_analysis['volume_ratio']:.1f}x)")
        
        # SHORT signal conditions
        elif rsi > self.rsi_overbought and ema_signal == "BEARISH":
            signal = "SHORT"
            reason_parts.append(f"RSI overbought ({rsi:.1f})")
            reason_parts.append("EMA bearish crossover")
            
            if volume_analysis["high_volume"]:
                reason_parts.append(f"High volume ({volume_analysis['volume_ratio']:.1f}x)")
        
        # Strong momentum signals (even without RSI extremes)
        elif ema_signal == "BULLISH" and price_momentum > 2.0 and volume_analysis["high_volume"]:
            signal = "LONG"
            reason_parts.append(f"Strong bullish momentum ({price_momentum:.1f}%)")
            reason_parts.append("EMA bullish + high volume")
        
        elif ema_signal == "BEARISH" and price_momentum < -2.0 and volume_analysis["high_volume"]:
            signal = "SHORT"
            reason_parts.append(f"Strong bearish momentum ({price_momentum:.1f}%)")
            reason_parts.append("EMA bearish + high volume")
        
        # Default HOLD
        else:
            reason_parts.append("No clear setup")
            reason_parts.append(f"RSI: {rsi:.1f}, EMA: {ema_signal}")
        
        # Calculate confidence
        confidence = self.calculate_confidence(rsi, ema_signal, volume_analysis, price_momentum)

        # ---------------------------
        # Confidence-driven fallback
        # If our rule-set didn't produce LONG/SHORT but the confidence is
        # above the configurable MIN_CONFIDENCE, convert HOLD into a trade
        # using price momentum to select direction. This is an aggressive
        # data-collection mode and reversible.
        # ---------------------------
        if signal == "HOLD" and confidence >= getattr(config, 'MIN_CONFIDENCE', 40.0):
            # Choose direction by momentum: non-negative momentum => LONG, else SHORT
            chosen = "LONG" if price_momentum >= 0 else "SHORT"
            signal = chosen
            reason_parts.append(f"Confidence-driven {chosen} (confidence={confidence}%)")

        
        # Calculate entry, stop loss, and take profit
        if signal == "LONG":
            entry_price = current_price
            stop_loss = current_price * (1 - config.STOP_LOSS_PERCENT / 100)
            take_profit = current_price * (1 + config.TAKE_PROFIT_PERCENT / 100)
        elif signal == "SHORT":
            entry_price = current_price
            stop_loss = current_price * (1 + config.STOP_LOSS_PERCENT / 100)
            take_profit = current_price * (1 - config.TAKE_PROFIT_PERCENT / 100)
        else:
            entry_price = current_price
            stop_loss = None
            take_profit = None
        
        # Classify signal quality based on confidence
        if confidence >= 80:
            quality = "PREMIUM"
        elif confidence >= 60:
            quality = "GOOD"
        elif confidence >= 40:
            quality = "MODERATE"
        else:
            quality = "POOR"
        
        # Build signal result
        result = {
            "signal": signal,
            "quality": quality,
            "confidence": confidence,
            "reason": " | ".join(reason_parts),
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2) if stop_loss else None,
            "take_profit": round(take_profit, 2) if take_profit else None,
            "technical_data": {
                "rsi": round(rsi, 2),
                "ema_short": round(ema_short, 2),
                "ema_long": round(ema_long, 2),
                "ema_signal": ema_signal,
                "price_momentum": round(price_momentum, 2),
                "volume_ratio": round(volume_analysis["volume_ratio"], 2),
                "high_volume": volume_analysis["high_volume"],
                # Volatility metrics
                "atr": round(atr, 6) if atr is not None else None,
                "atr_pct": round(atr_pct, 4) if atr_pct is not None else None,
                "stddev_returns_pct": round(stddev_returns, 4) if stddev_returns is not None else None
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Attempt to fetch market microstructure (bid/ask) if available via BybitClient
        try:
            client = BybitClient()
            # If candles include symbol info, use it; otherwise main will pass symbol
            symbol = candles[0].get('symbol') if 'symbol' in candles[0] else None
            bid, ask = (None, None)
            if symbol:
                bid, ask = client.get_bid_ask(symbol)

            # Fallback: estimate from last candle high/low
            if bid is None or ask is None:
                last_high = candles[-1].get('high')
                last_low = candles[-1].get('low')
                if last_high is not None and last_low is not None:
                    ask = ask or last_high
                    bid = bid or last_low

            spread = None
            spread_pct = None
            if bid is not None and ask is not None and current_price:
                spread = ask - bid
                spread_pct = (spread / current_price) * 100

            # Attach microstructure data
            result['technical_data']['bid'] = round(bid, 6) if bid is not None else None
            result['technical_data']['ask'] = round(ask, 6) if ask is not None else None
            result['technical_data']['spread'] = round(spread, 6) if spread is not None else None
            result['technical_data']['spread_pct'] = round(spread_pct, 6) if spread_pct is not None else None
        except Exception:
            # Non-fatal: skip bid/ask if fetch fails
            pass
        
        return result
    
    
    def print_signal(self, signal: Dict, symbol: str = "BTC"):
        """
        Print signal in a formatted way
        
        Args:
            signal: Signal dictionary
            symbol: Trading symbol
        """
        print("\n" + "="*70)
        print(f"SIGNAL GENERATED: {symbol}")
        print("="*70)
        
        # Signal header
        signal_emoji = "🟢" if signal["signal"] == "LONG" else "🔴" if signal["signal"] == "SHORT" else "⚪"
        print(f"\n{signal_emoji} {signal['signal']} | Quality: {signal['quality']} | Confidence: {signal['confidence']}%")
        
        # Reason
        print(f"\nReason: {signal['reason']}")
        
        # Price levels
        print(f"\nEntry Price: ${signal['entry_price']:,.2f}")
        if signal['stop_loss']:
            print(f"Stop Loss:   ${signal['stop_loss']:,.2f} ({config.STOP_LOSS_PERCENT}%)")
        if signal['take_profit']:
            print(f"Take Profit: ${signal['take_profit']:,.2f} ({config.TAKE_PROFIT_PERCENT}%)")
        
        # Technical data
        print("\nTechnical Indicators:")
        tech = signal['technical_data']
        print(f"  RSI: {tech['rsi']:.2f}")
        print(f"  EMA Short (9): ${tech['ema_short']:,.2f}")
        print(f"  EMA Long (21): ${tech['ema_long']:,.2f}")
        print(f"  EMA Signal: {tech['ema_signal']}")
        print(f"  Momentum: {tech['price_momentum']:.2f}%")
        print(f"  Volume: {tech['volume_ratio']:.2f}x avg ({'HIGH' if tech['high_volume'] else 'Normal'})")
        
        print("\n" + "="*70 + "\n")


def test_signal_generator():
    """Test the signal generator with mock data"""
    print("\n" + "="*60)
    print("TESTING SIGNAL GENERATOR")
    print("="*60 + "\n")
    
    # Import the Bybit client to get real candle data
    from bybit_client import BybitClient
    
    client = BybitClient()
    generator = SignalGenerator()
    
    print("\n[TEST] Generating signal for BTC...")
    
    # Get real candle data
    candles = client.get_candles("BTCUSDT", interval="15", limit=50)
    
    if candles:
        # Generate signal
        signal = generator.generate_signal(candles)
        
        # Print signal
        generator.print_signal(signal, symbol="BTCUSDT")
        
        # Validate signal
        if signal["signal"] in ["LONG", "SHORT", "HOLD"]:
            print("✅ TEST PASSED: Signal generated successfully")
        else:
            print("❌ TEST FAILED: Invalid signal type")
    else:
        print("❌ TEST FAILED: Could not fetch candle data")
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_signal_generator()
