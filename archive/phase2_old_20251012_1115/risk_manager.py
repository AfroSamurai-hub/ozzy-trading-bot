"""
OZZY SIMPLE - Risk Manager
Protects your capital with position sizing and risk controls
"""

from datetime import datetime, time
from typing import Dict, Optional, Tuple
from loguru import logger
import config
import sqlite3
import os


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
        
        # Trading hours configuration
        self.trading_hours_config = getattr(config, "TRADING_HOURS", {'enabled': True, 'start': 9, 'end': 21})
        self.trading_hours_enabled = self.trading_hours_config.get('enabled', True)
        self.trading_start_hour = self.trading_hours_config.get('start', 9)
        self.trading_end_hour = self.trading_hours_config.get('end', 21)
        
        # RISK_PER_TRADE in config may be a fraction (0.02) or percent (2); normalize to fraction
        rpt = config.RISK_PER_TRADE
        rpt_display = rpt*100 if rpt <= 1 else rpt
        
        # Daily loss limit: prefer absolute DAILY_LOSS_LIMIT if present, else MAX_DAILY_LOSS percent
        mdl_display = None
        if hasattr(config, 'DAILY_LOSS_LIMIT'):
            mdl_display = f"R{config.DAILY_LOSS_LIMIT}"
        else:
            mdl = getattr(config, 'MAX_DAILY_LOSS', None)
            mdl_display = f"{mdl}%" if mdl is not None else "Not set"

        # Stop/TP percent names in config
        sl = getattr(config, 'STOP_LOSS_PERCENT', getattr(config, 'STOP_LOSS_PCT', None))
        tp = getattr(config, 'TAKE_PROFIT_PERCENT', getattr(config, 'TAKE_PROFIT_PCT', None))
        
        logger.info("RiskManager initialized",
                    starting_capital=f"R{starting_capital:,.2f}",
                    risk_per_trade=f"{rpt_display}%",
                    max_daily_loss=mdl_display,
                    max_positions=config.MAX_POSITIONS,
                    stop_loss=f"{sl}%",
                    take_profit=f"{tp}%")


    def get_total_trades_from_db(self) -> int:
        """Return total number of trades in the database (all-time).

        Returns 0 if DB not found or query fails.
        """
        db = 'ozzy_simple.db'
        if not os.path.exists(db):
            return 0
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM trades')
            result = cur.fetchone()[0] or 0
            conn.close()
            return int(result)
        except Exception:
            return 0


    def get_deployed_capital_from_db(self) -> float:
        """Compute deployed capital from positions table.

        Attempts to use `current_price` when present, otherwise falls back to `entry_price`.
        Returns 0.0 if DB or table not present.
        """
        db = 'ozzy_simple.db'
        if not os.path.exists(db):
            return 0.0
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            # Inspect columns
            cur.execute("PRAGMA table_info('positions')")
            cols = [r[1] for r in cur.fetchall()]
            use_current = 'current_price' in cols
            if use_current:
                q = 'SELECT SUM(qty * current_price) FROM positions'
            else:
                # fallback to entry_price
                q = 'SELECT SUM(qty * entry_price) FROM positions'
            cur.execute(q)
            res = cur.fetchone()[0] or 0.0
            conn.close()
            return float(res)
        except Exception:
            return 0.0
    
    
    def _check_daily_reset(self):
        """Reset daily statistics if new day"""
        current_date = datetime.now().date()
        if current_date > self.last_reset_date:
            logger.info("New day detected, resetting daily stats",
                       previous_pnl=f"R{self.daily_pnl:,.2f}",
                       previous_trades=self.daily_trades)
            
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
        
        logger.info("Position sizing calculated",
                   risk_amount=f"R{adjusted_risk:,.2f}",
                   price_risk=f"${price_risk:,.2f}",
                   position_size=f"{position_size:.6f}",
                   position_value=f"R{position_value:,.2f}")
        
        return position_size, position_value
    
    
    def check_trading_hours(self) -> Tuple[bool, str]:
        """
        Check if current time is within trading hours
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        # If trading hours restriction is disabled, always allow trading
        if not self.trading_hours_enabled:
            return True, "24/7 trading (unrestricted)"
        
        current_time = datetime.now().time()
        
        # Treat end hour as inclusive through the hour (e.g., 23 -> 23:59:59)
        trading_start = time(self.trading_start_hour, 0, 0)
        trading_end = time(self.trading_end_hour, 59, 59)

        if trading_start <= current_time <= trading_end:
            return True, "Within trading hours"
        else:
            return False, f"Outside trading hours ({self.trading_start_hour}:00-{self.trading_end_hour}:59)"
    
    
    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """
        Check if daily loss limit has been reached
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        self._check_daily_reset()
        
        # Use absolute daily loss limit if provided (prefer stricter of configured limits)
        abs_limit = getattr(config, 'DAILY_LOSS_LIMIT', None)
        daps_abs_limit = getattr(config, 'ABSOLUTE_DAILY_LOSS_LIMIT', None)
        max_daily_loss = None
        if abs_limit is not None and daps_abs_limit is not None:
            max_daily_loss = min(float(abs_limit), float(daps_abs_limit))
        elif abs_limit is not None:
            max_daily_loss = float(abs_limit)
        elif daps_abs_limit is not None:
            max_daily_loss = float(daps_abs_limit)
        else:
            # Fallback to percent 'MAX_DAILY_LOSS' if present
            mdl = getattr(config, 'MAX_DAILY_LOSS', None)
            if mdl is None:
                # No limit configured
                return True, f"Daily P&L: R{self.daily_pnl:,.2f}"
            # Treat mdl as percent
            max_daily_loss = self.starting_capital * (float(mdl) / 100.0)
        
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
        logger.info("Running pre-trade checks...")
        
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

        # Check 5b: Max deployed capital percent (DAPS safety rail)
        try:
            max_deploy_pct = getattr(config, 'ABSOLUTE_MAX_DEPLOYED_PCT', None)
            if max_deploy_pct is not None:
                deployed_now = self.get_deployed_capital_from_db()
                max_deploy_value = float(self.starting_capital) * float(max_deploy_pct)
                if (deployed_now + position_value) > max_deploy_value:
                    checks.append((False, "Max Deployed Capital", f"Exceeds {max_deploy_pct*100:.0f}% cap (now R{deployed_now:,.2f} + new R{position_value:,.2f} > R{max_deploy_value:,.2f})"))
                else:
                    checks.append((True, "Max Deployed Capital", f"Within {max_deploy_pct*100:.0f}% cap (R{deployed_now+position_value:,.2f}/R{max_deploy_value:,.2f})"))
        except Exception:
            # Non-fatal if DB not ready
            checks.append((True, "Max Deployed Capital", "Check skipped"))
        
        # Check 6: Valid signal
        if signal["signal"] not in ["LONG", "SHORT"]:
            signal_ok = False
            signal_msg = f"Invalid signal type ({signal['signal']})"
        else:
            signal_ok = True
            signal_msg = f"Valid signal ({signal['signal']})"
        checks.append((signal_ok, "Signal Type", signal_msg))
        
        # Log all checks
        for passed, name, message in checks:
            status = "✔" if passed else "❌"
            if passed:
                logger.debug(f"{status} {name}: {message}")
            else:
                logger.warning(f"{status} {name}: {message}")
        
        # Determine overall approval
        all_passed = all(check[0] for check in checks)
        
        if all_passed:
            logger.info("✅ All checks passed - TRADE APPROVED")
            return True, "All safety checks passed"
        else:
            failed_checks = [check[1] for check in checks if not check[0]]
            reason = f"Failed checks: {', '.join(failed_checks)}"
            logger.warning(f"❌ Trade rejected - {reason}")
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
        
        logger.info("Trade opened",
                   position_value=f"R{position_value:,.2f}",
                   open_positions=self.open_positions,
                   remaining_capital=f"R{self.current_capital:,.2f}")
    
    
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
        
        logger.info("Trade closed",
                   pnl=f"R{pnl:,.2f}",
                   daily_pnl=f"R{self.daily_pnl:,.2f}",
                   open_positions=self.open_positions,
                   current_capital=f"R{self.current_capital:,.2f}")
    
    
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
        # Pull all-time totals from DB when possible
        all_time_trades = self.get_total_trades_from_db()
        deployed = self.get_deployed_capital_from_db()
        free_capital = stats['current_capital']
        # If deployed was computed from DB we should subtract from current capital to get free
        try:
            free_capital = stats['current_capital'] - deployed
        except Exception:
            free_capital = stats['current_capital']

        total_exposure = deployed  # for now

        logger.info("RISK MANAGER - CURRENT STATS")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"Session Starting Capital: R{stats['starting_capital']:,.2f}")
        logger.info(f"Deployed in Positions:    R{deployed:,.2f} ({(deployed / stats['starting_capital']*100) if stats['starting_capital'] else 0:.2f}%)")
        logger.info(f"Free Capital:             R{free_capital:,.2f} ({(free_capital / stats['starting_capital']*100) if stats['starting_capital'] else 0:.2f}%)")
        logger.info(f"Total Exposure:           R{total_exposure:,.2f} ({(total_exposure / stats['starting_capital']*100) if stats['starting_capital'] else 0:.2f}%)")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"Open Positions:           {stats['open_positions']}/{config.MAX_POSITIONS}")
        logger.info(f"Session Trades:           {stats['daily_trades']} (this session)")
        logger.info(f"All-Time Trades:          {all_time_trades} (total in database)")
        logger.info(f"Daily Trades:             {stats['daily_trades']} (completed today)")
        logger.info(f"Daily Loss Room:          R{stats['max_daily_loss_remaining']:,.2f}")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"All-Time P&L:             {('+' if stats['total_pnl']>=0 else '')}R{stats['total_pnl']:,.2f} ({stats['total_pnl_pct']:.1f}%)")
        # Compute win/loss from DB if possible
        all_wins = 0
        all_losses = 0
        try:
            db = 'ozzy_simple.db'
            if os.path.exists(db):
                conn = sqlite3.connect(db)
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM trades WHERE pnl>0')
                all_wins = cur.fetchone()[0] or 0
                cur.execute('SELECT COUNT(*) FROM trades WHERE pnl<0')
                all_losses = cur.fetchone()[0] or 0
                conn.close()
        except Exception:
            all_wins = 0
            all_losses = 0

        total_closed = all_wins + all_losses
        win_rate = (all_wins / total_closed * 100) if total_closed > 0 else 0.0
        logger.info(f"All-Time Win Rate:        {win_rate:.1f}% ({all_wins}W/{all_losses}L)")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def test_risk_manager():
    """Test the risk manager with mock scenarios"""
    logger.info("=" * 60)
    logger.info("TESTING RISK MANAGER")
    logger.info("=" * 60)
    
    # Initialize risk manager
    rm = RiskManager(starting_capital=10000.0)
    
    # Test 1: Position sizing
    logger.info("[TEST 1] Calculating position size...")
    entry_price = 120000.0
    stop_loss = 117600.0  # 2% stop loss
    confidence = 75.0
    
    position_size, position_value = rm.calculate_position_size(entry_price, stop_loss, confidence)
    
    if position_size > 0 and position_value > 0:
        logger.info("✅ TEST 1 PASSED: Position size calculated")
    else:
        logger.error("❌ TEST 1 FAILED: Invalid position size")
    
    # Test 2: Pre-trade checks
    logger.info("[TEST 2] Running pre-trade checks...")
    mock_signal = {
        "signal": "LONG",
        "confidence": 75.0,
        "entry_price": entry_price,
        "stop_loss": stop_loss
    }
    
    approved, reason = rm.pre_trade_checks(mock_signal, position_value)
    
    if approved:
        logger.info("✅ TEST 2 PASSED: Trade approved")
    else:
        logger.error(f"❌ TEST 2 FAILED: Trade rejected - {reason}")
    
    # Test 3: Risk stats
    logger.info("[TEST 3] Getting risk statistics...")
    rm.print_risk_stats()
    logger.info("✅ TEST 3 PASSED: Risk stats displayed")
    
    logger.info("=" * 60)
    logger.info("TESTING COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_risk_manager()
