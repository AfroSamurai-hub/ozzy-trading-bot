#!/bin/bash
set -e

# Change directory to the repository root relative to the script location
CDPATH="" cd -- "$(dirname -- "$0")/.."

echo "⚠️ EMERGENCY RIPCORD TRIGGERED — Reverting dynamic config changes..."

# 1. Restore files from backups
if [ -f "webhook.py.pre_dynamic" ]; then
    echo "Restoring webhook.py..."
    cp webhook.py.pre_dynamic webhook.py
else
    echo "❌ Error: webhook.py.pre_dynamic backup not found!"
    exit 1
fi

if [ -f "binance_monitor.pre_dynamic" ]; then
    echo "Restoring binance_monitor.py..."
    cp binance_monitor.pre_dynamic binance_monitor.py
else
    echo "❌ Error: binance_monitor.pre_dynamic backup not found!"
    exit 1
fi

# 2. Restart services
echo "Restarting systemd user services..."
systemctl --user restart ozzybot-live-micro-webhook.service

echo "✅ ROLLBACK COMPLETE — Services restored to pre-implementation state."
