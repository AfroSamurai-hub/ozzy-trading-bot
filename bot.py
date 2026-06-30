import json
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
import pytz
from filelock import FileLock
from config import RISK_PERCENT, KILL_ZONES, KILL_ZONE_BYPASS_SYMBOLS
try:
    from win_rate_tracker import get_stats
except ModuleNotFoundError:
    def get_stats(last_n=None):
        return None

CRYPTO_SYMBOLS = ["ETHUSD", "ETHUSDT", "SOLUSD", "SOLUSDT", "LINKUSDT", "DOGEUSDT", "SUIUSDT", "HYPEUSDT"]

SA_TZ = pytz.timezone("Africa/Johannesburg")

def is_kill_zone(symbol="XAUUSD"):
    # v2026-04-17: Bypass kill zone for specific pairs that showed 100% win rate when blocked
    if symbol in KILL_ZONE_BYPASS_SYMBOLS:
        return True
    if symbol in CRYPTO_SYMBOLS:
        return True
    now = datetime.now(SA_TZ)
    current_time = now.strftime("%H:%M")
    for zone in KILL_ZONES:
        if zone["start"] <= current_time <= zone["end"]:
            return True
    return False

def _resolve_kelly_inputs(win_rate, avg_rr):
    """Resolve Kelly inputs from args or recent closed trade stats."""
    if win_rate is not None and avg_rr is not None:
        return win_rate, avg_rr
    stats = get_stats(last_n=50)
    if not stats:
        return win_rate, avg_rr
    if int(stats.get("total_trades", 0)) < 50:
        return None, None
    resolved_win_rate = win_rate if win_rate is not None else stats.get("win_rate")
    resolved_avg_rr = avg_rr if avg_rr is not None else stats.get("avg_rr")
    return resolved_win_rate, resolved_avg_rr


def calculate_lot_size(balance, risk_percent, sl_distance, contract_size=100, win_rate=None, avg_rr=None):
    sl_distance_dec = Decimal(str(sl_distance))
    if sl_distance_dec <= Decimal("0"):
        return 0.01
    balance_dec = Decimal(str(balance))
    risk_percent_dec = Decimal(str(risk_percent))
    contract_size_dec = Decimal(str(contract_size))
    risk_amount = balance_dec * (risk_percent_dec / Decimal("100"))
    lot = risk_amount / (sl_distance_dec * contract_size_dec)
    resolved_win_rate, resolved_avg_rr = _resolve_kelly_inputs(win_rate, avg_rr)
    if resolved_win_rate is not None and resolved_avg_rr is not None:
        win_rate_dec = Decimal(str(resolved_win_rate))
        avg_rr_dec = Decimal(str(resolved_avg_rr))
        if avg_rr_dec > Decimal("0"):
            kelly = win_rate_dec - ((Decimal("1") - win_rate_dec) / avg_rr_dec)
            if kelly <= Decimal("0"):
                kelly_multiplier = Decimal("0.5")
            else:
                kelly_multiplier = kelly * Decimal("0.5")
            lot *= kelly_multiplier
    lot = lot.quantize(Decimal("0.01"))
    lot = max(Decimal("0.01"), lot)
    return float(lot)


def calculate_atr_levels(signal: str, entry: float, atr: float,
                          sl_mult: float, rr: float = 2.5):
    """
    Compute SL and TP from ATR.

    SL distance = atr * sl_mult
    TP distance = SL distance * rr  (enforces exact RR)

    Returns (sl, tp, sl_distance) all as floats rounded to 5 dp.
    """
    entry_dec = Decimal(str(entry))
    atr_dec = Decimal(str(atr))
    sl_mult_dec = Decimal(str(sl_mult))
    rr_dec = Decimal(str(rr))
    sl_distance = (atr_dec * sl_mult_dec).quantize(Decimal("0.00001"))
    tp_distance = (sl_distance * rr_dec).quantize(Decimal("0.00001"))

    if signal == "BUY":
        sl = (entry_dec - sl_distance).quantize(Decimal("0.00001"))
        tp = (entry_dec + tp_distance).quantize(Decimal("0.00001"))
    else:  # SELL
        sl = (entry_dec + sl_distance).quantize(Decimal("0.00001"))
        tp = (entry_dec - tp_distance).quantize(Decimal("0.00001"))

    return float(sl), float(tp), float(sl_distance)


def check_drawdown(paper_file: str, daily_limit_pct: float, balance: float) -> bool:
    """
    Return True if today's realised losses in paper_trades.json have hit the
    daily drawdown limit.

    Counts only trades with an exit_ts dated today.
    Win  → +reward_dollars
    Loss → -risk_dollars

    NOTE: accuracy depends on paper_trades.json being up to date.
    In live mode, replace this with a MetaAPI equity query.
    """
    today_str = date.today().isoformat()   # "2026-04-15"
    try:
        lock_file = str(Path(paper_file).with_name("paper_trades.json.lock"))
        with FileLock(lock_file):
            with open(paper_file) as f:
                data = json.load(f)
    except Exception:
        return False   # can't read file → don't block trading

    today_pnl = 0.0
    for t in data.get("trades", []):
        exit_ts = t.get("exit_ts") or ""
        if not exit_ts.startswith(today_str):
            continue
        status = t.get("status")
        if status == "win":
            today_pnl += float(t.get("reward_dollars", 0))
        elif status == "loss":
            today_pnl -= float(t.get("risk_dollars", 0))

    if balance <= 0:
        return False

    drawdown_pct = (today_pnl / balance) * 100
    return drawdown_pct <= -abs(daily_limit_pct)
