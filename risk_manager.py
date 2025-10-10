"""
OZZY SIMPLE - Risk Manager
Protects your capital with position sizing and risk controls
"""

from datetime import datetime, time
from typing import Dict, Optional, Tuple
import config


class RiskManager:
    """
    Manages risk for all trades.
    Calculates position sizes and enforces safety limits.
    """
    
    def __init__(self, starting_capital: float):
        """
        Initialize the risk manager
        
        Args:
            starting_capital: Starting account balance
        """
        self.starting_capital = starting_capital
        self.current_capital = starting_capital
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.total_trades = 0
        self.open_positions = 0
        
        # Reset daily stats at start of each day
        self.last_reset_date = datetime.now().date()
        
        # Trading hours (defaults to 9:00 - 21:00 if not provided in config)
        self.trading_start_hour = getattr(config, "TRADING_START_HOUR", 9)
        self.trading_end_hour = getattr(config, "TRADING_END_HOUR", 21)
        
        print("[RiskManager] Initialized")
        print(f"  Starting Capital: R{starting_capital:,.2f}")
        # RISK_PER_TRADE in config may be a fraction (0.02) or percent (2); normalize to fraction
        rpt = config.RISK_PER_TRADE
        rpt_display = rpt*100 if rpt <= 1 else rpt
        print(f"  Risk Per Trade: {rpt_display}%")

        # Daily loss limit: prefer absolute DAILY_LOSS_LIMIT if present, else MAX_DAILY_LOSS percent
        if hasattr(config, 'DAILY_LOSS_LIMIT'):
            print(f"  Max Daily Loss: R{config.DAILY_LOSS_LIMIT}")
        else:
            mdl = getattr(config, 'MAX_DAILY_LOSS', None)
            print(f"  Max Daily Loss: {mdl}%" if mdl is not None else "  Max Daily Loss: Not set")

        print(f"  Max Positions: {config.MAX_POSITIONS}")
        # Stop/TP percent names in config
        sl = getattr(config, 'STOP_LOSS_PERCENT', getattr(config, 'STOP_LOSS_PCT', None))
        tp = getattr(config, 'TAKE_PROFIT_PERCENT', getattr(config, 'TAKE_PROFIT_PCT', None))
        print(f"  Stop Loss: {sl}%")
        print(f"  Take Profit: {tp}%")
    
    
    def _check_daily_reset(self):
        """Reset daily statistics if new day"""
        current_date = datetime.now().date()
        if current_date > self.last_reset_date:
            print(f"[RiskManager] New day detected, resetting daily stats")
            print(f"  Previous day P&L: R{self.daily_pnl:,.2f}")
            print(f"  Previous day trades: {self.daily_trades}")
            
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset_date = current_date
    
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, 
                               signal_confidence: float = 100.0) -> Tuple[float, float]:
        """
        Calculate position size based on risk management rules
        
        Args:
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            signal_confidence: Signal confidence (0-100)
            
        Returns:
            Tuple of (position_size, position_value)
        """
        self._check_daily_reset()
        
        # Normalize RISK_PER_TRADE: if <=1 treat as fraction else percent
        rpt = config.RISK_PER_TRADE
        risk_fraction = rpt if rpt <= 1 else (rpt / 100.0)
        # Calculate risk amount (e.g., 2% of current capital)
        risk_amount = self.current_capital * risk_fraction
        
        # Adjust risk based on signal confidence
        # Use configurable MIN_CONFIDENCE as the lower bound for scaling.
        # Scale risk multiplier from 0.5x at MIN_CONFIDENCE up to 1.0x at 100%.
        min_conf = getattr(config, 'MIN_CONFIDENCE', 40.0)
        if signal_confidence < min_conf:
            confidence_multiplier = 0.0  # Don't trade below configured minimum confidence
        else:
            # Prevent division by zero when MIN_CONFIDENCE == 100
            denom = (100.0 - min_conf) if (100.0 - min_conf) != 0 else 1.0
            # Map [min_conf, 100] -> [0.5, 1.0]
            confidence_multiplier = 0.5 + ((signal_confidence - min_conf) / denom) * 0.5
        
        adjusted_risk = risk_amount * confidence_multiplier
        
        # Calculate price risk per unit
        price_risk = abs(entry_price - stop_loss)
        
        # Avoid division by zero
        if price_risk == 0:
            return 0.0, 0.0
        
        # Calculate position size (units)
        position_size = adjusted_risk / price_risk
        
        # Calculate position value
        position_value = position_size * entry_price
        
        # Cap position at 20% of capital (don't over-leverage)
        max_position_value = self.current_capital * 0.20
        if position_value > max_position_value:
            position_size = max_position_value / entry_price
            position_value = max_position_value
        
        print(f"[RiskManager] Position sizing:")
        print(f"  Risk Amount: R{adjusted_risk:,.2f} (confidence adjusted)")
        print(f"  Price Risk: ${price_risk:,.2f}")
        print(f"  Position Size: {position_size:.6f} units")
        print(f"  Position Value: R{position_value:,.2f}")
        
        return position_size, position_value
    
    
    def check_trading_hours(self) -> Tuple[bool, str]:
        """
        Check if current time is within trading hours
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        current_time = datetime.now().time()
        
        trading_start = time(self.trading_start_hour, 0)
        trading_end = time(self.trading_end_hour, 0)
        
        if trading_start <= current_time <= trading_end:
            return True, "Within trading hours"
        else:
            return False, f"Outside trading hours ({self.trading_start_hour}:00-{self.trading_end_hour}:00)"
    
    
    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """
        Check if daily loss limit has been reached
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        self._check_daily_reset()
        
        # Use absolute daily loss limit if provided
        if hasattr(config, 'DAILY_LOSS_LIMIT') and config.DAILY_LOSS_LIMIT is not None:
            max_daily_loss = config.DAILY_LOSS_LIMIT
        else:
            # Fallback to percent 'MAX_DAILY_LOSS' if present
            mdl = getattr(config, 'MAX_DAILY_LOSS', None)
            if mdl is None:
                # No limit configured
                return True, f"Daily P&L: R{self.daily_pnl:,.2f}"
            # Treat mdl as percent
            max_daily_loss = self.starting_capital * (mdl / 100.0)
        
        if self.daily_pnl <= -max_daily_loss:
            return False, f"Daily loss limit reached (R{abs(self.daily_pnl):,.2f})"
        
        return True, f"Daily P&L: R{self.daily_pnl:,.2f}"
    
    
    def check_max_positions(self) -> Tuple[bool, str]:
        """
        Check if maximum positions limit has been reached
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        if self.open_positions >= config.MAX_POSITIONS:
            return False, f"Max positions reached ({self.open_positions}/{config.MAX_POSITIONS})"
        
        return True, f"Open positions: {self.open_positions}/{config.MAX_POSITIONS}"
    
    
    def check_minimum_confidence(self, confidence: float) -> Tuple[bool, str]:
        """
        Check if signal confidence meets minimum threshold
        
        Args:
            confidence: Signal confidence (0-100)
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        if confidence < config.MIN_CONFIDENCE:
            return False, f"Confidence too low ({confidence}% < {config.MIN_CONFIDENCE}%)"
        
        return True, f"Confidence acceptable ({confidence}%)"
    
    
    def pre_trade_checks(self, signal: Dict, position_value: float) -> Tuple[bool, str]:
        """
        Run all pre-trade safety checks
        
        Args:
            signal: Signal dictionary
            position_value: Calculated position value
            
        Returns:
            Tuple of (is_approved, reason)
        """
        print(f"\n[RiskManager] Running pre-trade checks...")
        
        checks = []
        
        # Check 1: Trading hours
        hours_ok, hours_msg = self.check_trading_hours()
        checks.append((hours_ok, "Trading Hours", hours_msg))
        
        # Check 2: Daily loss limit
        loss_ok, loss_msg = self.check_daily_loss_limit()
        checks.append((loss_ok, "Daily Loss Limit", loss_msg))
        
        # Check 3: Max positions
        positions_ok, positions_msg = self.check_max_positions()
        checks.append((positions_ok, "Max Positions", positions_msg))
        
        # Check 4: Minimum confidence
        confidence_ok, confidence_msg = self.check_minimum_confidence(signal["confidence"])
        checks.append((confidence_ok, "Signal Confidence", confidence_msg))
        
        # Check 5: Sufficient capital
        if position_value > self.current_capital:
            capital_ok = False
            capital_msg = f"Insufficient capital (need R{position_value:,.2f}, have R{self.current_capital:,.2f})"
        else:
            capital_ok = True
            capital_msg = f"Sufficient capital (R{self.current_capital:,.2f})"
        checks.append((capital_ok, "Capital Check", capital_msg))
        
        # Check 6: Valid signal
        if signal["signal"] not in ["LONG", "SHORT"]:
            signal_ok = False
            signal_msg = f"Invalid signal type ({signal['signal']})"
        else:
            signal_ok = True
            signal_msg = f"Valid signal ({signal['signal']})"
        checks.append((signal_ok, "Signal Type", signal_msg))
        
        # Print all checks
        for passed, name, message in checks:
            status = "✔" if passed else "❌"
            print(f"  {status} {name}: {message}")
        
        # Determine overall approval
        all_passed = all(check[0] for check in checks)
        
        if all_passed:
            print(f"\n✅ All checks passed - TRADE APPROVED")
            return True, "All safety checks passed"
        else:
            failed_checks = [check[1] for check in checks if not check[0]]
            reason = f"Failed checks: {', '.join(failed_checks)}"
            print(f"\n❌ Trade rejected - {reason}")
            return False, reason
    
    
    def record_trade_opened(self, position_value: float):
        """
        Record that a trade was opened
        
        Args:
            position_value: Value of the position
        """
        self.open_positions += 1
        self.daily_trades += 1
        self.total_trades += 1
        self.current_capital -= position_value
        
        print(f"[RiskManager] Trade opened:")
        print(f"  Position value: R{position_value:,.2f}")
        print(f"  Open positions: {self.open_positions}")
        print(f"  Remaining capital: R{self.current_capital:,.2f}")
    
    
    def record_trade_closed(self, position_value: float, pnl: float):
        """
        Record that a trade was closed
        
        Args:
            position_value: Value of the position
            pnl: Profit/loss for the trade
        """
        self.open_positions -= 1
        self.current_capital += position_value + pnl
        self.daily_pnl += pnl
        
        print(f"[RiskManager] Trade closed:")
        print(f"  P&L: R{pnl:,.2f}")
        print(f"  Daily P&L: R{self.daily_pnl:,.2f}")
        print(f"  Open positions: {self.open_positions}")
        print(f"  Current capital: R{self.current_capital:,.2f}")
    
    
    def get_risk_stats(self) -> Dict:
        """
        Get current risk statistics
        
        Returns:
            Dictionary with risk stats
        """
        self._check_daily_reset()
        
        return {
            "starting_capital": self.starting_capital,
            "current_capital": self.current_capital,
            "total_pnl": self.current_capital - self.starting_capital,
            "total_pnl_pct": ((self.current_capital - self.starting_capital) / self.starting_capital) * 100,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": (self.daily_pnl / self.starting_capital) * 100,
            "open_positions": self.open_positions,
            "daily_trades": self.daily_trades,
            "total_trades": self.total_trades,
            "max_daily_loss_remaining": (self.starting_capital * getattr(config, 'MAX_DAILY_LOSS', 0) / 100) + self.daily_pnl
        }
    
    
    def print_risk_stats(self):
        """Print current risk statistics"""
        stats = self.get_risk_stats()
        
        print("\n" + "="*60)
        print("RISK MANAGER - CURRENT STATS")
        print("="*60)
        print(f"Starting Capital: R{stats['starting_capital']:,.2f}")
        print(f"Current Capital:  R{stats['current_capital']:,.2f}")
        print(f"Total P&L:        R{stats['total_pnl']:,.2f} ({stats['total_pnl_pct']:.2f}%)")
        print(f"Daily P&L:        R{stats['daily_pnl']:,.2f} ({stats['daily_pnl_pct']:.2f}%)")
        print(f"Open Positions:   {stats['open_positions']}/{config.MAX_POSITIONS}")
        print(f"Daily Trades:     {stats['daily_trades']}")
        print(f"Total Trades:     {stats['total_trades']}")
        print(f"Daily Loss Room:  R{stats['max_daily_loss_remaining']:,.2f}")
        print("="*60 + "\n")


def test_risk_manager():
    """Test the risk manager with mock scenarios"""
    print("\n" + "="*60)
    print("TESTING RISK MANAGER")
    print("="*60 + "\n")
    
    # Initialize risk manager
    rm = RiskManager(starting_capital=10000.0)
    
    # Test 1: Position sizing
    print("\n[TEST 1] Calculating position size...")
    entry_price = 120000.0
    stop_loss = 117600.0  # 2% stop loss
    confidence = 75.0
    
    position_size, position_value = rm.calculate_position_size(entry_price, stop_loss, confidence)
    
    if position_size > 0 and position_value > 0:
        print(f"✅ TEST 1 PASSED: Position size calculated")
    else:
        print(f"❌ TEST 1 FAILED: Invalid position size")
    
    # Test 2: Pre-trade checks
    print("\n[TEST 2] Running pre-trade checks...")
    mock_signal = {
        "signal": "LONG",
        "confidence": 75.0,
        "entry_price": entry_price,
        "stop_loss": stop_loss
    }
    
    approved, reason = rm.pre_trade_checks(mock_signal, position_value)
    
    if approved:
        print(f"✅ TEST 2 PASSED: Trade approved")
    else:
        print(f"❌ TEST 2 FAILED: Trade rejected - {reason}")
    
    # Test 3: Risk stats
    print("\n[TEST 3] Getting risk statistics...")
    rm.print_risk_stats()
    print(f"✅ TEST 3 PASSED: Risk stats displayed")
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_risk_manager()
