"""
OZZY SIMPLE - Demo Trading Bot
Demo version that tracks virtual capital growth from R10,000
"""

import time
import csv
import json
import sys
import sqlite3
import traceback
from datetime import datetime, time as datetime_time
from typing import Dict, List, Optional
from loguru import logger
import config
from bybit_client import BybitClient
from signal_generator import SignalGenerator
from risk_manager import RiskManager
from position_tracker import PositionTracker
from logger_config import setup_logger
import db
from time_filter_wrapper import TimeFilterWrapper
import os
from external_market_data import ExternalMarketData
from demo_utils import ensure_demo_database, get_demo_db_path


class DemoOzzyBot:
    """
    Demo trading bot that tracks virtual capital growth starting from R10,000.
    Uses real market data but no actual money is at risk.
    """
    
    def __init__(self):
        """Initialize the demo trading bot"""
        logger.info("=" * 70)
        logger.info("🤖 OZZY SIMPLE - DEMO TRADING BOT (R10,000 VIRTUAL CAPITAL)")
        logger.info("=" * 70)
        
        # Initialize demo database
        self.demo_db_path = ensure_demo_database()
        
        # Load current demo balance
        self.current_balance = self._get_current_balance()
        logger.info(f"💰 Current Demo Balance: R{self.current_balance:,.2f}")
        
        # Initialize components (use demo balance for risk calculations)
        logger.info("Initializing components...")
        self.client = BybitClient()
        self.signal_generator = SignalGenerator(self.client)
        self.risk_manager = RiskManager(self.current_balance)
        # Keep risk manager capital aligned with demo balance at start
        self.risk_manager.current_capital = self.current_balance
        # Lightweight fallback for symbols not fully supported by Bybit public API
        self.external_md = ExternalMarketData()
        self._external_symbols = {
            'XAUUSDT', 'EURUSD', 'GBPUSD', 'USDJPY'
        }
        self._symbol_supported: Dict[str, bool] = {}
        
        # Trading state
        self.is_running = False
        self.open_positions = {}  # {symbol: {position data}}

        # Position tracker (keeps a separate JSON snapshot updated every minute)
        self.position_tracker = PositionTracker(self.client, lambda: self.open_positions)
        self.position_tracker.start()
        
        # Demo logging
        self.demo_log_file = "demo_trades.csv"
        self._initialize_demo_trades_log()
        
        logger.info("✅ Demo Bot initialized successfully!")
        logger.info("=" * 70)

        # Resilience and logging
        self.backoff_seconds = 1
        self.max_backoff = 300
        self.api_error_count = 0
        
        # Time filter A/B test (optional in demo mode)
        env_toggle = os.getenv("OZZY_DEMO_TIME_FILTER", "").strip().lower()
        if env_toggle:
            demo_time_filter_enabled = env_toggle in ("1", "true", "yes", "on")
        else:
            demo_time_filter_enabled = bool(getattr(config, "DEMO_TIME_FILTER_ENABLED", False))
        if getattr(config, "PAPER_TRADING", True) and not env_toggle:
            # Default to disabled for demo/paper trading unless explicitly requested
            demo_time_filter_enabled = False
        self.time_filter = TimeFilterWrapper(
            test_name="demo_time_filter",
            avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC (low volatility)
            enabled=demo_time_filter_enabled
        )
        logger.info(f"🧪 Demo A/B Test initialized: demo_time_filter")
        logger.info(f"   Avoid hours (Test group): {self.time_filter.avoid_hours}")
        logger.info(f"   Enabled: {self.time_filter.enabled}")

    def _get_current_balance(self) -> float:
        """Get current demo balance from database"""
        conn = sqlite3.connect(self.demo_db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT current_balance FROM demo_config ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return float(result[0])
        else:
            logger.error("❌ No demo config found!")
            sys.exit(1)
    
    def _update_demo_balance(self, new_balance: float, trade_pnl: float = 0):
        """Update demo balance in database"""
        conn = sqlite3.connect(self.demo_db_path)
        cursor = conn.cursor()
        
        # Update current balance
        cursor.execute('''
            UPDATE demo_config 
            SET current_balance = ?, total_pnl = total_pnl + ?
            WHERE id = (SELECT id FROM demo_config ORDER BY id DESC LIMIT 1)
        ''', (new_balance, trade_pnl))
        
        conn.commit()
        conn.close()
        
        self.current_balance = new_balance
        # Keep risk manager capital in sync with demo balance
        if hasattr(self, "risk_manager"):
            self.risk_manager.current_capital = new_balance
        logger.info(f"💰 Demo Balance Updated: R{new_balance:,.2f} (Trade P&L: {trade_pnl:+.2f})")
    
    def _increment_trade_count(self):
        """Increment total trades counter"""
        conn = sqlite3.connect(self.demo_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE demo_config 
            SET total_trades = total_trades + 1
            WHERE id = (SELECT id FROM demo_config ORDER BY id DESC LIMIT 1)
        ''', )
        
        conn.commit()
        conn.close()
    
    def _log_demo_trade(self, symbol: str, side: str, entry_price: float, exit_price: float,
                       quantity: float, entry_time: str, exit_time: str, pnl: float,
                       pnl_percentage: float, confidence: float, rsi: float, ma_signal: str,
                       balance_after: float):
        """Log completed demo trade to database"""
        conn = sqlite3.connect(self.demo_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO demo_trades (
                symbol, side, entry_price, exit_price, quantity, entry_time, exit_time,
                pnl, pnl_percentage, status, confidence, rsi, ma_signal, balance_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?, ?, ?, ?)
        ''', (symbol, side, entry_price, exit_price, quantity, entry_time, exit_time,
              pnl, pnl_percentage, confidence, rsi, ma_signal, balance_after))
        
        conn.commit()
        conn.close()
    
    def _update_daily_summary(self):
        """Update daily summary at end of day"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect(self.demo_db_path)
        cursor = conn.cursor()
        
        # Get today's trades
        cursor.execute('''
            SELECT COUNT(*), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END),
                   MAX(pnl), MIN(pnl), SUM(pnl)
            FROM demo_trades 
            WHERE DATE(entry_time) = ?
        ''', (today,))
        
        trade_stats = cursor.fetchone()
        trades_count = trade_stats[0] or 0
        winning_trades = trade_stats[1] or 0
        losing_trades = trade_stats[2] or 0
        best_trade = trade_stats[3] or 0
        worst_trade = trade_stats[4] or 0
        daily_pnl = trade_stats[5] or 0
        
        win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0
        
        # Get starting balance for today (yesterday's ending balance)
        cursor.execute('''
            SELECT ending_balance FROM demo_daily_summary 
            WHERE date < ? ORDER BY date DESC LIMIT 1
        ''', (today,))
        
        starting_balance_result = cursor.fetchone()
        if starting_balance_result:
            starting_balance = starting_balance_result[0]
        else:
            starting_balance = 10000.0  # First day
        
        ending_balance = self.current_balance
        daily_pnl_percent = (daily_pnl / starting_balance * 100) if starting_balance > 0 else 0
        
        # Calculate min/max balance for today (simplified - use ending balance)
        max_balance = ending_balance
        min_balance = starting_balance if daily_pnl < 0 else ending_balance
        drawdown_percent = ((starting_balance - min_balance) / starting_balance * 100) if min_balance < starting_balance else 0
        
        # Insert or update daily summary
        cursor.execute('''
            INSERT OR REPLACE INTO demo_daily_summary (
                date, starting_balance, ending_balance, trades_count, winning_trades,
                losing_trades, win_rate, daily_pnl, daily_pnl_percent, best_trade,
                worst_trade, max_balance, min_balance, drawdown_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (today, starting_balance, ending_balance, trades_count, winning_trades,
              losing_trades, win_rate, daily_pnl, daily_pnl_percent, best_trade,
              worst_trade, max_balance, min_balance, drawdown_percent))
        
        conn.commit()
        conn.close()
    
    def _initialize_demo_trades_log(self):
        """Initialize CSV file for demo trade logging"""
        try:
            # Create CSV with headers if it doesn't exist
            with open(self.demo_log_file, 'x', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "entry_timestamp", "exit_timestamp", "symbol", "side",
                    "entry_price", "exit_price", "position_size", "position_value",
                    "pnl", "duration_seconds", "quality", "confidence", "balance_after",
                    "entry_reason", "exit_reason"
                ])
            logger.info(f"Created new demo trades log: {self.demo_log_file}")
        except FileExistsError:
            logger.info(f"Using existing demo trades log: {self.demo_log_file}")
    
    def _log_completed_demo_trade(self, entry_time: datetime, exit_time: datetime, symbol: str, side: str,
                                 entry_price: float, exit_price: float, position_size: float,
                                 position_value: float, pnl: float, quality: str, confidence: float,
                                 balance_after: float, entry_reason: str = "", exit_reason: str = ""):
        """Append a completed demo trade to CSV"""
        try:
            duration = int((exit_time - entry_time).total_seconds()) if entry_time and exit_time else None
            with open(self.demo_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                    exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                    symbol,
                    side,
                    round(entry_price, 6) if entry_price is not None else "",
                    round(exit_price, 6) if exit_price is not None else "",
                    position_size,
                    round(position_value, 6),
                    round(pnl, 6),
                    duration,
                    quality,
                    confidence,
                    round(balance_after, 2),
                    entry_reason,
                    exit_reason
                ])
        except Exception as e:
            logger.error(f"Failed to log completed demo trade: {e}", exc_info=True)

    def _is_symbol_supported(self, symbol: str) -> bool:
        """
        Check once whether Bybit provides candle data for this symbol.
        Caches the result to avoid repeated failing requests that cause backoff.
        """
        if symbol in self._symbol_supported:
            return self._symbol_supported[symbol]
        try:
            candles = self.client.get_candles(symbol, interval="15", limit=5)
            supported = bool(candles)
        except Exception:
            supported = False

        if supported:
            self._symbol_supported[symbol] = True
            logger.info(f"✅ Symbol supported by Bybit data source: {symbol}")
        else:
            self._symbol_supported[symbol] = False
            logger.info(f"⏭️  Skipping unsupported symbol on Bybit data source: {symbol}")
        return supported
    
    def check_signal(self, symbol: str) -> Optional[Dict]:
        """
        Check for trading signal on a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Signal dictionary or None if no signal
        """
        logger.info(f"Checking signal for {symbol}...")

        # Skip symbols that we already know are unsupported by Bybit
        if not self._is_symbol_supported(symbol) and symbol not in self._external_symbols:
            return None
        
        primary_supported = self._is_symbol_supported(symbol)

        # Get candle data from primary source when supported
        candles = None
        if primary_supported:
            candles = self.client.get_candles(symbol, interval="15", limit=50)

        # Limited fallback to external market data for FX/Gold
        if (not candles) and symbol in self._external_symbols:
            fallback = self.external_md.get_candles(symbol, interval='15', limit=50)
            if fallback:
                candles = fallback
                logger.info(f"Using external market data for {symbol}")
        if not candles:
            if not primary_supported and symbol in self._external_symbols:
                logger.warning(f"No external market data available for {symbol}; skipping until next cycle")
                return None
            logger.warning(f"Failed to get candle data for {symbol}")
            # backoff handling
            self.api_error_count += 1
            sleep_for = min(self.backoff_seconds * (2 ** (self.api_error_count - 1)), self.max_backoff)
            logger.warning(f"API error count={self.api_error_count}; sleeping for {sleep_for}s")
            time.sleep(sleep_for)
            return None
        
        # Generate signal
        signal = self.signal_generator.generate_signal(candles, symbol=symbol)
        
        # Apply time filter for A/B test
        signal, test_group = self.time_filter.apply_filter(signal, symbol)
        
        # Store test group for later use in trade execution
        signal['test_group'] = test_group
        
        # Log signal summary
        signal_emoji = "🟢" if signal["signal"] == "LONG" else "🔴" if signal["signal"] == "SHORT" else "⚪"
        logger.info(f"{signal_emoji} {signal['signal']} | {signal['quality']} | {signal['confidence']}% confidence")
        logger.info(f"Reason: {signal['reason']}")

        # reset api error counter on success
        self.api_error_count = 0

        return signal
    
    def execute_trade(self, symbol: str, signal: Dict) -> bool:
        """
        Execute a demo trade based on signal
        
        Args:
            symbol: Trading symbol
            signal: Signal dictionary
            
        Returns:
            True if trade executed successfully
        """
        logger.info(f"💼 Attempting to execute DEMO {signal['signal']} trade on {symbol}...")
        
        # Update risk manager with current demo balance
        self.risk_manager.current_capital = self.current_balance
        
        # Calculate position size based on CURRENT demo balance
        position_size, position_value = self.risk_manager.calculate_position_size(
            signal["entry_price"],
            signal["stop_loss"],
            signal["confidence"]
        )
        
        if position_size == 0:
            logger.warning("Position size is zero - demo trade aborted")
            return False
        
        # Run pre-trade checks
        approved, reason = self.risk_manager.pre_trade_checks(signal, position_value)
        
        if not approved:
            logger.warning(f"Demo trade rejected by risk manager: {reason}")
            return False
        
        # DEMO: Simulate successful order execution
        logger.info(f"📝 DEMO MODE: Simulating order execution...")
        
        # Record trade opened
        self.risk_manager.record_trade_opened(position_value)
        
        # Store position
        self.open_positions[symbol] = {
            "signal": signal,
            "position_size": position_size,
            "position_value": position_value,
            "entry_time": datetime.now(),
            "entry_price": signal["entry_price"]  # Store explicitly for demo
        }
        
        # Increment trade count
        self._increment_trade_count()
        
        # Get test group from signal and format entry reason with A/B test tag
        test_group = signal.get('test_group', 'unknown')
        entry_reason = self.time_filter.format_entry_reason(
            signal.get('reason', ''),
            test_group
        )
        
        logger.info(f"✅ DEMO Trade executed successfully!")
        logger.info(f"Position: {position_size} {symbol} @ ${signal['entry_price']:,.2f}")
        logger.info(f"Position Value: R{position_value:,.2f} (based on R{self.current_balance:,.2f} balance)")
        logger.info(f"📊 A/B Test: Assigned to {test_group.upper()} group")

        return True
    
    def monitor_positions(self):
        """Monitor and manage open demo positions"""
        if not self.open_positions:
            return
        
        logger.info(f"👁️  Monitoring {len(self.open_positions)} open DEMO position(s)...")
        
        for symbol, position in list(self.open_positions.items()):
            # Get current price
            current_price = self.client.get_current_price(symbol)
            if current_price is None:
                logger.warning(f"Could not fetch current price for {symbol}; skipping")
                continue

            signal = position.get("signal", {})
            entry_price = position.get("entry_price") or signal.get("entry_price")
            
            if entry_price is None:
                logger.warning(f"No entry price for {symbol} - skipping")
                continue

            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")
            
            # Calculate current P&L
            side = signal.get("signal")

            if side == "LONG":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                pnl_amount = (current_price - entry_price) * position.get("position_size", 0)
            else:  # SHORT
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                pnl_amount = (entry_price - current_price) * position.get("position_size", 0)

            logger.info(f"📊 DEMO {symbol}: ${current_price:,.2f} | P&L: {pnl_pct:+.2f}% (R{pnl_amount:+,.2f})")
            
            # Check stop loss
            if side == "LONG" and current_price <= stop_loss:
                logger.warning(f"🛑 DEMO Stop loss hit for {symbol}!")
                self.close_position(symbol, current_price, "STOP_LOSS")
            
            elif side == "SHORT" and current_price >= stop_loss:
                logger.warning(f"🛑 DEMO Stop loss hit for {symbol}!")
                self.close_position(symbol, current_price, "STOP_LOSS")
            
            # Check take profit
            elif side == "LONG" and current_price >= take_profit:
                logger.info(f"🎯 DEMO Take profit hit for {symbol}!")
                self.close_position(symbol, current_price, "TAKE_PROFIT")
            
            elif side == "SHORT" and current_price <= take_profit:
                logger.info(f"🎯 DEMO Take profit hit for {symbol}!")
                self.close_position(symbol, current_price, "TAKE_PROFIT")
    
    def close_position(self, symbol: str, exit_price: float, reason: str):
        """
        Close a demo position
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            reason: Reason for closing
        """
        if symbol not in self.open_positions:
            return
        
        position = self.open_positions[symbol]
        signal = position["signal"]
        entry_price = position.get("entry_price") or signal.get("entry_price")
        
        # Calculate P&L
        if signal["signal"] == "LONG":
            pnl = (exit_price - entry_price) * position["position_size"]
        else:  # SHORT
            pnl = (entry_price - exit_price) * position["position_size"]
        
        # DEMO: Simulate successful closing order
        logger.info(f"📝 DEMO MODE: Simulating closing order...")
        
        # Update demo balance
        new_balance = self.current_balance + pnl
        self._update_demo_balance(new_balance, pnl)
        
        # Record trade closed
        self.risk_manager.record_trade_closed(position["position_value"], pnl)
        
        # Log to demo database
        entry_time_str = position["entry_time"].strftime("%Y-%m-%d %H:%M:%S")
        exit_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pnl_percentage = (pnl / position["position_value"]) * 100
        
        self._log_demo_trade(
            symbol=symbol,
            side=signal["signal"],
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=position["position_size"],
            entry_time=entry_time_str,
            exit_time=exit_time_str,
            pnl=pnl,
            pnl_percentage=pnl_percentage,
            confidence=signal.get("confidence", 0),
            rsi=signal.get("technical_data", {}).get("rsi", 0),
            ma_signal=signal.get("technical_data", {}).get("ma_signal", ""),
            balance_after=new_balance
        )
        
        # Log to CSV
        self._log_completed_demo_trade(
            entry_time=position["entry_time"],
            exit_time=datetime.now(),
            symbol=symbol,
            side=signal['signal'],
            entry_price=entry_price,
            exit_price=exit_price,
            position_size=position['position_size'],
            position_value=position['position_value'],
            pnl=pnl,
            quality=signal.get('quality', ''),
            confidence=signal.get('confidence', 0.0),
            balance_after=new_balance,
            entry_reason=signal.get('reason', ''),
            exit_reason=reason
        )
        
        # Remove position
        del self.open_positions[symbol]
        
        logger.info(f"✅ DEMO Position closed: {symbol} | P&L: R{pnl:+,.2f} | Reason: {reason}")
        logger.info(f"💰 New Demo Balance: R{new_balance:,.2f}")
    
    def close_all_positions(self, reason: str = "EOD_CLOSE"):
        """Close all open demo positions"""
        if not self.open_positions:
            return
        
        logger.info(f"🔒 Closing all DEMO positions ({reason})...")
        
        for symbol in list(self.open_positions.keys()):
            current_price = self.client.get_current_price(symbol)
            if current_price:
                self.close_position(symbol, current_price, reason)

        # Stop position tracker and save final snapshot
        try:
            self.position_tracker.save_positions()
            self.position_tracker.stop()
        except Exception as e:
            logger.error(f"Error stopping position tracker: {e}", exc_info=True)
    
    def trading_loop(self):
        """Main demo trading loop"""
        logger.info("🚀 Starting DEMO trading loop...")
        logger.info(f"💰 Starting Balance: R{self.current_balance:,.2f}")
        logger.info(f"Trading symbols: {', '.join(config.TRADING_SYMBOLS)}")
        logger.info(f"Check interval: {config.CHECK_INTERVAL_MINUTES} minutes")
        
        # Display trading hours status
        if config.TRADING_HOURS['enabled']:
            logger.info(f"Trading hours: {config.TRADING_HOURS['start']:02d}:00 - {config.TRADING_HOURS['end']:02d}:00 SAST")
        else:
            logger.info("Trading hours: 24/7 (unrestricted)")
        
        logger.info("=" * 70)
        
        self.is_running = True
        last_daily_update = datetime.now().date()
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # Update daily summary if new day
                if current_time.date() > last_daily_update:
                    self._update_daily_summary()
                    last_daily_update = current_time.date()
                
                # Check if within trading hours
                is_trading_hours, _ = self.risk_manager.check_trading_hours()
                
                if is_trading_hours:
                    logger.info(f"⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} | Balance: R{self.current_balance:,.2f}")
                    
                    # Monitor existing positions
                    self.monitor_positions()
                    
                    # Check for new signals (if not at max positions)
                    if self.risk_manager.open_positions < config.MAX_POSITIONS:
                        for symbol in config.TRADING_SYMBOLS:
                            # Skip if already have position in this symbol
                            if symbol in self.open_positions:
                                continue
                            
                            # Check signal
                            signal = self.check_signal(symbol)
                            
                            if signal and signal["signal"] in ["LONG", "SHORT"]:
                                # Attempt to execute demo trade
                                self.execute_trade(symbol, signal)
                    
                    # Display risk stats
                    self.risk_manager.print_risk_stats()
                
                else:
                    # Outside trading hours
                    if config.CLOSE_POSITIONS_EOD and self.open_positions:
                        logger.info("🌙 Outside trading hours, closing all DEMO positions...")
                        self.close_all_positions("EOD_CLOSE")
                
                # Sleep until next check
                logger.info(f"💤 Sleeping for {config.CHECK_INTERVAL_MINUTES} minutes...")
                time.sleep(config.CHECK_INTERVAL_MINUTES * 60)
                
            except KeyboardInterrupt:
                logger.warning("⚠️  Keyboard interrupt received!")
                break
            except Exception as e:
                # Log and attempt to continue with exponential backoff
                logger.error(f"Error in demo trading loop: {e}", exc_info=True)
                backoff = min(self.backoff_seconds * (2 ** self.api_error_count), self.max_backoff)
                self.api_error_count += 1
                logger.warning(f"Backing off for {backoff} seconds before retrying...")
                time.sleep(backoff)
                continue
        
        # Cleanup
        logger.info("🛑 Stopping DEMO trading bot...")
        if self.open_positions:
            logger.info("Closing all open DEMO positions...")
            self.close_all_positions("BOT_STOPPED")
        
        # Final daily summary update
        self._update_daily_summary()
        
        logger.info("=" * 70)
        logger.info(f"🏁 DEMO TRADING BOT STOPPED")
        logger.info(f"💰 Final Demo Balance: R{self.current_balance:,.2f}")
        logger.info("=" * 70)
    
    def start(self):
        """Start the demo trading bot"""
        self.trading_loop()


def main():
    """Main entry point"""
    # Initialize logger first (use demo log file)
    setup_logger(log_file="demo_bot.log")
    
    # Ensure demo database exists
    demo_db_path = ensure_demo_database()
    logger.info(f"Demo database ready: {demo_db_path}")
    
    # Supervisor: restart bot if it crashes unexpectedly
    restart_delay = 5
    max_restarts = 10
    restarts = 0
    logger.info("=" * 70)
    logger.info("OZZY SIMPLE - DEMO CRYPTO TRADING BOT")
    logger.info("=" * 70)
    logger.warning("⚠️  DEMO MODE - VIRTUAL R10,000 STARTING CAPITAL")

    bot = None
    while True:
        try:
            bot = DemoOzzyBot()
            bot.start()
            # If start() returns normally, exit supervisor loop
            break

        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt received - stopping demo supervisor")
            break

        except Exception as e:
            # Unexpected crash - log and attempt restart
            logger.critical(f"Supervisor: Demo Bot crashed with: {e}", exc_info=True)
            restarts += 1
            if restarts > max_restarts:
                logger.critical("Supervisor: too many restarts, exiting")
                break
            sleep_time = restart_delay * restarts
            logger.warning(f"Supervisor: restarting demo bot in {sleep_time}s (attempt {restarts}/{max_restarts})")
            time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical("Demo Bot crashed with unhandled exception", exc_info=True)
        sys.exit(1)
