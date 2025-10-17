"""
Telegram notifications for trading bot
Sends updates about test start/end, trades, and critical events
"""
import os
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading notifications via Telegram"""
    
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if self.enabled:
            logger.info("📱 Telegram notifier initialized")
        else:
            logger.info("⚠️ Telegram notifier disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env)")
    
    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram"""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("✅ Telegram message sent")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")
            return False
    
    def notify_test_start(self, duration_hours: float, symbol: str, capital: str) -> bool:
        """Notify when test starts"""
        message = f"""
🚀 <b>Trading Bot Test Started!</b>

📊 <b>Symbol:</b> {symbol}
💰 <b>Capital:</b> {capital}
⏱️ <b>Duration:</b> {duration_hours:.1f} hours
🕐 <b>Interval:</b> 15 minutes

<i>Bot is now running in background...</i>
        """.strip()
        return self.send_message(message)
    
    def notify_test_end(self, stats: dict) -> bool:
        """Notify when test completes"""
        win_rate = stats.get('win_rate', 0) * 100
        total_trades = stats.get('total_trades', 0)
        total_pnl = stats.get('total_pnl', 0)
        total_pnl_pct = stats.get('total_pnl_pct', 0)
        
        message = f"""
🏁 <b>Trading Bot Test Complete!</b>

📊 <b>Results:</b>
• Total Trades: {total_trades}
• Win Rate: {win_rate:.1f}%
• P&L: {total_pnl:+.2f} ({total_pnl_pct:+.2f}%)

<i>Check logs for detailed analysis</i>
        """.strip()
        return self.send_message(message)
    
    def notify_trade_opened(self, position: dict) -> bool:
        """Notify when position opens"""
        side = position.get('side', 'UNKNOWN')
        price = position.get('entry_price', 0)
        size = position.get('size', 0)
        confidence = position.get('confidence', 0) * 100
        
        emoji = "📈" if side == "LONG" else "📉"
        
        message = f"""
{emoji} <b>Position Opened!</b>

<b>Side:</b> {side}
<b>Price:</b> ${price:,.2f}
<b>Size:</b> ${size:,.2f}
<b>Confidence:</b> {confidence:.1f}%

<i>TP: +3.5% | SL: -1.5%</i>
        """.strip()
        return self.send_message(message)
    
    def notify_trade_closed(self, trade: dict) -> bool:
        """Notify when position closes"""
        side = trade.get('side', 'UNKNOWN')
        entry_price = trade.get('entry_price', 0)
        exit_price = trade.get('exit_price', 0)
        realized_pnl = trade.get('realized_pnl', 0)
        realized_pnl_pct = trade.get('realized_pnl_pct', 0)
        reason = trade.get('exit_reason', 'UNKNOWN')
        
        emoji = "✅" if realized_pnl > 0 else "❌"
        outcome = "WIN" if realized_pnl > 0 else "LOSS"
        
        message = f"""
{emoji} <b>Position Closed - {outcome}!</b>

<b>Side:</b> {side}
<b>Entry:</b> ${entry_price:,.2f}
<b>Exit:</b> ${exit_price:,.2f}
<b>P&L:</b> ${realized_pnl:+.2f} ({realized_pnl_pct:+.2f}%)
<b>Reason:</b> {reason}
        """.strip()
        return self.send_message(message)
    
    def notify_error(self, error_msg: str) -> bool:
        """Notify about errors"""
        message = f"""
⚠️ <b>Bot Error!</b>

<code>{error_msg}</code>

<i>Check logs for details</i>
        """.strip()
        return self.send_message(message)
    
    def notify_milestone(self, milestone: str, details: str = "") -> bool:
        """Notify about milestones (5 trades, 10 trades, etc)"""
        message = f"""
🎯 <b>Milestone Reached!</b>

{milestone}

{details}
        """.strip()
        return self.send_message(message)


# Test if run directly
if __name__ == "__main__":
    notifier = TelegramNotifier()
    if notifier.enabled:
        notifier.send_message("🤖 <b>Telegram Bot Test</b>\n\n<i>If you see this, it's working!</i>")
    else:
        print("⚠️ Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
