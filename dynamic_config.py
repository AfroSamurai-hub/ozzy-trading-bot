"""Dynamic configuration manager with in-memory caching, hot-reloading, and fail-open fallbacks."""

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache parameters
_CACHE = {}
_LAST_LOADED_TIME = 0.0
_LAST_MTIME = 0.0
_CHECK_COOLDOWN_SEC = 5.0  # Avoid disk I/O on high-frequency signals, check at most every 5s

def get_config_path() -> Path:
    """Return the active dynamic config path from environment.

    The unified instance sets HERMES_DYNAMIC_CONFIG explicitly. If it is missing,
    fall back to the single dynamic_config.json rather than guessing mode from DB path.
    """
    config_path_str = os.environ.get("HERMES_DYNAMIC_CONFIG")
    if config_path_str:
        return Path(config_path_str)

    return Path(__file__).parent / "config" / "dynamic_config.json"

def _load_config_file() -> dict:
    """Read the JSON configuration file from disk safely."""
    path = get_config_path()
    if not path.exists():
        logger.warning(f"Dynamic config file does not exist at {path}. Using default fallbacks.")
        return {}
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.error(f"Dynamic config file at {path} is not a JSON object. Using defaults.")
                return {}
            return data
    except Exception as e:
        logger.error(f"Failed to load dynamic config from {path}: {e}. Using default fallbacks.")
        return {}

def reload_if_needed() -> None:
    """Reload config file into memory if it was modified on disk and cooldown expired."""
    global _CACHE, _LAST_LOADED_TIME, _LAST_MTIME
    
    now = time.monotonic()
    if now - _LAST_LOADED_TIME < _CHECK_COOLDOWN_SEC:
        return
        
    path = get_config_path()
    if not path.exists():
        _CACHE = {}
        _LAST_LOADED_TIME = now
        _LAST_MTIME = 0.0
        return
        
    try:
        mtime = os.path.getmtime(path)
        if mtime != _LAST_MTIME:
            logger.info(f"Dynamic config file changed at {path}. Reloading...")
            _CACHE = _load_config_file()
            _LAST_MTIME = mtime
    except Exception as e:
        logger.error(f"Error checking modification time for dynamic config at {path}: {e}")
        
    _LAST_LOADED_TIME = now

def get_param(key: str, default_val: any) -> any:
    """Get a parameter from dynamic config cache with a fail-safe fallback."""
    try:
        reload_if_needed()
    except Exception as e:
        logger.error(f"Failed to check for dynamic config reload: {e}")
        
    val = _CACHE.get(key)
    if val is None:
        return default_val
        
    # Strictly preserve default's type if possible
    if default_val is not None:
        try:
            expected_type = type(default_val)
            if expected_type == float:
                return float(val)
            elif expected_type == int:
                return int(val)
            elif expected_type == bool:
                if isinstance(val, str):
                    return val.lower() in ("true", "1", "yes")
                return bool(val)
            elif expected_type == str:
                return str(val)
        except (ValueError, TypeError) as e:
            logger.error(f"Type conversion failed for dynamic param '{key}' (val: {val}) to type {type(default_val)}: {e}. Falling back to default.")
            return default_val

    return val


def get_symbol_param(symbol: str, key: str, default_val: any) -> any:
    """Return a per-symbol dynamic parameter, falling back to the top-level value."""
    try:
        reload_if_needed()
    except Exception as e:
        logger.error(f"Failed to check for dynamic config reload: {e}")

    per_symbol = _CACHE.get("per_symbol")
    if isinstance(per_symbol, dict):
        symbol_config = per_symbol.get(symbol.upper())
        if isinstance(symbol_config, dict) and symbol_config.get(key) is not None:
            val = symbol_config.get(key)
            if default_val is not None:
                try:
                    expected_type = type(default_val)
                    if expected_type == float:
                        return float(val)
                    elif expected_type == int:
                        return int(val)
                    elif expected_type == bool:
                        if isinstance(val, str):
                            return val.lower() in ("true", "1", "yes")
                        return bool(val)
                    elif expected_type == str:
                        return str(val)
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"Type conversion failed for dynamic symbol param '{symbol}.{key}' "
                        f"(val: {val}) to type {type(default_val)}: {e}. Falling back."
                    )
            return val

    return get_param(key, default_val)
