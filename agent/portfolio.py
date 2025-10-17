"""
Paper Trading Portfolio Manager with full P&L tracking
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from utils.currency import format_currency, format_currency_signed

logger = logging.getLogger(__name__)

class PaperTradingPortfolio:
    """Simulates a trading portfolio with real-time P&L tracking"""
    
    def __init__(self, starting_capital: float = 10000.0, max_positions: int = 20, max_exposure_pct: float = 0.80, load_previous_state: bool = False):
        """
        Initialize paper trading portfolio.
        
        Args:
            starting_capital: Starting capital (in configured currency via format_currency)
            max_positions: Maximum number of open positions (default: 20)
            max_exposure_pct: Maximum portfolio exposure as percentage (default: 0.80 = 80%)
            load_previous_state: Whether to load previous portfolio state (default: False for fresh tests)
        """
        self.starting_capital = starting_capital
        self.capital = starting_capital
        self.positions: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self.state_file = Path("logs/portfolio_state.json")
        
        # 🔧 Risk management limits (EVOLVED - not added on top)
        self.MAX_POSITIONS = max_positions
        self.MAX_EXPOSURE_PCT = max_exposure_pct
        
        # Load previous state only if explicitly requested
        if load_previous_state:
            self._load_state()
        else:
            logger.info(f"💰 Portfolio initialized with fresh capital: {format_currency(self.starting_capital)}")
    
    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size: float,
        confidence: float,
        reason: str
    ) -> Optional[Dict]:
        """
        Open a simulated position
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "LONG" or "SHORT"
            entry_price: Entry price from live feed
            size: Position size in USD
            confidence: AI confidence (0.0-1.0)
            reason: AI reasoning for trade
        
        Returns:
            Position dictionary, or None if rejected by risk checks
        """
        # 🔧 EVOLVED: Pre-flight risk checks (prevent over-leverage)
        open_positions = [p for p in self.positions if p.get('status') == 'OPEN']
        
        # Check 1: Sufficient capital
        if self.capital < size:
            logger.warning(
                f"⚠️ Cannot open position: Insufficient capital "
                f"({format_currency(self.capital)} < {format_currency(size)})"
            )
            return None
        
        # Check 2: Max positions limit
        if len(open_positions) >= self.MAX_POSITIONS:
            logger.warning(f"⚠️ Cannot open position: Max positions reached ({len(open_positions)}/{self.MAX_POSITIONS})")
            return None
        
        # Check 3: Portfolio exposure limit
        current_exposure = sum(p['size'] for p in open_positions)
        new_exposure = current_exposure + size
        exposure_pct = new_exposure / self.starting_capital
        
        if exposure_pct > self.MAX_EXPOSURE_PCT:
            logger.warning(
                f"⚠️ Cannot open position: Exposure limit "
                f"({exposure_pct:.1%} > {self.MAX_EXPOSURE_PCT:.1%})"
            )
            return None
        
        # All checks passed - proceed with position opening
        qty = size / entry_price
        
        position = {
            'id': len(self.positions) + len(self.closed_trades) + 1,
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'current_price': entry_price,
            'size': size,
            'qty': qty,
            'pnl': 0.0,
            'pnl_pct': 0.0,
            'confidence': confidence,
            'reason': reason,
            'entry_time': datetime.now().isoformat(),
            'status': 'OPEN'
        }
        
        self.positions.append(position)
        self.capital -= size
        
        # 🔧 EVOLVED: Enhanced logging with portfolio state
        open_count = len([p for p in self.positions if p.get('status') == 'OPEN'])
        logger.info(
            f"✅ Opened {side} position #{position['id']}: {symbol} @ {format_currency(entry_price)} "
            f"({format_currency(size)}, conf: {confidence:.2%})"
        )
        logger.info(
            f"📊 Portfolio: {open_count}/{self.MAX_POSITIONS} positions, "
            f"{format_currency(self.capital)} capital remaining"
        )
        
        self._save_state()
        return position
    
    def update_positions(self, symbol: str, current_price: float):
        """
        Update all positions with current price from live feed
        
        Args:
            symbol: Trading pair
            current_price: Current price from WebSocket
        """
        for pos in self.positions:
            if pos['symbol'] == symbol:
                pos['current_price'] = current_price
                
                # Calculate P&L
                if pos['side'] == 'LONG':
                    current_value = pos['qty'] * current_price
                    entry_value = pos['size']
                    pos['pnl'] = current_value - entry_value
                else:  # SHORT
                    current_value = pos['qty'] * current_price
                    entry_value = pos['size']
                    pos['pnl'] = entry_value - current_value
                
                pos['pnl_pct'] = (pos['pnl'] / pos['size']) * 100
        
        self._save_state()
    
    def close_position(
        self,
        position_id: int,
        exit_price: float,
        reason: str
    ) -> Optional[Dict]:
        """
        Close a position and realize P&L
        
        Args:
            position_id: Position ID to close
            exit_price: Exit price from live feed
            reason: Reason for closing (TP/SL/AI decision)
        
        Returns:
            Closed trade dictionary
        """
        for i, pos in enumerate(self.positions):
            if pos['id'] == position_id:
                # Calculate final P&L
                if pos['side'] == 'LONG':
                    proceeds = pos['qty'] * exit_price
                else:  # SHORT
                    proceeds = pos['size'] * 2 - (pos['qty'] * exit_price)
                
                realized_pnl = proceeds - pos['size']
                
                # Add proceeds to capital
                self.capital += proceeds
                
                # Move to closed trades
                closed_trade = {
                    **pos,
                    'exit_price': exit_price,
                    'exit_time': datetime.now().isoformat(),
                    'realized_pnl': realized_pnl,
                    'realized_pnl_pct': (realized_pnl / pos['size']) * 100,
                    'exit_reason': reason,
                    'status': 'CLOSED',
                    'outcome': 'WIN' if realized_pnl > 0 else 'LOSS' if realized_pnl < 0 else 'NEUTRAL'
                }
                
                self.closed_trades.append(closed_trade)
                self.positions.pop(i)
                
                logger.info(
                    f"📊 Closed {pos['side']} position: {pos['symbol']} "
                    f"@ {format_currency(exit_price)} → P&L: {format_currency_signed(realized_pnl)} "
                    f"({realized_pnl / pos['size'] * 100:+.2f}%)"
                )
                
                self._save_state()
                return closed_trade
        
        return None
    
    def get_total_equity(self) -> float:
        """Calculate total equity (capital + position values)"""
        position_value = sum(
            p['qty'] * p['current_price'] 
            for p in self.positions
        )
        return self.capital + position_value
    
    def get_total_pnl(self) -> float:
        """Get all-time P&L (realized + unrealized)"""
        unrealized = sum(p['pnl'] for p in self.positions)
        realized = sum(t['realized_pnl'] for t in self.closed_trades)
        return realized + unrealized
    
    def get_performance_stats(self) -> Dict:
        """Calculate performance statistics for AI learning"""
        total_trades = len(self.closed_trades)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0
            }
        
        wins = [t for t in self.closed_trades if t['outcome'] == 'WIN']
        losses = [t for t in self.closed_trades if t['outcome'] == 'LOSS']
        
        total_profit = sum(t['realized_pnl'] for t in wins)
        total_loss = abs(sum(t['realized_pnl'] for t in losses))
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_profit = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        return {
            'total_trades': total_trades,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_pnl': self.get_total_pnl(),
            'total_pnl_pct': (self.get_total_pnl() / self.starting_capital) * 100,
            'best_trade': max(self.closed_trades, key=lambda x: x['realized_pnl']) if self.closed_trades else None,
            'worst_trade': min(self.closed_trades, key=lambda x: x['realized_pnl']) if self.closed_trades else None
        }
    
    def _save_state(self):
        """Save portfolio state to file for dashboard"""
        state = {
            'starting_capital': self.starting_capital,
            'capital': self.capital,
            'total_equity': self.get_total_equity(),
            'total_pnl': self.get_total_pnl(),
            'positions': self.positions,
            'closed_trades': self.closed_trades[-50:],  # Last 50
            'performance': self.get_performance_stats(),
            'last_update': datetime.now().isoformat()
        }
        
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load previous portfolio state if exists"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                self.starting_capital = state.get('starting_capital', self.starting_capital)
                self.capital = state.get('capital', self.capital)
                self.positions = state.get('positions', [])
                self.closed_trades = state.get('closed_trades', [])
                
                logger.info(
                    f"📂 Loaded portfolio state: {format_currency(self.capital)} capital, "
                    f"{len(self.positions)} open positions"
                )
            except Exception as e:
                logger.warning(f"Could not load portfolio state: {e}")