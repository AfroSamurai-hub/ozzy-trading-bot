#!/usr/bin/env python3
"""
Trading Pattern Learning System

This module analyzes completed trades, extracts patterns, and updates 
the pattern database with performance data for overnight learning.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.rolling_window_db import RollingWindowPatternDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs/labeler.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("LearningSystem")

# Constants
DECISIONS_FILE = PROJECT_ROOT / "logs/decisions.json"
PORTFOLIO_STATE_FILE = PROJECT_ROOT / "logs/portfolio_state.json"
VECTOR_DB_PATH = str(PROJECT_ROOT / "data/vector_db")

class PatternLearner:
    """Analyzes trade outcomes and updates pattern database with learning data"""
    
    def __init__(self):
        """Initialize the pattern learner"""
        self.db = RollingWindowPatternDB(persist_directory=VECTOR_DB_PATH)
        self.unlabeled_patterns = set()
        self._load_unlabeled_patterns()
    
    def _load_unlabeled_patterns(self) -> None:
        """Load unlabeled patterns from the database"""
        try:
            # Get all patterns from the database
            data = self.db.collection.get(include=["metadatas"])
            
            # Find patterns that are unlabeled (pending)
            for i, metadata in enumerate(data.get("metadatas", [])):
                if metadata.get("label", "") == "PENDING":
                    pattern_id = data.get("ids", [])[i]
                    self.unlabeled_patterns.add(pattern_id)
            
            logger.info(f"Found {len(self.unlabeled_patterns)} unlabeled patterns")
        except Exception as e:
            logger.error(f"Failed to load unlabeled patterns: {e}")
    
    def load_decisions(self) -> Dict[str, Any]:
        """Load trading decisions from the log file"""
        try:
            if not DECISIONS_FILE.exists():
                return {"decisions": [], "portfolio": {}}
            with open(DECISIONS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Failed to load decisions: {e}")
            return {"decisions": [], "portfolio": {}}
    
    def load_portfolio_state(self) -> Dict[str, Any]:
        """Load portfolio state from file"""
        try:
            if not PORTFOLIO_STATE_FILE.exists():
                return {}
            with open(PORTFOLIO_STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Failed to load portfolio state: {e}")
            return {}
    
    def analyze_closed_trades(self) -> List[Dict]:
        """Analyze closed trades and extract learning data"""
        portfolio_state = self.load_portfolio_state()
        closed_trades = portfolio_state.get("closed_trades", [])
        
        if not closed_trades:
            # Try loading from decisions file as backup
            decisions_data = self.load_decisions()
            decisions = decisions_data.get("decisions", [])
            closed_trades = [d for d in decisions if d.get("status") == "CLOSED"]
        
        analyzed_trades = []
        
        for trade in closed_trades:
            # Skip trades we don't have enough data for
            if not trade.get("reason") or not trade.get("outcome"):
                continue
            
            # Extract pattern features from trade data
            pattern_features = self._extract_pattern_features(trade)
            if pattern_features:
                analyzed_trades.append(pattern_features)
        
        return analyzed_trades
    
    def _extract_pattern_features(self, trade: Dict) -> Optional[Dict]:
        """Extract pattern features from a closed trade"""
        try:
            # Extract key information
            symbol = trade.get("symbol")
            reason = trade.get("reason", "")
            outcome = trade.get("outcome")  # WIN or LOSS
            
            # Try to identify the pattern that led to this trade
            pattern_id = self._find_pattern_by_reason(reason)
            
            if not pattern_id:
                # If we can't find the pattern, create a new entry
                return {
                    "symbol": symbol,
                    "reason": reason,
                    "outcome": outcome,
                    "realized_pnl": trade.get("realized_pnl", 0.0),
                    "realized_pnl_pct": trade.get("realized_pnl_pct", 0.0),
                    "pattern_name": self._extract_pattern_name(reason)
                }
            else:
                # We found the pattern in the database
                result = {
                    "pattern_id": pattern_id,
                    "symbol": symbol,
                    "reason": reason,
                    "outcome": outcome,
                    "realized_pnl": trade.get("realized_pnl", 0.0),
                    "realized_pnl_pct": trade.get("realized_pnl_pct", 0.0),
                    "pattern_name": self._extract_pattern_name(reason)
                }
                
                # If the pattern is unlabeled, we'll label it
                if pattern_id in self.unlabeled_patterns:
                    result["needs_labeling"] = True
                
                return result
        except Exception as e:
            logger.error(f"Failed to extract pattern features: {e}")
            return None
    
    def _find_pattern_by_reason(self, reason: str) -> Optional[str]:
        """Find a pattern ID based on the trade reason"""
        # In a real implementation, this would do a more sophisticated
        # search through the vector database to find the pattern
        return None
    
    def _extract_pattern_name(self, reason: str) -> str:
        """Extract pattern name from the trade reason"""
        reason_lower = reason.lower()
        
        if "whale accumulation" in reason_lower:
            return "Whale Accumulation"
        elif "bullish divergence" in reason_lower:
            return "Bullish Divergence"
        elif "resistance break" in reason_lower:
            return "Resistance Breakout"
        elif "support bounce" in reason_lower:
            return "Support Bounce"
        elif "volume spike" in reason_lower:
            return "Volume Spike"
        elif "ma cross" in reason_lower or "moving average cross" in reason_lower:
            return "MA Crossover"
        elif "rsi" in reason_lower and "oversold" in reason_lower:
            return "RSI Oversold"
        elif "rsi" in reason_lower and "overbought" in reason_lower:
            return "RSI Overbought"
        else:
            return "Generic Pattern"
    
    def label_patterns(self, analyzed_trades: List[Dict]) -> int:
        """Update pattern labels based on trade outcomes"""
        labeled_count = 0
        
        for trade in analyzed_trades:
            if not trade.get("needs_labeling"):
                continue
            
            pattern_id = trade.get("pattern_id")
            outcome = trade.get("outcome")
            
            if pattern_id and outcome:
                success = self.db.update_pattern_label(pattern_id, outcome)
                if success:
                    labeled_count += 1
                    self.unlabeled_patterns.remove(pattern_id)
        
        return labeled_count
    
    def update_pattern_statistics(self) -> None:
        """Update overall pattern statistics"""
        # This would aggregate performance by pattern type
        # and update metadata in the database for better decision making
        pass
    
    def run_learning_cycle(self) -> Dict[str, Any]:
        """Run a complete learning cycle"""
        start_time = time.time()
        
        # Analyze closed trades
        analyzed_trades = self.analyze_closed_trades()
        logger.info(f"Analyzed {len(analyzed_trades)} closed trades")
        
        # Label patterns
        labeled_count = self.label_patterns(analyzed_trades)
        logger.info(f"Labeled {labeled_count} patterns")
        
        # Update pattern statistics
        self.update_pattern_statistics()
        
        # Return results
        return {
            "analyzed_trades": len(analyzed_trades),
            "labeled_patterns": labeled_count,
            "unlabeled_remaining": len(self.unlabeled_patterns),
            "runtime_seconds": time.time() - start_time,
        }


def main():
    """Main function to run the learning system"""
    parser = argparse.ArgumentParser(description="Trading Pattern Learning System")
    parser.add_argument("--continuous", action="store_true", help="Run continuously at intervals")
    parser.add_argument("--interval", type=int, default=3600, help="Interval in seconds for continuous mode (default: 3600)")
    args = parser.parse_args()
    
    logger.info("Starting Trading Pattern Learning System")
    learner = PatternLearner()
    
    if args.continuous:
        logger.info(f"Running in continuous mode with {args.interval}s interval")
        
        try:
            while True:
                results = learner.run_learning_cycle()
                logger.info(f"Learning cycle complete: {results}")
                logger.info(f"Next cycle in {args.interval} seconds")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Learning system stopped by user")
    else:
        # Run once
        results = learner.run_learning_cycle()
        logger.info(f"Learning cycle complete: {results}")


if __name__ == "__main__":
    main()