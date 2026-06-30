#!/usr/bin/env python3
"""
OZZYBOT — Live Portfolio Server & Explorer Backend
Queries trades.db and live Binance futures tickers to feed real-time PnL data
to the Interactive Architecture Explorer dashboard.
"""
import os
import sys
import json
import sqlite3
import urllib.request
import http.server
import socketserver

PORT = 8080
DB_PATH = "/home/rick/ozzy-bot/trades.db"
REPORTS_DIR = "/home/rick/ozzy-bot/reports"

def _normalize_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().lower()
    if not normalized or normalized in {"all", "any", "unified"}:
        return None
    return normalized


def _row_mode(row: dict) -> str | None:
    for key in ("mode", "execution_mode", "instance_mode"):
        value = row.get(key)
        if value:
            return str(value).strip().lower()
    return None


def _mode_matches(row: dict, mode: str | None) -> bool:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode is None:
        return True
    return _row_mode(row) == normalized_mode


def fetch_binance_prices() -> dict:
    """Fetch current futures prices in one request."""
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {item["symbol"]: float(item["price"]) for item in data}
    except Exception as err:
        print(f"Error fetching Binance tickers: {err}", file=sys.stderr)
    return {}

def get_live_portfolio(db_path: str = DB_PATH, mode: str | None = None) -> list:
    """Queries open trades and maps them to live prices and net PnLs."""
    if not os.path.exists(db_path):
        return []
        
    prices = fetch_binance_prices()
    
    trades = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Fetch trades with exit_price IS NULL
        cur = conn.execute(
            "SELECT id, ts, symbol, direction, entry_price, qty, sl, tp, timeframe, execution_state, mode FROM trades WHERE exit_price IS NULL"
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        for r in rows:
            if not _mode_matches(r, mode):
                continue
            symbol = r["symbol"]
            current_price = prices.get(symbol, r["entry_price"])
            entry_price = float(r["entry_price"] or 0)
            qty = float(r["qty"] or 0)
            
            # Calculate real-time gross PnL
            if r["direction"] == "BUY":
                gross_pnl = (current_price - entry_price) * qty
            else:
                gross_pnl = (entry_price - current_price) * qty
                
            # Apply dynamic fee deductions if shadow
            if r["execution_state"] == "shadow":
                fee_entry = entry_price * qty * 0.0005
                fee_exit = current_price * qty * 0.0005
                slippage = entry_price * qty * 0.0002
                net_pnl = gross_pnl - (fee_entry + fee_exit + slippage)
            else:
                # Standard Testnet PnL (ignoring fees or direct exchange replication)
                net_pnl = gross_pnl
                
            trades.append({
                "id": r["id"],
                "ts": r["ts"],
                "symbol": symbol,
                "direction": r["direction"],
                "entry_price": entry_price,
                "qty": qty,
                "sl": float(r["sl"] or 0),
                "tp": float(r["tp"] or 0),
                "timeframe": r["timeframe"],
                "execution_state": r["execution_state"],
                "mode": r.get("mode"),
                "current_price": current_price,
                "net_pnl": net_pnl
            })
    except Exception as db_err:
        print(f"Database query error: {db_err}", file=sys.stderr)
    return trades

def get_recent_history(db_path: str = DB_PATH, mode: str | None = None) -> list:
    """Queries recent closed trades from the sqlite database."""
    if not os.path.exists(db_path):
        return []
        
    trades = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Fetch last 15 closed trades (where exit_price IS NOT NULL)
        cur = conn.execute(
            "SELECT id, ts, symbol, direction, entry_price, exit_price, qty, pnl, exit_reason, execution_state, timeframe, mode FROM trades WHERE exit_price IS NOT NULL ORDER BY id DESC"
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        for r in rows:
            if not _mode_matches(r, mode):
                continue
            trades.append({
                "id": r["id"],
                "ts": r["ts"],
                "symbol": r["symbol"],
                "direction": r["direction"],
                "entry_price": float(r["entry_price"] or 0),
                "exit_price": float(r["exit_price"] or 0),
                "qty": float(r["qty"] or 0),
                "pnl": float(r["pnl"] or 0),
                "exit_reason": r["exit_reason"],
                "execution_state": r["execution_state"],
                "timeframe": r["timeframe"],
                "mode": r.get("mode")
            })
    except Exception as db_err:
        print(f"Database history query error: {db_err}", file=sys.stderr)
        
    return trades[:15]

def get_optimizer_report(db_path: str = DB_PATH) -> dict:
    """Compiles live 30-day stats vs shadow benchmarks from trades.db and returns JSON."""
    if not os.path.exists(db_path):
        return {"raw": "\x1b[91mError: trades.db not found.\x1b[0m"}
        
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # We need UTC timestamp for last 30 days
        from datetime import datetime, timezone, timedelta
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Fetch Standard trades
        cur = conn.execute(
            "SELECT * FROM trades WHERE ts >= ? AND execution_state IN ('closed', 'confirmed', 'entry_filled')",
            (thirty_days_ago,)
        )
        live_rows = [dict(r) for r in cur.fetchall()]
        
        # 2. Fetch Shadow trades
        cur = conn.execute(
            "SELECT * FROM trades WHERE ts >= ? AND execution_state IN ('shadow_closed', 'shadow')",
            (thirty_days_ago,)
        )
        shadow_rows = [dict(r) for r in cur.fetchall()]
        
        conn.close()
        
        def calculate_stats(rows):
            if not rows:
                return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "net_pnl": 0.0, "profit_factor": 0.0, "avg_pnl": 0.0}
            pnl_list = [float(r.get("pnl") or 0) for r in rows]
            total = len(rows)
            wins_list = [p for p in pnl_list if p > 0]
            losses_list = [p for p in pnl_list if p <= 0]
            
            wins = len(wins_list)
            losses = len(losses_list)
            win_rate = (wins / total) * 100.0 if total > 0 else 0.0
            net_pnl = sum(pnl_list)
            avg_pnl = net_pnl / total if total > 0 else 0.0
            
            sum_wins = sum(wins_list)
            sum_losses = abs(sum(losses_list))
            profit_factor = sum_wins / sum_losses if sum_losses > 0 else (sum_wins if sum_wins > 0 else 1.0)
            
            return {
                "total": total,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "net_pnl": net_pnl,
                "profit_factor": profit_factor,
                "avg_pnl": avg_pnl
            }
            
        live_stats = calculate_stats(live_rows)
        shadow_stats = calculate_stats(shadow_rows)
        
        # Formulate terminal string with \x1b codes
        lines = []
        lines.append("==========================================================")
        lines.append("⚡  \x1b[1mOZZYBOT DYNAMIC ALPHA OPTIMIZATION REPORT\x1b[0m  ⚡")
        lines.append("==========================================================")
        lines.append(f"Analysis Period: Past 30 Days | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("──────────────────────────────────────────────────────────")
        
        # Live Stats
        live_color = "\x1b[92m" if live_stats["net_pnl"] >= 0 else "\x1b[91m"
        lines.append("  \x1b[1mStandard Executed Trades (Live/Testnet)\x1b[0m")
        lines.append(f"    ├─ Total Trades:  {live_stats['total']}")
        lines.append(f"    ├─ Win Rate:      \x1b[1m{live_stats['win_rate']:.1f}%\x1b[0m ({live_stats['wins']} W / {live_stats['losses']} L)")
        lines.append(f"    ├─ Profit Factor: \x1b[1m{live_stats['profit_factor']:.2f}\x1b[0m")
        lines.append(f"    ├─ Avg PnL:       {live_color}${live_stats['avg_pnl']:.2f}\x1b[0m")
        lines.append(f"    └─ Net Profit:    {live_color}${live_stats['net_pnl']:+.2f}\x1b[0m")
        lines.append("")
        
        # Shadow Stats
        shadow_color = "\x1b[92m" if shadow_stats["net_pnl"] >= 0 else "\x1b[91m"
        lines.append("  \x1b[1mVirtual Shadow Trades (Filtered/Skipped)\x1b[0m")
        lines.append(f"    ├─ Total Trades:  {shadow_stats['total']}")
        lines.append(f"    ├─ Win Rate:      \x1b[1m{shadow_stats['win_rate']:.1f}%\x1b[0m ({shadow_stats['wins']} W / {shadow_stats['losses']} L)")
        lines.append(f"    ├─ Profit Factor: \x1b[1m{shadow_stats['profit_factor']:.2f}\x1b[0m")
        lines.append(f"    ├─ Avg PnL:       {shadow_color}${shadow_stats['avg_pnl']:.2f}\x1b[0m")
        lines.append(f"    └─ Net Profit:    {shadow_color}${shadow_stats['net_pnl']:+.2f}\x1b[0m")
        lines.append("──────────────────────────────────────────────────────────")
        
        # Recommendations
        lines.append("🎯 \x1b[1mDECISION ENGINE RECOMMENDATION:\x1b[0m")
        if shadow_stats["total"] >= 3:
            if shadow_stats["win_rate"] >= 58.0 and shadow_stats["profit_factor"] >= 1.4:
                lines.append("  \x1b[92m🟢 OPPORTUNITY DETECTED — Loose Gating Rules!\x1b[0m")
                lines.append("  Virtual shadow/Grade-C trades are highly profitable after fees & spread.")
                lines.append("  \x1b[1mActionable suggestions for config/dynamic_config_testnet.json:\x1b[0m")
                lines.append("    1. Set \x1b[94m\"SETUP_GRADE_C_LIVE\": true\x1b[0m to harvest these setups.")
                lines.append("    2. Loosen volume limits: decrease \x1b[94m\"grade_a_volume_min\": 0.95\x1b[0m")
            elif live_stats["win_rate"] >= 50.0 and shadow_stats["win_rate"] < 40.0:
                lines.append("  \x1b[94m🔒 RISK FILTERS VALIDATED — Maintain strict rules!\x1b[0m")
                lines.append("  Your live strategy is profitable, while shadow trades are heavily losing.")
                lines.append("  The current dynamic filter system is doing its job perfectly to protect capital.")
                lines.append("  \x1b[1mActionable suggestions:\x1b[0m")
                lines.append("    • Keep live thresholds intact. Filters are currently in optimal state.")
            elif live_stats["win_rate"] < 45.0 and shadow_stats["win_rate"] < 45.0:
                lines.append("  \x1b[91m⚠️ WARNING — High Chop / Correlation Drawdown Regime!\x1b[0m")
                lines.append("  Both live and shadow trades are experiencing high chop failure rates.")
                lines.append("  \x1b[1mActionable suggestions for config/dynamic_config_testnet.json:\x1b[0m")
                lines.append("    1. Tighten ADX trend strength: increase \x1b[94m\"adx_threshold\": 30.0\x1b[0m")
                lines.append("    2. Decrease risk allocation: set \x1b[94m\"risk_multiplier_grade_b\": 0.35\x1b[0m")
            else:
                lines.append("  \x1b[93m🟡 STABLE FLOW — No adjustments recommended.\x1b[0m")
                lines.append("  Live and shadow distributions are aligned within normal variance bounds.")
                lines.append("  Maintain current dynamic configurations and re-evaluate in 7 days.")
        else:
            lines.append(f"  \x1b[93m🟡 INSUFFICIENT SHADOW DATA ({shadow_stats['total']}/3)\x1b[0m")
            lines.append("  System needs a larger sample size of virtual shadow trades to formulate an optimizer edge.")
            lines.append("  Re-run this command once more shadow setups are captured and closed.")
            
        lines.append("==========================================================")
        return {"raw": "\n".join(lines)}
        
    except Exception as e:
        return {"raw": f"\x1b[91mError compiling database stats: {e}\x1b[0m"}

class LivePortfolioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static assets from reports directory
        super().__init__(*args, directory=REPORTS_DIR, **kwargs)

    def do_GET(self):
        # Intercept api endpoints
        if self.path.startswith("/api/portfolio"):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            mode = query.get("mode", [None])[0]
            
            db_path = DB_PATH
            if "HERMES_TRADE_DB" in os.environ:
                db_path = os.environ["HERMES_TRADE_DB"]
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            portfolio = get_live_portfolio(db_path, mode=mode)
            self.wfile.write(json.dumps(portfolio).encode("utf-8"))
        elif self.path.startswith("/api/history"):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            mode = query.get("mode", [None])[0]
            
            db_path = DB_PATH
            if "HERMES_TRADE_DB" in os.environ:
                db_path = os.environ["HERMES_TRADE_DB"]
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            history = get_recent_history(db_path, mode=mode)
            self.wfile.write(json.dumps(history).encode("utf-8"))
        elif self.path.startswith("/api/optimizer"):
            from urllib.parse import urlparse

            db_path = DB_PATH
            if "HERMES_TRADE_DB" in os.environ:
                db_path = os.environ["HERMES_TRADE_DB"]
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            report = get_optimizer_report(db_path)
            self.wfile.write(json.dumps(report).encode("utf-8"))
        else:
            # Fall back to standard file server
            super().do_GET()

def main():
    # Force socket reuse to prevent port-in-use exceptions on rapid restarts
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), LivePortfolioHandler) as httpd:
        print(f"🚀 OzzyBot Live Explorer Server active on http://localhost:{PORT}")
        print(f"📡 Real-time /api/portfolio database bridge enabled.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down backend portfolio server.")

if __name__ == "__main__":
    main()
