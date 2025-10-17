"""
Data-Driven Trading Improvements

Three manager classes implementing fixes discovered from trading data analysis:
1. DynamicConfidenceCalculator - Adjusts confidence based on market conditions
2. PatternDiversityManager - Prevents over-reliance on single patterns
3. EntrySpacingManager - Enforces minimum time between entries

Philosophy: "Evolve, not add and break"
Based on: AI_LEARNING_INSIGHTS.md analysis (Oct 15, 2025)
"""

import logging
from datetime import datetime
from typing import Dict, Tuple, Any, Optional
from collections import deque

logger = logging.getLogger(__name__)


class DynamicConfidenceCalculator:
    """
    Adjusts AI confidence based on real market conditions.
    
    Problem Solved: AI was giving flat 75% confidence to all trades
    Solution: Add modifiers for RSI, volume, time-of-day, pattern performance
    
    Expected: Confidence will range 50-90% instead of flat 75%
    """
    
    def __init__(self):
        self.recent_pattern_performance = {}  # pattern_name -> recent win rate
        
    def calculate_dynamic_confidence(
        self, 
        base_confidence: float, 
        market_data: Dict[str, Any],
        pattern_name: Optional[str] = None
    ) -> Tuple[float, str]:
        """
        Calculate confidence with multiple market condition modifiers.
        
        Args:
            base_confidence: AI's base confidence from pattern matching
            market_data: Current market indicators (RSI, volume, etc.)
            pattern_name: Name of pattern being used
            
        Returns:
            (adjusted_confidence, explanation)
        """
        confidence = base_confidence
        adjustments = []
        
        # RSI modifier (strong signals boost confidence)
        rsi = market_data.get('rsi', 50)
        if rsi < 30:  # Oversold - bullish for longs
            confidence += 0.05
            adjustments.append(f"RSI oversold (+5%)")
        elif rsi > 70:  # Overbought - bearish for longs
            confidence -= 0.10
            adjustments.append(f"RSI overbought (-10%)")
        elif 45 <= rsi <= 55:  # Neutral zone (uncertain)
            confidence -= 0.05
            adjustments.append(f"RSI neutral (-5%)")
        
        # Volume modifier (high volume = more reliable)
        volume_24h = market_data.get('volume_24h', 0)
        volume_avg = market_data.get('volume_avg', 1)
        
        if volume_24h > 0 and volume_avg > 0:
            volume_ratio = volume_24h / volume_avg
            if volume_ratio > 1.5:  # 50% above average
                confidence += 0.05
                adjustments.append(f"High volume (+5%)")
            elif volume_ratio < 0.7:  # 30% below average
                confidence -= 0.10
                adjustments.append(f"Low volume (-10%)")
        
        # Time-of-day modifier (based on general crypto trading patterns)
        hour = datetime.now().hour
        if 15 <= hour <= 18:  # US session open (high activity)
            confidence += 0.03
            adjustments.append(f"Optimal time (+3%)")
        elif 12 <= hour <= 15:  # Low volume period
            confidence -= 0.08
            adjustments.append(f"Low activity hours (-8%)")
        
        # Pattern performance modifier (if we have recent data)
        if pattern_name and pattern_name in self.recent_pattern_performance:
            pattern_win_rate = self.recent_pattern_performance[pattern_name]
            if pattern_win_rate > 0.65:  # Pattern performing well
                confidence += 0.05
                adjustments.append(f"Pattern hot (+5%)")
            elif pattern_win_rate < 0.45:  # Pattern underperforming
                confidence -= 0.15
                adjustments.append(f"Pattern cold (-15%)")
        
        # Clamp to reasonable range (50-90%)
        original_confidence = confidence
        confidence = max(0.50, min(0.90, confidence))
        
        # Create explanation
        if adjustments:
            explanation = f"Base {base_confidence:.1%} → {confidence:.1%} ({', '.join(adjustments)})"
        else:
            explanation = f"Confidence: {confidence:.1%} (no adjustments)"
        
        if original_confidence != confidence:
            clamped_dir = "raised" if confidence > original_confidence else "lowered"
            explanation += f" [clamped {clamped_dir} to valid range]"
        
        logger.info(f"   💡 {explanation}")
        
        return confidence, explanation
    
    def update_pattern_performance(self, pattern_name: str, win_rate: float):
        """Update recent performance for a pattern"""
        self.recent_pattern_performance[pattern_name] = win_rate


class PatternDiversityManager:
    """
    Prevents over-reliance on single pattern by tracking usage.
    
    Problem Solved: 100% of trades used whale accumulation pattern
    Solution: Track pattern usage, penalize overused patterns
    
    Expected: Pattern mix will be ~40% whale, 30% RSI, 30% other
    """
    
    def __init__(self, window_size: int = 20, max_usage_pct: float = 0.50):
        self.pattern_usage = deque(maxlen=window_size)  # Rolling window of recent patterns
        self.window_size = window_size
        self.max_usage_pct = max_usage_pct
        self.decision_counter = 0
        
    def should_use_pattern(self, pattern_name: str) -> Tuple[bool, str]:
        """
        Check if pattern can be used without creating over-reliance.
        
        Args:
            pattern_name: Name of pattern AI wants to use
            
        Returns:
            (allowed, reason)
        """
        if not pattern_name:
            return True, "No pattern specified"
        
        # Not enough data yet - allow
        if len(self.pattern_usage) < 5:
            return True, "Building pattern diversity baseline"
        
        # Count usage of this pattern in recent window
        pattern_count = sum(1 for p in self.pattern_usage if p == pattern_name)
        usage_pct = pattern_count / len(self.pattern_usage)
        
        # Check if pattern is overused
        if usage_pct >= self.max_usage_pct:
            return False, (
                f"Pattern '{pattern_name}' overused: {usage_pct:.0%} "
                f"(max {self.max_usage_pct:.0%})"
            )
        
        # Warn if approaching limit
        if usage_pct > 0.40:
            logger.warning(
                f"   ⚠️  Pattern '{pattern_name}' heavily used: {usage_pct:.0%} "
                f"(consider diversifying)"
            )
        
        return True, f"Pattern usage OK ({usage_pct:.0%})"
    
    def record_pattern_usage(self, pattern_name: str):
        """Record which pattern was used for this decision"""
        self.pattern_usage.append(pattern_name)
        self.decision_counter += 1
        
        # Log diversity stats periodically
        if self.decision_counter % 10 == 0:
            self._log_diversity_stats()
    
    def _log_diversity_stats(self):
        """Log current pattern distribution"""
        if not self.pattern_usage:
            return
        
        # Count pattern distribution
        pattern_counts = {}
        for pattern in self.pattern_usage:
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        
        logger.info("   📊 Pattern Diversity (last %d decisions):", len(self.pattern_usage))
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            pct = count / len(self.pattern_usage) * 100
            logger.info(f"      • {pattern}: {count} ({pct:.0f}%)")


class EntrySpacingManager:
    """
    Enforces minimum time between entries to prevent clustering.
    
    Problem Solved: 6 positions opened in 5.3 minutes (all at same price)
    Solution: Minimum 10 minutes between entries, wait for confirmation
    
    Expected: Entries will be spread out, better entry prices
    """
    
    def __init__(
        self, 
        min_spacing_seconds: int = 600,  # 10 minutes
        confirmation_wait_seconds: int = 120  # 2 minutes
    ):
        self.last_entry_time: Optional[datetime] = None
        self.last_signal_time: Optional[datetime] = None
        self.last_pattern_used: Optional[str] = None
        
        self.min_spacing_seconds = min_spacing_seconds
        self.same_pattern_spacing = min_spacing_seconds * 2  # 20 minutes for same pattern
        self.confirmation_wait = confirmation_wait_seconds
        
    def can_enter_position(
        self, 
        current_pattern: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if enough time has passed since last entry.
        
        Args:
            current_pattern: Pattern being used for this trade
            current_time: Current time (defaults to now)
            
        Returns:
            (allowed, reason)
        """
        if current_time is None:
            current_time = datetime.now()
        
        # First entry - always allowed
        if self.last_entry_time is None:
            return True, "First entry"
        
        # Calculate time since last entry
        time_since_last = (current_time - self.last_entry_time).total_seconds()
        
        # If same pattern as last trade, require longer spacing
        if current_pattern == self.last_pattern_used:
            if time_since_last < self.same_pattern_spacing:
                wait_remaining = self.same_pattern_spacing - time_since_last
                return False, (
                    f"Same pattern '{current_pattern}' - wait {wait_remaining:.0f}s more "
                    f"(min {self.same_pattern_spacing}s)"
                )
        
        # Different pattern, check minimum spacing
        if time_since_last < self.min_spacing_seconds:
            wait_remaining = self.min_spacing_seconds - time_since_last
            return False, (
                f"Entry spacing: wait {wait_remaining:.0f}s more "
                f"(min {self.min_spacing_seconds}s)"
            )
        
        return True, f"Entry timing OK ({time_since_last:.0f}s since last)"
    
    def should_wait_for_confirmation(
        self,
        signal_detected_time: datetime,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if we should wait for price confirmation after signal.
        
        Args:
            signal_detected_time: When AI first detected the signal
            current_time: Current time (defaults to now)
            
        Returns:
            (should_wait, reason)
        """
        if current_time is None:
            current_time = datetime.now()
        
        time_since_signal = (current_time - signal_detected_time).total_seconds()
        
        if time_since_signal < self.confirmation_wait:
            wait_remaining = self.confirmation_wait - time_since_signal
            return True, f"Waiting for confirmation: {wait_remaining:.0f}s"
        
        return False, "Confirmation wait complete"
    
    def record_entry(self, entry_time: datetime, pattern_used: str):
        """Record when position was entered and what pattern was used"""
        self.last_entry_time = entry_time
        self.last_pattern_used = pattern_used
        logger.info(
            f"   ⏰ Entry recorded: {pattern_used} at "
            f"{entry_time.strftime('%H:%M:%S')}"
        )
    
    def record_signal(self, signal_time: datetime):
        """Record when signal was first detected"""
        self.last_signal_time = signal_time


# Global instances (initialized in trader.py)
_confidence_calculator: Optional[DynamicConfidenceCalculator] = None
_pattern_manager: Optional[PatternDiversityManager] = None
_spacing_manager: Optional[EntrySpacingManager] = None


def get_confidence_calculator() -> DynamicConfidenceCalculator:
    """Get global confidence calculator instance"""
    global _confidence_calculator
    if _confidence_calculator is None:
        _confidence_calculator = DynamicConfidenceCalculator()
    return _confidence_calculator


def get_pattern_manager() -> PatternDiversityManager:
    """Get global pattern diversity manager instance"""
    global _pattern_manager
    if _pattern_manager is None:
        _pattern_manager = PatternDiversityManager()
    return _pattern_manager


def get_spacing_manager() -> EntrySpacingManager:
    """Get global entry spacing manager instance"""
    global _spacing_manager
    if _spacing_manager is None:
        _spacing_manager = EntrySpacingManager()
    return _spacing_manager
