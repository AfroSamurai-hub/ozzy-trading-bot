#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path('/home/rick/ozzy-bot')
LOG_PATH = Path(os.path.expanduser('~/ozzy-bot/trades.log'))
if not LOG_PATH.exists():
    LOG_PATH = ROOT / 'trades.log'
CONFIG_PATH = ROOT / 'config' / 'dynamic_config_testnet.json'
PORT = 8765

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OzzyBot Institutional Trading Desk HUD</title>
<style>
  :root {
    --bg:#0b0f19;
    --panel:#111827;
    --border:#1f2937;
    --muted:#64748b;
    --text:#e2e8f0;
    --cyan:#22d3ee;
    --green:#4ade80;
    --amber:#fbbf24;
    --red:#f87171;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    height: 100vh;
    overflow: hidden;
  }
  .desk {
    height: 100vh;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 10px;
    padding: 10px;
  }
  .quad {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
  }
  .quad h2 {
    margin: 0 0 10px;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  .kv {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 12px;
  }
  .kv > div {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid #1a2235;
    font-size: 13px;
  }
  .kv span:first-child { color: var(--muted); }
  .kv span:last-child { font-weight: 700; color: #f8fafc; }
  .val-huge { font-size: 22px; letter-spacing: -0.02em; }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left;
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 4px 0;
    border-bottom: 1px solid var(--border);
  }
  td {
    font-size: 13px;
    padding: 5px 0;
    border-bottom: 1px solid #1a2235;
  }
  .log-feed {
    flex: 1 1 auto;
    overflow: auto;
    margin-top: 6px;
  }
  .log-row {
    font-size: 12px;
    padding: 4px 0;
    border-bottom: 1px solid #1a2235;
    word-break: break-all;
    white-space: pre-wrap;
  }
  .pill {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 800;
  }
  .pill.ok { background: rgba(74,222,128,0.15); color: var(--green); border: 1px solid rgba(74,222,128,0.3); }
  .pill.bad { background: rgba(248,113,113,0.15); color: var(--red); border: 1px solid rgba(248,113,113,0.3); }
  .pill.warn { background: rgba(251,191,36,0.15); color: var(--amber); border: 1px solid rgba(251,191,36,0.3); }
  .pill.info { background: rgba(34,211,238,0.15); color: var(--cyan); border: 1px solid rgba(34,211,238,0.3); }
  .scroll { overflow:auto; }
</style>
</head>
<body>
  <main class="desk">
    <section class="quad">
      <h2>Q1 · Balance Sheet</h2>
      <div class="kv">
        <div><span>Wallet Balance</span><span class="val-huge" id="equity">—</span></div>
        <div><span>Realized PnL</span><span id="realized-pnl">—</span></div>
        <div><span>Withdrawals</span><span id="withdrawals">—</span></div>
        <div><span>Last Updated</span><span id="stamp">—</span></div>
      </div>
    </section>

    <section class="quad">
      <h2>Q2 · Position Risks</h2>
      <div class="kv">
        <div><span>Open Positions</span><span class="val-huge" id="positions">—</span></div>
        <div><span>Working Orders</span><span class="val-huge" id="working-orders">—</span></div>
        <div><span>Protection</span><span id="protection">—</span></div>
        <div><span>Execution Mode</span><span id="exec-mode">—</span></div>
      </div>
    </section>

    <section class="quad">
      <h2>Q3 · Symbol Grid</h2>
      <div class="scroll" style="flex:1 1 auto; overflow:auto;">
        <table>
          <thead><tr><th>Symbol</th><th>Status</th></tr></thead>
          <tbody id="sym-body"><tr><td colspan="2" style="color:var(--muted)">Loading…</td></tr></tbody>
        </table>
      </div>
    </section>

    <section class="quad">
      <h2>Q4 · Log Flow</h2>
      <div class="log-feed" id="log-feed"><div style="color:var(--muted)">Awaiting stream…</div></div>
    </section>
  </main>

  <script>
    const $ = id => document.getElementById(id);
    function money(v){ return v==null ? '—' : '$'+Number(v).toLocaleString(undefined,{maximumFractionDigits:2}); }
    function pill(txt, cls='info'){ return `<span class="pill ${cls}">${txt}</span>`; }
    function esc(s){ return String(s??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

    function cleanLog(raw){
      try {
        const o = JSON.parse(raw);
        const parts = [o.ts||'', o.symbol||'', o.event||'', o.status||'', typeof o.message==='string' ? o.message : JSON.stringify(o.message), o.reason||''].filter(Boolean);
        if(parts.length) return esc(parts.join('  |  '));
      } catch(e){}
      return esc(String(raw||'').replace(/^[\s\[\]{}"']+|[\s\[\]{}"']+$/g, '').replace(/\"/g,'"'));
    }

    async function refresh(){
      try {
        const res = await fetch('/api/status', {cache:'no-store'});
        const d = await res.json();
        $('stamp').textContent = d.generated_at || '—';
        $('equity').textContent = money(d.equity_usd);
        $('realized-pnl').textContent = '—';
        $('withdrawals').textContent = '—';
        $('positions').textContent = d.open_positions ?? '—';
        $('working-orders').textContent = d.protection_truth?.stale_algo_order_count ?? '—';
        const h = d.protection_truth?.healthy;
        $('protection').innerHTML = h===true ? pill('HEALTHY','ok') : (h===false ? pill('DRIFT','bad') : pill('NO DATA'));
        $('exec-mode').textContent = d.execution_mode || '—';

        const syms = new Set();
        const logs = Array.isArray(d.log_tail) ? d.log_tail : [];
        for(const row of logs){ try{ const o = JSON.parse(row); if(o.symbol) syms.add(o.symbol); }catch(e){} }
        const tb = $('sym-body');
        const html = [...syms].sort().map(s => `<tr><td>${esc(s)}</td><td>ACTIVE</td></tr>`).join('');
        tb.innerHTML = html.length ? html : '<tr><td colspan="2" style="color:var(--muted)">No active feeds</td></tr>';

        const feed = $('log-feed');
        const rows = logs.slice(-40).reverse().map(r => `<div class="log-row">${cleanLog(r)}</div>`).join('');
        feed.innerHTML = rows || '<div class="log-row" style="color:var(--muted)">No events</div>';
      } catch(err) {
        $('log-feed').innerHTML = `<div class="log-row" style="color:var(--red)">${esc(err.message||err)}</div>`;
      }
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def fetch_bot_status() -> dict:
    try:
        with urlopen('http://127.0.0.1:5000/status', timeout=3) as response:
            return json.loads(response.read().decode('utf-8'))
    except URLError as exc:
        return {'status': 'error', 'error': str(exc)}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def tail_lines(path: Path, count: int = 20) -> list[str]:
    try:
        lines = path.read_text(errors='replace').splitlines()
        return lines[-count:]
    except Exception as exc:
        return [f'Unable to read log: {exc}']


def build_payload() -> dict:
    cfg = read_json(CONFIG_PATH)
    bot = fetch_bot_status()
    reconciliation = bot.get('reconciliation') or {}
    protection = bot.get('product_sync_health', {}).get('protection_truth') or bot.get('protection') or {}
    testnet = bot.get('testnet') or {}
    risk = bot.get('risk') or {}
    return {
        'generated_at': datetime.now(UTC).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'),
        'execution_mode': bot.get('execution_mode'),
        'active_symbols_count': len(bot.get('active_symbols') or []),
        'equity_usd': testnet.get('equity', risk.get('equity_usd')),
        'open_positions': testnet.get('positions', 0),
        'active_blockers': bot.get('active_blockers') or [],
        'product_sync_issues': bot.get('product_sync_health', {}).get('issues') or [],
        'operator_actions': bot.get('product_sync_health', {}).get('operator_action_required') or [],
        'testnet_blocked': bool(testnet.get('blocked', False)),
        'trailing_config': {
            'breakeven_trigger_r': cfg.get('breakeven_trigger_r'),
            'trail_activation_r': cfg.get('trail_activation_r'),
            'trail_distance_r': cfg.get('trail_distance_r'),
            'momentum_exit_r': cfg.get('momentum_exit_r'),
            'profit_protect_r': cfg.get('profit_protect_r'),
            'time_reduce_hours': cfg.get('time_reduce_hours'),
            'time_exit_hours': cfg.get('time_exit_hours'),
        },
        'protection_truth': {
            'healthy': bool(protection.get('healthy', reconciliation.get('healthy', False))),
            'critical_mismatches': int(protection.get('critical_mismatches', reconciliation.get('critical_mismatch_count', 0)) or 0),
            'warning_count': int(protection.get('warnings', reconciliation.get('warning_count', 0)) or 0),
            'stale_algo_order_count': int(protection.get('stale_algo_orders', reconciliation.get('stale_algo_order_count', 0)) or 0),
        },
        'log_tail': tail_lines(LOG_PATH, 20),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            body = HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/api/status':
            body = json.dumps(build_payload()).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/health':
            body = b'ok'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        return


def main() -> None:
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'OzzyBot dashboard running on http://127.0.0.1:{PORT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
