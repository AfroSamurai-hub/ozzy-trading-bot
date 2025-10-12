"""
Position Tracker

Saves open positions to positions.json, updates P&L in real-time, tracks duration,
calculates portfolio value, and updates the JSON file every minute.
"""
import json
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Any
from loguru import logger

from bybit_client import BybitClient
import config


class PositionTracker:
    def __init__(self, client: BybitClient, get_positions_fn: Callable[[], Dict[str, Any]],
                 file_path: str = "positions.json", update_interval: int = 60):
        """
        Args:
            client: BybitClient instance used to fetch current prices and balances
            get_positions_fn: callable that returns current open positions mapping
            file_path: path to JSON file to write
            update_interval: seconds between automatic updates
        """
        self.client = client
        self.get_positions = get_positions_fn
        self.file_path = file_path
        self.update_interval = update_interval

        self._stop_event = threading.Event()
        self._thread = None

    def _compute_unrealized(self, pos: Dict, current_price: float) -> Dict:
        qty = pos.get("position_size") or pos.get("qty") or 0
        entry_price = pos.get("entry_price") or pos.get("order", {}).get("price") or 0
        side = pos.get("signal", {}).get("signal") if isinstance(pos.get("signal"), dict) else pos.get("signal")
        # allow older position dicts where signal is nested
        if isinstance(side, dict):
            side = side.get("signal")

        if side == "LONG":
            unrealized = (current_price - entry_price) * qty
            current_value = current_price * qty
            margin = 0.0
        else:  # SHORT or unknown treated as short when side == 'SHORT'
            unrealized = (entry_price - current_price) * qty
            current_value = - (current_price * qty)
            margin = (pos.get("order", {}).get("margin") or 
                      pos.get("margin") or 
                      (pos.get("position_value", 0) * config.SHORT_MARGIN))

        return {
            "qty": qty,
            "entry_price": entry_price,
            "current_price": current_price,
            "unrealized_pnl": unrealized,
            "current_value": current_value,
            "margin": margin,
        }

    def update_positions(self) -> Dict:
        """
        Build a snapshot of positions with real-time prices, P&L, durations, and portfolio value.
        Returns the snapshot dict.
        """
        positions = self.get_positions() or {}
        snapshot = {
            "updated_at": datetime.now().isoformat(),
            "positions": {},
            "portfolio_value": None,
            "cash_balance": None
        }

        # Fetch cash balance once
        try:
            cash = self.client.get_balance() or 0.0
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}", exc_info=True)
            cash = None

        snapshot["cash_balance"] = cash

        total_unrealized = 0.0
        equity_parts = 0.0

        for symbol, pos in positions.items():
            # Expect pos to contain at least entry_price, position_size/qty, entry_time, side/signal
            # Determine current price
            try:
                current_price = self.client.get_current_price(symbol) or 0.0
            except Exception as e:
                logger.error(f"Failed to fetch current price for {symbol}: {e}", exc_info=True)
                current_price = 0.0

            # Validate current price - skip positions with invalid prices
            if current_price is None or current_price <= 0:
                logger.warning(f"Skipping position {symbol} due to invalid price: {current_price}")
                continue

            # Compute unrealized
            computed = self._compute_unrealized(pos, current_price)

            # Duration
            entry_time = pos.get("entry_time")
            if isinstance(entry_time, str):
                try:
                    entry_dt = datetime.fromisoformat(entry_time)
                except Exception as e:
                    logger.debug(f"Failed to parse entry_time '{entry_time}' for {symbol}: {e}")
                    entry_dt = None
            elif isinstance(entry_time, datetime):
                entry_dt = entry_time
            else:
                entry_dt = None

            duration_seconds = None
            if entry_dt is not None:
                duration_seconds = int((datetime.now() - entry_dt).total_seconds())

        signal = pos.get("signal") if isinstance(pos.get("signal"), dict) else {}
        stop_loss = None
        take_profit = None
        if isinstance(signal, dict):
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")

        snapshot["positions"][symbol] = {
            "symbol": symbol,
            "side": pos.get("signal", {}).get("signal") if isinstance(pos.get("signal"), dict) else pos.get("signal"),
            "qty": computed["qty"],
            "entry_price": computed["entry_price"],
            "current_price": computed["current_price"],
            "unrealized_pnl": round(computed["unrealized_pnl"], 6),
            "current_value": round(computed["current_value"], 6),
            "margin": pos.get("order", {}).get("margin") or pos.get("margin") or computed.get("margin"),
            "entry_time": entry_dt.isoformat() if entry_dt is not None else None,
            "duration_seconds": duration_seconds,
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }

        total_unrealized += computed["unrealized_pnl"]
        # For equity parts: for longs use current_value, for shorts use margin + unrealized
        side = snapshot["positions"][symbol]["side"]
        if side == "LONG":
            equity_parts += computed["current_value"]
        elif side == "SHORT":
            margin = snapshot["positions"][symbol]["margin"] or 0.0
            equity_parts += margin + computed["unrealized_pnl"]
        else:
            equity_parts += computed["current_value"]

        # Portfolio value = cash balance + equity parts
        try:
            portfolio_value = (cash or 0.0) + equity_parts
        except Exception as e:
            logger.error(f"Failed to calculate portfolio value: {e}", exc_info=True)
            portfolio_value = None

        snapshot["portfolio_value"] = round(portfolio_value, 6) if portfolio_value is not None else None

        # Write to JSON file
        try:
            with open(self.file_path, "w") as f:
                json.dump(snapshot, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to write positions to {self.file_path}: {e}", exc_info=True)

        return snapshot

    def save_positions(self):
        """Immediate save/update of positions.json"""
        return self.update_positions()

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self.update_positions()
            except Exception as e:
                logger.error(f"Error updating positions: {e}", exc_info=True)
            # Sleep in small increments to be responsive to stop events
            for _ in range(int(self.update_interval)):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
