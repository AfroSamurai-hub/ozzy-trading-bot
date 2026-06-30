#!/usr/bin/env python3
"""OzzyBot Health Check Alert Sender

Reads the .health_alert_pending flag file and sends a Telegram alert
using the existing telegram_client module. Only sends if the flag exists.

Zero token cost — just HTTP request to Telegram API.
"""
import sys
import os
from datetime import datetime

# Add bot directory to path
BOT_DIR = "/home/rick/ozzy-bot"
sys.path.insert(0, BOT_DIR)

ALERT_FLAG = os.path.join(BOT_DIR, ".health_alert_pending")

def send_alert():
    if not os.path.exists(ALERT_FLAG):
        return
    
    # Read the issues
    with open(ALERT_FLAG, 'r') as f:
        issues = f.read().strip()
    
    if not issues:
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = (
        f"🚨 <b>OzzyBot Health Alert</b>\n\n"
        f"{issues}\n"
        f"⏰ {timestamp} SAST\n\n"
        f"<i>Check: systemctl --user status ozzybot-webhook.service ozzybot-monitor.service</i>"
    )
    
    try:
        from telegram_client import send_message
        send_message(message)
        print(f"[{timestamp}] Alert sent via Telegram")
        
        # Clear the flag after sending
        os.remove(ALERT_FLAG)
    except Exception as e:
        print(f"[{timestamp}] Failed to send alert: {e}")

if __name__ == "__main__":
    send_alert()
