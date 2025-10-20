"""
SIMPLE Risk Management - 1% Rule Only
Keep it stupid simple: no fancy portfolio optimization, just the basics.
"""
from __future__ import annotations
from typing import Dict, List
from datetime import datetime

class SimpleRiskManager:
    """
    The simplest possible risk management:
    - Risk 1% of capital per trade
    - Max 2 positions open
    - Max 6% total portfolio heat
    - 3% daily loss limit
    
    That's it. No complex math needed.
    """
    
    def __init__(self, config):
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = config.MAX_POSITIONS
        self.max_heat = config.MAX_PORTFOLIO_HEAT
        self.daily_loss_limit = config.DAILY_LOSS_LIMIT
        self.capital = config.STARTING_CAPITAL
        
        self.open_positions: List[Dict] = []
        self.daily_pnl = 0.0
        self.daily_start_capital = config.STARTING_CAPITAL
    
    def calculate_position_size(self, entry: float, stop: float, signal: str) -> Dict:
        """
        Simple position sizing: Risk 1% of capital
        
        Formula:
        - Risk Amount = Capital × 1%
        - Distance to Stop = |Entry - Stop|
        - Position Size = Risk Amount / Distance to Stop
        """
        # Risk amount in ZAR
        risk_amount = self.capital * self.risk_per_trade
        
        # Distance to stop loss (price difference)
        stop_distance = abs(entry - stop)
        
        if stop_distance == 0 or stop_distance < entry * 0.001:  # Sanity check
            return {
                'approved': False,
                'reason': 'Stop loss too tight or invalid'
            }
        
        # Calculate position size
        position_size = risk_amount / stop_distance
        position_value = position_size * entry
        
        # Additional check: position shouldn't be > 5% of capital
        max_position_value = self.capital * 0.05
        if position_value > max_position_value:
            position_size = max_position_value / entry
            position_value = max_position_value
        
        return {
            'approved': True,
            'size': position_size,
            'value': position_value,
            'risk_amount': risk_amount,
            'risk_pct': self.risk_per_trade * 100
        }
    
    def can_open_position(self, signal: Dict) -> Dict:
        """
        Pre-trade risk checks - simple rules only
        
        Returns:
            {'approved': True/False, 'reason': str}
        """
        # Check 1: Max positions limit
        if len(self.open_positions) >= self.max_positions:
            return {
                'approved': False,
                'reason': f'Max positions ({self.max_positions}) already open'
            }
        
        # Check 2: Portfolio heat (total risk exposure)
        current_heat = sum(p.get('risk_pct', 0) / 100 for p in self.open_positions)
        new_heat = current_heat + self.risk_per_trade
        
        if new_heat > self.max_heat:
            return {
                'approved': False,
                'reason': f'Portfolio heat too high ({current_heat*100:.1f}% + {self.risk_per_trade*100:.1f}% > {self.max_heat*100:.1f}%)'
            }
        
        # Check 3: Daily loss limit
        daily_loss_pct = abs(self.daily_pnl) / self.daily_start_capital
        if self.daily_pnl < 0 and daily_loss_pct >= self.daily_loss_limit:
            return {
                'approved': False,
                'reason': f'Daily loss limit hit ({daily_loss_pct*100:.1f}% >= {self.daily_loss_limit*100:.1f}%)'
            }
        
        # Check 4: Signal quality (basic sanity)
        if signal.get('confidence', 0) < 30:
            return {
                'approved': False,
                'reason': f"Signal confidence too low ({signal.get('confidence', 0):.0f}%)"
            }
        
        # All checks passed
        return {
            'approved': True,
            'reason': 'All risk checks passed'
        }
    
    def add_position(self, position: Dict):
        """Track a new open position"""
        self.open_positions.append(position)
    
    def close_position(self, position_id: str, exit_price: float, exit_time: datetime) -> Dict:
        """Close a position and update P&L"""
        for i, pos in enumerate(self.open_positions):
            if pos.get('id') == position_id:
                # Calculate P&L
                entry = pos['entry']
                size = pos['size']
                signal = pos['signal']
                
                if signal == "LONG":
                    pnl = (exit_price - entry) * size
                else:  # SHORT
                    pnl = (entry - exit_price) * size
                
                # Update tracking
                self.daily_pnl += pnl
                self.capital += pnl
                
                # Remove from open positions
                closed_pos = self.open_positions.pop(i)
                closed_pos['exit_price'] = exit_price
                closed_pos['exit_time'] = exit_time
                closed_pos['pnl'] = pnl
                
                return closed_pos
        
        return {'error': f'Position {position_id} not found'}
    
    def reset_daily_pnl(self):
        """Call this at start of each trading day"""
        self.daily_pnl = 0.0
        self.daily_start_capital = self.capital
    
    def get_stats(self) -> Dict:
        """Get current risk statistics"""
        current_heat = sum(p.get('risk_pct', 0) / 100 for p in self.open_positions)
        
        return {
            'capital': self.capital,
            'open_positions': len(self.open_positions),
            'current_heat': current_heat * 100,
            'max_heat': self.max_heat * 100,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': (self.daily_pnl / self.daily_start_capital * 100) if self.daily_start_capital > 0 else 0
        }
