#!/bin/bash
# OzzyBot Live Status Monitor
# v2026-06-27 — Unified core status.

echo "=========================================="
echo "  OZZYBOT LIVE STATUS"
echo "=========================================="
echo ""

echo "🌐 Core Services:"
for svc in ozzybot-webhook ozzybot-monitor ozzybot-telegram-cmd ozzybot-signal.timer ozzybot-15m-reversion.timer ozzybot-openclaw-trend-executor ozzybot-openclaw-breakout-executor ozzybot-openclaw-macro-scout ozzybot-context-observer; do
    systemctl --user is-active "$svc" >/dev/null 2>&1 && echo "  ✅ $svc" || echo "  ❌ $svc DOWN"
done

echo ""
echo "📊 Ports:"
ss -tlnp 2>/dev/null | grep -E "5001" | awk '{print "  " $4 " → " $7}'

echo ""
echo "📈 Latest Webhook Activity (unified 5001):"
tail -50 /home/rick/ozzy-bot/webhook.log 2>/dev/null | grep -E "CRYPTO_ENTRY|APPROVED|REJECTED|STARTUP" | tail -3

echo ""
echo "💰 Last 5 Trades / Events:"
tail -5 /home/rick/ozzy-bot/trades.log 2>/dev/null || echo "  (no trades yet)"

echo ""
echo "🔍 Quick Commands:"
echo "  watch webhook:   journalctl --user -u ozzybot-webhook -f"
echo "  watch monitor:   journalctl --user -u ozzybot-monitor -f"
echo "  check status:    ./status.sh"
echo "  restart webhook: systemctl --user restart ozzybot-webhook"
echo "  restart monitor: systemctl --user restart ozzybot-monitor"
echo "  health check:    venv/bin/python ozzybot_doctor.py"
echo ""
