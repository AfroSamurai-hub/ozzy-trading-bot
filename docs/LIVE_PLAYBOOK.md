# Live Execution Playbook

> Step-by-step guide for switching from testnet to live and managing the bot day-to-day.
> Created: 2026-05-18

---

## Pre-Launch Checklist

### 1. Environment Preparation

```bash
# 1. Verify live API keys are in .env
grep BINANCE_API_KEY .env
grep BINANCE_API_SECRET .env
# Should show LIVE keys (NOT demo/testnet keys)

# 2. Back up current state
bash scripts/backup.sh

# 3. Verify backup exists
ls -la backups/
```

### 2. Config Changes

In `config.py`:

```python
BINANCE_TESTNET = False        # ← CRITICAL: switch to live
RISK_PCT = 0.02                # 2% per trade (conservative for $500)
MAX_POSITIONS = 3              # Max 3 concurrent positions
MAX_POSITIONS_PER_SYMBOL = 1   # No pyramiding at $500
```

Optional (in `binance_connector.py`):
```python
# Reduce ETH leverage for margin headroom
BINANCE_LEVERAGE = {
    "ETHUSDT": 10,   # was 20
    "SOLUSDT": 10,
    "LINKUSDT": 10,
    "DOGEUSDT": 10,
}
```

### 3. Stop Services (Graceful)

```bash
systemctl --user stop ozzybot-webhook
systemctl --user stop ozzybot-breakeven
# Wait 10 seconds for any in-progress trades
sleep 10
```

### 4. Clear Testnet State (Optional but Recommended)

```bash
# Rename testnet DB to keep history
mv trades.db trades_testnet_final.db

# Bot will create fresh trades.db on next start
```

### 5. Start Live Services

```bash
systemctl --user start ozzybot-webhook
sleep 5
systemctl --user start ozzybot-breakeven

# Verify both are active
systemctl --user status ozzybot-webhook
systemctl --user status ozzybot-breakeven
```

### 6. Validation Checks

```bash
# Check logs for live mode confirmation
tail -f webhook.log | grep -i "live\|testnet\|startup"

# Verify monitor sees live positions
tail -f binance_monitor.log | grep -i "startup\|position\|live"

# Check Telegram for startup notification
```

---

## Daily Operations

### Morning Check (7 AM SAST)

```bash
# Service status
systemctl --user status ozzybot-webhook ozzybot-breakeven

# Quick health check
bash scripts/health_check.sh

# Review overnight activity
tail -n 50 trades.log | grep -i "approved\|rejected\|error\|milestone"

# Check open positions
curl -s http://localhost:5000/status | python -m json.tool
```

### Evening Check (6 PM SAST)

```bash
# Same as morning + equity snapshot
python -c "import trade_db; print(trade_db.get_current_equity())"

# Review PnL for the day
tail -n 100 trades.log | grep -i "pnl\|profit\|loss\|close"
```

---

## Emergency Procedures

### Service Down

```bash
# Auto-restart attempts happen every 5 min via cron + health_check.sh
# If persistent failure:

systemctl --user restart ozzybot-webhook
systemctl --user restart ozzybot-breakeven

# If restart fails, check logs
journalctl --user -u ozzybot-webhook -n 50
journalctl --user -u ozzybot-breakeven -n 50
```

### Need to Halt All Trading (Market Crash / Personal Emergency)

```bash
# Option 1: Stop webhook (no new signals)
systemctl --user stop ozzybot-webhook

# Option 2: Close all positions immediately
python -c "
from binance_connector import client
positions = client.futures_position_information()
for p in positions:
    amt = float(p.get('positionAmt', 0))
    if abs(amt) > 0:
        side = 'SELL' if amt > 0 else 'BUY'
        client.futures_create_order(symbol=p['symbol'], side=side, type='MARKET', quantity=abs(amt))
        print(f'Closed {p[\"symbol\"]}')
"

# Option 3: Flip to testnet (emergency only — requires config change + restart)
# Edit config.py: BINANCE_TESTNET = True
# systemctl --user restart ozzybot-webhook
```

### Telegram Bot Commands

| Command | Purpose |
|---------|---------|
| `/status` | Show open positions + equity |
| `/close SYMBOL` | Close position immediately |
| `/breakeven SYMBOL` | Move SL to entry |
| `/trail SYMBOL` | Activate trailing stop |

---

## Position Sizing Reference ($500 Account)

| Symbol | Leverage | 2% Risk ($10) | Min Notional | Actual Risk |
|--------|----------|---------------|--------------|-------------|
| SOL | 10x | ~$100 pos | ~$5 | ~$10 |
| LINK | 10x | ~$100 pos | ~$5 | ~$10 |
| ETH | 10x | ~$100 pos | ~$5 | ~$10 |
| DOGE | 10x | ~$100 pos | ~$5 | ~$10 |

**Rule:** If calculated notional < $5, skip the trade (risk too small to be meaningful).

---

## Weekly Review Checklist

Every Sunday evening:

- [ ] Review all closed trades in `trades.log`
- [ ] Calculate weekly win rate and average R
- [ ] Check if any filter is rejecting too many good signals
- [ ] Verify backup from last 7 days exists
- [ ] Review `docs/FINANCIAL_MODEL.md` vs actual performance
- [ ] Update `docs/CHANGELOG.md` with any config changes

---

## Contact / Escalation

| Issue | Action |
|-------|--------|
| Bot not responding | Check `systemctl --user status` + logs |
| Position not closing | Use Telegram `/close SYMBOL` or manual Binance app |
| API key errors | Verify `.env` has LIVE keys, not testnet |
| Large unexpected loss | Halt trading, review logs, check for bug |
| Mac Mini migration | Follow `docs/STRATEGIC_ROADMAP.md` Q3 plan |

---

*Last updated: 2026-05-18*
*Next review: Before live launch (2026-05-25)*
