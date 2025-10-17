"""
Utility functions for safe type conversions
"""
import logging

logger = logging.getLogger(__name__)

def safe_float(value, default=0.0):
    """
    Safely convert value to float
    
    Args:
        value: Value to convert (can be None, str, int, float)
        default: Default value if conversion fails (default: 0.0)
    
    Returns:
        float: Converted value or default
    """
    if value is None:
        return default
    
    try:
        return float(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not convert {value} to float: {e}")
        return default

def safe_int(value, default=0):
    """
    Safely convert value to int
    
    Args:
        value: Value to convert
        default: Default value if conversion fails (default: 0)
    
    Returns:
        int: Converted value or default
    """
    if value is None:
        return default
    
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not convert {value} to int: {e}")
        return default
