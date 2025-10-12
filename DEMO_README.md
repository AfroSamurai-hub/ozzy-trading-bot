# 🚀 OZZY SIMPLE - DEMO TRADING SYSTEM

**R10,000 Virtual Capital Demo Test**

A complete forward-looking demo trading system that tracks virtual capital growth from R10,000 using real market data but no actual money at risk.

## ✨ Features

- **📊 Virtual R10,000 starting capital** - Track real growth
- **🔄 Dynamic position sizing** - Based on current balance (not fixed amounts)
- **📈 Real market data** - Uses live Bybit API for authentic signals
- **📋 Comprehensive tracking** - Database, logs, and reports
- **🎯 Live dashboard** - Real-time performance monitoring
- **📅 Daily summaries** - Automatic end-of-day reporting
- **🎪 A/B testing** - Same time filter tests as live bot
- **💾 Separate database** - Completely isolated from main trading

## 🚀 Quick Start

### 1. Initialize Demo Database
```bash
./venv/bin/python scripts/fresh_demo_test.py --init
```

### 2. Start Demo Bot
```bash
bash scripts/start_demo.sh
```

### 3. Monitor Live Dashboard (New Terminal)
```bash
./venv/bin/python scripts/demo_dashboard.py
```

### 4. Check Status Anytime
```bash
./venv/bin/python scripts/fresh_demo_test.py --status
```

### 5. Generate Reports
```bash
# Comprehensive report
./venv/bin/python scripts/demo_report.py --full

# Quick weekly summary
./venv/bin/python scripts/demo_report.py --weekly
```

## 📋 Files Created

### Core Files
- **`demo_main.py`** - Demo trading bot (tracks R10,000 virtual capital)
- **`demo_trades.db`** - Separate SQLite database for demo trades
- **`demo_bot.log`** - Demo bot log file
- **`demo_trades.csv`** - CSV export of completed trades

### Scripts
- **`scripts/fresh_demo_test.py`** - Initialize and manage demo database
- **`scripts/demo_dashboard.py`** - Live performance dashboard
- **`scripts/demo_report.py`** - Comprehensive reporting
- **`scripts/start_demo.sh`** - Helper script to start demo bot
- **`scripts/demo_commands.sh`** - Commands reference

## 📊 Dashboard Preview

```
╔══════════════════════════════════════════════════════════════╗
║  💰 FRESH DEMO TEST - LIVE PERFORMANCE                       ║
╠══════════════════════════════════════════════════════════════╣
║  📊 CAPITAL TRACKING:                                        ║
║     Starting Capital:  R10,000.00                            ║
║     Current Balance:   R10,457.23                            ║
║     Total Gain:        R457.23 (+4.57%) 🔥                   ║
║     Days Running:      3                                     ║
║                                                              ║
║  📈 TRADING STATS:                                           ║
║     Total Trades:      47                                    ║
║     Winning Trades:    29 (61.7%)                            ║
║     Losing Trades:     18 (38.3%)                            ║
║     Average per Trade: R9.73                                 ║
║                                                              ║
║  🎯 MILESTONES:                                              ║
║     ✅ R10,000 (Start)                                       ║
║     ✅ R10,250 (Day 1.5)                                     ║
║     🎯 R11,000 (54% progress)                                ║
║     ⏳ R12,000                                               ║
║     ⏳ R15,000 (Target for Month 1)                          ║
╚══════════════════════════════════════════════════════════════╝
```

## 📈 How It Works

### Virtual Capital Tracking
1. **Starts with R10,000** - Fresh virtual capital
2. **Dynamic position sizing** - Uses CURRENT balance for risk calculations
3. **Real P&L tracking** - Balance grows/shrinks with each trade
4. **Compound growth** - Later trades use larger position sizes as balance grows

### Example Flow
```
Day 1: R10,000 → Trade 1: +R45 → Balance: R10,045
Day 1: R10,045 → Trade 2: -R23 → Balance: R10,022
Day 2: R10,022 → Trade 3: +R67 → Balance: R10,089
...continues for 7-30 days...
```

### Database Schema
- **`demo_config`** - Starting capital, current balance, totals
- **`demo_trades`** - Individual trade records with P&L
- **`demo_daily_summary`** - End-of-day performance summaries

## 🎯 Assessment Criteria

The system evaluates your trading performance on:

- **✅ Profitability** - Positive returns after 7+ days
- **✅ Win Rate** - Target: >55% winning trades
- **✅ Risk Management** - Max drawdown <15%
- **✅ Consistency** - Steady daily performance
- **✅ Sample Size** - Minimum 20 trades for reliability

## 📊 Reports

### Status Report
```bash
./venv/bin/python scripts/fresh_demo_test.py --status
```
Quick overview of current performance.

### Comprehensive Report
```bash
./venv/bin/python scripts/demo_report.py --full
```
Detailed analysis with:
- Capital performance metrics
- Trading statistics (win rate, profit factor)
- Risk analysis (drawdown, recovery time)
- Weekly breakdown
- **Go/No-Go recommendation** for live trading
- Projected live performance with R50,000

### Weekly/Monthly Summaries
```bash
./venv/bin/python scripts/demo_report.py --weekly
./venv/bin/python scripts/demo_report.py --monthly
```

## 🔧 Technical Details

### Differences from Main Bot
- Uses `demo_trades.db` instead of main database
- Logs to `demo_bot.log` instead of `bot.log`
- Tracks virtual balance growth (no real money)
- Position sizes scale with current balance
- Separate A/B test tracking

### Integration
- **Same signals** - Uses identical signal generation
- **Same risk rules** - Risk manager with updated balance
- **Real market data** - Live Bybit API feeds
- **Same time filters** - A/B test consistency

## 🚦 Usage Workflow

### Setup Phase
1. Initialize demo database
2. Start demo bot
3. Monitor with dashboard

### Monitoring Phase (7-30 days)
- Check dashboard daily
- Review status weekly
- Track balance growth

### Assessment Phase
- Generate comprehensive report
- Evaluate readiness for live trading
- Make go/no-go decision

### Decision Examples

**✅ Ready for Live Trading:**
```
Win Rate: 58.3% ✅
Total Return: +12.4% ✅
Max Drawdown: 4.2% ✅
Trades: 67 ✅
VERDICT: READY FOR LIVE! 🚀
```

**❌ Needs Improvement:**
```
Win Rate: 47.1% ❌
Total Return: -3.2% ❌
Max Drawdown: 18.7% ❌
Trades: 23 ❌
VERDICT: NEEDS WORK 🔧
```

## 🛠️ Troubleshooting

### Demo Bot Won't Start
```bash
# Check if demo database exists
ls -la demo_trades.db

# Reinitialize if needed
./venv/bin/python scripts/fresh_demo_test.py --init
```

### Dashboard Not Working
```bash
# Check Rich library
./venv/bin/python -c "import rich; print('Rich OK')"

# Test without live display
./venv/bin/python -c "from scripts.demo_dashboard import DemoDashboard; print('Dashboard OK')"
```

### No Trading Activity
- Verify Bybit API connection
- Check trading hours configuration
- Monitor `demo_bot.log` for errors

## 📝 Command Reference

```bash
# Core Commands
./venv/bin/python scripts/fresh_demo_test.py --init     # Initialize
bash scripts/start_demo.sh                              # Start bot
./venv/bin/python scripts/demo_dashboard.py             # Dashboard
./venv/bin/python scripts/fresh_demo_test.py --status   # Status
./venv/bin/python scripts/demo_report.py --full         # Report

# Monitoring
tail -f demo_bot.log                                     # Watch logs
pkill -f 'demo_main.py'                                 # Stop bot

# Quick Reference
bash scripts/demo_commands.sh                           # All commands
```

## 🎯 Success Metrics

**Minimum Viable Demo:**
- 7 days running
- 15+ trades completed
- Positive overall return
- <10% max drawdown

**Production Ready:**
- 30 days running
- 50+ trades completed
- >55% win rate
- >10% total return
- <15% max drawdown
- Consistent weekly gains

## 🚀 Live Trading Transition

Once demo proves successful:

1. **Stop demo bot**
2. **Review final comprehensive report**
3. **Configure live bot with real capital**
4. **Start with conservative position sizes**
5. **Monitor closely for first week**

---

**⚠️ Remember: This is DEMO mode with virtual R10,000. No real money is at risk.**

**🎯 Goal: Prove your system works before risking real capital!**