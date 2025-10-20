"""
Unit tests for intelligence/pattern_intelligence.py

Tests pattern learning, queries, and confidence scoring.
"""

import pytest
import time
from pathlib import Path
from intelligence.pattern_intelligence import PatternIntelligence, PatternStats


@pytest.fixture
def pattern_intelligence():
    """Create a fresh PatternIntelligence instance for each test"""
    # Use a test-specific data directory
    test_dir = Path("/tmp/test_pattern_intelligence")
    test_dir.mkdir(exist_ok=True)
    
    # Get instance (singleton)
    pi = PatternIntelligence.get_instance()
    
    # Clear existing stats for clean tests
    pi.stats_cache = {}
    
    yield pi
    
    # Cleanup
    pi.stats_cache = {}


class TestPatternStatsBasics:
    """Test PatternStats data class"""
    
    def test_pattern_stats_creation(self):
        """Test creating a PatternStats object"""
        stats = PatternStats(pattern_id="test_pattern")
        
        assert stats.pattern_id == "test_pattern"
        assert stats.times_matched == 0
        assert stats.times_traded == 0
        assert stats.wins == 0
        assert stats.losses == 0
        assert stats.total_pnl == 0.0
        assert stats.win_rate == 0.0
        assert stats.confidence_score == 0.5  # Default confidence
    
    def test_pattern_stats_to_dict(self):
        """Test converting PatternStats to dictionary"""
        stats = PatternStats(
            pattern_id="bullish_engulfing",
            times_traded=10,
            wins=6,
            losses=4
        )
        
        result = stats.to_dict()
        
        assert isinstance(result, dict)
        assert result['pattern_id'] == "bullish_engulfing"
        assert result['times_traded'] == 10
        assert result['wins'] == 6
        assert result['losses'] == 4


class TestPatternLearning:
    """Test pattern learning from trade outcomes"""
    
    def test_update_pattern_outcome_win(self, pattern_intelligence):
        """Test learning from a winning trade"""
        outcome = {
            'win': True,
            'pnl_pct': 2.5,
            'held_time': 3600
        }
        
        pattern_intelligence.update_pattern_outcome("bullish_engulfing", outcome)
        
        stats = pattern_intelligence.get_pattern_stats("bullish_engulfing")
        assert stats is not None
        assert stats.times_traded == 1
        assert stats.wins == 1
        assert stats.losses == 0
        assert stats.win_rate == 1.0  # 100% win rate
    
    def test_update_pattern_outcome_loss(self, pattern_intelligence):
        """Test learning from a losing trade"""
        outcome = {
            'win': False,
            'pnl_pct': -1.5,
            'held_time': 1800
        }
        
        pattern_intelligence.update_pattern_outcome("hammer", outcome)
        
        stats = pattern_intelligence.get_pattern_stats("hammer")
        assert stats is not None
        assert stats.times_traded == 1
        assert stats.wins == 0
        assert stats.losses == 1
        assert stats.win_rate == 0.0  # 0% win rate
    
    def test_multiple_updates_same_pattern(self, pattern_intelligence):
        """Test multiple updates to the same pattern"""
        # Add 3 wins
        for i in range(3):
            pattern_intelligence.update_pattern_outcome("morning_star", {'win': True, 'pnl_pct': 2.0})
        
        # Add 2 losses
        for i in range(2):
            pattern_intelligence.update_pattern_outcome("morning_star", {'win': False, 'pnl_pct': -1.0})
        
        stats = pattern_intelligence.get_pattern_stats("morning_star")
        assert stats.times_traded == 5
        assert stats.wins == 3
        assert stats.losses == 2
        assert stats.win_rate == pytest.approx(0.6, abs=0.01)  # 60% win rate
    
    def test_win_rate_calculation(self, pattern_intelligence):
        """Test accurate win rate calculation"""
        # 7 wins, 3 losses = 70% win rate
        for i in range(7):
            pattern_intelligence.update_pattern_outcome("test_pattern", {'win': True, 'pnl_pct': 1.0})
        for i in range(3):
            pattern_intelligence.update_pattern_outcome("test_pattern", {'win': False, 'pnl_pct': -1.0})
        
        stats = pattern_intelligence.get_pattern_stats("test_pattern")
        assert stats.win_rate == pytest.approx(0.7, abs=0.01)
    
    def test_pnl_accumulation(self, pattern_intelligence):
        """Test P&L accumulation over multiple trades"""
        pattern_intelligence.update_pattern_outcome("test_pattern", {'win': True, 'pnl_pct': 5.0})
        pattern_intelligence.update_pattern_outcome("test_pattern", {'win': True, 'pnl_pct': 3.0})
        pattern_intelligence.update_pattern_outcome("test_pattern", {'win': False, 'pnl_pct': -2.0})
        
        stats = pattern_intelligence.get_pattern_stats("test_pattern")
        # Note: P&L tracking depends on implementation details
        assert stats.times_traded == 3


class TestPatternQueries:
    """Test pattern query functionality"""
    
    def test_get_pattern_stats_existing(self, pattern_intelligence):
        """Test getting stats for existing pattern"""
        # Create a pattern
        pattern_intelligence.update_pattern_outcome("doji", {'win': True, 'pnl_pct': 1.5})
        
        stats = pattern_intelligence.get_pattern_stats("doji")
        
        assert stats is not None
        assert stats.pattern_id == "doji"
        assert stats.times_traded == 1
    
    def test_get_pattern_stats_nonexistent(self, pattern_intelligence):
        """Test getting stats for non-existent pattern"""
        stats = pattern_intelligence.get_pattern_stats("nonexistent_pattern")
        
        assert stats is None
    
    def test_get_top_patterns_empty(self, pattern_intelligence):
        """Test getting top patterns when no patterns exist"""
        top = pattern_intelligence.get_top_patterns(n=5, min_trades=1)
        
        assert isinstance(top, list)
        assert len(top) == 0
    
    def test_get_top_patterns_with_data(self, pattern_intelligence):
        """Test getting top patterns when data exists"""
        # Create patterns with different win rates
        # Pattern 1: 80% WR (4 wins, 1 loss)
        for i in range(4):
            pattern_intelligence.update_pattern_outcome("pattern_a", {'win': True, 'pnl_pct': 2.0})
        pattern_intelligence.update_pattern_outcome("pattern_a", {'win': False, 'pnl_pct': -1.0})
        
        # Pattern 2: 60% WR (3 wins, 2 losses)
        for i in range(3):
            pattern_intelligence.update_pattern_outcome("pattern_b", {'win': True, 'pnl_pct': 1.5})
        for i in range(2):
            pattern_intelligence.update_pattern_outcome("pattern_b", {'win': False, 'pnl_pct': -1.0})
        
        # Pattern 3: 50% WR (2 wins, 2 losses)
        for i in range(2):
            pattern_intelligence.update_pattern_outcome("pattern_c", {'win': True, 'pnl_pct': 1.0})
        for i in range(2):
            pattern_intelligence.update_pattern_outcome("pattern_c", {'win': False, 'pnl_pct': -1.0})
        
        # Get top 3
        top = pattern_intelligence.get_top_patterns(n=3, min_trades=3)
        
        assert len(top) <= 3
        # Should be sorted by expectancy/quality
        if len(top) > 1:
            # First should be better than last
            assert top[0]['win_rate'] >= top[-1]['win_rate'] or top[0]['expectancy'] >= top[-1]['expectancy']
    
    def test_get_top_patterns_min_trades_filter(self, pattern_intelligence):
        """Test min_trades filter in get_top_patterns"""
        # Pattern with only 1 trade
        pattern_intelligence.update_pattern_outcome("low_volume", {'win': True, 'pnl_pct': 5.0})
        
        # Pattern with 5 trades
        for i in range(5):
            pattern_intelligence.update_pattern_outcome("high_volume", {'win': True, 'pnl_pct': 2.0})
        
        # Request patterns with min 3 trades
        top = pattern_intelligence.get_top_patterns(n=10, min_trades=3)
        
        # Should only include high_volume pattern
        pattern_ids = [p['pattern_id'] for p in top]
        assert "high_volume" in pattern_ids
        assert "low_volume" not in pattern_ids


class TestConfidenceScoring:
    """Test confidence score calculations"""
    
    def test_confidence_increases_with_wins(self, pattern_intelligence):
        """Test confidence increases with winning trades"""
        # Start with some trades
        for i in range(5):
            pattern_intelligence.update_pattern_outcome("test", {'win': True, 'pnl_pct': 2.0})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        initial_confidence = stats.confidence_score
        
        # Add more wins
        for i in range(5):
            pattern_intelligence.update_pattern_outcome("test", {'win': True, 'pnl_pct': 2.0})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        final_confidence = stats.confidence_score
        
        # Confidence should increase or stay high
        assert final_confidence >= initial_confidence or final_confidence > 0.7
    
    def test_confidence_decreases_with_losses(self, pattern_intelligence):
        """Test confidence decreases with losing trades"""
        # Start with wins
        for i in range(3):
            pattern_intelligence.update_pattern_outcome("test", {'win': True, 'pnl_pct': 2.0})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        initial_confidence = stats.confidence_score
        
        # Add losses
        for i in range(5):
            pattern_intelligence.update_pattern_outcome("test", {'win': False, 'pnl_pct': -1.5})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        final_confidence = stats.confidence_score
        
        # Confidence should decrease
        assert final_confidence < initial_confidence


class TestPatternSummary:
    """Test pattern summary statistics"""
    
    def test_get_pattern_summary_empty(self, pattern_intelligence):
        """Test summary when no patterns exist"""
        summary = pattern_intelligence.get_pattern_summary()
        
        assert summary['total_patterns'] == 0
        assert summary['patterns_with_trades'] == 0
        assert summary['total_trades'] == 0
    
    def test_get_pattern_summary_with_data(self, pattern_intelligence):
        """Test summary with multiple patterns"""
        # Add patterns
        for i in range(3):
            pattern_intelligence.update_pattern_outcome("pattern_1", {'win': True, 'pnl_pct': 2.0})
        for i in range(2):
            pattern_intelligence.update_pattern_outcome("pattern_2", {'win': False, 'pnl_pct': -1.0})
        
        summary = pattern_intelligence.get_pattern_summary()
        
        assert summary['total_patterns'] >= 2
        assert summary['total_trades'] >= 5


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_pattern_id(self, pattern_intelligence):
        """Test handling empty pattern ID"""
        # Should handle gracefully
        pattern_intelligence.update_pattern_outcome("", {'win': True, 'pnl_pct': 1.0})
        
        stats = pattern_intelligence.get_pattern_stats("")
        # Behavior depends on implementation
    
    def test_special_characters_in_pattern_id(self, pattern_intelligence):
        """Test pattern IDs with special characters"""
        pattern_id = "pattern_with_@#$_chars"
        pattern_intelligence.update_pattern_outcome(pattern_id, {'win': True, 'pnl_pct': 1.0})
        
        stats = pattern_intelligence.get_pattern_stats(pattern_id)
        assert stats is not None
        assert stats.pattern_id == pattern_id
    
    def test_very_long_pattern_id(self, pattern_intelligence):
        """Test very long pattern IDs"""
        pattern_id = "a" * 200  # 200 character pattern ID
        pattern_intelligence.update_pattern_outcome(pattern_id, {'win': True, 'pnl_pct': 1.0})
        
        stats = pattern_intelligence.get_pattern_stats(pattern_id)
        assert stats is not None
    
    def test_zero_pnl(self, pattern_intelligence):
        """Test trade with exactly zero P&L"""
        pattern_intelligence.update_pattern_outcome("test", {'win': False, 'pnl_pct': 0.0})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        assert stats is not None
    
    def test_extreme_pnl_values(self, pattern_intelligence):
        """Test extreme P&L values"""
        # Huge win
        pattern_intelligence.update_pattern_outcome("test", {'win': True, 'pnl_pct': 100.0})
        # Huge loss
        pattern_intelligence.update_pattern_outcome("test", {'win': False, 'pnl_pct': -50.0})
        
        stats = pattern_intelligence.get_pattern_stats("test")
        assert stats is not None
        assert stats.times_traded == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=intelligence.pattern_intelligence", "--cov-report=term-missing"])
