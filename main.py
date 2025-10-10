"""
OZZY SIMPLE - Main Trading Bot
Orchestrates all components and executes the trading strategy
"""

import time
import csv
import json
import sys
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


class OzzyBot:
    """
    Main trading bot that orchestrates all components.
    Checks for signals, manages risk, and executes trades.
    """
    
    def __init__(self):
        """Initialize the trading bot"""
        logger.info("=" * 70)
        logger.info("🤖 OZZY SIMPLE - AUTOMATED TRADING BOT")
        logger.info("=" * 70)
        
        # Initialize components
        logger.info("Initializing components...")
        self.client = BybitClient()
        self.signal_generator = SignalGenerator()
        self.risk_manager = RiskManager(config.STARTING_CAPITAL)
        
        # Trading state
        self.is_running = False
        self.open_positions = {}  # {symbol: {position data}}

        # Position tracker (keeps a separate JSON snapshot updated every minute)
        self.position_tracker = PositionTracker(self.client, lambda: self.open_positions)
        self.position_tracker.start()
        
        # CSV logging
        self.trades_log_file = "trades.csv"
        self._initialize_trades_log()
        
        logger.info("✅ Bot initialized successfully!")
        logger.info("=" * 70)

        # Resilience and logging
        self.backoff_seconds = 1
        self.max_backoff = 300
        self.api_error_count = 0
    
    
    def _initialize_trades_log(self):
        """Initialize CSV file for trade logging"""
        try:
            # Create CSV with headers if it doesn't exist
            # trades.csv will store completed trades only
            with open(self.trades_log_file, 'x', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "entry_timestamp", "exit_timestamp", "symbol", "side",
                    "entry_price", "exit_price", "position_size", "position_value",
                    "pnl", "duration_seconds", "quality", "confidence", "entry_reason", "exit_reason"
                ])
            logger.info(f"Created new trades log: {self.trades_log_file}")

            # signals.csv stores every generated signal (including HOLD) for ML
            self.signals_log_file = "signals.csv"
            try:
                with open(self.signals_log_file, 'x', newline='', encoding='utf-8') as f2:
                    writer2 = csv.writer(f2)
                    writer2.writerow([
                        "timestamp", "symbol", "signal", "confidence", "quality",
                        "rsi", "ema_short", "ema_long", "volume_ratio", "momentum",
                        "hour", "day_of_week", "atr_pct", "stddev_returns_pct", "reason"
                    ])
                logger.info(f"Created new signals log: {self.signals_log_file}")
            except FileExistsError:
                logger.info(f"Using existing signals log: signals.csv")
        except FileExistsError:
            logger.info(f"Using existing trades log: {self.trades_log_file}")
            # ensure signals_log_file attribute exists when file already existed
            self.signals_log_file = getattr(self, 'signals_log_file', 'signals.csv')
    
    
    def _log_trade(self, trade_data: Dict):
        """
        Log trade to CSV file
        
        Args:
            trade_data: Dictionary with trade information
        """
        # Deprecated: main now writes only completed trades via _log_completed_trade
        pass

    def _log_signal(self, symbol: str, signal: Dict):
        """Append the generated signal (including HOLD) to signals.csv for ML."""
        try:
            tech = signal.get('technical_data', {})
            ts = signal.get('timestamp') or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dt = datetime.now()
            hour = dt.hour
            day_of_week = dt.weekday()
            with open(self.signals_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    ts,
                    symbol,
                    signal.get('signal'),
                    signal.get('confidence'),
                    signal.get('quality'),
                    tech.get('rsi'),
                    tech.get('ema_short'),
                    tech.get('ema_long'),
                    tech.get('volume_ratio'),
                    tech.get('price_momentum'),
                    hour,
                    day_of_week,
                    tech.get('atr_pct'),
                    tech.get('stddev_returns_pct'),
                    signal.get('reason')
                ])
        except Exception as e:
            # best-effort logging; non-fatal
            logger.error(f"Failed to write signal to CSV: {e}", exc_info=True)

    def _log_completed_trade(self, entry_time: datetime, exit_time: datetime, symbol: str, side: str,
                             entry_price: float, exit_price: float, position_size: float,
                             position_value: float, pnl: float, quality: str, confidence: float,
                             entry_reason: str = "", exit_reason: str = ""):
        """Append a completed trade row to trades.csv"""
        try:
            duration = int((exit_time - entry_time).total_seconds()) if entry_time and exit_time else None
            with open(self.trades_log_file, 'a', newline='', encoding='utf-8') as f:
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
                    entry_reason,
                    exit_reason
                ])
        except Exception as e:
            logger.error(f"Failed to log completed trade: {e}", exc_info=True)
    
    
    def check_signal(self, symbol: str) -> Optional[Dict]:
        """
        Check for trading signal on a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Signal dictionary or None if no signal
        """
        logger.info(f"Checking signal for {symbol}...")
        
        # Get candle data
        candles = self.client.get_candles(symbol, interval="15", limit=50)
        if not candles:
            logger.warning(f"Failed to get candle data for {symbol}")
            # backoff handling
            self.api_error_count += 1
            sleep_for = min(self.backoff_seconds * (2 ** (self.api_error_count - 1)), self.max_backoff)
            logger.warning(f"API error count={self.api_error_count}; sleeping for {sleep_for}s")
            time.sleep(sleep_for)
            return None
        
        # Generate signal
        signal = self.signal_generator.generate_signal(candles)
        
        # Log signal summary
        signal_emoji = "🟢" if signal["signal"] == "LONG" else "🔴" if signal["signal"] == "SHORT" else "⚪"
        logger.info(f"{signal_emoji} {signal['signal']} | {signal['quality']} | {signal['confidence']}% confidence")
        logger.info(f"Reason: {signal['reason']}")
        
        # Log every signal (including HOLDs) for ML
        try:
            self._log_signal(symbol, signal)
        except Exception as e:
            logger.error(f"Failed to log signal: {e}", exc_info=True)

        # reset api error counter on success
        self.api_error_count = 0

        return signal
    
    
    def execute_trade(self, symbol: str, signal: Dict) -> bool:
        """
        Execute a trade based on signal
        
        Args:
            symbol: Trading symbol
            signal: Signal dictionary
            
        Returns:
            True if trade executed successfully
        """
        logger.info(f"💼 Attempting to execute {signal['signal']} trade on {symbol}...")
        
        # Calculate position size
        position_size, position_value = self.risk_manager.calculate_position_size(
            signal["entry_price"],
            signal["stop_loss"],
            signal["confidence"]
        )
        
        if position_size == 0:
            logger.warning("Position size is zero - trade aborted")
            return False
        
        # Run pre-trade checks
        approved, reason = self.risk_manager.pre_trade_checks(signal, position_value)
        
        if not approved:
            logger.warning(f"Trade rejected by risk manager: {reason}")
            
            # Log rejected trade
            self._log_trade({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "signal": signal["signal"],
                "confidence": signal["confidence"],
                "quality": signal["quality"],
                "entry_price": signal["entry_price"],
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "position_size": position_size,
                "position_value": position_value,
                "status": "REJECTED",
                "exit_price": "",
                "pnl": ""
            })
            
            return False
        
        # Place order
        side = "Buy" if signal["signal"] == "LONG" else "Sell"
        order_result = self.client.place_order(
            symbol=symbol,
            side=side,
            qty=position_size,
            order_type="Market",
            stop_loss=signal["stop_loss"],
            take_profit=signal["take_profit"]
        )
        
        if not order_result.get("success"):
            logger.error(f"Order failed: {order_result.get('message')}")
            return False
        
        # Record trade
        self.risk_manager.record_trade_opened(position_value)
        
        # Store position
        self.open_positions[symbol] = {
            "signal": signal,
            "order": order_result,
            "position_size": position_size,
            "position_value": position_value,
            "entry_time": datetime.now()
        }
        
        # Log successful trade
        self._log_trade({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "signal": signal["signal"],
            "confidence": signal["confidence"],
            "quality": signal["quality"],
            "entry_price": signal["entry_price"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "position_size": position_size,
            "position_value": position_value,
            "status": "OPENED",
            "exit_price": "",
            "pnl": ""
        })
        
        logger.info(f"✅ Trade executed successfully!")
        logger.info(f"Order ID: {order_result['order_id']}")
        logger.info(f"Position: {position_size} {symbol} @ ${signal['entry_price']:,.2f}")
        
        # Save position snapshot after opening a trade
        try:
            self.position_tracker.save_positions()
        except Exception as e:
            logger.error(f"Failed to save positions: {e}", exc_info=True)

        return True
    
    
    def monitor_positions(self):
        """Monitor and manage open positions"""
        if not self.open_positions:
            return
        
        logger.info(f"👁️  Monitoring {len(self.open_positions)} open position(s)...")
        
        for symbol, position in list(self.open_positions.items()):
            # Get current price
            current_price = self.client.get_current_price(symbol)
            if not current_price:
                continue
            
            signal = position["signal"]
            entry_price = signal["entry_price"]
            stop_loss = signal["stop_loss"]
            take_profit = signal["take_profit"]
            
            # Calculate current P&L
            if signal["signal"] == "LONG":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            pnl_amount = (current_price - entry_price) * position["position_size"]
            
            logger.info(f"{symbol}: ${current_price:,.2f} | P&L: {pnl_pct:+.2f}% (R{pnl_amount:+,.2f})")
            
            # Check stop loss
            if signal["signal"] == "LONG" and current_price <= stop_loss:
                logger.warning(f"🛑 Stop loss hit for {symbol}!")
                self.close_position(symbol, current_price, "STOP_LOSS")
            
            elif signal["signal"] == "SHORT" and current_price >= stop_loss:
                logger.warning(f"🛑 Stop loss hit for {symbol}!")
                self.close_position(symbol, current_price, "STOP_LOSS")
            
            # Check take profit
            elif signal["signal"] == "LONG" and current_price >= take_profit:
                logger.info(f"🎯 Take profit hit for {symbol}!")
                self.close_position(symbol, current_price, "TAKE_PROFIT")
            
            elif signal["signal"] == "SHORT" and current_price <= take_profit:
                logger.info(f"🎯 Take profit hit for {symbol}!")
                self.close_position(symbol, current_price, "TAKE_PROFIT")
    
    
    def close_position(self, symbol: str, exit_price: float, reason: str):
        """
        Close an open position
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            reason: Reason for closing
        """
        if symbol not in self.open_positions:
            return
        
        position = self.open_positions[symbol]
        signal = position["signal"]
        
        # Calculate P&L
        if signal["signal"] == "LONG":
            pnl = (exit_price - signal["entry_price"]) * position["position_size"]
        else:  # SHORT
            pnl = (signal["entry_price"] - exit_price) * position["position_size"]
        
        # Place closing order
        side = "Sell" if signal["signal"] == "LONG" else "Buy"
        order_result = self.client.place_order(
            symbol=symbol,
            side=side,
            qty=position["position_size"],
            order_type="Market"
        )
        
        if order_result.get("success"):
            # Record trade closed
            self.risk_manager.record_trade_closed(position["position_value"], pnl)
            
            # Log closed trade
            self._log_trade({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "signal": signal["signal"],
                "confidence": signal["confidence"],
                "quality": signal["quality"],
                "entry_price": signal["entry_price"],
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "position_size": position["position_size"],
                "position_value": position["position_value"],
                "status": reason,
                "exit_price": exit_price,
                "pnl": round(pnl, 2)
            })
            
            # Remove position
            del self.open_positions[symbol]
            
            logger.info(f"✅ Position closed: {symbol} | P&L: R{pnl:+,.2f} | Reason: {reason}")
            # Log completed trade to trades.csv
            try:
                entry_time = position.get('entry_time')
                if isinstance(entry_time, datetime):
                    et = entry_time
                else:
                    et = datetime.now()

                self._log_completed_trade(
                    entry_time=et,
                    exit_time=datetime.now(),
                    symbol=symbol,
                    side=signal['signal'],
                    entry_price=signal['entry_price'],
                    exit_price=exit_price,
                    position_size=position['position_size'],
                    position_value=position['position_value'],
                    pnl=pnl,
                    quality=signal.get('quality', ''),
                    confidence=signal.get('confidence', 0.0),
                    entry_reason=signal.get('reason', ''),
                    exit_reason=reason
                )
            except Exception as e:
                logger.error(f"Failed to log completed trade: {e}", exc_info=True)
        else:
            logger.error(f"Failed to close position: {order_result.get('message')}")

        # After any close attempt (whether successful or not), save position snapshot
        try:
            self.position_tracker.save_positions()
        except Exception as e:
            logger.error(f"Failed to save positions snapshot after close: {e}", exc_info=True)

    def save_state(self):
        """Save in-memory state (open positions, risk stats) to state.json"""
        try:
            state = {
                'open_positions': self.open_positions,
                'risk': self.risk_manager.get_risk_stats(),
                'timestamp': datetime.now().isoformat()
            }
            with open('state.json', 'w', encoding='utf-8') as f:
                json.dump(state, f, default=str, indent=2)
            logger.info("Saved state.json")
        except Exception as e:
            logger.error(f"Failed to save state.json: {e}", exc_info=True)
    
    
    def close_all_positions(self, reason: str = "EOD_CLOSE"):
        """Close all open positions"""
        if not self.open_positions:
            return
        
        logger.info(f"🔒 Closing all positions ({reason})...")
        
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
        """Main trading loop"""
        logger.info("🚀 Starting trading loop...")
        logger.info(f"Trading symbols: {', '.join(config.TRADING_SYMBOLS)}")
        logger.info(f"Check interval: {config.CHECK_INTERVAL_MINUTES} minutes")
        logger.info(f"Trading hours: {config.TRADING_START_HOUR}:00 - {config.TRADING_END_HOUR}:00 SAST")
        logger.info("=" * 70)
        
        self.is_running = True
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # Check if within trading hours
                is_trading_hours, _ = self.risk_manager.check_trading_hours()
                
                if is_trading_hours:
                    logger.info(f"⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
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
                                # Attempt to execute trade
                                self.execute_trade(symbol, signal)
                    
                    # Display risk stats
                    self.risk_manager.print_risk_stats()
                
                else:
                    # Outside trading hours
                    if config.CLOSE_POSITIONS_EOD and self.open_positions:
                        logger.info("🌙 Outside trading hours, closing all positions...")
                        self.close_all_positions("EOD_CLOSE")
                
                # Sleep until next check
                logger.info(f"💤 Sleeping for {config.CHECK_INTERVAL_MINUTES} minutes...")
                time.sleep(config.CHECK_INTERVAL_MINUTES * 60)
                
            except KeyboardInterrupt:
                logger.warning("⚠️  Keyboard interrupt received!")
                break
            except Exception as e:
                # Log and attempt to continue with exponential backoff
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                # Save state and backoff
                self.save_state()
                backoff = min(self.backoff_seconds * (2 ** self.api_error_count), self.max_backoff)
                self.api_error_count += 1
                logger.warning(f"Backing off for {backoff} seconds before retrying...")
                time.sleep(backoff)
                continue
        
        # Cleanup
        logger.info("🛑 Stopping trading bot...")
        if self.open_positions:
            logger.info("Closing all open positions...")
            self.close_all_positions("BOT_STOPPED")

        # Save state on shutdown
        try:
            self.save_state()
        except Exception as e:
            logger.error(f"Failed during final state save: {e}", exc_info=True)
        
        logger.info("=" * 70)
        logger.info("🏁 TRADING BOT STOPPED")
        logger.info("=" * 70)
    
    
    def start(self):
        """Start the trading bot"""
        self.trading_loop()


def main():
    """Main entry point"""
    # Initialize logger first
    setup_logger()
    
    # Supervisor: restart bot if it crashes unexpectedly
    restart_delay = 5
    max_restarts = 10
    restarts = 0
    logger.info("=" * 70)
    logger.info("OZZY SIMPLE - CRYPTO DAY TRADING BOT")
    logger.info("=" * 70)

    while True:
        try:
            if config.PAPER_TRADING:
                logger.warning("⚠️  PAPER TRADING MODE - NO REAL MONEY AT RISK")
            else:
                logger.critical("🚨 LIVE TRADING MODE - REAL MONEY AT RISK!")
                response = input("Are you sure you want to continue? (yes/no): ")
                if response.lower() != "yes":
                    logger.info("Exiting...")
                    return

            bot = OzzyBot()
            bot.start()
            # If start() returns normally, exit supervisor loop
            break

        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt received - stopping supervisor")
            try:
                bot.save_state()
            except Exception as e:
                logger.error(f"Failed to save state on shutdown: {e}", exc_info=True)
            break

        except Exception as e:
            # Unexpected crash - log, save state, and attempt restart
            logger.critical(f"Supervisor: Bot crashed with: {e}", exc_info=True)
            try:
                bot.save_state()
            except Exception as e2:
                logger.error(f"Failed to save state after crash: {e2}", exc_info=True)
            restarts += 1
            if restarts > max_restarts:
                logger.critical("Supervisor: too many restarts, exiting")
                break
            sleep_time = restart_delay * restarts
            logger.warning(f"Supervisor: restarting bot in {sleep_time}s (attempt {restarts}/{max_restarts})")
            time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical("Bot crashed with unhandled exception", exc_info=True)
        sys.exit(1)
