"""
Unit tests for agent/portfolio.py - PaperTradingPortfolio

Tests position management, P&L calculations, and risk limits.
CORRECTED to match actual PaperTradingPortfolio API.
"""

import pytest
from agent.portfolio import PaperTradingPortfolio


class TestPortfolioInitialization:
    """Test portfolio initialization"""
    
    def test_default_initialization(self):
        """Test portfolio with default parameters"""
        portfolio = PaperTradingPortfolio(load_previous_state=False)
        
        assert portfolio.starting_capital == 10000.0
        assert portfolio.capital == 10000.0
        assert len(portfolio.positions) == 0
        assert len(portfolio.closed_trades) == 0
        assert portfolio.MAX_POSITIONS == 20
        assert portfolio.MAX_EXPOSURE_PCT == 0.80
    
    def test_custom_initialization(self):
        """Test portfolio with custom parameters"""
        portfolio = PaperTradingPortfolio(
            starting_capital=50000.0,
            max_positions=10,
            max_exposure_pct=0.5,
            load_previous_state=False
        )
        
        assert portfolio.starting_capital == 50000.0
        assert portfolio.capital == 50000.0
        assert portfolio.MAX_POSITIONS == 10
        assert portfolio.MAX_EXPOSURE_PCT == 0.5


class TestPositionOpening:
    """Test opening positions"""
    
    def test_open_long_position(self):
        """Test opening a long position"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        pos = portfolio.open_position(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=50000.0,
            size=1000.0,  # $1000 position
            confidence=0.75,
            reason="Bullish engulfing pattern detected",
            pattern_id="bullish_engulfing"
        )
        
        assert pos is not None
        assert pos['symbol'] == "BTCUSDT"
        assert pos['side'] == "LONG"
        assert pos['entry_price'] == 50000.0
        assert pos['size'] == 1000.0
        assert pos['qty'] == pytest.approx(1000.0 / 50000.0, abs=0.001)  # 0.02 BTC
        assert pos['confidence'] == 0.75
        assert pos['pattern_id'] == "bullish_engulfing"
        assert pos['status'] == "OPEN"
        assert 'id' in pos
        assert 'entry_time' in pos
        
        # Capital should be reduced
        assert portfolio.capital == 9000.0
        assert len(portfolio.positions) == 1
    
    def test_open_short_position(self):
        """Test opening a short position"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        pos = portfolio.open_position(
            symbol="ETHUSDT",
            side="SHORT",
            entry_price=3000.0,
            size=500.0,
            confidence=0.68,
            reason="Bearish divergence",
            pattern_id="bearish_engulfing"
        )
        
        assert pos is not None
        assert pos['side'] == "SHORT"
        assert pos['entry_price'] == 3000.0
        assert portfolio.capital == 9500.0
    
    def test_multiple_positions(self):
        """Test opening multiple positions"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        pos1 = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test 1")
        pos2 = portfolio.open_position("ETHUSDT", "LONG", 3000.0, 500.0, 0.70, "Test 2")
        
        assert len(portfolio.positions) == 2
        assert pos1['id'] != pos2['id']
        assert portfolio.capital == 8500.0  # 10000 - 1000 - 500


class TestRiskLimits:
    """Test risk management limits"""
    
    def test_insufficient_capital(self):
        """Test rejection when insufficient capital"""
        portfolio = PaperTradingPortfolio(starting_capital=1000.0, load_previous_state=False)
        
        # Try to open position larger than capital
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 2000.0, 0.75, "Too large")
        
        assert pos is None  # Should be rejected
        assert len(portfolio.positions) == 0
        assert portfolio.capital == 1000.0  # Capital unchanged
    
    def test_max_positions_limit(self):
        """Test max positions limit"""
        portfolio = PaperTradingPortfolio(
            starting_capital=10000.0,
            max_positions=3,
            load_previous_state=False
        )
        
        # Open 3 positions (at limit)
        for i in range(3):
            portfolio.open_position("BTCUSDT", "LONG", 50000.0, 100.0, 0.75, f"Position {i}")
        
        # Try to open 4th position
        pos4 = portfolio.open_position("ETHUSDT", "LONG", 3000.0, 100.0, 0.75, "Position 4")
        
        assert pos4 is None  # Should be rejected
        assert len(portfolio.positions) == 3  # Still only 3 positions
    
    def test_exposure_limit(self):
        """Test portfolio exposure limit"""
        portfolio = PaperTradingPortfolio(
            starting_capital=10000.0,
            max_exposure_pct=0.5,  # 50% max exposure
            load_previous_state=False
        )
        
        # Open position at 40% exposure (OK)
        pos1 = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 4000.0, 0.75, "Position 1")
        assert pos1 is not None
        
        # Try to open another 40% position (would exceed 50% limit)
        pos2 = portfolio.open_position("ETHUSDT", "LONG", 3000.0, 4000.0, 0.75, "Position 2")
        assert pos2 is None  # Should be rejected


class TestPositionClosing:
    """Test closing positions"""
    
    def test_close_long_position_profit(self):
        """Test closing long position with profit"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open long at 50000
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        
        # Close at 52000 (profit)
        closed = portfolio.close_position(pos['id'], 52000.0, "take_profit")
        
        assert closed is not None
        assert closed['exit_price'] == 52000.0
        assert closed['exit_reason'] == "take_profit"
        assert closed['realized_pnl'] > 0  # Should have profit
        assert closed['realized_pnl_pct'] > 0
        assert closed['outcome'] == 'WIN'
        assert closed['status'] == 'CLOSED'
        
        # Position should be removed from active positions
        assert len(portfolio.positions) == 0
        assert len(portfolio.closed_trades) == 1
        
        # Capital should increase (profit added)
        assert portfolio.capital > 9000.0
    
    def test_close_long_position_loss(self):
        """Test closing long position with loss"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open long at 50000
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        
        # Close at 48000 (loss)
        closed = portfolio.close_position(pos['id'], 48000.0, "stop_loss")
        
        assert closed is not None
        assert closed['realized_pnl'] < 0  # Should have loss
        assert closed['outcome'] == 'LOSS'
        
        # Total capital should be less than starting capital (we lost money)
        assert portfolio.capital < 10000.0
    
    def test_close_short_position_profit(self):
        """Test closing short position with profit"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open short at 50000
        pos = portfolio.open_position("BTCUSDT", "SHORT", 50000.0, 1000.0, 0.75, "Test")
        
        # Close at 48000 (profit for short)
        closed = portfolio.close_position(pos['id'], 48000.0, "take_profit")
        
        assert closed is not None
        assert closed['realized_pnl'] > 0  # Should have profit
        assert closed['outcome'] == 'WIN'
    
    def test_close_short_position_loss(self):
        """Test closing short position with loss"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open short at 50000
        pos = portfolio.open_position("BTCUSDT", "SHORT", 50000.0, 1000.0, 0.75, "Test")
        
        # Close at 52000 (loss for short)
        closed = portfolio.close_position(pos['id'], 52000.0, "stop_loss")
        
        assert closed is not None
        assert closed['realized_pnl'] < 0  # Should have loss
        assert closed['outcome'] == 'LOSS'
    
    def test_close_nonexistent_position(self):
        """Test closing position that doesn't exist"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        closed = portfolio.close_position(999, 50000.0, "manual")
        
        assert closed is None


class TestPnLCalculations:
    """Test P&L calculation accuracy"""
    
    def test_long_pnl_calculation(self):
        """Test P&L calculation for long position"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open long: entry 50000, size 1000
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        qty = pos['qty']  # 1000/50000 = 0.02 BTC
        
        # Close at 55000
        closed = portfolio.close_position(pos['id'], 55000.0, "take_profit")
        
        # Long P&L: (exit_price * qty) - size
        # = (55000 * 0.02) - 1000 = 1100 - 1000 = 100
        expected_pnl = (55000 * qty) - 1000
        assert closed['realized_pnl'] == pytest.approx(expected_pnl, abs=0.01)
        assert closed['realized_pnl_pct'] == pytest.approx(10.0, abs=0.1)  # 100/1000 = 10%
    
    def test_short_pnl_calculation(self):
        """Test P&L calculation for short position"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Open short: entry 50000, size 1000
        pos = portfolio.open_position("BTCUSDT", "SHORT", 50000.0, 1000.0, 0.75, "Test")
        qty = pos['qty']
        
        # Close at 48000
        closed = portfolio.close_position(pos['id'], 48000.0, "take_profit")
        
        # Short P&L: (size * 2) - (exit_price * qty) - size
        # = 2000 - (48000 * 0.02) - 1000 = 2000 - 960 - 1000 = 40
        proceeds = 1000 * 2 - (48000 * qty)
        expected_pnl = proceeds - 1000
        assert closed['realized_pnl'] == pytest.approx(expected_pnl, abs=0.01)


class TestPortfolioMetrics:
    """Test portfolio metrics and statistics"""
    
    def test_get_total_equity(self):
        """Test total equity calculation"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Initially, equity = capital
        assert portfolio.get_total_equity() == 10000.0
        
        # Open position
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        
        # Update position with new price
        portfolio.update_positions("BTCUSDT", 51000.0)
        
        # Equity = capital + position value
        # Capital = 9000, Position value = 0.02 * 51000 = 1020
        # Total = 10020
        equity = portfolio.get_total_equity()
        assert equity > 10000.0  # Should have unrealized profit
    
    def test_get_total_pnl(self):
        """Test total P&L calculation"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Initially no P&L
        assert portfolio.get_total_pnl() == 0.0
        
        # Open and close position with profit
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        portfolio.close_position(pos['id'], 52000.0, "take_profit")
        
        # Should have positive P&L
        total_pnl = portfolio.get_total_pnl()
        assert total_pnl > 0
    
    def test_performance_stats(self):
        """Test performance statistics"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        # Make 2 winning trades and 1 losing trade
        pos1 = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test 1")
        portfolio.close_position(pos1['id'], 52000.0, "take_profit")  # Win
        
        pos2 = portfolio.open_position("BTCUSDT", "LONG", 52000.0, 1000.0, 0.75, "Test 2")
        portfolio.close_position(pos2['id'], 54000.0, "take_profit")  # Win
        
        pos3 = portfolio.open_position("BTCUSDT", "LONG", 54000.0, 1000.0, 0.75, "Test 3")
        portfolio.close_position(pos3['id'], 53000.0, "stop_loss")  # Loss
        
        stats = portfolio.get_performance_stats()
        
        assert stats is not None
        assert isinstance(stats, dict)


class TestUpdatePositions:
    """Test position updates with live prices"""
    
    def test_update_long_position_profit(self):
        """Test updating long position with profitable price"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        
        # Update with higher price (profit)
        portfolio.update_positions("BTCUSDT", 52000.0)
        
        updated_pos = portfolio.positions[0]
        assert updated_pos['current_price'] == 52000.0
        assert updated_pos['pnl'] > 0
        assert updated_pos['pnl_pct'] > 0
    
    def test_update_long_position_loss(self):
        """Test updating long position with losing price"""
        portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
        
        pos = portfolio.open_position("BTCUSDT", "LONG", 50000.0, 1000.0, 0.75, "Test")
        
        # Update with lower price (loss)
        portfolio.update_positions("BTCUSDT", 48000.0)
        
        updated_pos = portfolio.positions[0]
        assert updated_pos['current_price'] == 48000.0
        assert updated_pos['pnl'] < 0
        assert updated_pos['pnl_pct'] < 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
