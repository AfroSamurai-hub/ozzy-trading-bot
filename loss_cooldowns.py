import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

COOLDOWN_FILE = Path("/home/rick/ozzy-bot/observer/loss_cooldowns.json")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _live_micro_cooldown_enabled() -> bool:
    return _env_bool("HERMES_LIVE_MICRO_LOSS_COOLDOWN_ENABLED", False)

def load_cooldowns() -> list[dict]:
    """Load active cooldowns from the durable JSON file, filtering out expired ones."""
    if not COOLDOWN_FILE.exists():
        return []
    
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOLDOWN_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            
            # Filter out expired cooldowns
            now = datetime.now(timezone.utc)
            active = []
            for item in data:
                expires_at_str = item.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str)
                        # Ensure timezone aware comparison
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        if expires_at > now:
                            active.append(item)
                    except Exception as e:
                        logger.error(f"Error parsing expires_at: {e}")
            return active
    except Exception as e:
        logger.error(f"Error loading cooldowns from {COOLDOWN_FILE}: {e}")
        return []

def save_cooldowns(cooldowns: list[dict]) -> None:
    """Save cooldowns to the durable JSON file safely."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOLDOWN_FILE, "w") as f:
            json.dump(cooldowns, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving cooldowns to {COOLDOWN_FILE}: {e}")

def register_cooldown(
    trade_id: int,
    symbol: str,
    direction: str,
    setup_grade: str,
    strategy: str,
    timeframe: str,
    pnl: float,
    is_live_micro: bool
) -> None:
    """Create a new cooldown record if the trade closed with a realized loss."""
    if pnl >= 0:
        return
    if is_live_micro and not _live_micro_cooldown_enabled():
        return
    
    now = datetime.now(timezone.utc)
    
    # Load durations from env/config
    live_hours = int(os.environ.get("LIVE_MICRO_LOSS_COOLDOWN_HOURS", "6"))
    testnet_hours = int(os.environ.get("TESTNET_LOSS_COOLDOWN_HOURS", "4"))
    
    hours = live_hours if is_live_micro else testnet_hours
    expires_at = now + timedelta(hours=hours)
    
    instance = "LIVE_MICRO" if is_live_micro else "STANDARD_TESTNET"
    
    cooldown = {
        "previous_trade_id": trade_id,
        "previous_symbol": symbol,
        "instance": instance,
        "symbol": symbol,
        "side": direction,
        "setup_grade": setup_grade,
        "strategy": strategy,
        "timeframe": timeframe,
        "realized_pnl": pnl,
        "closed_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "reason": f"Realized loss of {pnl:.2f} on {symbol} {direction} {strategy} ({instance})"
    }
    
    cooldowns = load_cooldowns()
    # Check if there is already a cooldown for this exact trade_id to avoid duplicates
    if any(item.get("previous_trade_id") == trade_id for item in cooldowns):
        return
        
    cooldowns.append(cooldown)
    save_cooldowns(cooldowns)
    
    # Requirement 8: Logs should include LOSS_COOLDOWN_CREATED
    from logger import plain_log
    plain_log("LOSS_COOLDOWN_CREATED", {
        "trade_id": trade_id,
        "symbol": symbol,
        "direction": direction,
        "instance": instance,
        "pnl": pnl,
        "expires_at": expires_at.isoformat()
    })

def check_cooldown(
    symbol: str,
    direction: str,
    setup_grade: str,
    strategy: str,
    timeframe: str,
    is_live_micro: bool
) -> dict | None:
    """Check if the incoming signal is blocked by any active cooldowns."""
    if is_live_micro and not _live_micro_cooldown_enabled():
        return None

    cooldowns = load_cooldowns()
    now = datetime.now(timezone.utc)
    
    for item in cooldowns:
        # Check expiry first
        expires_at_str = item.get("expires_at")
        if not expires_at_str:
            continue
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                continue
        except Exception:
            continue
            
        # Check matching instance
        item_is_live_micro = item.get("instance") == "LIVE_MICRO"
        if item_is_live_micro != is_live_micro:
            continue
            
        # LIVE_MICRO cooldown check: same symbol after ANY realized loss
        if is_live_micro:
            if item.get("symbol") == symbol:
                return item
                
        # TESTNET cooldown check: same symbol + same direction + same setup/profile
        else:
            if (
                item.get("symbol") == symbol and
                item.get("side") == direction and
                item.get("setup_grade") == setup_grade and
                item.get("strategy") == strategy
            ):
                return item
                
    return None
