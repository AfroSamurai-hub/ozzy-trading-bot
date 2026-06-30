#!/home/rick/ozzy-bot/venv/bin/python
"""
OZZYBOT HEALTH DOCTOR DIAGNOSTICS
Designed by Antigravity AI
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, '/home/rick/ozzy-bot')

C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_YELLOW = '\033[93m'
C_BLUE = '\033[94m'
C_BOLD = '\033[1m'
C_RESET = '\033[0m'

# List of user units checked by the doctor.  The third field marks whether a
# unit is required for the live-micro execution path; deprecated/testnet units
# are informational so they do not create false critical alerts.
CORE_UNITS = [
    ("ozzybot-webhook.service", "Unified Webhook", True),
    ("ozzybot-monitor.service", "Lifecycle Monitor", True),
    ("ozzybot-telegram-cmd.service", "Telegram Command Bot", True),
    ("ozzybot-signal.timer", "Hourly Signal Timer", True),
    ("ozzybot-15m-reversion.timer", "15m Reversion Scanner Timer", True),
    ("ozzybot-openclaw-macro-scout.timer", "OpenClaw 4H Scout", True),
    ("ozzybot-openclaw-trend-executor.timer", "OpenClaw Executor", True),
    ("ozzybot-openclaw-breakout-executor.timer", "OpenClaw Breakout Trigger", True),
    ("ozzybot-doctor-watchdog.timer", "Doctor Watchdog", True),
    ("ozzybot-openclaw-market-sniper.timer", "OpenClaw Sniper", False),
]

# Shared state files: path → (expected_max_age_seconds, writer, consumers)
# expected_max_age = writer timer interval + 30 min buffer
STATE_FILES = {
    "/home/rick/ozzy-bot/shared/market_regimes.json":               (5 * 3600, "macro_scout.py",        ["signal_generator.py", "15m_reversion_scanner.py"]),
    "/home/rick/ozzy-bot/shared/active_orders.json":                (2 * 3600, "trend_executor.py",      ["openclaw_breakout_executor.py", "telegram_reporter.py (reporting only)"]),
    "/home/rick/ozzy-bot/shared/openclaw_breakout_state.json":       (10 * 60, "openclaw_breakout_executor.py", ["ozzybot_doctor.py", "telegram_reporter.py (reporting only)"]),
    "/home/rick/ozzy-bot/shared/sniper_candidates.json":            (1800,     "market_sniper.py",       ["15m_reversion_scanner.py"]),
    "/home/rick/ozzy-bot/shared/scout.heartbeat":                   (5 * 3600, "macro_scout.py",        ["ozzybot_doctor.py", "telegram_reporter.py"]),
    "/home/rick/ozzy-bot/shared/executor.heartbeat":                (2 * 3600, "trend_executor.py",      ["ozzybot_doctor.py", "telegram_reporter.py"]),
    "/home/rick/ozzy-bot/shared/sniper.heartbeat":                  (1800,     "market_sniper.py",       ["ozzybot_doctor.py", "telegram_reporter.py"]),
    # Observer directory — written by ozzy_context_observer.py (every 5 min)
    # NOTE: loss_cooldowns and orphan_positions are only rewritten when open
    # trades exist. With no open positions the observer skips them intentionally.
    # Use a 12h window so a quiet period doesn't trigger false STALE alerts.
    "/home/rick/ozzy-bot/observer/loss_cooldowns.json":             (24 * 3600, "context_observer.py",    ["webhook.py (via loss_cooldowns.py)"]),
    "/home/rick/ozzy-bot/observer/orphan_positions.json":           (24 * 3600, "context_observer.py",    ["webhook.py", "command_center.py"]),
    "/home/rick/ozzy-bot/observer/loss_minimization_candidates.json": (1800,   "context_observer.py",    ["telegram_client.py (notify_loss_minimization_candidate)"]),
    "/home/rick/ozzy-bot/observer/action_queue.json":               (1800,     "context_observer.py",    ["context_observer.py (self-managed queue)"]),
}

# HERMES_ env vars explicitly excluded from coverage check
# (secrets live in .env, not live-micro.env; or are intentionally left unset)
ENV_COVERAGE_SKIP = {
    "HERMES_BINANCE_API_KEY", "HERMES_BINANCE_API_SECRET",
    "HERMES_BINANCE_DEMO_API_KEY", "HERMES_BINANCE_DEMO_API_SECRET",
    "HERMES_GEMINI_MODEL",
    # Intentionally NOT set — regime gate controls this dynamically
    "HERMES_MR_LIVE_LANES", "HERMES_MR_LIVE_SYMBOLS",
    # Not needed in live-micro instance
    "HERMES_OBSIDIAN_EXPORT_DISABLED", "HERMES_OZZY_MEMORY_DB",
    "HERMES_STATUS_KEY", "HERMES_REVERSAL_CAPTURE_SYMBOLS",
}

def check_unit_status(unit):
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            check=False,
        )
        state = proc.stdout.strip()
        if proc.returncode == 0 and state == "active":
            return "active", "running"
        return "inactive", state or "unknown"
    except Exception:
        return "unknown", "error"

def check_port_binds():
    binds = {}
    try:
        proc = subprocess.run(["ss", "-tuln"], capture_output=True, text=True, check=True)
        for line in proc.stdout.splitlines():
            if ":5000" in line:
                binds[5000] = "0.0.0.0" if "0.0.0.0:5000" in line or "*:5000" in line or "[::]:5000" in line else "127.0.0.1"
            if ":5001" in line:
                binds[5001] = "0.0.0.0" if "0.0.0.0:5001" in line or "*:5001" in line or "[::]:5001" in line else "127.0.0.1"
    except Exception:
        pass

    for port in [5000, 5001]:
        if port not in binds:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                binds[port] = "detected"
                s.close()
            except Exception:
                binds[port] = "closed"
    return binds

def check_cloudflared():
    try:
        proc = subprocess.run(["pgrep", "-f", "cloudflared"], capture_output=True, text=True)
        return proc.returncode == 0
    except Exception:
        return False


def check_state_file_freshness(overall_ok: bool) -> bool:
    """Check that all shared state files are within their expected refresh windows."""
    import time
    print(f"\n{C_BOLD}5. SHARED STATE FILE FRESHNESS{C_RESET}")
    print("-" * 60)
    now = time.time()
    for path, (max_age, writer, consumers) in STATE_FILES.items():
        if not os.path.exists(path):
            print(f"  {C_RED}MISSING{C_RESET}  {os.path.basename(path):<35} (writer: {writer})")
            overall_ok = False
            continue
        age = now - os.path.getmtime(path)
        age_min = int(age / 60)
        max_min = int(max_age / 60)
        if age > max_age:
            print(f"  {C_RED}STALE{C_RESET}    {os.path.basename(path):<35} age={age_min}m  limit={max_min}m  writer={writer}")
            overall_ok = False
        else:
            print(f"  {C_GREEN}FRESH{C_RESET}    {os.path.basename(path):<35} age={age_min}m  limit={max_min}m")
    return overall_ok


def classify_state_file_consumers(consumers: list[str]) -> tuple[str, str]:
    """Classify whether a shared state file has an execution consumer or only reports."""
    if not consumers:
        return "ORPHANED", "no consumers registered"
    executable = [c for c in consumers if "reporting only" not in c.lower() and "telegram_reporter" not in c.lower()]
    if not executable:
        return "REPORTING_ONLY", "no execution consumer; state is advisory/reporting only"
    return "WIRED", "execution consumer present"


def check_shared_state_seams(overall_ok: bool) -> bool:
    """Warn about state files whose consumers are missing or reporting-only."""
    print(f"\n{C_BOLD}6. SHARED STATE SEAM AUDIT{C_RESET}")
    print("-" * 60)
    for path, (_, writer, consumers) in STATE_FILES.items():
        fname = os.path.basename(path)
        status, reason = classify_state_file_consumers(consumers)
        if status == "ORPHANED":
            print(f"  {C_RED}ORPHANED{C_RESET} {fname:<35} written by {writer} — {reason}")
            overall_ok = False
        elif status == "REPORTING_ONLY":
            print(f"  {C_YELLOW}REPORT{C_RESET}   {fname:<35} → {', '.join(consumers)} — {reason}")
            overall_ok = False
        else:
            print(f"  {C_GREEN}WIRED{C_RESET}    {fname:<35} → {', '.join(consumers)}")
    return overall_ok


def check_env_coverage(overall_ok: bool) -> bool:
    """Check that HERMES_* vars referenced in Python are present in live-micro.env."""
    import re
    print(f"\n{C_BOLD}7. ENV COVERAGE CHECK{C_RESET}")
    print("-" * 60)
    env_file = "/home/rick/ozzy-bot/config/live-micro.env"
    try:
        defined = set()
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    defined.add(line.split("=", 1)[0].strip())
    except Exception as e:
        print(f"  {C_RED}Cannot read env file: {e}{C_RESET}")
        return overall_ok

    # Scan all .py files for os.getenv("HERMES_*") calls
    referenced = set()
    root = "/home/rick/ozzy-bot"
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("venv", "__pycache__", ".git")]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, fname)) as f:
                    for match in re.finditer(r'os\.getenv\([\'"]( HERMES_[A-Z_]+)[\'"]', f.read()):
                        referenced.add(match.group(1).strip())
            except Exception:
                pass

    missing = (referenced - defined) - ENV_COVERAGE_SKIP
    if missing:
        for var in sorted(missing):
            print(f"  {C_YELLOW}MISSING{C_RESET}  {var}")
        print(f"  {C_YELLOW}{len(missing)} var(s) used in code but not in live-micro.env{C_RESET}")
    else:
        print(f"  {C_GREEN}All HERMES_* vars are documented in live-micro.env{C_RESET}")
    return overall_ok

def assess_openclaw_breakout_state(path: str | Path = "/home/rick/ozzy-bot/shared/openclaw_breakout_state.json", max_age_seconds: int = 600) -> dict:
    """Assess whether the OpenClaw breakout watcher is scanning recently."""
    p = Path(path)
    if not p.exists():
        return {"status": "CRITICAL", "reason": "openclaw_breakout_state missing", "path": str(p)}
    age = time.time() - p.stat().st_mtime
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception as exc:
        return {"status": "CRITICAL", "reason": f"openclaw_breakout_state unreadable: {exc}", "path": str(p)}
    if age > max_age_seconds:
        return {"status": "CRITICAL", "reason": f"openclaw_breakout_state stale age={int(age)}s", "age_seconds": int(age), "path": str(p)}
    results = data.get("last_results") or []
    checked = len(results) if isinstance(results, list) else 0
    fired = sum(1 for row in results if isinstance(row, dict) and row.get("status") == "FIRED")
    return {"status": "OK", "reason": "fresh", "age_seconds": int(age), "checked": checked, "fired_recent": fired, "path": str(p)}


def _is_transient_binance_error(message: str) -> bool:
    text = str(message or "").lower()
    return any(
        marker in text
        for marker in (
            "timeout",
            "timed out",
            "read timed out",
            "code=-1007",
            "temporary failure",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "remote end closed connection",
        )
    )


def classify_product_sync_health(status_json: dict) -> dict:
    """Classify product sync/protection truth from webhook /status JSON."""
    health = status_json.get("product_sync_health") or {}
    protection = health.get("protection_truth") or status_json.get("protection") or {}
    reconciliation = status_json.get("reconciliation") or {}
    critical = int(protection.get("critical_mismatches") or 0)
    operator_actions = health.get("operator_action_required") or []
    issues = health.get("issues") or []
    healthy_raw = protection.get("healthy", critical == 0)
    reconciliation_unavailable = bool(
        "exchange_reconciliation_unavailable" in issues
        or protection.get("data_unavailable")
        or reconciliation.get("data_unavailable")
        or (healthy_raw is None and (protection.get("reconciliation_refresh_error") or reconciliation.get("reconciliation_refresh_error")))
    )
    if reconciliation_unavailable and critical == 0 and not operator_actions:
        return {
            "status": "DEGRADED",
            "reason": "exchange reconciliation unavailable/stale; using cached or unknown state",
            "critical_mismatches": 0,
            "operator_action_required": [],
            "pause_entries_recommended": False,
        }
    healthy = bool(healthy_raw)
    if critical > 0 or operator_actions or not healthy:
        return {
            "status": "CRITICAL",
            "reason": "exchange/db/protection mismatch",
            "critical_mismatches": critical,
            "operator_action_required": operator_actions,
            "pause_entries_recommended": True,
        }
    return {"status": "OK", "reason": "db_exchange_and_protection_agree", "critical_mismatches": 0, "operator_action_required": [], "pause_entries_recommended": False}


def default_status_url() -> str:
    """Return the authoritative local status URL for the active runtime."""
    explicit = os.getenv("HERMES_STATUS_URL")
    if explicit:
        return explicit
    port = os.getenv("HERMES_PORT") or os.getenv("PORT") or "5001"
    return f"http://127.0.0.1:{port}/status"


def fetch_webhook_status(url: str | None = None) -> dict:
    """Fetch the active runtime webhook /status."""
    if url is None:
        url = default_status_url()
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def summarize_lane_performance(
    db_path: str | Path = "/home/rick/ozzy-bot/trades.db",
    since: str = "2026-06-01",
    include_archived: bool = False,
) -> list[dict]:
    """Return lane scorecard grouped by strategy_label since a cutoff."""
    db = Path(db_path)
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    archived_clause = "" if include_archived else "AND COALESCE(strategy_label, 'UNKNOWN') NOT IN ('1H_TREND_CONTINUATION')"
    try:
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(strategy_label, 'UNKNOWN') AS strategy_label,
                COUNT(*) AS trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS win_rate_pct,
                ROUND(SUM(COALESCE(pnl, 0)), 2) AS pnl,
                ROUND(SUM(COALESCE(r_multiple, 0)), 2) AS sum_r,
                ROUND(AVG(COALESCE(r_multiple, 0)), 3) AS avg_r
            FROM trades
            WHERE ts >= ?
              AND exit_price IS NOT NULL
              AND COALESCE(exit_reason, '') NOT IN ('execution_failed','execution_timeout_flat','migrated','migrated_legacy','migrated_duplicate','ghost_cleanup','stale_entry_filled_cleanup')
              {archived_clause}
            GROUP BY COALESCE(strategy_label, 'UNKNOWN')
            ORDER BY sum_r DESC, trades DESC
            """,
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def render_watchdog_scorecard() -> tuple[bool, list[str]]:
    """Build concise watchdog scorecard lines and return (ok, lines)."""
    lines = []
    overall_ok = True
    openclaw = assess_openclaw_breakout_state()
    if openclaw["status"] != "OK":
        overall_ok = False
    lines.append(f"OpenClaw breakout watcher: {openclaw['status']} — {openclaw['reason']}")

    try:
        sync = classify_product_sync_health(fetch_webhook_status())
    except Exception as exc:
        sync = {"status": "CRITICAL", "reason": f"status fetch failed: {exc}", "pause_entries_recommended": True}
    if sync["status"] == "CRITICAL":
        overall_ok = False
    lines.append(f"DB/exchange/protection sync: {sync['status']} — {sync['reason']}")

    lanes = summarize_lane_performance()
    lines.append("Lane scorecard since 2026-06-01 (archived 1H_TREND_CONTINUATION omitted):")
    if not lanes:
        lines.append("  no closed lane data")
    for row in lanes[:6]:
        lines.append(
            f"  {row['strategy_label']}: trades={row['trades']} WR={row['win_rate_pct']}% PnL={row['pnl']} SumR={row['sum_r']}"
        )
    return overall_ok, lines


def validate_binance_subprocess(env_file=None):
    python_path = "/home/rick/ozzy-bot/venv/bin/python"
    code = """
import os, sys
sys.path.append('/home/rick/ozzy-bot')
env_file = {env_file_repr}
if env_file:
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k] = v.strip('\"\\'')
try:
    from binance_connector import validate_binance_credentials, get_balance
    ok, reason = validate_binance_credentials()
    if ok:
        bal = get_balance()
        equity = bal.get('equity', 0)
        curr = bal.get('currency', 'USDT')
        print(f"OK|{{equity}}|{{curr}}|{{reason}}")
    else:
        print(f"FAIL|0|USDT|{{reason}}")
except Exception as e:
    print(f"ERROR|0|USDT|{{e}}")
"""
    code_formatted = code.format(env_file_repr=repr(env_file))
    try:
        proc = subprocess.run(
            [python_path, "-c", code_formatted],
            capture_output=True,
            text=True,
            timeout=10
        )
        return proc.stdout.strip()
    except Exception as e:
        return f"ERROR|0|USDT|{e}"


def classify_binance_validation_output(raw_output: str) -> dict:
    """Classify Doctor's direct Binance credential check without false CRITICAL on timeouts."""
    line = next(
        (line for line in str(raw_output or "").splitlines() if line.startswith(("OK|", "FAIL|", "ERROR|"))),
        "",
    )
    if line.startswith("OK|"):
        _, equity, currency, message = line.split("|", 3)
        return {"status": "OK", "equity": equity, "currency": currency, "message": message}
    message = line.split("|")[-1] if "|" in line else (raw_output or "Connection Failed")
    if _is_transient_binance_error(message):
        return {"status": "DEGRADED", "equity": "0", "currency": "USDT", "message": message}
    return {"status": "CRITICAL", "equity": "0", "currency": "USDT", "message": message}


def main():
    if "--watchdog-only" in sys.argv:
        ok, lines = render_watchdog_scorecard()
        for line in lines:
            print(line)
        if not ok and "--watchdog-alert" in sys.argv:
            try:
                import telegram_client
                telegram_client.send_message("🔴 <b>OZZYBOT DOCTOR WATCHDOG</b>\n" + "\n".join(lines[:10]))
            except Exception as exc:
                print(f"Telegram alert failed: {exc}")
        return 0

    print(f"{C_BOLD}{C_BLUE}============================================================{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}             OZZYBOT HEALTH DOCTOR DIAGNOSTICS              {C_RESET}")
    print(f"{C_BOLD}{C_BLUE}============================================================{C_RESET}")

    overall_ok = True

    # 1. Check systemd units
    print(f"\n{C_BOLD}1. SYSTEMD USER SERVICES & TIMERS{C_RESET}")
    print("-" * 60)
    for unit, desc, required in CORE_UNITS:
        state, substate = check_unit_status(unit)
        if state == "active":
            status_str = f"{C_GREEN}ACTIVE ({substate}){C_RESET}"
        elif state == "inactive":
            status_str = f"{C_RED}INACTIVE ({substate}){C_RESET}" if required else f"{C_BLUE}INACTIVE ({substate}) - optional{C_RESET}"
            if required:
                overall_ok = False
        else:
            status_str = f"{C_RED}FAILED ({substate}){C_RESET}" if required else f"{C_BLUE}{state.upper()} ({substate}) - optional{C_RESET}"
            if required:
                overall_ok = False
        criticality = "required" if required else "optional"
        print(f"  {desc:<25} ({unit:<36}) : {status_str} [{criticality}]")

    # 2. Check port bindings
    print(f"\n{C_BOLD}2. WEBHOOK PORT BINDINGS & SECURITY{C_RESET}")
    print("-" * 60)
    binds = check_port_binds()
    for port, desc, required in [(5000, "Testnet Webhook", False), (5001, "Live Micro Webhook", True)]:
        bind_status = binds.get(port, "closed")
        if bind_status == "0.0.0.0":
            print(f"  Port {port} ({desc}) : {C_YELLOW}Exposed Globally (0.0.0.0) - SECURITY WARNING!{C_RESET}")
        elif bind_status == "127.0.0.1":
            print(f"  Port {port} ({desc}) : {C_GREEN}Securely Bound to localhost (127.0.0.1){C_RESET}")
        elif bind_status == "detected":
            print(f"  Port {port} ({desc}) : {C_GREEN}Listening (interface not verified){C_RESET}")
        else:
            status = f"{C_RED}CLOSED / NOT LISTENING!{C_RESET}" if required else f"{C_BLUE}closed / optional{C_RESET}"
            print(f"  Port {port} ({desc}) : {status}")
            if required:
                overall_ok = False

    # 3. Check cloudflared (AUXILIARY/LEGACY)
    print(f"\n{C_BOLD}3. AUXILIARY & LEGACY SERVICES{C_RESET}")
    print("-" * 60)
    cf_running = check_cloudflared()
    if cf_running:
        print(f"  Cloudflare Tunnel (cloudflared) : {C_GREEN}RUNNING (Auxiliary / Legacy - Non-critical){C_RESET}")
    else:
        print(f"  Cloudflare Tunnel (cloudflared) : {C_BLUE}NOT RUNNING (Auxiliary / Legacy - Non-critical){C_RESET}")

    # 4. Check exchange connectivity
    print(f"\n{C_BOLD}4. BINANCE EXCHANGE INFRASTRUCTURE{C_RESET}")
    print("-" * 60)

    # Testnet check
    print("  Checking Binance Testnet Connection ... ", end="", flush=True)
    t_res = validate_binance_subprocess(None)
    t_status = classify_binance_validation_output(t_res)

    if t_status["status"] == "OK":
        print(f"{C_GREEN}OK{C_RESET} (Equity: {t_status['equity']} {t_status['currency']}, {t_status['message']})")
    elif t_status["status"] == "DEGRADED":
        print(f"{C_YELLOW}DEGRADED{C_RESET} ({t_status['message']} — transient Binance timeout/slowness; not critical)")
    else:
        print(f"{C_RED}FAILED{C_RESET} ({t_status['message']})")
        overall_ok = False

    # Live Micro check
    print("  Checking Binance Live Micro Connection ... ", end="", flush=True)
    l_res = validate_binance_subprocess("/home/rick/ozzy-bot/config/live-micro.env")
    l_status = classify_binance_validation_output(l_res)

    if l_status["status"] == "OK":
        print(f"{C_GREEN}OK{C_RESET} (Equity: {l_status['equity']} {l_status['currency']}, {l_status['message']})")
    elif l_status["status"] == "DEGRADED":
        print(f"{C_YELLOW}DEGRADED{C_RESET} ({l_status['message']} — transient Binance timeout/slowness; not critical)")
    else:
        print(f"{C_RED}FAILED{C_RESET} ({l_status['message']})")
        overall_ok = False

    # 5-7: New seam / freshness / env checks
    overall_ok = check_state_file_freshness(overall_ok)
    overall_ok = check_shared_state_seams(overall_ok)
    check_env_coverage(overall_ok)  # env gaps are warnings, not overall_ok blockers

    # 8. Watchdog scorecard
    watchdog_ok, watchdog_lines = render_watchdog_scorecard()
    print(f"\n{C_BOLD}8. WATCHDOG SCORECARD{C_RESET}")
    print("-" * 60)
    for line in watchdog_lines:
        colour = C_GREEN if "OK" in line else C_RED if "CRITICAL" in line else C_RESET
        print(f"  {colour}{line}{C_RESET}")
    if not watchdog_ok:
        overall_ok = False
        if "--watchdog-alert" in sys.argv:
            try:
                import telegram_client
                telegram_client.send_message("🔴 <b>OZZYBOT DOCTOR WATCHDOG</b>\n" + "\n".join(watchdog_lines[:10]))
            except Exception as exc:
                print(f"  {C_YELLOW}Telegram alert failed: {exc}{C_RESET}")

    # Final summary
    print(f"\n{C_BOLD}{C_BLUE}============================================================{C_RESET}")
    if overall_ok:
        print(f"{C_BOLD}{C_GREEN}        DIAGNOSTICS COMPLETE: ALL CRITICAL SYSTEMS HEALTHY          {C_RESET}")
    else:
        print(f"{C_BOLD}{C_RED}        DIAGNOSTICS COMPLETE: CRITICAL SYSTEM ISSUES DETECTED        {C_RESET}")
    print(f"{C_BOLD}{C_BLUE}============================================================{C_RESET}")

    sys.exit(0 if overall_ok else 1)

if __name__ == "__main__":
    main()
