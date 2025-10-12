"""
TIME FILTER WRAPPER
Wraps signal generation to implement A/B testing for time-of-day filters

Usage in main.py:
    from time_filter_wrapper import TimeFilterWrapper
    
    # Initialize wrapper
    time_filter = TimeFilterWrapper(
        test_name="time_filter_night",
        avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC
        enabled=True  # Set to False to disable test
    )
    
    # In check_signal():
    signal = self.signal_generator.generate_signal(candles)
    
    # Apply time filter
    signal, test_group = time_filter.apply_filter(signal, symbol)
    
    # When logging trade, include test group in entry_reason:
    entry_reason = f"TEST_{test_name}_{test_group}_{original_reason}"
"""

import random
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from loguru import logger


class TimeFilterWrapper:
    """Wrapper for implementing time-of-day filter A/B tests"""
    
    def __init__(self,
                 test_name: str = "time_filter_night",
                 avoid_hours: List[Tuple[int, int]] = None,
                 enabled: bool = True):
        """
        Initialize time filter wrapper
        
        Args:
            test_name: Name for this test (used in database tags)
            avoid_hours: List of (start_hour, end_hour) tuples to avoid
            enabled: Whether test is active (False = all control group)
        """
        self.test_name = test_name
        self.avoid_hours = avoid_hours or [(22, 2)]
        self.enabled = enabled
        
        logger.info(f"TimeFilterWrapper initialized: test={test_name}, "
                   f"avoid_hours={avoid_hours}, enabled={enabled}")
    
    def is_in_avoid_window(self, hour: int) -> bool:
        """Check if hour is in any avoid window"""
        for start, end in self.avoid_hours:
            if start < end:
                # Normal range (e.g., 10-14)
                if start <= hour < end:
                    return True
            else:
                # Wraps midnight (e.g., 22-2)
                if hour >= start or hour < end:
                    return True
        return False
    
    def assign_test_group(self) -> str:
        """Randomly assign to control or test group (50/50)"""
        if not self.enabled:
            return "control"
        return random.choice(["control", "test"])
    
    def apply_filter(self, signal: Dict, symbol: str) -> Tuple[Dict, str]:
        """
        Apply time filter to signal based on random group assignment
        
        Args:
            signal: Signal dictionary from signal generator
            symbol: Trading symbol
            
        Returns:
            (modified_signal, test_group)
        """
        # Assign test group
        test_group = self.assign_test_group()
        
        # If control group, return signal unchanged
        if test_group == "control":
            logger.debug(f"{symbol}: Control group - no time filter applied")
            return signal, test_group
        
        # Test group: check time
        current_hour = datetime.now(timezone.utc).hour
        
        if self.is_in_avoid_window(current_hour):
            # In avoid window - convert signal to HOLD
            logger.info(f"{symbol}: Test group - skipping signal (hour {current_hour} "
                       f"in avoid window {self.avoid_hours})")
            
            # Create HOLD signal
            filtered_signal = {
                "signal": "HOLD",
                "confidence": 0,
                "quality": "FILTERED",
                "reason": f"Time filter: avoiding hour {current_hour:02d}:00 UTC " +
                         f"(avoid windows: {self.avoid_hours})",
                "rsi": signal.get("rsi", 0),
                "ema_trend": signal.get("ema_trend", "NEUTRAL"),
                "volume_confirmed": False,
                "original_signal": signal["signal"],  # Keep original for logging
                "original_confidence": signal["confidence"]
            }
            
            return filtered_signal, test_group
        else:
            # Outside avoid window - allow trade
            logger.debug(f"{symbol}: Test group - hour {current_hour} OK, allowing trade")
            return signal, test_group
    
    def format_entry_reason(self, base_reason: str, test_group: str) -> str:
        """
        Format entry reason to include test group tag
        
        Args:
            base_reason: Original entry reason
            test_group: "control" or "test"
            
        Returns:
            Tagged entry reason for database
        """
        if not self.enabled:
            return base_reason
        
        # Format: TEST_time_filter_night_control_rsi_oversold
        return f"TEST_{self.test_name}_{test_group}_{base_reason}"


# Convenience function for easy integration
def create_time_filter(enabled: bool = False) -> Optional[TimeFilterWrapper]:
    """
    Create time filter wrapper with default settings
    
    Args:
        enabled: Whether to enable the test
        
    Returns:
        TimeFilterWrapper instance or None if disabled
    """
    if not enabled:
        return None
    
    return TimeFilterWrapper(
        test_name="time_filter_night",
        avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC (low volatility)
        enabled=True
    )
