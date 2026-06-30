#!/usr/bin/env python3
"""
Binance Futures Trade Journal
Tracks every trade lifecycle: entry → management → exit → analysis.
Stores in ~/.hermes/trading-journal/binance_journal.json
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_PATH = Path(os.getenv("HERMES_BINANCE_JOURNAL", Path.home() / ".hermes" / "trading-journal" / "binance_journal.json"))


def _load_journal() -> dict:
    if JOURNAL_PATH.exists():
        with open(JOURNAL_PATH, "r") as f:
            return json.load(f)
    return {"trades": [], "config": {"version": "1.0.0", "created": datetime.now(timezone.utc).isoformat()}}


def _save_journal(journal: dict):
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL_PATH, "w") as f:
        json.dump(journal, f, indent=2)


def open_trade(symbol: str, side: str, entry_price: float, quantity: float,
               sl_price: float, tp_price: float, leverage: int = 5,
               reason: str = "signal", order_id: str = None) -> dict:
    """Record a new trade opening."""
    journal = _load_journal()
    
    risk = abs(entry_price - sl_price) * quantity
    reward = abs(tp_price - entry_price) * quantity
    rr = round(reward / risk, 2) if risk > 0 else 0
    
    trade = {
        "id": f"{symbol}_{int(time.time())}",
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "quantity": quantity,
        "leverage": leverage,
        "risk_usd": round(risk, 2),
        "reward_usd": round(reward, 2),
        "rr_planned": rr,
        "reason": reason,
        "order_id": order_id,
        "status": "open",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
        "exit_price": None,
        "exit_reason": None,
        "realized_pnl": None,
        "commissions": 0,
        "funding": 0,
        "max_profit": 0,
        "max_drawdown": 0,
        "duration_hours": None,
        "outcome": None,
        "r_multiple": None,
        "lessons": [],
    }
    
    journal["trades"].append(trade)
    _save_journal(journal)
    
    return trade


def close_trade(trade_id: str, exit_price: float, exit_reason: str,
                realized_pnl: float, commissions: float = 0, funding: float = 0) -> dict:
    """Record a trade closing."""
    journal = _load_journal()
    
    for trade in journal["trades"]:
        if trade["id"] == trade_id or trade.get("order_id") == trade_id:
            trade["status"] = "closed"
            trade["closed_at"] = datetime.now(timezone.utc).isoformat()
            trade["exit_price"] = exit_price
            trade["exit_reason"] = exit_reason
            trade["realized_pnl"] = round(realized_pnl, 2)
            trade["commissions"] = round(commissions, 2)
            trade["funding"] = round(funding, 2)
            
            # Calculate duration
            opened = datetime.fromisoformat(trade["opened_at"])
            closed = datetime.fromisoformat(trade["closed_at"])
            trade["duration_hours"] = round((closed - opened).total_seconds() / 3600, 2)
            
            # Net PnL
            net_pnl = realized_pnl - commissions + funding
            trade["net_pnl"] = round(net_pnl, 2)
            
            # R-multiple
            if trade["risk_usd"] > 0:
                trade["r_multiple"] = round(net_pnl / trade["risk_usd"], 2)
            
            # Outcome
            if net_pnl > 0:
                trade["outcome"] = "win"
            else:
                trade["outcome"] = "loss"
            
            _save_journal(journal)
            return trade
    
    return None


def update_trade(trade_id: str, **kwargs):
    """Update trade metadata (max profit, drawdown, lessons, etc)."""
    journal = _load_journal()
    
    for trade in journal["trades"]:
        if trade["id"] == trade_id or trade.get("order_id") == trade_id:
            trade.update(kwargs)
            _save_journal(journal)
            return trade
    return None


def get_stats() -> dict:
    """Generate comprehensive trading statistics."""
    journal = _load_journal()
    trades = journal["trades"]
    closed = [t for t in trades if t["status"] == "closed"]
    open_trades = [t for t in trades if t["status"] == "open"]
    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    
    if not closed:
        return {
            "total_trades": 0,
            "open_trades": len(open_trades),
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "total_commissions": 0,
            "total_funding": 0,
            "avg_rr": 0,
            "avg_win_r": 0,
            "avg_loss_r": 0,
            "expectancy": 0,
            "avg_duration_hours": 0,
            "by_symbol": {},
            "by_exit_reason": {},
            "message": "No closed trades yet. Keep trading!",
        }
    
    total_pnl = sum(t.get("net_pnl", 0) for t in closed)
    total_commissions = sum(t.get("commissions", 0) for t in closed)
    total_funding = sum(t.get("funding", 0) for t in closed)
    
    win_rate = len(wins) / len(closed) * 100
    avg_rr = sum(t.get("r_multiple", 0) for t in closed) / len(closed)
    avg_win_r = sum(t.get("r_multiple", 0) for t in wins) / len(wins) if wins else 0
    avg_loss_r = sum(t.get("r_multiple", 0) for t in losses) / len(losses) if losses else 0
    
    # Expectancy
    expectancy = (win_rate / 100 * avg_win_r) - ((1 - win_rate / 100) * abs(avg_loss_r))
    
    # By symbol
    by_symbol = {}
    for t in closed:
        sym = t["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0, "rr": []}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"] += t.get("net_pnl", 0)
        by_symbol[sym]["rr"].append(t.get("r_multiple", 0))
        if t["outcome"] == "win":
            by_symbol[sym]["wins"] += 1
        else:
            by_symbol[sym]["losses"] += 1
    
    # By exit reason
    by_exit = {}
    for t in closed:
        reason = t.get("exit_reason", "unknown")
        if reason not in by_exit:
            by_exit[reason] = {"count": 0, "wins": 0, "losses": 0, "pnl": 0}
        by_exit[reason]["count"] += 1
        by_exit[reason]["pnl"] += t.get("net_pnl", 0)
        if t["outcome"] == "win":
            by_exit[reason]["wins"] += 1
        else:
            by_exit[reason]["losses"] += 1
    
    # Duration analysis
    durations = [t["duration_hours"] for t in closed if t["duration_hours"]]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    return {
        "total_trades": len(closed),
        "open_trades": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "total_commissions": round(total_commissions, 2),
        "total_funding": round(total_funding, 2),
        "avg_rr": round(avg_rr, 2),
        "avg_win_r": round(avg_win_r, 2),
        "avg_loss_r": round(avg_loss_r, 2),
        "expectancy": round(expectancy, 2),
        "avg_duration_hours": round(avg_duration, 1),
        "by_symbol": {k: {**v, "rr": [round(r, 2) for r in v["rr"]]} for k, v in by_symbol.items()},
        "by_exit_reason": by_exit,
    }


def print_report():
    """Print formatted report."""
    stats = get_stats()
    
    print(f"{'='*60}")
    print(f"📊 BINANCE FUTURES JOURNAL — PERFORMANCE REPORT")
    print(f"{'='*60}")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Total Trades: {stats['total_trades']} (Open: {stats['open_trades']})")
    
    if not stats["total_trades"]:
        print(f"\n📋 {stats.get('message', 'No closed trades yet. Keep trading!')}")
        print(f"{'='*60}")
        return
    
    print(f"Win Rate:     {stats['win_rate']}% ({stats['wins']}W / {stats['losses']}L)")
    print(f"Net PnL:      ${stats['total_pnl']:+.2f}")
    print(f"Commissions:  ${stats['total_commissions']:.2f}")
    print(f"Funding:      ${stats['total_funding']:.2f}")
    print(f"Avg R-Mult:   {stats['avg_rr']}R")
    print(f"Avg Win:      {stats['avg_win_r']}R")
    print(f"Avg Loss:     {stats['avg_loss_r']}R")
    print(f"Expectancy:   {stats['expectancy']}R per trade")
    print(f"Avg Duration: {stats['avg_duration_hours']}h")
    print(f"{'='*60}")
    
    if stats.get("by_symbol"):
        print(f"\n📈 BY SYMBOL:")
        for sym, s in sorted(stats["by_symbol"].items()):
            wr = s["wins"] / s["trades"] * 100 if s["trades"] > 0 else 0
            print(f"  {sym}: {s['trades']} trades | {s['wins']}W/{s['losses']}L | WR: {wr:.0f}% | PnL: ${s['pnl']:+.2f}")
    
    if stats.get("by_exit_reason"):
        print(f"\n🚪 BY EXIT REASON:")
        for reason, s in sorted(stats["by_exit_reason"].items()):
            wr = s["wins"] / s["count"] * 100 if s["count"] > 0 else 0
            print(f"  {reason}: {s['count']} | {s['wins']}W/{s['losses']}L | WR: {wr:.0f}% | PnL: ${s['pnl']:+.2f}")
    
    print(f"{'='*60}")
    
    # Show recent trades
    journal = _load_journal()
    closed = [t for t in journal["trades"] if t["status"] == "closed"]
    if closed:
        print(f"\n📋 RECENT TRADES:")
        for t in closed[-10:]:
            pnl_str = f"+${t.get('net_pnl', 0):.2f}" if t.get("net_pnl", 0) > 0 else f"-${abs(t.get('net_pnl', 0)):.2f}"
            print(f"  [{t['opened_at'][:16]}] {t['symbol']} {t['side']} | {t['entry_price']:,} → {t.get('exit_price', '?'):,}")
            print(f"    Exit: {t.get('exit_reason', '?')} | {t.get('r_multiple', '?')}R | {t.get('duration_hours', '?')}h | {t.get('outcome', '?').upper()} | {pnl_str}")
    
    print(f"{'='*60}")


if __name__ == "__main__":
    print_report()
