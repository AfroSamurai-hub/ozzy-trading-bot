"""
Slack notification system for trading alerts
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send trading alerts to Slack"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)
        
        if not self.enabled:
            logger.warning("Slack notifications disabled: no webhook URL configured")
    
    def send_message(self, text: str, blocks: Optional[list] = None) -> bool:
        """Send a message to Slack"""
        if not self.enabled:
            return False
        
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    def notify_position_opened(
        self,
        symbol: str,
        entry_price: float,
        size: float,
        confidence: float,
        reason: str
    ) -> bool:
        """Notify when a new position is opened"""
        text = f"🟢 Position Opened: {symbol}"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🟢 Position Opened: {symbol}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Entry Price:*\n${entry_price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Position Size:*\n${size:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:*\n{confidence:.0%}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:* {reason}"
                }
            }
        ]
        return self.send_message(text, blocks)
    
    def notify_position_closed(
        self,
        symbol: str,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
        outcome: str
    ) -> bool:
        """Notify when a position is closed"""
        emoji = "🟢" if outcome == "WIN" else "🔴" if outcome == "LOSS" else "⚪"
        text = f"{emoji} Position Closed: {symbol}"
        
        pnl_color = "good" if pnl >= 0 else "danger"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Position Closed: {symbol}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Exit Price:*\n${exit_price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*P&L:*\n${pnl:+,.2f} ({pnl_pct:+.2f}%)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Outcome:*\n{outcome}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:* {reason}"
                }
            }
        ]
        return self.send_message(text, blocks)
    
    def notify_daily_summary(
        self,
        total_pnl: float,
        total_pnl_pct: float,
        wins: int,
        losses: int,
        open_positions: int
    ) -> bool:
        """Send daily trading summary"""
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        emoji = "🎉" if total_pnl > 0 else "😔" if total_pnl < 0 else "😐"
        
        text = f"{emoji} Daily Trading Summary"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Daily Trading Summary"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total P&L:*\n${total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Win Rate:*\n{win_rate:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Trades:*\n{wins}W / {losses}L"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Open Positions:*\n{open_positions}"
                    }
                ]
            }
        ]
        return self.send_message(text, blocks)
    
    def notify_test_start(self, duration_hours: float, symbol: str) -> bool:
        """Notify when a test starts"""
        text = f"🚀 Trading Bot Started: {symbol}"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 Trading Bot Started"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Symbol:*\n{symbol}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{duration_hours:.1f} hours"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Started:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            }
        ]
        return self.send_message(text, blocks)
    
    def notify_test_complete(
        self,
        duration_hours: float,
        total_pnl: float,
        wins: int,
        losses: int
    ) -> bool:
        """Notify when a test completes"""
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        emoji = "✅" if total_pnl > 0 else "❌"
        
        text = f"{emoji} Trading Test Complete"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Trading Test Complete"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{duration_hours:.1f} hours"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total P&L:*\n${total_pnl:+,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Win Rate:*\n{win_rate:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Trades:*\n{wins}W / {losses}L"
                    }
                ]
            }
        ]
        return self.send_message(text, blocks)
    
    def notify_position_update(
        self,
        position: Dict,
        current_price: float,
        tp_price: float,
        sl_price: float
    ) -> bool:
        """
        Send visual update showing position progress toward TP/SL
        
        Args:
            position: Position dict with entry_price, size, unrealized_pnl, etc.
            current_price: Current market price
            tp_price: Take profit target price
            sl_price: Stop loss trigger price
        """
        symbol = position.get("symbol", "UNKNOWN")
        entry_price = position.get("entry_price", 0)
        size = position.get("size", 0)
        unrealized_pnl = position.get("unrealized_pnl", 0)
        pnl_pct = (unrealized_pnl / size * 100) if size > 0 else 0
        
        # Calculate progress toward TP and SL
        tp_distance = tp_price - entry_price
        sl_distance = entry_price - sl_price
        current_distance = current_price - entry_price
        
        # Progress percentages
        if current_distance >= 0:
            # Moving toward TP
            tp_progress = min(100, (current_distance / tp_distance * 100)) if tp_distance > 0 else 0
            sl_progress = 0
        else:
            # Moving toward SL
            tp_progress = 0
            sl_progress = min(100, (abs(current_distance) / sl_distance * 100)) if sl_distance > 0 else 0
        
        # Visual progress bars
        tp_bar = self._create_progress_bar(tp_progress, "🟢")
        sl_bar = self._create_progress_bar(sl_progress, "🔴")
        
        # Status indicator
        if pnl_pct >= 2.5:
            status = "🚀 NEAR TAKE PROFIT!"
            color = "#36a64f"  # Green
        elif pnl_pct >= 1.0:
            status = "📈 Profitable"
            color = "#36a64f"
        elif pnl_pct >= -0.5:
            status = "➡️ Neutral"
            color = "#808080"
        elif pnl_pct >= -1.2:
            status = "⚠️ Approaching Stop Loss"
            color = "#ff9900"  # Orange
        else:
            status = "🚨 NEAR STOP LOSS!"
            color = "#ff0000"  # Red
        
        text = f"📊 Position Update: {symbol}"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Position Update: {symbol}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Entry:* ${entry_price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Current:* ${current_price:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*P&L:* ${unrealized_pnl:+,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*P&L %:* {pnl_pct:+.2f}%"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status:* {status}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🎯 Take Profit:* ${tp_price:,.2f} (+3.0%)\n"
                        f"{tp_bar} {tp_progress:.0f}%\n\n"
                        f"*🛑 Stop Loss:* ${sl_price:,.2f} (-1.5%)\n"
                        f"{sl_bar} {sl_progress:.0f}%"
                    )
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Position #{position.get('id', '?')} • Size: ${size:,.2f} • {datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            }
        ]
        
        return self.send_message(text, blocks)
    
    def notify_positions_summary(
        self,
        positions: list,
        current_prices: Dict[str, float],
        total_pnl: float,
        capital: float
    ) -> bool:
        """
        Send summary of all open positions with visual indicators
        
        Args:
            positions: List of open position dicts
            current_prices: Dict mapping symbol to current price
            total_pnl: Total unrealized P&L
            capital: Current available capital
        """
        if not positions:
            return self.send_message("ℹ️ No open positions")
        
        # Group positions by status
        near_tp = []
        profitable = []
        neutral = []
        warning = []
        near_sl = []
        
        for pos in positions:
            pnl_pct = (pos.get("unrealized_pnl", 0) / pos.get("size", 1) * 100)
            if pnl_pct >= 2.5:
                near_tp.append(pos)
            elif pnl_pct >= 1.0:
                profitable.append(pos)
            elif pnl_pct >= -0.5:
                neutral.append(pos)
            elif pnl_pct >= -1.2:
                warning.append(pos)
            else:
                near_sl.append(pos)
        
        # Create summary text
        summary_lines = []
        if near_tp:
            summary_lines.append(f"🚀 Near TP: {len(near_tp)}")
        if profitable:
            summary_lines.append(f"📈 Profitable: {len(profitable)}")
        if neutral:
            summary_lines.append(f"➡️ Neutral: {len(neutral)}")
        if warning:
            summary_lines.append(f"⚠️ Warning: {len(warning)}")
        if near_sl:
            summary_lines.append(f"🚨 Near SL: {len(near_sl)}")
        
        summary = " • ".join(summary_lines)
        
        text = f"📊 Positions Summary ({len(positions)} open)"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Positions Summary"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Open Positions:*\n{len(positions)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total P&L:*\n${total_pnl:+,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Capital:*\n${capital:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status Breakdown:*\n{summary}"
                }
            }
        ]
        
        # Add details for concerning positions (near SL or near TP)
        if near_sl or near_tp:
            blocks.append({"type": "divider"})
            
            if near_sl:
                sl_details = []
                for pos in near_sl[:3]:  # Show top 3
                    symbol = pos.get("symbol", "?")
                    pnl_pct = (pos.get("unrealized_pnl", 0) / pos.get("size", 1) * 100)
                    sl_details.append(f"🚨 {symbol}: {pnl_pct:+.2f}%")
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Positions Near Stop Loss:*\n" + "\n".join(sl_details)
                    }
                })
            
            if near_tp:
                tp_details = []
                for pos in near_tp[:3]:  # Show top 3
                    symbol = pos.get("symbol", "?")
                    pnl_pct = (pos.get("unrealized_pnl", 0) / pos.get("size", 1) * 100)
                    tp_details.append(f"🚀 {symbol}: {pnl_pct:+.2f}%")
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Positions Near Take Profit:*\n" + "\n".join(tp_details)
                    }
                })
        
        return self.send_message(text, blocks)
    
    def _create_progress_bar(self, percentage: float, emoji: str = "🟦") -> str:
        """Create a visual progress bar"""
        filled = int(percentage / 10)  # 10 blocks for 100%
        empty = 10 - filled
        return emoji * filled + "⬜" * empty


# Smoke test
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python slack_notifier.py <webhook_url>")
        sys.exit(1)
    
    notifier = SlackNotifier(webhook_url=sys.argv[1])
    
    # Test notification
    success = notifier.send_message("🧪 Test notification from Ozzy Trading Bot")
    
    if success:
        print("✅ Slack notification sent successfully!")
    else:
        print("❌ Failed to send Slack notification")
        sys.exit(1)
