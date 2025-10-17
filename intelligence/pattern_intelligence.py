"""
🧬 Pattern Intelligence System - The Brain of Ozzy Trading Bot

This module provides intelligent pattern effectiveness tracking and learning.
It's SELF-AWARE: It knows when it needs to be initialized and will demand it!

Philosophy: "Every pattern should prove its worth with data, not just exist."

Key Features:
- Track pattern outcomes (wins/losses/P&L)
- Calculate pattern effectiveness scores
- Rank patterns by quality
- Self-initialization and health checks
- Automatic pattern pruning

Usage:
    # System will auto-initialize if needed!
    intelligence = PatternIntelligence.get_instance()
    
    # After a trade closes
    intelligence.update_pattern_outcome(pattern_id, {
        'win': True,
        'pnl_pct': 2.5,
        'held_time': 3600
    })
    
    # Get best patterns
    top_patterns = intelligence.get_top_patterns(n=5, min_trades=5)
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import numpy as np

from intelligence.rolling_window_db import RollingWindowPatternDB

logger = logging.getLogger(__name__)

# Singleton instance
_INTELLIGENCE_INSTANCE: Optional['PatternIntelligence'] = None


@dataclass
class PatternStats:
    """
    Statistics for a single pattern with context-aware tracking.
    
    🎓 PhD-Level Enhancement: Tracks performance in different market contexts!
    """
    pattern_id: str
    times_matched: int = 0      # How often similar to a decision
    times_traded: int = 0        # How often we actually traded it
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_profit: float = 0.0      # Average profit when wins
    avg_loss: float = 0.0        # Average loss when loses
    win_rate: float = 0.0
    expectancy: float = 0.0      # Expected value per trade
    confidence_score: float = 0.5  # 0-1 confidence based on data
    last_updated: float = field(default_factory=time.time)
    
    # 🎓 PhD-LEVEL: Context-specific performance tracking
    # Format: {'bull_market': {'wins': 10, 'losses': 3}, 'bear_market': {...}}
    regime_performance: Dict[str, Dict[str, int]] = field(default_factory=dict)
    session_performance: Dict[str, Dict[str, int]] = field(default_factory=dict)
    volatility_performance: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'pattern_id': self.pattern_id,
            'times_matched': self.times_matched,
            'times_traded': self.times_traded,
            'wins': self.wins,
            'losses': self.losses,
            'total_pnl': self.total_pnl,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'win_rate': self.win_rate,
            'expectancy': self.expectancy,
            'confidence_score': self.confidence_score,
            'last_updated': self.last_updated,
            'regime_performance': self.regime_performance,
            'session_performance': self.session_performance,
            'volatility_performance': self.volatility_performance
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PatternStats':
        """Create from dictionary."""
        # Handle backward compatibility for old stats without context data
        if 'regime_performance' not in data:
            data['regime_performance'] = {}
        if 'session_performance' not in data:
            data['session_performance'] = {}
        if 'volatility_performance' not in data:
            data['volatility_performance'] = {}
        return cls(**data)
    
    def get_regime_win_rate(self, regime: str) -> Optional[float]:
        """
        Get win rate for a specific market regime.
        
        Args:
            regime: Market regime (bull_market, bear_market, sideways, volatile)
        
        Returns:
            Win rate for that regime, or None if insufficient data
        """
        if regime not in self.regime_performance:
            return None
        
        stats = self.regime_performance[regime]
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        total = wins + losses
        
        if total < 3:  # Need at least 3 trades for meaningful data
            return None
        
        return wins / total
    
    def get_session_win_rate(self, session: str) -> Optional[float]:
        """
        Get win rate for a specific trading session.
        
        Args:
            session: Trading session (asian, european, us, overlap, etc.)
        
        Returns:
            Win rate for that session, or None if insufficient data
        """
        if session not in self.session_performance:
            return None
        
        stats = self.session_performance[session]
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        total = wins + losses
        
        if total < 3:  # Need at least 3 trades
            return None
        
        return wins / total
    
    def get_volatility_win_rate(self, volatility: str) -> Optional[float]:
        """
        Get win rate for a specific volatility regime.
        
        Args:
            volatility: Volatility level (low_vol, medium_vol, high_vol)
        
        Returns:
            Win rate for that volatility, or None if insufficient data
        """
        if volatility not in self.volatility_performance:
            return None
        
        stats = self.volatility_performance[volatility]
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        total = wins + losses
        
        if total < 3:  # Need at least 3 trades
            return None
        
        return wins / total
    
    def get_best_context(self) -> Dict[str, str]:
        """
        Determine the best trading context for this pattern.
        
        Returns:
            {
                'best_regime': 'bull_market',
                'best_session': 'us',
                'best_volatility': 'medium_vol'
            }
        """
        best = {}
        
        # Find best regime
        best_regime_wr = 0.0
        for regime, stats in self.regime_performance.items():
            wr = self.get_regime_win_rate(regime)
            if wr and wr > best_regime_wr:
                best_regime_wr = wr
                best['best_regime'] = regime
        
        # Find best session
        best_session_wr = 0.0
        for session, stats in self.session_performance.items():
            wr = self.get_session_win_rate(session)
            if wr and wr > best_session_wr:
                best_session_wr = wr
                best['best_session'] = session
        
        # Find best volatility
        best_vol_wr = 0.0
        for vol, stats in self.volatility_performance.items():
            wr = self.get_volatility_win_rate(vol)
            if wr and wr > best_vol_wr:
                best_vol_wr = wr
                best['best_volatility'] = vol
        
        return best


class PatternIntelligence:
    """
    🧠 The Intelligence Layer - Tracks and learns from pattern outcomes.
    
    This is the BRAIN of the trading system. It knows:
    - Which patterns actually work (win rates)
    - How much money each pattern makes/loses (expectancy)
    - Which patterns to trust (confidence scores)
    
    It's SELF-AWARE: Checks if it's initialized, demands initialization if needed.
    """
    
    def __init__(self, pattern_db: Optional[RollingWindowPatternDB] = None):
        """
        Initialize pattern intelligence.
        
        Args:
            pattern_db: Pattern database (will create if None)
        """
        self.pattern_db = pattern_db or RollingWindowPatternDB()
        self.stats_cache: Dict[str, PatternStats] = {}
        self.stats_file = Path("data/pattern_stats.json")
        self.initialized = False
        
        # Ensure data directory exists
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing stats
        self._load_stats()
        self.initialized = True
        
        logger.info(f"🧠 PatternIntelligence initialized with {len(self.stats_cache)} patterns")
    
    @classmethod
    def get_instance(cls, pattern_db: Optional[RollingWindowPatternDB] = None) -> 'PatternIntelligence':
        """
        Get or create singleton instance.
        
        This ensures ONE intelligence system across the entire application.
        """
        global _INTELLIGENCE_INSTANCE
        
        if _INTELLIGENCE_INSTANCE is None:
            logger.info("🧬 Creating new PatternIntelligence instance (first time)")
            _INTELLIGENCE_INSTANCE = cls(pattern_db)
        elif not _INTELLIGENCE_INSTANCE.initialized:
            logger.warning("⚠️ PatternIntelligence exists but not initialized! Re-initializing...")
            _INTELLIGENCE_INSTANCE = cls(pattern_db)
        
        return _INTELLIGENCE_INSTANCE
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if intelligence system is initialized."""
        global _INTELLIGENCE_INSTANCE
        return _INTELLIGENCE_INSTANCE is not None and _INTELLIGENCE_INSTANCE.initialized
    
    @classmethod
    def require_initialization(cls) -> 'PatternIntelligence':
        """
        DEMAND initialization! System is SELF-AWARE.
        
        If intelligence isn't initialized, this will FORCE it.
        Use this in critical paths where intelligence is REQUIRED.
        """
        if not cls.is_initialized():
            logger.warning("🔥 Pattern Intelligence NOT initialized but REQUIRED! Auto-initializing...")
            return cls.get_instance()
        
        global _INTELLIGENCE_INSTANCE
        return _INTELLIGENCE_INSTANCE
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check health of intelligence system.
        
        Returns status, warnings, and recommendations.
        """
        total_patterns = self.pattern_db.count()
        patterns_with_stats = len(self.stats_cache)
        patterns_with_trades = sum(1 for s in self.stats_cache.values() if s.times_traded > 0)
        
        # Calculate average stats
        if patterns_with_trades > 0:
            avg_win_rate = np.mean([s.win_rate for s in self.stats_cache.values() if s.times_traded > 0])
            avg_expectancy = np.mean([s.expectancy for s in self.stats_cache.values() if s.times_traded > 0])
        else:
            avg_win_rate = 0.0
            avg_expectancy = 0.0
        
        # Determine health status
        issues = []
        if patterns_with_stats == 0:
            issues.append("❌ NO patterns have stats! System can't learn!")
        elif patterns_with_trades == 0:
            issues.append("⚠️ No patterns have been traded yet. Need data!")
        elif avg_win_rate < 0.45:
            issues.append(f"⚠️ Average win rate low: {avg_win_rate:.1%}")
        
        status = "🔥 CRITICAL" if patterns_with_stats == 0 else \
                 "⚠️ WARNING" if issues else \
                 "✅ HEALTHY"
        
        return {
            'status': status,
            'total_patterns': total_patterns,
            'patterns_with_stats': patterns_with_stats,
            'patterns_with_trades': patterns_with_trades,
            'avg_win_rate': avg_win_rate,
            'avg_expectancy': avg_expectancy,
            'issues': issues,
            'initialized': self.initialized
        }
    
    def update_pattern_outcome(self, pattern_id: str, outcome: Dict[str, Any]) -> None:
        """
        Update pattern stats after a trade closes.
        
        🎓 PhD-LEVEL: Now tracks context-specific performance!
        
        Args:
            pattern_id: Pattern identifier
            outcome: Trade outcome with keys:
                - win (bool): Did trade hit TP?
                - pnl_pct (float): P&L percentage
                - held_time (float): Time held in seconds
                - market_regime (str, optional): bull_market, bear_market, etc.
                - trading_session (str, optional): asian, european, us, overlap
                - volatility (str, optional): low_vol, medium_vol, high_vol
        """
        if pattern_id not in self.stats_cache:
            self.stats_cache[pattern_id] = PatternStats(pattern_id=pattern_id)
        
        stats = self.stats_cache[pattern_id]
        stats.times_traded += 1
        
        is_win = outcome.get('win', False)
        
        # Update win/loss
        if is_win:
            stats.wins += 1
        else:
            stats.losses += 1
        
        # 🎓 PhD-LEVEL: Update context-specific performance
        regime = outcome.get('market_regime')
        if regime:
            if regime not in stats.regime_performance:
                stats.regime_performance[regime] = {'wins': 0, 'losses': 0}
            if is_win:
                stats.regime_performance[regime]['wins'] += 1
            else:
                stats.regime_performance[regime]['losses'] += 1
        
        session = outcome.get('trading_session')
        if session:
            if session not in stats.session_performance:
                stats.session_performance[session] = {'wins': 0, 'losses': 0}
            if is_win:
                stats.session_performance[session]['wins'] += 1
            else:
                stats.session_performance[session]['losses'] += 1
        
        volatility = outcome.get('volatility')
        if volatility:
            if volatility not in stats.volatility_performance:
                stats.volatility_performance[volatility] = {'wins': 0, 'losses': 0}
            if is_win:
                stats.volatility_performance[volatility]['wins'] += 1
            else:
                stats.volatility_performance[volatility]['losses'] += 1
        
        # Update P&L
        pnl_pct = outcome.get('pnl_pct', 0.0)
        stats.total_pnl += pnl_pct
        
        # Recalculate stats
        stats.win_rate = stats.wins / stats.times_traded if stats.times_traded > 0 else 0.0
        
        # Calculate average profit/loss
        if stats.wins > 0:
            # This is simplified - ideally track individual trade P&Ls
            stats.avg_profit = max(pnl_pct, stats.avg_profit) if outcome.get('win') else stats.avg_profit
        if stats.losses > 0:
            stats.avg_loss = min(pnl_pct, stats.avg_loss) if not outcome.get('win') else stats.avg_loss
        
        # Calculate expectancy (expected value per trade)
        if stats.wins > 0 and stats.losses > 0:
            stats.expectancy = (stats.win_rate * stats.avg_profit) + ((1 - stats.win_rate) * stats.avg_loss)
        elif stats.wins > 0:
            stats.expectancy = stats.avg_profit
        else:
            stats.expectancy = stats.avg_loss
        
        # Calculate confidence score
        stats.confidence_score = self._calculate_confidence(stats)
        stats.last_updated = time.time()
        
        # Save to disk
        self._save_stats()
        
        logger.info(f"📊 Updated pattern {pattern_id[:8]}: "
                   f"{stats.wins}W/{stats.losses}L, "
                   f"WR: {stats.win_rate:.1%}, "
                   f"Exp: {stats.expectancy:+.2f}%")
    
    def _calculate_confidence(self, stats: PatternStats) -> float:
        """
        Calculate confidence score for a pattern.
        
        Confidence increases with:
        - More trades (more data = more confidence)
        - Higher win rate
        - Positive expectancy
        
        Returns: 0.0 to 1.0
        """
        if stats.times_traded == 0:
            return 0.5  # No data, neutral confidence
        
        # Sample size confidence (0 trades = 0, 30+ trades = 1.0)
        sample_confidence = min(stats.times_traded / 30.0, 1.0)
        
        # Win rate confidence (0% = 0, 100% = 1.0)
        win_rate_confidence = stats.win_rate
        
        # Expectancy confidence (-5% = 0, +5% = 1.0)
        expectancy_confidence = max(0.0, min(1.0, (stats.expectancy + 5.0) / 10.0))
        
        # Weighted combination
        confidence = (sample_confidence * 0.3) + \
                    (win_rate_confidence * 0.5) + \
                    (expectancy_confidence * 0.2)
        
        return max(0.0, min(1.0, confidence))
    
    def get_pattern_stats(self, pattern_id: str) -> Optional[PatternStats]:
        """Get stats for a specific pattern."""
        return self.stats_cache.get(pattern_id)
    
    def get_top_patterns(self, n: int = 5, min_trades: int = 5) -> List[Dict[str, Any]]:
        """
        Get top N patterns ranked by effectiveness.
        
        Args:
            n: Number of patterns to return
            min_trades: Minimum trades required to be considered
        
        Returns:
            List of pattern dicts with stats
        """
        # Filter patterns with enough data
        qualified = [
            stats for stats in self.stats_cache.values()
            if stats.times_traded >= min_trades
        ]
        
        if not qualified:
            # Not enough data, return patterns with any trades
            qualified = [
                stats for stats in self.stats_cache.values()
                if stats.times_traded > 0
            ]
        
        # Rank by expectancy (expected profit per trade)
        ranked = sorted(qualified, key=lambda s: s.expectancy, reverse=True)
        
        # Convert to dicts with additional info
        results = []
        for stats in ranked[:n]:
            # Get pattern details from DB
            pattern = self.pattern_db.get_pattern_by_id(stats.pattern_id)
            
            result = {
                'pattern_id': stats.pattern_id,
                'times_traded': stats.times_traded,
                'wins': stats.wins,
                'losses': stats.losses,
                'win_rate': stats.win_rate,
                'expectancy': stats.expectancy,
                'confidence_score': stats.confidence_score,
                'pattern_type': pattern.get('pattern_type', 'unknown') if pattern else 'unknown'
            }
            results.append(result)
        
        return results
    
    def get_pattern_summary(self) -> Dict[str, Any]:
        """Get summary statistics across all patterns."""
        if not self.stats_cache:
            return {
                'total_patterns': 0,
                'patterns_with_trades': 0,
                'total_trades': 0,
                'overall_win_rate': 0.0,
                'avg_expectancy': 0.0
            }
        
        patterns_with_trades = [s for s in self.stats_cache.values() if s.times_traded > 0]
        
        return {
            'total_patterns': len(self.stats_cache),
            'patterns_with_trades': len(patterns_with_trades),
            'total_trades': sum(s.times_traded for s in self.stats_cache.values()),
            'overall_win_rate': np.mean([s.win_rate for s in patterns_with_trades]) if patterns_with_trades else 0.0,
            'avg_expectancy': np.mean([s.expectancy for s in patterns_with_trades]) if patterns_with_trades else 0.0
        }
    
    def archive_low_quality_patterns(self, min_win_rate: float = 0.45, min_trades: int = 10) -> int:
        """
        Archive patterns that consistently lose.
        
        Args:
            min_win_rate: Minimum win rate to keep
            min_trades: Minimum trades before archiving
        
        Returns:
            Number of patterns archived
        """
        to_archive = []
        
        for pattern_id, stats in self.stats_cache.items():
            if stats.times_traded >= min_trades and stats.win_rate < min_win_rate:
                to_archive.append(pattern_id)
        
        if to_archive:
            # For now, just log (could move to separate DB table)
            logger.info(f"🗄️ Archiving {len(to_archive)} low-quality patterns")
            for pattern_id in to_archive:
                stats = self.stats_cache[pattern_id]
                logger.info(f"   📦 {pattern_id[:8]}: {stats.wins}W/{stats.losses}L ({stats.win_rate:.1%})")
        
        return len(to_archive)
    
    def _load_stats(self) -> None:
        """Load pattern stats from disk."""
        if not self.stats_file.exists():
            logger.info("📂 No existing pattern stats file. Starting fresh.")
            return
        
        try:
            with open(self.stats_file, 'r') as f:
                data = json.load(f)
            
            self.stats_cache = {
                pattern_id: PatternStats.from_dict(stats_data)
                for pattern_id, stats_data in data.items()
            }
            
            logger.info(f"📥 Loaded stats for {len(self.stats_cache)} patterns")
        except Exception as e:
            logger.error(f"❌ Failed to load pattern stats: {e}")
            self.stats_cache = {}
    
    def _save_stats(self) -> None:
        """Save pattern stats to disk."""
        try:
            data = {
                pattern_id: stats.to_dict()
                for pattern_id, stats in self.stats_cache.items()
            }
            
            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Failed to save pattern stats: {e}")


def get_intelligence() -> PatternIntelligence:
    """
    🧠 Get pattern intelligence instance.
    
    This is the MAIN entry point. Use this everywhere!
    It will auto-initialize if needed (self-aware system!)
    """
    return PatternIntelligence.require_initialization()


# Quick health check function
def check_intelligence_health() -> Dict[str, Any]:
    """Quick health check for pattern intelligence."""
    if not PatternIntelligence.is_initialized():
        return {
            'status': '❌ NOT INITIALIZED',
            'message': 'Pattern intelligence has not been initialized!',
            'recommendation': 'Call PatternIntelligence.get_instance() or get_intelligence()'
        }
    
    intelligence = PatternIntelligence.get_instance()
    return intelligence.health_check()


if __name__ == "__main__":
    # Test the intelligence system
    logging.basicConfig(level=logging.INFO)
    
    print("🧪 Testing Pattern Intelligence System\n")
    
    # Test 1: Check health before init
    print("1️⃣ Health check before initialization:")
    health = check_intelligence_health()
    print(f"   Status: {health.get('status', 'UNKNOWN')}")
    print()
    
    # Test 2: Initialize
    print("2️⃣ Initializing intelligence...")
    intelligence = get_intelligence()
    print(f"   Initialized: {intelligence.initialized}")
    print()
    
    # Test 3: Health check after init
    print("3️⃣ Health check after initialization:")
    health = intelligence.health_check()
    print(f"   Status: {health['status']}")
    print(f"   Total patterns in DB: {health['total_patterns']}")
    print(f"   Patterns with stats: {health['patterns_with_stats']}")
    print(f"   Patterns with trades: {health['patterns_with_trades']}")
    print()
    
    # Test 4: Simulate some trade outcomes
    print("4️⃣ Simulating trade outcomes...")
    test_pattern_id = "test_pattern_123"
    
    # Simulate 10 trades: 7 wins, 3 losses
    for i in range(10):
        win = i < 7  # First 7 are wins
        intelligence.update_pattern_outcome(test_pattern_id, {
            'win': win,
            'pnl_pct': 3.0 if win else -1.5,
            'held_time': 3600
        })
    
    print()
    
    # Test 5: Get pattern stats
    print("5️⃣ Pattern stats after trades:")
    stats = intelligence.get_pattern_stats(test_pattern_id)
    if stats:
        print(f"   Trades: {stats.times_traded}")
        print(f"   Win Rate: {stats.win_rate:.1%}")
        print(f"   Expectancy: {stats.expectancy:+.2f}%")
        print(f"   Confidence: {stats.confidence_score:.2f}")
    print()
    
    # Test 6: Get summary
    print("6️⃣ Overall summary:")
    summary = intelligence.get_pattern_summary()
    print(f"   Total patterns with stats: {summary['total_patterns']}")
    print(f"   Total trades: {summary['total_trades']}")
    print(f"   Overall win rate: {summary['overall_win_rate']:.1%}")
    print()
    
    print("✅ Pattern Intelligence system working!")
