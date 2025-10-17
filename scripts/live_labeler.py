#!/usr/bin/env python3
"""Live pattern labeler for Ozzy Simple.

This script monitors the decision log and updates the pattern database
with actual outcomes, creating a self-learning system.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.rolling_window_db import RollingWindowPatternDB

# Constants
DECISIONS_LOG_FILE = PROJECT_ROOT / "logs/decisions.json"
# How long to wait before labeling a trade (in seconds)
LABELING_DELAY = 300  # 5 minutes
# Profit target percentage for a WIN label
PROFIT_TARGET = 0.01  # 1%
# Stop loss percentage for a LOSS label
STOP_LOSS = -0.01  # -1%

logger = logging.getLogger(__name__)

async def monitor_and_label(pattern_db: RollingWindowPatternDB, interval_seconds: int = 10) -> None:
    """
    Monitor the decisions log and update pattern labels based on outcomes.
    
    Args:
        pattern_db: The pattern database to update
        interval_seconds: How often to check for updates (in seconds)
    """
    logger.info("🏷️ Starting live pattern labeler...")
    
    last_check = time.time()
    
    while True:
        try:
            # Wait for the next check interval
            await asyncio.sleep(interval_seconds)
            
            # Load decisions
            decisions = load_decisions()
            
            # Find unlabeled patterns that need updates
            updated_count = await update_pattern_labels(pattern_db, decisions)
            
            if updated_count > 0:
                logger.info(f"🏷️ Updated {updated_count} pattern labels")
            
            # Update last check time
            last_check = time.time()
            
        except Exception as e:
            logger.error(f"❌ Error in pattern labeler: {e}")
            await asyncio.sleep(5)  # Wait before retrying after an error

def load_decisions() -> Dict[str, Any]:
    """Load trading decisions from the log file."""
    try:
        if not DECISIONS_LOG_FILE.exists():
            return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}
        
        with open(DECISIONS_LOG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}

async def update_pattern_labels(
    pattern_db: RollingWindowPatternDB, 
    data: Dict[str, Any]
) -> int:
    """
    Update pattern labels based on trading outcomes.
    
    Args:
        pattern_db: The pattern database to update
        data: The decisions data from the log file
        
    Returns:
        int: Number of patterns updated
    """
    decisions = data.get("decisions", [])
    update_count = 0
    
    current_time = time.time()
    
    for decision in decisions:
        # Skip decisions that don't need labeling
        if decision.get("outcome") is not None:
            continue
        
        # Get decision timestamp
        timestamp_str = decision.get("timestamp")
        if not timestamp_str:
            continue
            
        try:
            # Convert ISO timestamp to unix time
            decision_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            continue
        
        # Skip if not enough time has passed for labeling
        if current_time - decision_time < LABELING_DELAY:
            continue
        
        # Get pattern ID from metadata
        pattern_id = f"{decision.get('symbol')}_{int(decision_time * 1000)}"
        
        # Try to find the pattern in the database
        pattern = pattern_db.get_pattern_by_id(pattern_id)
        if not pattern:
            continue
        
        # Calculate profit/loss
        entry_price = decision.get("entry_price")
        current_price = decision.get("current_price", entry_price)
        
        if not entry_price or not current_price:
            continue
            
        price_change = (current_price - entry_price) / entry_price
        
        # Determine outcome based on price change
        outcome = None
        if price_change >= PROFIT_TARGET:
            outcome = "WIN"
        elif price_change <= STOP_LOSS:
            outcome = "LOSS"
        else:
            outcome = "NEUTRAL"
        
        # Update pattern label in database
        pattern_db.update_pattern_label(pattern_id, outcome)
        
        # Update the decision log with the outcome
        decision["outcome"] = outcome
        decision["current_price"] = current_price
        decision["current_pnl"] = (current_price - entry_price) * decision.get("position_size", 0)
        decision["current_pnl_pct"] = price_change * 100
        
        update_count += 1
    
    # If any updates were made, save the decision log
    if update_count > 0:
        with open(DECISIONS_LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    return update_count

async def main() -> None:
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Initialize the pattern database
    pattern_db = RollingWindowPatternDB()
    
    # Load patterns from CSV if it exists
    historical_csv = PROJECT_ROOT / "data/historical/BTCUSDT_5m_bootstrap.csv"
    if historical_csv.exists():
        try:
            logger.info(f"📥 Loading bootstrap patterns from {historical_csv}...")
            loaded = pattern_db.load_from_csv(str(historical_csv), clear_existing=False, apply_pruning=False)
            logger.info(f"   → Loaded {loaded} patterns (DB total: {pattern_db.count()})")
        except Exception as e:
            logger.error(f"❌ Failed to load bootstrap patterns: {e}")
    
    # Start the labeler
    await monitor_and_label(pattern_db)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Pattern labeler stopped by user")
    except Exception as e:
        logger.error(f"Pattern labeler failed: {e}")
        sys.exit(1)