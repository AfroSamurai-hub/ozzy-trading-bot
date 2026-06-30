#!/usr/bin/env python3
"""
OZZYBOT — Virtual Shadow Trade Exit Tracker
Monitors shadow database entries in real-time, matching them against batched Binance futures
ticker prices, enforcing strict rate-limiting sleep cycles, and logging precise fee-adjusted PnLs.
"""
import sys
import os
import time
import requests
import logging
from datetime import datetime, UTC

# Allow importing from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trade_db
import telegram_client
from logger import plain_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def fetch_batched_prices() -> dict:
    """Fetch current prices of all futures symbols in a single REST request."""
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return {item["symbol"]: float(item["price"]) for item in resp.json()}
        else:
            logger.warning(f"Binance returned status code {resp.status_code}: {resp.text}")
    except Exception as err:
        logger.error(f"Error fetching batched prices from Binance: {err}")
    return {}

def track_shadow_trades():
    logger.info("Initializing OzzyBot Virtual Shadow Exit Tracker loop...")
    
    while True:
        try:
            # 1. Fetch all open shadow trades
            # Open shadow trades carry exit_price IS NULL and execution_state = 'shadow'
            with trade_db._connect() as conn:
                cur = conn.execute("SELECT * FROM trades WHERE exit_price IS NULL AND execution_state = 'shadow'")
                open_shadows = [dict(r) for r in cur.fetchall()]
                
            if open_shadows:
                # 2. Fetch batched ticker prices (Exactly ONE REST call for all pairs)
                prices = fetch_batched_prices()
                
                if prices:
                    for t in open_shadows:
                        symbol = t["symbol"]
                        direction = t["direction"]
                        entry_price = float(t["entry_price"])
                        qty = float(t["qty"])
                        sl = float(t["sl"])
                        tp = float(t["tp"])
                        trade_id = t["id"]
                        
                        curr_price = prices.get(symbol)
                        if not curr_price:
                            continue
                            
                        exit_price = None
                        exit_reason = None
                        
                        # 3. Check for SL/TP hit virtual conditions
                        if direction == "BUY":
                            if curr_price <= sl:
                                exit_price = sl
                                exit_reason = "sl"
                            elif curr_price >= tp:
                                exit_price = tp
                                exit_reason = "tp"
                        else: # SELL
                            if curr_price >= sl:
                                exit_price = sl
                                exit_reason = "sl"
                            elif curr_price <= tp:
                                exit_price = tp
                                exit_reason = "tp"
                                
                        # 4. Process virtual close
                        if exit_price and exit_reason:
                            logger.info(f"⚡ Shadow trade {trade_id} ({symbol}) hit virtual {exit_reason.upper()} level at ${exit_price:.4f}")
                            
                            # 💎 Fee Reality Check:
                            # Taker fees: 0.05% entry + 0.05% exit = 0.10% total fee
                            # Slippage: 0.02% total spread slippage
                            size_entry = entry_price * qty
                            size_exit = exit_price * qty
                            
                            # Gross PnL
                            if direction == "BUY":
                                gross_pnl = (exit_price - entry_price) * qty
                            else:
                                gross_pnl = (entry_price - exit_price) * qty
                                
                            fee_entry = size_entry * 0.0005
                            fee_exit = size_exit * 0.0005
                            slippage = size_entry * 0.0002
                            
                            total_fees_and_slippage = fee_entry + fee_exit + slippage
                            net_pnl = gross_pnl - total_fees_and_slippage
                            
                            # Calculate duration
                            try:
                                entry_dt = datetime.strptime(t["ts"], "%Y-%m-%d %H:%M:%S")
                                entry_dt = entry_dt.replace(tzinfo=UTC)
                                duration_min = int((datetime.now(UTC) - entry_dt).total_seconds() / 60)
                            except Exception:
                                duration_min = 0
                                
                            # Close the trade in trades.db
                            trade_db.close_trade(
                                trade_id=trade_id,
                                exit_price=exit_price,
                                pnl=net_pnl,
                                gross_pnl=gross_pnl,
                                fees=fee_entry + fee_exit,
                                funding=0.0,
                                exit_reason=exit_reason,
                                duration_min=duration_min
                            )
                            
                            # Force execution_state to 'shadow_closed' (close_trade sets it to 'closed' by default)
                            with trade_db._connect() as conn:
                                conn.execute("UPDATE trades SET execution_state = 'shadow_closed' WHERE id = ?", (trade_id,))
                                conn.commit()
                                
                            plain_log("SHADOW_TRADE_CLOSED", {
                                "trade_id": trade_id,
                                "symbol": symbol,
                                "direction": direction,
                                "entry": entry_price,
                                "exit": exit_price,
                                "reason": exit_reason,
                                "gross_pnl": gross_pnl,
                                "deductions": total_fees_and_slippage,
                                "net_pnl": net_pnl,
                                "duration_min": duration_min
                            })
                            
                            # Dispatch beautiful premium Telegram card
                            telegram_client.notify_shadow_exit(
                                symbol=symbol,
                                direction=direction,
                                entry=entry_price,
                                exit_price=exit_price,
                                net_pnl=net_pnl,
                                exit_reason=exit_reason,
                                setup_grade=t.get("setup_grade")
                            )
            
        except Exception as loop_err:
            logger.error(f"Error inside shadow tracker loop: {loop_err}")
            
        # 5. Enforce strict 15-second loop protection (rest rate-limiting)
        time.sleep(15)

if __name__ == "__main__":
    try:
        track_shadow_trades()
    except KeyboardInterrupt:
        logger.info("Exited by operator command.")
