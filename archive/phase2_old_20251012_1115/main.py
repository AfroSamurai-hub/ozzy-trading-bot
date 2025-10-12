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
try:
    from bybit_client_optimized import CachedBybitClient  # type: ignore
except Exception:
    CachedBybitClient = None
from signal_generator import SignalGenerator
from risk_manager import RiskManager
from position_tracker import PositionTracker
from logger_config import setup_logger
import db
from time_filter_wrapper import TimeFilterWrapper
from ai_signal_validator import AISignalValidator
from external_market_data import ExternalMarketData
try:
    from phase2_executor import Phase2Executor  # type: ignore
except Exception:
    Phase2Executor = None
try:
    # Adaptive position sizing (feature-flagged)
    from adaptive_position_manager import DynamicAdaptivePositionManager  # type: ignore
except Exception:
    DynamicAdaptivePositionManager = None
try:
    # Optional ambitious AI agent; enabled via config.AMBITIOUS_AI
    from ozzy_ai_agent import OzzyAIAgent  # type: ignore
except Exception:
    OzzyAIAgent = None  # fallback if agent not present


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
        # Use optimized client if enabled and available; else default client
        if getattr(config, 'OPTIMIZED_BYBIT_CLIENT', False) and CachedBybitClient is not None:
            logger.info("🧠 Using optimized Bybit client (caching + rate limiting)")
            self.client = CachedBybitClient()
        else:
            self.client = BybitClient()
        self.signal_generator = SignalGenerator()
        self.risk_manager = RiskManager(config.STARTING_CAPITAL)
        self.external_md = ExternalMarketData()
        # Adaptive sizing manager (optional)
        self.adaptive_manager = None
        if getattr(config, 'ADAPTIVE_SIZING_ENABLED', False) and DynamicAdaptivePositionManager is not None:
            try:
                self.adaptive_manager = DynamicAdaptivePositionManager(getattr(config, 'STARTING_CAPITAL', 5000))
                logger.info("🧮 Adaptive Position Manager enabled")
            except Exception as e:
                logger.warning(f"Adaptive manager init failed: {e}")
        
        # Trading state
        self.is_running = False
        self.open_positions = {}  # {symbol: {position data}}
        # Cache to track if a symbol is supported by current market data source
        self._symbol_supported = {}  # type: Dict[str, bool]

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
        
        # Time filter A/B test (disabled by default; enable via config.TIME_FILTER_ENABLED)
        self.time_filter = TimeFilterWrapper(
            test_name="time_filter_night",
            avoid_hours=getattr(config, 'TIME_FILTER_AVOID_WINDOWS', [(22, 2)]),
            enabled=bool(getattr(config, 'TIME_FILTER_ENABLED', False))
        )
        logger.info("🧪 A/B Test initialized: time_filter_night")
        logger.info(f"   Avoid hours (Test group): {self.time_filter.avoid_hours}")
        logger.info(f"   Enabled: {self.time_filter.enabled}")

        # Safety overrides (circuit breakers for Phase 3+)
        self.safety = SafetyOverride(self.client)
        
        # AI Signal Validator (Phase 1.5 - AI Integration)
        try:
            self.ai_validator = AISignalValidator()
            self.ai_enabled = True
            logger.info("🤖 AI Signal Validator initialized - Phase 1.5 active!")
        except Exception as e:
            logger.warning(f"AI validator failed to initialize: {e}")
            self.ai_enabled = False

        # Ambitious AI Agent (optional Phase 1.5+ - goal-driven partner)
        self.ai_agent_enabled = False
        if OzzyAIAgent is not None and getattr(config, 'AMBITIOUS_AI', False):
            try:
                self.ai_agent = OzzyAIAgent()
                self.ai_agent_enabled = True
                logger.info("🔥 Ambitious AI Agent initialized - Goal-driven mode ON")
            except Exception as e:
                logger.warning(f"Ambitious AI init failed: {e}")

        # Phase 2 paper trading executor (enabled when not in monitor-only)
        self.phase2_executor = None
        if not getattr(config, 'MONITOR_ONLY_MODE', True) and Phase2Executor is not None:
            try:
                self.phase2_executor = Phase2Executor()
                logger.info("✅ Phase 2 Executor initialized")
                # One-time warmup/repair and memory load
                try:
                    self.phase2_executor.warmup(self.client.get_current_price)
                except Exception:
                    logger.debug("Phase 2 warmup failed", exc_info=True)
            except Exception as e:
                logger.warning(f"Phase 2 executor init failed: {e}")

    def _is_symbol_supported(self, symbol: str) -> bool:
        """Test once whether a symbol provides candles on current market data source.

        Caches the result to avoid repeated failing calls for unsupported symbols
        (e.g., some FX pairs on current venue)."""
        if symbol in self._symbol_supported:
            return self._symbol_supported[symbol]
        try:
            candles = self.client.get_candles(symbol, interval="15", limit=5)
            ok = bool(candles)
            if ok:
                # Cache only positive support to avoid perma-blacklisting on transient API errors
                self._symbol_supported[symbol] = True
                logger.info(f"✅ Symbol supported: {symbol}")
                return True
            else:
                logger.info(f"⏭️  Skipping unsupported symbol on data source: {symbol}")
                return False
        except Exception:
            logger.info(f"⏭️  Skipping unsupported symbol on data source: {symbol}")
            return False
    
    
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
        # Also write to SQLite (best-effort) using high-level API
        try:
            tech = signal.get('technical_data', {})
            dt = datetime.now()
            db.log_signal({
                'timestamp': signal.get('timestamp') or dt.strftime("%Y-%m-%d %H:%M:%S"),
                'symbol': symbol,
                'signal': signal.get('signal'),
                'confidence': signal.get('confidence'),
                'quality': signal.get('quality'),
                'rsi': tech.get('rsi'),
                'ema_short': tech.get('ema_short'),
                'ema_long': tech.get('ema_long'),
                'volume_ratio': tech.get('volume_ratio'),
                'momentum': tech.get('price_momentum'),
                'hour': dt.hour,
                'day_of_week': dt.weekday(),
                'atr_pct': tech.get('atr_pct'),
                'stddev_returns_pct': tech.get('stddev_returns_pct'),
                'reason': signal.get('reason')
            })
        except Exception:
            # non-fatal if DB write fails
            logger.debug("DB write for signal failed", exc_info=True)

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
        # DB write handled via log_trade_open/log_trade_close lifecycle elsewhere
    
    
    def check_signal(self, symbol: str) -> Optional[Dict]:
        """
        Check for trading signal on a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Signal dictionary or None if no signal
        """
        logger.info(f"Checking signal for {symbol}...")
        
        # Get candle data (Bybit first; fallback to external for FX/Gold in monitor-only)
        candles = self.client.get_candles(symbol, interval="15", limit=50)
        if not candles and getattr(config, 'MONITOR_ONLY_MODE', False):
            # External adapter supports XAU/FX; safe for monitoring
            candles = self.external_md.get_candles(symbol, interval='15', limit=50)
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
        
        # Apply time filter for A/B test
        signal, test_group = self.time_filter.apply_filter(signal, symbol)
        
        # Store test group for later use in trade execution
        signal['test_group'] = test_group
        
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
        position_size = None
        position_value = None
        use_adaptive = (
            getattr(config, 'ADAPTIVE_SIZING_ENABLED', False)
            and self.adaptive_manager is not None
            and signal.get('signal') in ['LONG', 'SHORT']
        )

        if use_adaptive:
            # Map confidence to tier buckets used by dashboard
            conf = float(signal.get('confidence', 0.0) or 0.0)
            if conf >= 45:
                tier = 'T1'
            elif conf >= 35:
                tier = 'T2'
            else:
                tier = 'T3'

            # Get capital from risk manager for session accuracy
            current_capital = getattr(self.risk_manager, 'current_capital', getattr(config, 'STARTING_CAPITAL', 5000))
            try:
                pos_info = self.adaptive_manager.calculate_position_size(tier, current_capital=current_capital)
                # Convert currency position (R) into exchange quantity based on entry price
                entry_price = float(signal["entry_price"]) if signal.get("entry_price") else None
                if not entry_price or entry_price <= 0:
                    raise ValueError("Invalid entry price for adaptive sizing")
                position_value = float(pos_info['position_size'])
                position_size = position_value / entry_price
                logger.info(
                    "Adaptive sizing: tier=%s value=R%.2f qty=%.6f (cap R%.2f)",
                    tier, position_value, position_size, current_capital
                )
            except Exception as e:
                logger.warning(f"Adaptive sizing failed, falling back: {e}")

        if position_size is None or position_value is None:
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
        # Persist an 'open' trade record in DB and store its id for later updates
        try:
            # Get test group from signal and format entry reason with A/B test tag
            test_group = signal.get('test_group', 'unknown')
            entry_reason = self.time_filter.format_entry_reason(
                signal.get('reason', ''),
                test_group
            )
            
            db_id = db.log_trade_open({
                'entry_timestamp': self.open_positions[symbol]['entry_time'].strftime("%Y-%m-%d %H:%M:%S"),
                'symbol': symbol,
                'side': signal["signal"],
                'entry_price': signal["entry_price"],
                'position_size': position_size,
                'position_value': position_value,
                'quality': signal.get('quality', ''),
                'confidence': signal.get('confidence', 0.0),
                'entry_reason': entry_reason  # Tagged with test group
            })
            self.open_positions[symbol]['db_trade_id'] = db_id
            
            # Log test group assignment
            logger.info(f"📊 A/B Test: Assigned to {test_group.upper()} group")
        except Exception:
            logger.debug("Failed to persist trade open to DB", exc_info=True)

        # Log successful trade (CSV fallback)
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
            if current_price is None and getattr(config, 'MONITOR_ONLY_MODE', False):
                # Best-effort external price for FX/Gold
                try:
                    current_price = self.external_md.get_current_price(symbol)
                except Exception:
                    current_price = None
            if current_price is None:
                logger.warning(f"Could not fetch current price for {symbol}; skipping")
                continue

            signal = position.get("signal", {})
            # Determine entry price: prefer explicitly stored entry in position or signal, else order price
            entry_price = None
            entry_source = None
            # If signal is a dict and contains entry_price, use it
            if isinstance(signal, dict) and signal.get("entry_price"):
                entry_price = float(signal.get("entry_price"))
                entry_source = "signal.entry_price"
            # Else, check if order price present (from place_order)
            elif position.get("order") and position["order"].get("price"):
                try:
                    entry_price = float(position["order"].get("price"))
                    entry_source = "order.price"
                except Exception:
                    entry_price = None
            # Else, check if we stored entry_price directly on position
            elif position.get("entry_price"):
                entry_price = float(position.get("entry_price"))
                entry_source = "position.entry_price"
            else:
                # Last resort: try position value / size to infer price
                try:
                    entry_price = float(position.get("position_value", 0)) / float(position.get("position_size", 1))
                    entry_source = "inferred"
                except Exception:
                    entry_price = None
                    entry_source = "unknown"

            if entry_price is None or entry_price == 0:
                logger.warning(f"Invalid entry price for {symbol} (source={entry_source}) - skipping")
                continue

            stop_loss = None
            take_profit = None
            if isinstance(signal, dict):
                stop_loss = signal.get("stop_loss")
                take_profit = signal.get("take_profit")
            else:
                stop_loss = position.get("stop_loss")
                take_profit = position.get("take_profit")
            
            # Calculate current P&L
            side = None
            if isinstance(signal, dict):
                side = signal.get("signal")
            else:
                side = position.get("side") or position.get("signal")

            if side == "LONG":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                pnl_amount = (current_price - entry_price) * position.get("position_size", 0)
            else:  # SHORT
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                pnl_amount = (entry_price - current_price) * position.get("position_size", 0)

            logger.debug(f"{symbol} debug: entry_source={entry_source} entry_price={entry_price} current_price={current_price} size={position.get('position_size')} ")
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
            
            # Update DB trade row if we have the id
            try:
                db_id = position.get('db_trade_id')
                if db_id is not None:
                    exit_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    db.log_trade_close(db_id, exit_ts, exit_price, pnl, reason)
            except Exception:
                logger.debug("Failed to update DB trade close", exc_info=True)

            # Log closed trade (CSV fallback)
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
            # Record into safety override
            try:
                self.safety.record_trade(pnl)
            except Exception:
                logger.debug("Safety override record_trade failed", exc_info=True)
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
        
        # Display trading hours status
        if config.TRADING_HOURS['enabled']:
            logger.info(f"Trading hours: {config.TRADING_HOURS['start']:02d}:00 - {config.TRADING_HOURS['end']:02d}:00 SAST")
        else:
            logger.info("Trading hours: 24/7 (unrestricted)")
        
        logger.info("=" * 70)
        
        self.is_running = True
        
        while self.is_running:
            try:
                current_time = datetime.now()

                # Safety check: halt trading if circuit-breakers triggered
                try:
                    if not self.safety.check_safety():
                        logger.critical("🛑 TRADING HALTED - Safety override triggered")
                        break
                except Exception:
                    logger.debug("Safety override check failed", exc_info=True)
                
                # Check if within trading hours
                is_trading_hours, _ = self.risk_manager.check_trading_hours()
                
                if is_trading_hours:
                    logger.info(f"⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Monitor existing positions only when actually trading
                    if not getattr(config, 'MONITOR_ONLY_MODE', False):
                        self.monitor_positions()
                        # Also monitor Phase 2 paper trades (if enabled)
                        if self.phase2_executor is not None:
                            try:
                                self.phase2_executor.monitor_open_positions(self.client.get_current_price)
                            except Exception:
                                logger.debug("Phase 2 monitor failed", exc_info=True)
                    
                    # Check for new signals (if not at max positions)
                    if self.risk_manager.open_positions < config.MAX_POSITIONS:
                        for symbol in config.TRADING_SYMBOLS:
                            # Skip symbols not supported by current data source (only in live/trade mode).
                            # In monitor-only, allow symbols that may be supplied by the external adapter (FX/Gold).
                            if not getattr(config, 'MONITOR_ONLY_MODE', False):
                                if not self._is_symbol_supported(symbol):
                                    continue
                            # Skip if already have position in this symbol
                            if symbol in self.open_positions and not getattr(config, 'MONITOR_ONLY_MODE', False):
                                continue

                            # Check signal
                            signal = self.check_signal(symbol)

                            # NEW: AI Signal Validation (Phase 1.5)
                            if signal and signal.get('signal') in ['LONG', 'SHORT']:
                                # Conservative validator (existing)
                                if self.ai_enabled:
                                    try:
                                        logger.info(f"🤖 Requesting AI analysis for {symbol} {signal['signal']}...")
                                        # Include symbol (and flatten key tech metrics) so DB rows don't show UNKNOWN
                                        ai_payload = dict(signal)
                                        ai_payload['symbol'] = symbol
                                        rsi_val = signal.get('technical_data', {}).get('rsi') if isinstance(signal.get('technical_data'), dict) else None
                                        if rsi_val is not None:
                                            ai_payload['rsi'] = rsi_val
                                        ai_analysis = self.ai_validator.validate_signal(ai_payload)
                                        # Store on signal for logs/monitoring
                                        signal['ai_recommendation'] = ai_analysis.get('recommendation')
                                        signal['ai_confidence'] = ai_analysis.get('ai_confidence')
                                        signal['ai_agrees'] = ai_analysis.get('agreement')
                                    except Exception as e:
                                        logger.warning(f"AI validation error: {e}")

                                # Ambitious agent (optional, parallel analysis)
                                if self.ai_agent_enabled:
                                    try:
                                        logger.info(f"🔥 OZZY AI AGENT analyzing {symbol} {signal['signal']} (ambitious mode)...")
                                        _ = self.ai_agent.analyze_signal({
                                            'symbol': symbol,
                                            'action': signal.get('signal'),
                                            'confidence': signal.get('confidence'),
                                            'quality': signal.get('quality'),
                                            'entry_price': signal.get('entry_price'),
                                            'stop_loss': signal.get('stop_loss'),
                                            'take_profit': signal.get('take_profit'),
                                            'risk_reward_ratio': signal.get('risk_reward_ratio'),
                                            # Optional technicals mapping if present
                                            'rsi': signal.get('technical_data', {}).get('rsi'),
                                            'ema_trend': f"{signal.get('technical_data', {}).get('ema_short')}/{signal.get('technical_data', {}).get('ema_long')}",
                                            'volume_ratio': signal.get('technical_data', {}).get('volume_ratio'),
                                            'momentum': signal.get('technical_data', {}).get('price_momentum'),
                                        })
                                    except Exception as e:
                                        logger.warning(f"Ambitious AI analysis failed: {e}")

                            # Phase 2: when not monitor-only, execute paper trades via Phase2Executor
                            if not getattr(config, 'MONITOR_ONLY_MODE', False) and self.phase2_executor is not None:
                                executed_by_phase2 = False
                                if signal and signal.get('signal') in ['LONG', 'SHORT']:
                                    # Build payload for Phase2Executor
                                    payload = {
                                        'symbol': symbol,
                                        'action': signal.get('signal'),
                                        'confidence': signal.get('confidence'),
                                        'quality': signal.get('quality'),
                                        'entry_price': signal.get('entry_price'),
                                        'stop_loss': signal.get('stop_loss'),
                                        'take_profit': signal.get('take_profit'),
                                        'risk_reward_ratio': signal.get('risk_reward_ratio'),
                                        'technical_data': signal.get('technical_data') or {},
                                        # Include conservative AI validator outputs if present
                                        'ai_recommendation': signal.get('ai_recommendation'),
                                        'ai_confidence': signal.get('ai_confidence'),
                                        'ai_agreement': signal.get('ai_agrees')
                                    }
                                    try:
                                        phase2_trade = self.phase2_executor.process_signal(payload)
                                        executed_by_phase2 = phase2_trade is not None
                                        if executed_by_phase2:
                                            try:
                                                self.phase2_executor.enforce_max_positions(self.client.get_current_price)
                                            except Exception:
                                                logger.debug("Phase 2 enforce_max_positions failed", exc_info=True)
                                    except Exception:
                                        logger.warning("Phase 2 executor failed to process signal", exc_info=True)
                                if executed_by_phase2:
                                    # Phase 2 handled execution, skip legacy path to avoid duplicates
                                    continue

                            # Monitor-only fallback: just log
                            if getattr(config, 'MONITOR_ONLY_MODE', False):
                                if signal and signal.get('signal') in ['LONG', 'SHORT']:
                                    ai_tag = ""
                                    if self.ai_enabled and signal.get('ai_recommendation'):
                                        ai_tag = f" AI:{signal['ai_recommendation']}"
                                    if self.ai_agent_enabled:
                                        ai_tag += " | AGENT:ON"
                                    logger.info(f"📊 MONITOR: {symbol} {signal['signal']} conf={signal['confidence']}% entry=${signal['entry_price']}{ai_tag}")
                                continue

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


class SafetyOverride:
    """Circuit breakers for live trading phases.

    - Daily loss limit in currency
    - Consecutive losses threshold
    - Account drawdown threshold vs STARTING_CAPITAL
    """

    def __init__(self, client: BybitClient):
        self.client = client
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_reset = datetime.now().date()

    def _maybe_reset(self):
        today = datetime.now().date()
        if today > self.last_reset:
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.last_reset = today

    def check_safety(self) -> bool:
        self._maybe_reset()

        # Daily loss limit
        try:
            daily_limit = getattr(config, 'DAILY_LOSS_LIMIT', None)
            daps_limit = getattr(config, 'ABSOLUTE_DAILY_LOSS_LIMIT', None)
            if daily_limit is not None and daps_limit is not None:
                daily_limit = min(float(daily_limit), float(daps_limit))
            if daily_limit is not None and self.daily_pnl <= -float(daily_limit):
                logger.error("🚨 EMERGENCY STOP: Daily loss limit reached",
                             daily_pnl=f"R{self.daily_pnl:,.2f}", limit=f"R{daily_limit:,.2f}")
                return False
        except Exception:
            pass

        # Consecutive losses
        try:
            max_losses = getattr(config, 'MAX_CONSECUTIVE_LOSSES', 3)
            if self.consecutive_losses >= int(max_losses):
                logger.error("🚨 EMERGENCY STOP: Too many consecutive losses",
                             count=self.consecutive_losses)
                return False
        except Exception:
            pass

        # Account drawdown (only relevant for live trading with real API keys)
        try:
            if not getattr(config, 'PAPER_TRADING', True) and not getattr(config, 'MONITOR_ONLY_MODE', False):
                balance = self.client.get_balance() or 0.0
                baseline = float(getattr(config, 'STARTING_CAPITAL', 0.0))
                if baseline and balance and balance < baseline * 0.80:
                    logger.error("🚨 EMERGENCY STOP: Account down 20%",
                                 balance=f"R{balance:,.2f}", baseline=f"R{baseline:,.2f}")
                    return False
        except Exception:
            # In monitor-only mode or without valid API keys, skip balance check
            if not getattr(config, 'MONITOR_ONLY_MODE', False):
                logger.debug("Balance check failed, but continuing in monitor mode")
            pass

        return True

    def record_trade(self, pnl: float) -> None:
        self._maybe_reset()
        self.daily_pnl += float(pnl or 0.0)
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0


def main():
    """Main entry point"""
    # Initialize logger first
    setup_logger()
    # Initialize DB schema
    try:
        db.create_tables()
    except Exception as e:
        logger.error(f"Failed to initialize DB schema: {e}")
    
    # Supervisor: restart bot if it crashes unexpectedly
    restart_delay = 5
    max_restarts = 10
    restarts = 0
    logger.info("=" * 70)
    logger.info("OZZY SIMPLE - CRYPTO DAY TRADING BOT")
    logger.info("=" * 70)

    bot = None
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
                if bot:
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
