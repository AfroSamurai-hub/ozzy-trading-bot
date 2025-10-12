#!/usr/bin/env python3
"""
Phase 2: AI-Enhanced Paper Trading Executor
Strategy: AI Optimizer (Balanced)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import sqlite3

from ozzy_ai_agent import OzzyAIAgent
import config
from loguru import logger


class Phase2Executor:
    """
    Executes paper trades based on AI Optimizer strategy
    """

    def __init__(self):
        self.ai_agent = OzzyAIAgent()
        self.paper_balance = float(getattr(config, 'STARTING_CAPITAL', 10000.0))
        self.open_positions: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self.daily_loss = 0.0
        self.trades_today = 0
        self._repaired_once = False

        self._db_path = Path(__file__).resolve().parent / "ozzy_simple.db"
        self._ensure_tables()
        self._record_phase2_start()
        self._load_open_trades_from_db()

        logger.success("🚀 PHASE 2 EXECUTOR INITIALIZED")
        logger.info(
            "   Capital: R{cap:,.2f} | Strategy: {strategy} | Risk/Trade: {risk:.2f}% | Max Daily Loss: {max_loss:.2f}%",
            cap=self.paper_balance,
            strategy="AI Optimizer (Balanced)",
            risk=getattr(config, 'RISK_PER_TRADE', 0.02) * 100,
            max_loss=getattr(config, 'MAX_DAILY_LOSS', 0.05) * 100,
        )

    def should_execute(self, base_signal: Dict[str, Any], ai_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strategy 2: AI Optimizer (Balanced)
        Execute on APPROVE + confident IMPROVE + strong CHALLENGE
        """

        action = ai_analysis.get('action')
        ai_confidence = float(ai_analysis.get('ai_confidence') or 0)
        opportunity_score = float(ai_analysis.get('opportunity_score') or 0)
        conviction = ai_analysis.get('conviction_level')

        # Check daily loss limit
        if abs(self.daily_loss) >= getattr(config, 'STARTING_CAPITAL', 10000.0) * getattr(config, 'MAX_DAILY_LOSS', 0.05):
            return {
                'execute': False,
                'reason': f"Daily loss limit reached: R{abs(self.daily_loss):.2f}"
            }

        # Check max positions
        if len(self.open_positions) >= getattr(config, 'MAX_POSITIONS', 3):
            return {
                'execute': False,
                'reason': f"Max positions reached: {getattr(config, 'MAX_POSITIONS', 3)}"
            }

        # APPROVE - Always execute
        if action == 'APPROVE' and getattr(config, 'EXECUTE_ON_APPROVE', True):
            return {
                'execute': True,
                'reason': f"AI APPROVE ({conviction} conviction)",
                'use_ai_params': False,
                'position_size_multiplier': 1.0 if conviction == 'MEDIUM' else 1.2
            }

        # IMPROVE - Execute if confident
        elif action == 'IMPROVE' and getattr(config, 'EXECUTE_ON_IMPROVE', True):
            min_conf = float(getattr(config, 'MIN_AI_CONFIDENCE_IMPROVE', 65.0))
            min_opp = float(getattr(config, 'MIN_OPPORTUNITY_SCORE_IMPROVE', 7.0))
            if ai_confidence >= min_conf and opportunity_score >= min_opp:
                improvements = ai_analysis.get('improvements', {})
                return {
                    'execute': True,
                    'reason': f"AI IMPROVE (conf:{ai_confidence:.1f}%, opp:{opportunity_score:.1f})",
                    'use_ai_params': True,
                    'improved_entry': improvements.get('entry_price'),
                    'improved_stop': improvements.get('stop_loss'),
                    'improved_target': improvements.get('take_profit'),
                    'position_size_multiplier': improvements.get('position_size_multiplier', 1.0)
                }

        # CHALLENGE - Execute if high conviction
        elif action == 'CHALLENGE' and getattr(config, 'EXECUTE_ON_CHALLENGE', True):
            min_opp = float(getattr(config, 'MIN_OPPORTUNITY_SCORE_CHALLENGE', 8.0))
            if (conviction in ['HIGH', 'EXTREME'] and opportunity_score >= min_opp):
                execution = ai_analysis.get('execution_plan', {})
                if execution.get('recommendation') == 'EXECUTE_MODIFIED':
                    improvements = ai_analysis.get('improvements', {})
                    return {
                        'execute': True,
                        'reason': f"AI CHALLENGE accepted (opp:{opportunity_score:.1f})",
                        'use_ai_params': True,
                        'improved_entry': improvements.get('entry_price'),
                        'improved_stop': improvements.get('stop_loss'),
                        'improved_target': improvements.get('take_profit'),
                        'position_size_multiplier': 1.0
                    }

        # REJECT - Don't execute
        elif action == 'REJECT':
            return {
                'execute': False,
                'reason': f"AI REJECT (conf:{ai_confidence:.1f}%)"
            }

        # Default: Don't execute
        return {
            'execute': False,
            'reason': f"AI {action} - criteria not met"
        }

    def _ensure_tables(self) -> None:
        """Make sure the paper_trades table exists."""

        try:
            with sqlite3.connect(self._db_path) as conn:
                # Meta key-value store
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS meta (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT NOT NULL,
                        value TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS paper_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        entry REAL,
                        stop REAL,
                        target REAL,
                        size REAL,
                        value REAL,
                        risk REAL,
                        ai_action TEXT,
                        ai_confidence REAL,
                        base_confidence REAL,
                        opportunity_score REAL,
                        reason TEXT,
                        status TEXT,
                        phase TEXT,
                        version TEXT,
                        exit_timestamp TEXT,
                        exit_price REAL,
                        pnl REAL
                    )
                    """
                )
                conn.commit()
        except sqlite3.Error as exc:
            logger.error(f"Failed to ensure paper_trades table: {exc}")

    def _record_phase2_start(self) -> None:
        """Record a fresh Phase 2 start timestamp to meta for dashboard filtering."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                ts = datetime.now().isoformat(timespec='seconds')
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    ("phase2_start_ts", ts)
                )
                conn.commit()
                logger.info(f"📍 Phase 2 start recorded at {ts}")
        except sqlite3.Error as exc:
            logger.warning(f"Could not record phase2_start_ts: {exc}")

    def calculate_position_size(self, entry: float, stop: float, symbol: str):
        """Calculate position size.

        Priority:
        1) If PHASE_2_USE_FIXED_POSITION, allocate fixed percent of capital.
        2) Else use risk-based sizing from stop distance.
        Also enforce optional total portfolio exposure cap.
        """

        try:
            if getattr(config, 'PHASE_2_USE_FIXED_POSITION', False):
                pct = float(getattr(config, 'PHASE_2_FIXED_POSITION_PCT', 0.30) or 0.30)
                position_value = max(self.paper_balance * pct, 0.0)
                if not entry or entry <= 0:
                    return 0.0, 0.0
                position_size = position_value / float(entry)
                return position_size, position_value
            # Risk-based sizing if fixed position is disabled
            risk_pct = float(getattr(config, 'RISK_PER_TRADE_PCT', 0.02) or 0.02)
            max_position_pct = float(getattr(config, 'MAX_POSITION_PCT', 0.20) or 0.20)
            exposure_cap = float(getattr(config, 'PORTFOLIO_EXPOSURE_CAP_PCT', 0.50) or 0.50)
            if not entry or not stop or entry <= 0 or stop <= 0:
                return 0.0, 0.0
            risk_amount = self.paper_balance * risk_pct
            stop_distance = abs(entry - stop)
            if stop_distance == 0:
                return 0.0, 0.0
            stop_distance_pct = stop_distance / entry
            position_value = risk_amount / stop_distance_pct
            # Apply per-position cap
            max_position_value = self.paper_balance * max_position_pct
            position_value = min(position_value, max_position_value)
            # Apply portfolio exposure cap
            max_exposure = self.paper_balance * exposure_cap
            if position_value > max_exposure:
                position_value = max_exposure
            position_size = position_value / entry
            return position_size, position_value
        except Exception:
            return 0.0, 0.0
        stop_distance_pct = stop_distance / float(entry)

        position_value = risk_amount / max(stop_distance_pct, 1e-9)
        position_size = position_value / float(entry)

        # Optional portfolio exposure cap (e.g., 10% of balance)
        try:
            cap_pct = float(getattr(config, 'PORTFOLIO_EXPOSURE_CAP_PCT', 0.0) or 0.0)
            if cap_pct > 0:
                cap_value = float(self.paper_balance) * cap_pct
                remaining = max(0.0, cap_value - self._current_exposure_value())
                if remaining <= 1e-9:
                    logger.info("Exposure cap reached: skipping new size", current_exposure=self._current_exposure_value(), cap=cap_value)
                    return 0.0, 0.0
                if position_value > remaining:
                    position_value = remaining
                    position_size = position_value / float(entry)
        except Exception:
            # non-fatal
            pass

        return position_size, position_value

    def execute_paper_trade(self, signal: Dict[str, Any], ai_analysis: Dict[str, Any], decision: Dict[str, Any]):
        """Execute paper trade"""

        # Determine parameters
        if decision.get('use_ai_params'):
            # Use AI-proposed params if provided; otherwise fall back to base signal
            entry = decision.get('improved_entry') or signal.get('entry_price')
            stop = decision.get('improved_stop') or signal.get('stop_loss')
            target = decision.get('improved_target') or signal.get('take_profit')
        else:
            entry = signal.get('entry_price')
            stop = signal.get('stop_loss')
            target = signal.get('take_profit')

        # Final safety: if any level is still missing, derive from entry/current price
        try:
            if not entry or float(entry) <= 0:
                entry = signal.get('entry_price')
            if not entry or float(entry) <= 0:
                # Best-effort fallback from current market; caller can pass a price fn later for repairs
                entry = float(0)
            if not stop or float(stop) <= 0:
                if entry:
                    if signal.get('action') == 'LONG':
                        stop = float(entry) * (1 - float(getattr(config, 'STOP_LOSS_PERCENT', 1.5)) / 100.0)
                    else:
                        stop = float(entry) * (1 + float(getattr(config, 'STOP_LOSS_PERCENT', 1.5)) / 100.0)
            if not target or float(target) <= 0:
                if entry:
                    if signal.get('action') == 'LONG':
                        target = float(entry) * (1 + float(getattr(config, 'TAKE_PROFIT_PERCENT', 1.5)) / 100.0)
                    else:
                        target = float(entry) * (1 - float(getattr(config, 'TAKE_PROFIT_PERCENT', 1.5)) / 100.0)
        except Exception:
            # Non-fatal; will be repaired later if still zeros
            pass

        # Calculate position size
        base_size, base_value = self.calculate_position_size(entry, stop, signal['symbol'])
        multiplier = float(decision.get('position_size_multiplier', 1.0) or 1.0)

        final_size = base_size * multiplier
        final_value = base_value * multiplier

        # Hard validation: abort trade creation if levels or size are invalid
        try:
            if not entry or float(entry) <= 0 or not stop or float(stop) <= 0 or not target or float(target) <= 0:
                logger.warning("Abort paper trade: invalid levels (entry/stop/target)", entry=entry, stop=stop, target=target)
                return None
            if not final_size or final_size <= 0 or not final_value or final_value <= 0:
                logger.warning("Abort paper trade: zero position size/value (possibly due to exposure cap)", size=final_size, value=final_value)
                return None
        except Exception:
            logger.warning("Abort paper trade: validation error on levels/size")
            return None

        # Create trade record
        trade = {
            'id': len(self.closed_trades) + len(self.open_positions) + 1,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': signal['symbol'],
            'side': signal['action'],
            'entry': entry,
            'stop': stop,
            'target': target,
            'size': final_size,
            'value': final_value,
            'risk': final_value * float(getattr(config, 'RISK_PER_TRADE', 0.02)),
            'ai_action': ai_analysis.get('action'),
            'ai_confidence': ai_analysis.get('ai_confidence'),
            'base_confidence': signal.get('confidence'),
            'opportunity_score': ai_analysis.get('opportunity_score'),
            'reason': decision['reason'],
            'status': 'OPEN',
            'phase': 'PHASE_2',
            'version': 'v1'
        }

        self.open_positions.append(trade)
        self.trades_today += 1

        db_id = self._record_trade(trade)
        if db_id is not None:
            trade['id'] = db_id

        logger.success(
            "✅ PAPER TRADE EXECUTED | #{id} {symbol} {side} | entry R{entry:.2f} | stop R{stop:.2f} | target R{target:.2f} | size {size:.4f} | value R{value:.2f} | reason: {reason}",
            id=trade['id'],
            symbol=trade['symbol'],
            side=trade['side'],
            entry=float(trade['entry'] or 0),
            stop=float(trade['stop'] or 0),
            target=float(trade['target'] or 0),
            size=trade['size'],
            value=trade['value'],
            reason=trade['reason'],
        )

        return trade

    def _load_open_trades_from_db(self) -> None:
        """Load existing OPEN Phase 2 trades into memory so we can monitor/close them."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, timestamp, symbol, side, entry, stop, target, size, value, ai_action, ai_confidence,
                           base_confidence, opportunity_score, reason
                    FROM paper_trades
                    WHERE status='OPEN' AND phase='PHASE_2'
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()

        except sqlite3.Error as exc:
            logger.warning(f"Could not load open paper trades: {exc}")
            return

        if not rows:
            return

        existing_by_id = {
            int(t['id']): t
            for t in self.open_positions
            if isinstance(t, dict) and t.get('id') is not None
        }

        loaded = 0
        for r in rows:
            (tid, ts, symbol, side, entry, stop, target, size, value,
             ai_action, ai_conf, base_conf, opp_score, reason) = r

            trade = {
                'id': int(tid),
                'timestamp': ts,
                'symbol': symbol,
                'side': side,
                'entry': float(entry or 0),
                'stop': float(stop or 0),
                'target': float(target or 0),
                'size': float(size or 0),
                'value': float(value or 0),
                'risk': float(value or 0) * float(getattr(config, 'RISK_PER_TRADE', 0.02)),
                'ai_action': ai_action,
                'ai_confidence': float(ai_conf or 0),
                'base_confidence': float(base_conf or 0),
                'opportunity_score': float(opp_score or 0),
                'reason': reason,
                'status': 'OPEN',
                'phase': 'PHASE_2',
                'version': 'v1'
            }

            if trade['id'] in existing_by_id:
                # Refresh the cached record with the latest DB snapshot
                existing_by_id[trade['id']].update(trade)
            else:
                self.open_positions.append(trade)
                loaded += 1

        if loaded:
            logger.info(f"🔄 Loaded {loaded} open Phase 2 trade(s) from DB into memory")

    def _update_trade_levels_and_size(self, trade_id: int, entry: float, stop: float, target: float,
                                      size: Optional[float] = None, value: Optional[float] = None,
                                      risk: Optional[float] = None) -> None:
        """Update levels (and optionally size/value/risk) for an existing open paper trade in DB."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                if size is None or value is None or risk is None:
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET entry = ?, stop = ?, target = ?
                        WHERE id = ? AND status = 'OPEN'
                        """,
                        (float(entry or 0), float(stop or 0), float(target or 0), int(trade_id)),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET entry = ?, stop = ?, target = ?, size = ?, value = ?, risk = ?
                        WHERE id = ? AND status = 'OPEN'
                        """,
                        (
                            float(entry or 0), float(stop or 0), float(target or 0),
                            float(size or 0), float(value or 0), float(risk or 0), int(trade_id)
                        ),
                    )
                conn.commit()
        except sqlite3.Error as exc:
            logger.error(f"Failed to update trade levels: {exc}")

    def _repair_open_trades_missing_levels(self, price_fn) -> int:
        """Backfill any OPEN Phase 2 trades that have missing entry/stop/target or zero size/value.

        Returns number of repaired trades.
        """
        repaired = 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, symbol, side, entry, stop, target, size, value
                    FROM paper_trades
                    WHERE status='OPEN' AND phase='PHASE_2'
                    """
                )
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error(f"Failed to read paper_trades for repair: {exc}")
            return 0

        for row in rows:
            trade_id, symbol, side, entry, stop, target, size, value = row
            entry = float(entry or 0)
            stop = float(stop or 0)
            target = float(target or 0)
            size = float(size or 0)
            value = float(value or 0)

            needs_levels = (entry <= 0) or (stop <= 0) or (target <= 0)
            needs_size = (size <= 0) or (value <= 0)
            if not needs_levels and not needs_size:
                continue

            # Get a current price as fallback for entry
            try:
                current_price = price_fn(symbol)
            except Exception:
                current_price = None
            if not current_price or current_price <= 0:
                continue

            if entry <= 0:
                entry = float(current_price)
            if stop <= 0:
                if side.upper() == 'LONG':
                    stop = entry * (1 - float(getattr(config, 'STOP_LOSS_PERCENT', 1.5)) / 100.0)
                else:
                    stop = entry * (1 + float(getattr(config, 'STOP_LOSS_PERCENT', 1.5)) / 100.0)
            if target <= 0:
                if side.upper() == 'LONG':
                    target = entry * (1 + float(getattr(config, 'TAKE_PROFIT_PERCENT', 1.5)) / 100.0)
                else:
                    target = entry * (1 - float(getattr(config, 'TAKE_PROFIT_PERCENT', 1.5)) / 100.0)

            if needs_size:
                # Recompute size/value based on configured sizing model
                new_size, new_value = self.calculate_position_size(entry, stop, symbol)
                size = new_size
                value = new_value
                risk = value * float(getattr(config, 'RISK_PER_TRADE', 0.02))
                self._update_trade_levels_and_size(trade_id, entry, stop, target, size, value, risk)
            else:
                self._update_trade_levels_and_size(trade_id, entry, stop, target)

            # Update in-memory trade if present
            for t in self.open_positions:
                if int(t.get('id') or 0) == int(trade_id):
                    t['entry'] = entry
                    t['stop'] = stop
                    t['target'] = target
                    if needs_size:
                        t['size'] = size
                        t['value'] = value
                        t['risk'] = value * float(getattr(config, 'RISK_PER_TRADE', 0.02))
                    break

            repaired += 1

        if repaired:
            logger.info(f"🛠️  Repaired {repaired} open paper trade(s) with missing levels/size")
        return repaired

    def _record_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        """Persist paper trade to sqlite for dashboard visibility."""

        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                        INSERT INTO paper_trades (
                            timestamp, symbol, side, entry, stop, target,
                            size, value, risk, ai_action, ai_confidence,
                            base_confidence, opportunity_score, reason, status,
                            phase, version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade['timestamp'],
                        trade['symbol'],
                        trade['side'],
                        float(trade['entry'] or 0),
                        float(trade['stop'] or 0),
                        float(trade['target'] or 0),
                        float(trade['size'] or 0),
                        float(trade['value'] or 0),
                        float(trade['risk'] or 0),
                        trade.get('ai_action'),
                        float(trade.get('ai_confidence') or 0),
                        float(trade.get('base_confidence') or 0),
                        float(trade.get('opportunity_score') or 0),
                        trade.get('reason'),
                        trade.get('status'),
                        trade.get('phase'),
                        trade.get('version'),
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as exc:
            logger.error(f"Failed to record paper trade: {exc}")
            return None

    def update_trade_exit(self, trade_id: int, exit_price: float, pnl: float):
        """Update an existing paper trade with exit details."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    UPDATE paper_trades
                    SET exit_timestamp = ?, exit_price = ?, pnl = ?, status = 'CLOSED'
                    WHERE id = ?
                    """,
                    (
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        float(exit_price or 0),
                        float(pnl or 0),
                        int(trade_id),
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            logger.error(f"Failed to update paper trade exit: {exc}")

    def process_signal(self, base_signal: Dict[str, Any]):
        """Main entry point: Process signal with AI and execute if approved"""

        # Prefer conservative AI validator output if present on base_signal
        ai_analysis: Dict[str, Any]
        if base_signal.get('ai_recommendation'):
            rec = str(base_signal.get('ai_recommendation') or '').upper()
            ai_analysis = {
                'action': 'APPROVE' if rec == 'APPROVE' else ('IMPROVE' if rec == 'MODIFY' else ('REJECT' if rec == 'REJECT' else rec)),
                'ai_confidence': float(base_signal.get('ai_confidence') or 0),
                'opportunity_score': float(base_signal.get('confidence') or 0) / 10.0,
                'conviction_level': 'MEDIUM'
            }
            # Minimal improvements passthrough
            ai_analysis['improvements'] = {}
        else:
            # Fallback to ambitious AI agent analysis
            ai_analysis = self.ai_agent.analyze_signal(base_signal)

        # Check if should execute
        decision = self.should_execute(base_signal, ai_analysis)

        # Execute if approved
        if decision.get('execute'):
            trade = self.execute_paper_trade(base_signal, ai_analysis, decision)
            return trade
        else:
            logger.info(
                "⏭️  PAPER TRADE SKIPPED | {symbol} {side} | reason: {reason}",
                symbol=base_signal.get('symbol'),
                side=base_signal.get('action'),
                reason=decision['reason'],
            )
            return None

    def monitor_open_positions(self, price_fn) -> None:
        """Monitor open paper positions and close on TP/SL hits.

        price_fn: callable(symbol) -> current price (float)
        """
        if not self.open_positions:
            return

        for trade in list(self.open_positions):
            symbol = trade['symbol']
            side = trade['side']  # 'LONG' or 'SHORT'
            try:
                price = price_fn(symbol)
            except Exception:
                price = None
            if price is None:
                continue

            entry = float(trade.get('entry') or 0)
            stop = float(trade.get('stop') or 0)
            target = float(trade.get('target') or 0)
            size = float(trade.get('size') or 0)

            hit = None
            if side == 'LONG':
                if stop and price <= stop:
                    hit = 'STOP_LOSS'
                elif target and price >= target:
                    hit = 'TAKE_PROFIT'
            else:  # SHORT
                if stop and price >= stop:
                    hit = 'STOP_LOSS'
                elif target and price <= target:
                    hit = 'TAKE_PROFIT'

            if not hit:
                continue

            # Calculate PnL
            if side == 'LONG':
                pnl = (price - entry) * size
            else:
                pnl = (entry - price) * size

            # Update stats and balance
            self.paper_balance += pnl
            self.daily_loss += pnl

            # Persist
            self.update_trade_exit(trade['id'], price, pnl)

            # Move to closed and remove from open list
            trade['status'] = 'CLOSED'
            trade['exit_price'] = price
            trade['pnl'] = pnl
            trade['exit_reason'] = hit
            trade['exit_timestamp'] = datetime.now().isoformat(timespec='seconds')
            self.closed_trades.append(trade)
            self.open_positions.remove(trade)

            logger.success(
                "✅ PAPER TRADE CLOSED | #{id} {symbol} {side} | exit R{exit:.2f} | P&L R{pnl:+.2f} | {reason}",
                id=trade['id'], symbol=symbol, side=side, exit=price, pnl=pnl, reason=hit
            )

    def warmup(self, price_fn) -> None:
        """Run one-time repairs for legacy rows and ensure in-memory cache is loaded."""
        if self._repaired_once:
            return
        try:
            # load again in case init occurred before DB had rows
            self._load_open_trades_from_db()
        except Exception:
            logger.debug("Warmup: load open trades failed", exc_info=True)
        try:
            repaired = self._repair_open_trades_missing_levels(price_fn)
            if repaired:
                # After repair, refresh memory snapshot to reflect repaired sizes/levels
                self.open_positions.clear()
                self._load_open_trades_from_db()
        except Exception:
            logger.debug("Warmup: repair failed", exc_info=True)
        self._repaired_once = True

    def _current_exposure_value(self) -> float:
        return sum(float(t.get('value') or 0.0) for t in self.open_positions if t.get('status') == 'OPEN')

    def enforce_max_positions(self, price_fn, max_positions: Optional[int] = None) -> int:
        """Close worst-performing open positions until count <= max_positions.

        Returns number of positions closed.
        """
        max_positions = int(max_positions or getattr(config, 'MAX_POSITIONS', 3))
        if len(self.open_positions) <= max_positions:
            return 0

        scored: List[Any] = []
        for t in list(self.open_positions):
            symbol = t.get('symbol')
            side = (t.get('side') or '').upper()
            entry = float(t.get('entry') or 0)
            size = float(t.get('size') or 0)
            if not symbol or entry <= 0 or size <= 0:
                continue
            try:
                price = price_fn(symbol)
            except Exception:
                price = None
            if price is None:
                continue
            pnl = (price - entry) * size if side == 'LONG' else (entry - price) * size
            scored.append((pnl, t, price))

        if not scored:
            return 0

        scored.sort(key=lambda x: x[0])  # worst first
        excess = len(self.open_positions) - max_positions
        closed = 0
        for i in range(min(excess, len(scored))):
            pnl, t, price = scored[i]
            self.update_trade_exit(t['id'], price, pnl)
            self.paper_balance += pnl
            self.daily_loss += pnl
            t['status'] = 'CLOSED'
            t['exit_price'] = price
            t['pnl'] = pnl
            t['exit_reason'] = 'MAX_POSITIONS_ENFORCEMENT'
            t['exit_timestamp'] = datetime.now().isoformat(timespec='seconds')
            self.closed_trades.append(t)
            try:
                self.open_positions.remove(t)
            except ValueError:
                pass
            logger.warning(
                "🔒 MAX_POSITIONS ENFORCEMENT | Closed #{id} {sym} {side} | P&L R{pnl:+.2f}",
                id=t['id'], sym=t['symbol'], side=t['side'], pnl=pnl
            )
            closed += 1

        return closed

    def get_stats(self) -> Dict[str, Any]:
        """Get current stats"""

        total_trades = len(self.closed_trades)
        if total_trades == 0:
            win_rate = 0
            total_pnl = 0
        else:
            wins = sum(1 for t in self.closed_trades if t['pnl'] > 0)
            win_rate = wins / total_trades * 100
            total_pnl = sum(t['pnl'] for t in self.closed_trades)

        return {
            'capital': self.paper_balance,
            'open_positions': len(self.open_positions),
            'total_trades': total_trades,
            'trades_today': self.trades_today,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'daily_loss': self.daily_loss,
            'roi': (total_pnl / getattr(config, 'STARTING_CAPITAL', 10000.0) * 100) if total_trades > 0 else 0
        }

    def print_stats(self) -> None:
        """Print current statistics"""

        stats = self.get_stats()

        print("\n" + "="*70)
        print("📊 PHASE 2 STATISTICS")
        print("="*70)
        print(f"Capital: R{stats['capital']:,.2f}")
        print(f"Total P&L: R{stats['total_pnl']:+,.2f} ({stats['roi']:+.2f}%)")
        print(f"Open Positions: {stats['open_positions']}/{getattr(config,'MAX_POSITIONS',3)}")
        print(f"Completed Trades: {stats['total_trades']}")
        print(f"Trades Today: {stats['trades_today']}")
        print(f"Win Rate: {stats['win_rate']:.1f}%")
        print(f"Daily Loss: R{stats['daily_loss']:+,.2f}")
        print("="*70 + "\n")

    # Optional helper for simulated closing based on TP/SL would go here if we later add price polling.


if __name__ == "__main__":
    print(
        """
╔═══════════════════════════════════════════════════════════════════╗
║                    PHASE 2 EXECUTOR READY                         ║
║                                                                   ║
║  Add this to your main.py:                                        ║
║                                                                   ║
║  from phase2_executor import Phase2Executor                       ║
║  self.phase2_executor = Phase2Executor()                          ║
║                                                                   ║
║  In signal processing loop:                                       ║
║  trade = self.phase2_executor.process_signal(signal_payload)      ║
╚═══════════════════════════════════════════════════════════════════╝
    """
    )
