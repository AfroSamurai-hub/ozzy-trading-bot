# 🎯 QUICK COMMANDS CHEAT SHEET

## Watch Your A/B Test Live

```bash
# EASIEST - Just run this:
cd ~/ozzy-simple
./watch.sh
```

## All Options

| Command | What It Does | Speed |
|---------|-------------|-------|
| `./watch.sh` | Beautiful live dashboard | 10s refresh |
| `./venv/bin/python scripts/live_dashboard.py --refresh 5` | Fast dashboard | 5s refresh |
| `tail -f bot.log \| grep "A/B Test"` | Live logs | Real-time |
| `watch -n 30 './venv/bin/python scripts/test_time_filter.py --status'` | Simple view | 30s refresh |

## What You'll See

- **Progress:** X/50 Control, X/50 Test (need 100 total)
- **Win Rate:** Control vs Test comparison
- **Avg P&L:** Profit per trade comparison
- **Recent Trades:** Last 10 trades with P&L
- **Status:** Leading group and by how much

## Exit

Press `Ctrl+C` to stop any live view

## More Info

- Full guide: `cat LIVE_MONITORING_GUIDE.md`
- Test status: `./venv/bin/python scripts/test_time_filter.py --status`
- Bot status: `ps aux | grep main.py`

---

**Created:** October 11, 2025  
**Status:** ✅ Ready to use!  
