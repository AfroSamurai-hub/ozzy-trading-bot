"""
🎓 Market Context Analyzers - PhD-Level Quant Intelligence

These analyzers provide rich contextual data to help the AI understand
WHEN and WHY patterns work, not just that they work.

Components:
1. MarketRegimeDetector - Bull/Bear/Sideways/Volatile detection
2. TradingSessionDetector - Asian/European/US session identification
3. VolatilityAnalyzer - Low/Medium/High volatility categorization
4. PatternQualityScorer - Rate the quality of current setup
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Complete market context snapshot"""
    regime: str  # bull_market, bear_market, sideways, volatile
    regime_strength: float  # 0-1, how strong is the trend
    session: str  # asian, european, us, overlap
    volatility: str  # low_vol, medium_vol, high_vol
    volatility_value: float  # Actual ATR or volatility measure
    volatility_expanding: bool  # Is volatility increasing?
    timestamp: datetime
    
    # Additional context
    hour_utc: int
    is_favorable_time: bool
    market_phase: str  # opening, mid_session, closing


class MarketRegimeDetector:
    """
    🎯 Detect market regime: Bull/Bear/Sideways/Volatile
    
    Uses multiple indicators:
    - EMA slope (trend direction)
    - Higher highs / Lower lows (trend confirmation)
    - Volatility (calm vs chaos)
    - Price position relative to moving averages
    """
    
    def __init__(self, ema_period: int = 50, lookback: int = 20):
        """
        Args:
            ema_period: EMA period for trend detection
            lookback: Bars to look back for slope calculation
        """
        self.ema_period = ema_period
        self.lookback = lookback
        logger.info(f"🎯 MarketRegimeDetector initialized (EMA={ema_period}, lookback={lookback})")
    
    def detect_regime(self, prices: pd.Series) -> Tuple[str, float]:
        """
        Detect market regime and its strength.
        
        Args:
            prices: Recent price data (recommend 100+ bars)
        
        Returns:
            (regime, strength) tuple
            - regime: 'bull_market', 'bear_market', 'sideways', 'volatile'
            - strength: 0-1, how strong the regime is
        """
        if len(prices) < self.ema_period + self.lookback:
            return 'unknown', 0.0
        
        # Calculate EMA
        ema = prices.ewm(span=self.ema_period, adjust=False).mean()
        
        # Current price vs EMA
        current_price = prices.iloc[-1]
        current_ema = ema.iloc[-1]
        price_vs_ema = (current_price - current_ema) / current_ema
        
        # EMA slope (rate of change)
        ema_slope = (ema.iloc[-1] - ema.iloc[-self.lookback]) / ema.iloc[-self.lookback]
        
        # Volatility (standard deviation of returns)
        returns = prices.pct_change().dropna()
        volatility = returns.rolling(self.lookback).std().iloc[-1]
        
        # Higher highs / Lower lows analysis
        recent_high = prices.iloc[-self.lookback:].max()
        recent_low = prices.iloc[-self.lookback:].min()
        previous_high = prices.iloc[-2*self.lookback:-self.lookback].max()
        previous_low = prices.iloc[-2*self.lookback:-self.lookback].min()
        
        higher_highs = recent_high > previous_high
        higher_lows = recent_low > previous_low
        lower_highs = recent_high < previous_high
        lower_lows = recent_low < previous_low
        
        # Decision logic
        if volatility > 0.05:  # High volatility (>5% daily moves)
            return 'volatile', min(volatility / 0.05, 1.0)
        
        elif price_vs_ema > 0.02 and ema_slope > 0.015 and higher_highs and higher_lows:
            # Strong bull: Price above EMA, EMA rising, making higher highs/lows
            strength = min((price_vs_ema + ema_slope) / 0.04, 1.0)
            return 'bull_market', strength
        
        elif price_vs_ema < -0.02 and ema_slope < -0.015 and lower_highs and lower_lows:
            # Strong bear: Price below EMA, EMA falling, making lower highs/lows
            strength = min((abs(price_vs_ema) + abs(ema_slope)) / 0.04, 1.0)
            return 'bear_market', strength
        
        elif abs(ema_slope) < 0.01 and abs(price_vs_ema) < 0.02:
            # Sideways: Flat EMA, price oscillating around it
            strength = 1.0 - abs(ema_slope) / 0.01
            return 'sideways', strength
        
        else:
            # Transitional / unclear
            return 'sideways', 0.5
    
    def get_regime_score(self, regime: str, pattern_regime_stats: Dict) -> float:
        """
        Score how favorable current regime is for a pattern.
        
        Args:
            regime: Current market regime
            pattern_regime_stats: Pattern's performance in different regimes
        
        Returns:
            Score 0-1 (1.0 = pattern loves this regime)
        """
        if regime not in pattern_regime_stats:
            return 0.5  # Unknown, neutral score
        
        pattern_win_rate = pattern_regime_stats[regime].get('win_rate', 0.5)
        return pattern_win_rate


class TradingSessionDetector:
    """
    🕐 Detect which trading session is active.
    
    Sessions (UTC):
    - Asian: 00:00-09:00 (Tokyo, Singapore, Hong Kong)
    - European: 07:00-16:00 (London, Frankfurt)
    - US: 13:00-22:00 (New York)
    - Overlap: 13:00-16:00 (EUR+US = HIGHEST VOLUME)
    """
    
    def __init__(self):
        logger.info("🕐 TradingSessionDetector initialized")
    
    def get_session(self, timestamp: Optional[datetime] = None) -> str:
        """
        Determine current trading session.
        
        Args:
            timestamp: Time to check (default: now UTC)
        
        Returns:
            'asian', 'european', 'us', 'overlap'
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Ensure UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        
        hour = timestamp.hour
        
        # Overlap: European + US (highest volume!)
        if 13 <= hour < 16:
            return 'overlap'
        
        # European session
        elif 7 <= hour < 16:
            return 'european'
        
        # US session
        elif 16 <= hour < 22:
            return 'us'
        
        # Asian session (late)
        elif 22 <= hour < 24:
            return 'asian_late'
        
        # Asian session (early)
        else:  # 0 <= hour < 7
            return 'asian_early'
    
    def is_high_volume_period(self, timestamp: Optional[datetime] = None) -> bool:
        """Check if we're in a high-volume trading period"""
        session = self.get_session(timestamp)
        return session in ['overlap', 'european', 'us']
    
    def get_session_score(self, session: str, pattern_session_stats: Dict) -> float:
        """
        Score how favorable current session is for a pattern.
        
        Args:
            session: Current session
            pattern_session_stats: Pattern's performance in different sessions
        
        Returns:
            Score 0-1 (1.0 = pattern loves this session)
        """
        if session not in pattern_session_stats:
            return 0.5  # Unknown, neutral score
        
        pattern_win_rate = pattern_session_stats[session].get('win_rate', 0.5)
        return pattern_win_rate


class VolatilityAnalyzer:
    """
    📊 Analyze and categorize volatility.
    
    Uses ATR (Average True Range) or returns-based volatility.
    Categorizes as: low, medium, high
    Tracks if volatility is expanding or contracting.
    """
    
    def __init__(self, atr_period: int = 14):
        """
        Args:
            atr_period: Period for ATR calculation
        """
        self.atr_period = atr_period
        logger.info(f"📊 VolatilityAnalyzer initialized (ATR period={atr_period})")
    
    def calculate_atr_percent(self, high: pd.Series, low: pd.Series, close: pd.Series) -> float:
        """
        Calculate ATR as percentage of price.
        
        Args:
            high, low, close: Price series
        
        Returns:
            ATR as percentage
        """
        if len(close) < self.atr_period + 1:
            return 0.0
        
        # True Range
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR
        atr = tr.rolling(self.atr_period).mean().iloc[-1]
        
        # As percentage of current price
        atr_pct = (atr / close.iloc[-1]) * 100
        
        return atr_pct
    
    def categorize_volatility(self, atr_pct: float) -> str:
        """
        Categorize volatility level.
        
        Args:
            atr_pct: ATR as percentage
        
        Returns:
            'low_vol', 'medium_vol', 'high_vol'
        """
        if atr_pct < 1.5:
            return 'low_vol'
        elif atr_pct < 3.0:
            return 'medium_vol'
        else:
            return 'high_vol'
    
    def is_volatility_expanding(self, recent_atr: List[float], window: int = 5) -> bool:
        """
        Check if volatility is expanding (increasing).
        
        Args:
            recent_atr: List of recent ATR values
            window: How many periods to compare
        
        Returns:
            True if volatility is expanding
        """
        if len(recent_atr) < window * 2:
            return False
        
        recent_avg = np.mean(recent_atr[-window:])
        previous_avg = np.mean(recent_atr[-window*2:-window])
        
        return recent_avg > previous_avg * 1.1  # 10% increase
    
    def get_volatility_context(
        self, 
        high: pd.Series, 
        low: pd.Series, 
        close: pd.Series
    ) -> Dict:
        """
        Get complete volatility context.
        
        Returns:
            {
                'atr_pct': float,
                'category': str,
                'expanding': bool,
                'percentile': float  # Where current ATR sits vs recent history
            }
        """
        # Current ATR
        current_atr = self.calculate_atr_percent(high, low, close)
        category = self.categorize_volatility(current_atr)
        
        # Historical ATRs for comparison
        recent_atrs = []
        for i in range(min(50, len(close) - self.atr_period)):
            atr = self.calculate_atr_percent(
                high.iloc[:-i-1] if i > 0 else high,
                low.iloc[:-i-1] if i > 0 else low,
                close.iloc[:-i-1] if i > 0 else close
            )
            recent_atrs.append(atr)
        
        expanding = self.is_volatility_expanding(recent_atrs) if len(recent_atrs) >= 10 else False
        
        # Percentile (where are we vs recent history?)
        if recent_atrs:
            percentile = (sum(1 for atr in recent_atrs if atr < current_atr) / len(recent_atrs))
        else:
            percentile = 0.5
        
        return {
            'atr_pct': current_atr,
            'category': category,
            'expanding': expanding,
            'percentile': percentile
        }


class PatternQualityScorer:
    """
    ⭐ Score the quality of a pattern setup.
    
    Combines multiple factors:
    - Pattern clarity/strength
    - Volume confirmation
    - Trend alignment
    - Risk/Reward ratio
    """
    
    def __init__(self):
        logger.info("⭐ PatternQualityScorer initialized")
    
    def score_pattern_strength(self, pattern_data: Dict) -> float:
        """
        Score how clear/strong the pattern is (0-1).
        
        Factors:
        - RSI divergence magnitude
        - Pattern formation clarity
        - Indicator alignment
        """
        # Placeholder - can be enhanced with specific pattern logic
        score = 0.7  # Default
        
        # Boost for extreme RSI (clear oversold/overbought)
        rsi = pattern_data.get('rsi', 50)
        if rsi < 30 or rsi > 70:
            score += 0.15
        
        return min(score, 1.0)
    
    def score_volume_confirmation(self, volume_change: float) -> float:
        """
        Score volume confirmation (0-1).
        
        Strong volume = strong move confirmation
        """
        if volume_change > 2.0:  # 2x average volume
            return 1.0
        elif volume_change > 1.5:  # 1.5x average volume
            return 0.8
        elif volume_change > 1.2:  # 1.2x average volume
            return 0.6
        elif volume_change > 0.8:  # Near average
            return 0.4
        else:  # Low volume
            return 0.2
    
    def score_trend_alignment(self, ema_ratio: float) -> float:
        """
        Score alignment with higher timeframe trend (0-1).
        
        Trading with the trend = higher success
        """
        if ema_ratio > 1.02:  # Strong uptrend
            return 1.0
        elif ema_ratio > 1.005:  # Mild uptrend
            return 0.7
        elif ema_ratio > 0.995:  # Neutral
            return 0.5
        elif ema_ratio > 0.98:  # Mild downtrend
            return 0.3
        else:  # Strong downtrend
            return 0.1
    
    def calculate_overall_quality(
        self,
        pattern_data: Dict,
        market_context: MarketContext
    ) -> Dict:
        """
        Calculate overall setup quality.
        
        Returns:
            {
                'pattern_strength': float,
                'volume_confirmation': float,
                'trend_alignment': float,
                'timing_score': float,
                'overall_quality': float
            }
        """
        pattern_strength = self.score_pattern_strength(pattern_data)
        volume_confirmation = self.score_volume_confirmation(
            pattern_data.get('volume_change', 1.0)
        )
        trend_alignment = self.score_trend_alignment(
            pattern_data.get('ema_ratio', 1.0)
        )
        
        # Timing score (session + volatility match)
        timing_score = 0.5
        if market_context.session in ['overlap', 'us']:
            timing_score += 0.3
        if market_context.volatility == 'medium_vol':
            timing_score += 0.2
        timing_score = min(timing_score, 1.0)
        
        # Overall quality (weighted average)
        overall_quality = (
            pattern_strength * 0.30 +
            volume_confirmation * 0.25 +
            trend_alignment * 0.25 +
            timing_score * 0.20
        )
        
        return {
            'pattern_strength': pattern_strength,
            'volume_confirmation': volume_confirmation,
            'trend_alignment': trend_alignment,
            'timing_score': timing_score,
            'overall_quality': overall_quality
        }


# Singleton instances for easy access
_regime_detector = None
_session_detector = None
_volatility_analyzer = None
_quality_scorer = None


def get_regime_detector() -> MarketRegimeDetector:
    """Get singleton instance of regime detector"""
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = MarketRegimeDetector()
    return _regime_detector


def get_session_detector() -> TradingSessionDetector:
    """Get singleton instance of session detector"""
    global _session_detector
    if _session_detector is None:
        _session_detector = TradingSessionDetector()
    return _session_detector


def get_volatility_analyzer() -> VolatilityAnalyzer:
    """Get singleton instance of volatility analyzer"""
    global _volatility_analyzer
    if _volatility_analyzer is None:
        _volatility_analyzer = VolatilityAnalyzer()
    return _volatility_analyzer


def get_quality_scorer() -> PatternQualityScorer:
    """Get singleton instance of quality scorer"""
    global _quality_scorer
    if _quality_scorer is None:
        _quality_scorer = PatternQualityScorer()
    return _quality_scorer


def build_market_context(
    prices: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    timestamp: Optional[datetime] = None
) -> MarketContext:
    """
    🎯 Build complete market context snapshot.
    
    This is the ONE function to call to get all context!
    
    Args:
        prices: Price series for regime detection
        high, low, close: OHLC data for volatility
        timestamp: Current time (default: now)
    
    Returns:
        MarketContext with all contextual information
    """
    regime_detector = get_regime_detector()
    session_detector = get_session_detector()
    volatility_analyzer = get_volatility_analyzer()
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    # Detect regime
    regime, regime_strength = regime_detector.detect_regime(prices)
    
    # Detect session
    session = session_detector.get_session(timestamp)
    
    # Analyze volatility
    vol_context = volatility_analyzer.get_volatility_context(high, low, close)
    
    # Additional context
    hour_utc = timestamp.hour
    is_favorable = session_detector.is_high_volume_period(timestamp)
    
    # Market phase
    if hour_utc in [0, 1, 7, 8, 13, 14]:
        phase = 'opening'
    elif hour_utc in [6, 12, 21, 22]:
        phase = 'closing'
    else:
        phase = 'mid_session'
    
    return MarketContext(
        regime=regime,
        regime_strength=regime_strength,
        session=session,
        volatility=vol_context['category'],
        volatility_value=vol_context['atr_pct'],
        volatility_expanding=vol_context['expanding'],
        timestamp=timestamp,
        hour_utc=hour_utc,
        is_favorable_time=is_favorable,
        market_phase=phase
    )
