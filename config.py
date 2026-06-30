# ============================================
# OZZY BOT — Configuration
# ============================================
import copy
import json
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()  # Load secrets from .env file


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_json_dict(name: str, default: dict):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    value = value.strip().strip("'\"")
    return json.loads(value)


@dataclass
class LaneConfig:
    symbols: list[str]
    timeframe: str
    risk_budget_pct: float
    max_positions: int
    max_positions_per_symbol: int
    enabled: bool
    signal_sources: list[str]
    setup_types: set[str] = field(default_factory=set)
    early_profit_protection: dict | None = None


# Trading settings
SYMBOL = "XAUUSD"
RISK_PERCENT = 5.0        # 5% per trade

# Binance Futures percentage-based risk per trade.
# 2% of equity per trade. Scales automatically as account grows.
RISK_PCT = _env_float("HERMES_RISK_PCT", 0.02)
SMALL_CAP_LAUNCH_MODE = _env_bool("HERMES_SMALL_CAP_LAUNCH_MODE", True)  # lower exposure until clean live sample exists.
# Micro-bootstrap mode is deprecated by the unified equity-percentage model.
# Kept as env-overridable for backward compatibility, but disabled by default.
MICRO_BOOTSTRAP_MODE = _env_bool("HERMES_MICRO_BOOTSTRAP_MODE", False)
MICRO_BOOTSTRAP_RISK_USD = _env_float("HERMES_MICRO_BOOTSTRAP_RISK_USD", 5.0)
MICRO_BOOTSTRAP_EQUITY_CEILING_USD = _env_float("HERMES_MICRO_BOOTSTRAP_EQUITY_CEILING_USD", 250.0)
MICRO_BOOTSTRAP_MAX_POSITIONS = _env_int("HERMES_MICRO_BOOTSTRAP_MAX_POSITIONS", 1)
# Live-micro experiment settings (safe defaults; aggressive overrides live in live-micro.env)
LIVE_MICRO_MIN_TRADE_RISK = _env_float("HERMES_LIVE_MICRO_MIN_TRADE_RISK", 1.24)
LIVE_MICRO_RISK_SAFETY_FACTOR = _env_float("HERMES_LIVE_MICRO_RISK_SAFETY_FACTOR", 0.90)
LIVE_MICRO_USE_THEORETICAL_DAILY_RISK_BLOCK = _env_bool("HERMES_LIVE_MICRO_USE_THEORETICAL_DAILY_RISK_BLOCK", False)
LIVE_MICRO_MAX_REALIZED_DAILY_LOSS_USD = _env_float("HERMES_LIVE_MICRO_MAX_REALIZED_DAILY_LOSS_USD", 11.0)
LIVE_MICRO_MAX_CONSECUTIVE_LOSSES = _env_int("HERMES_LIVE_MICRO_MAX_CONSECUTIVE_LOSSES", 2)
LIVE_MICRO_MAX_TRADES_PER_DAY = _env_int("HERMES_LIVE_MICRO_MAX_TRADES_PER_DAY", 3)
LIVE_MICRO_SAFETY_INCIDENT_RISK_MULTIPLIER = _env_float("HERMES_LIVE_MICRO_SAFETY_INCIDENT_RISK_MULTIPLIER", 0.5)
LIVE_MICRO_B_GRADE_MIN_VOLUME_RATIO = _env_float("HERMES_LIVE_MICRO_B_GRADE_MIN_VOLUME_RATIO", 1.10)
OPENCLAW_BREAKOUT_RISK_CAP_MULTIPLIER = _env_float("HERMES_OPENCLAW_BREAKOUT_RISK_CAP_MULTIPLIER", 1.0)
TESTNET_AUTO_PROTECT_ENABLED = _env_bool("HERMES_TESTNET_AUTO_PROTECT_ENABLED", False)
TESTNET_AUTO_PROTECT_DRY_RUN = _env_bool("HERMES_TESTNET_AUTO_PROTECT_DRY_RUN", True)
LIVE_AUTO_PROTECT_ENABLED = _env_bool("HERMES_LIVE_AUTO_PROTECT_ENABLED", False)
TESTNET_CASH_RATCHET_ENABLED = _env_bool("HERMES_TESTNET_CASH_RATCHET_ENABLED", TESTNET_AUTO_PROTECT_ENABLED)
LIVE_RISK_ESTIMATED_FEE_USD = _env_float("HERMES_LIVE_RISK_ESTIMATED_FEE_USD", 0.0)
LIVE_RISK_SLIPPAGE_BUFFER_USD = _env_float("HERMES_LIVE_RISK_SLIPPAGE_BUFFER_USD", 0.50)
# Unified daily safety rails. LIVE_MAX_DAILY_LOSS_USD=0 means derive from DAILY_LOSS_PCT * equity.
LIVE_MAX_DAILY_LOSS_USD = _env_float("HERMES_LIVE_MAX_DAILY_LOSS_USD", 0.0)
LIVE_MAX_DAILY_FULL_LOSSES = _env_int("HERMES_LIVE_MAX_DAILY_FULL_LOSSES", 1)
LIVE_REARM_AFTER_SAFETY_INCIDENT = _env_bool("HERMES_LIVE_REARM_AFTER_SAFETY_INCIDENT", True)
REQUIRE_CLEAN_RECONCILE_FOR_REARM = _env_bool("HERMES_REQUIRE_CLEAN_RECONCILE_FOR_REARM", True)
REARM_RISK_MULTIPLIER = _env_float("HERMES_REARM_RISK_MULTIPLIER", 0.5)
MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT = _env_int("HERMES_MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT", 1)

# ── Unified safety rails (v2026-06-17 refactor) ──────────────────────────────
# These apply regardless of testnet/live mode. No hidden bypasses.
HERMES_MODE = os.getenv("HERMES_MODE", "testnet").lower()
DAILY_LOSS_PCT = _env_float("HERMES_DAILY_LOSS_PCT", 2.0)
CONSECUTIVE_LOSS_HALT = _env_int("HERMES_CONSECUTIVE_LOSS_HALT", 3)
MAX_TRADES_PER_DAY = _env_int("HERMES_MAX_TRADES_PER_DAY", 5)
OPENCLAW_GATE = _env_bool("HERMES_OPENCLAW_GATE", True)
OPENCLAW_ENABLED_SETUPS = set(
    s.strip().upper()
    for s in os.getenv("HERMES_OPENCLAW_ENABLED_SETUPS", "BREAKOUT").split(",")
    if s.strip()
)

DATA_DRIVEN_LIVE_GATING = _env_bool("HERMES_DATA_DRIVEN_LIVE_GATING", True)
DATA_GATING_DB = os.getenv("HERMES_DATA_GATING_DB", "")
GRADE_HEALTH_MIN_TRADES = _env_int("HERMES_GRADE_HEALTH_MIN_TRADES", 5)
GRADE_HEALTH_LOOKBACK_TRADES = _env_int("HERMES_GRADE_HEALTH_LOOKBACK_TRADES", 20)
GRADE_HEALTH_MIN_AVG_PNL = _env_float("HERMES_GRADE_HEALTH_MIN_AVG_PNL", 0.0)
GRADE_HEALTH_RED_MAX_AVG_PNL = _env_float("HERMES_GRADE_HEALTH_RED_MAX_AVG_PNL", -10.0)
MIN_CLEAN_SAMPLES_FOR_STRATEGY_REDUCE = _env_int("HERMES_MIN_CLEAN_SAMPLES_FOR_STRATEGY_REDUCE", 5)
MIN_CLEAN_SAMPLES_FOR_STRATEGY_BLOCK = _env_int("HERMES_MIN_CLEAN_SAMPLES_FOR_STRATEGY_BLOCK", 20)
LIVE_GATE_REDUCED_RISK_MULTIPLIER = _env_float("HERMES_LIVE_GATE_REDUCED_RISK_MULTIPLIER", 0.5)
SYMBOL_HEAT_MIN_TRADES = _env_int("HERMES_SYMBOL_HEAT_MIN_TRADES", 3)
SYMBOL_HEAT_LOOKBACK_TRADES = _env_int("HERMES_SYMBOL_HEAT_LOOKBACK_TRADES", 12)
SYMBOL_HEAT_MIN_AVG_PNL = _env_float("HERMES_SYMBOL_HEAT_MIN_AVG_PNL", 0.0)
SYMBOL_HEAT_RED_MAX_AVG_PNL = _env_float("HERMES_SYMBOL_HEAT_RED_MAX_AVG_PNL", -10.0)
LIVE_MIN_OPPORTUNITY_ENABLED = _env_bool("HERMES_LIVE_MIN_OPPORTUNITY_ENABLED", True)
LIVE_MIN_OPPORTUNITY_HOURS = _env_float("HERMES_LIVE_MIN_OPPORTUNITY_HOURS", 24.0)
LIVE_MICRO_NO_NEW_ENTRIES = _env_bool("HERMES_LIVE_MICRO_NO_NEW_ENTRIES", False)
PROTECTION_TRUTH_REQUIRED = _env_bool("HERMES_PROTECTION_TRUTH_REQUIRED", True)
PROTECTION_TRUTH_LIVE_ONLY = _env_bool("HERMES_PROTECTION_TRUTH_LIVE_ONLY", False)
PROTECTION_TRUTH_RETRIES = _env_int("HERMES_PROTECTION_TRUTH_RETRIES", 10)
PROTECTION_TRUTH_RETRY_DELAY_SECONDS = _env_float("HERMES_PROTECTION_TRUTH_RETRY_DELAY_SECONDS", 1.0)
# Post-fill protection finalization runs the same repair path on testnet and live.
# A symbol that fills without verified protection gets an SL/TP placed immediately;
# only if repair fails is the position fail-closed.
POST_FILL_PROTECTION_TESTNET_MODE = "repair"
POST_FILL_PROTECTION_LIVE_MODE = "repair"
OZZY_MEMORY_DB = os.getenv("HERMES_OZZY_MEMORY_DB", "/home/rick/ozzy-bot/ozzy_memory.db")
# Gemini is an optional Hermes reasoning layer. It consumes evidence reports and
# has no broker/execution role.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
HERMES_GEMINI_ENABLED = _env_bool("HERMES_GEMINI_ENABLED", False)
HERMES_GEMINI_MODEL = os.getenv("HERMES_GEMINI_MODEL", "gemini-2.5-flash")
HERMES_GEMINI_MAX_CONTEXT_ROWS = _env_int("HERMES_GEMINI_MAX_CONTEXT_ROWS", 20)
HERMES_GEMINI_TEMPERATURE = _env_float("HERMES_GEMINI_TEMPERATURE", 0.2)
HERMES_EVIDENCE_ROW_LIMIT = _env_int("HERMES_EVIDENCE_ROW_LIMIT", 20)
MAX_POSITIONS = _env_int("HERMES_MAX_POSITIONS", 3)  # global cap — total open positions across all symbols
MAX_POSITIONS_PER_SYMBOL = _env_int("HERMES_MAX_POSITIONS_PER_SYMBOL", 1)  # max positions on same symbol
ALLOW_PYRAMIDING = _env_bool("HERMES_ALLOW_PYRAMIDING", False)      # disabled by default
PYRAMID_MIN_PROFIT_PCT = 0.5  # reserved for future use when pyramiding re-enabled
MIN_RR = _env_float("HERMES_MIN_RR", 2.5)              # minimum risk/reward ratio
DAILY_DRAWDOWN_LIMIT = _env_float("HERMES_DAILY_DRAWDOWN_LIMIT", 5.0)  # halt at -N% daily loss
DAILY_DRAWDOWN_ENABLED = _env_bool("HERMES_DAILY_DRAWDOWN_ENABLED", True)
SETUP_GRADE_RISK_MULTIPLIERS = _env_json_dict("HERMES_SETUP_GRADE_RISK_MULTIPLIERS", {"A": 1.0, "B": 0.75, "C": 0.0})
SETUP_GRADE_C_LIVE = False  # C setups are shadow logged only until enough evidence exists.
MIN_NOTIONAL_RISK_OVERRIDE_MODE = os.getenv("HERMES_MIN_NOTIONAL_RISK_OVERRIDE_MODE", "skip")  # "skip" | "allow_micro_growth"
MIN_NOTIONAL_MAX_RISK_MULT = _env_float("HERMES_MIN_NOTIONAL_MAX_RISK_MULT", 1.25)
# Fraction of available balance a new Binance futures entry may consume as
# initial margin. This leaves headroom for price drift, fees, and rounding.
BINANCE_ENTRY_MARGIN_UTILIZATION = _env_float("HERMES_BINANCE_ENTRY_MARGIN_UTILIZATION", 0.90)

# Slippage protection spread limit
MAX_SPREAD_PCT = _env_float("HERMES_MAX_SPREAD_PCT", 0.55)
MAX_ENTRY_DRIFT_PCT = _env_float("HERMES_MAX_ENTRY_DRIFT_PCT", 0.15)
MAX_SIGNAL_AGE_SECONDS = _env_int("HERMES_MAX_SIGNAL_AGE_SECONDS", 90)
LANE_BLOCK_MIN_TRADES = _env_int("HERMES_LANE_BLOCK_MIN_TRADES", 15)
LANE_BLOCK_AVG_R_FLOOR = _env_float("HERMES_LANE_BLOCK_AVG_R_FLOOR", -0.35)
LANE_BLOCK_TOTAL_R_FLOOR = _env_float("HERMES_LANE_BLOCK_TOTAL_R_FLOOR", -5.0)
LANE_BLOCK_RECOVERY_SHADOW_SAMPLES = _env_int("HERMES_LANE_BLOCK_RECOVERY_SHADOW_SAMPLES", 10)
LANE_BLOCK_RECOVERY_AVG_R = _env_float("HERMES_LANE_BLOCK_RECOVERY_AVG_R", 0.20)

# ── Lanes (first-class config objects) ─────────────────────────────────────────
LANES: dict[str, LaneConfig] = {
    "1H_TREND": LaneConfig(
        symbols=[
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
            "LINKUSDT",
            "SUIUSDT",
            "HYPEUSDT",
            "XAUUSDT",
            "NEARUSDT",
            "BNBUSDT",
            "ONDOUSDT",
            "WLDUSDT",
            "ZECUSDT",
            "DRIFTUSDT",
            "INJUSDT",
            "RENDERUSDT",
            "ENAUSDT",
            "SEIUSDT",
        ],
        timeframe="1h",
        risk_budget_pct=0.40,
        max_positions=4,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["signal_generator"],
    ),
    "15M_MEAN_REVERSION": LaneConfig(
        symbols=["LINKUSDT", "BNBUSDT"],
        timeframe="15m",
        risk_budget_pct=0.30,
        max_positions=2,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["15m_reversion_scanner"],
    ),
    "OPENCLAW_BREAKOUT": LaneConfig(
        symbols=[
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
            "LINKUSDT",
            "SUIUSDT",
            "HYPEUSDT",
            "XAUUSDT",
            "NEARUSDT",
            "BNBUSDT",
            "ONDOUSDT",
            "WLDUSDT",
            "ZECUSDT",
            "DRIFTUSDT",
            "INJUSDT",
            "RENDERUSDT",
            "ENAUSDT",
            "SEIUSDT",
        ],
        timeframe="15m",
        risk_budget_pct=0.30,
        max_positions=3,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["openclaw_breakout_executor"],
        setup_types={"BREAKOUT", "RETEST"},
    ),
}

EARLY_PROFIT_PROTECTION = {
    "enabled": True,
    "first_scale": {"profit_r": 0.50, "close_pct": 0.25, "move_sl_to_breakeven": True},
    "second_scale": {"profit_r": 1.00, "close_pct": 0.25, "move_sl_to_breakeven": True},
    "giveback_guard": {"min_peak_r": 0.50, "giveback_pct": 33.0, "reason": "early_giveback"},
}

EXIT_MILESTONE_PROFILES = {
    "macro": [
        {"gate_name": "milestone_0", "threshold": 0.50, "close_pct": 0.25},
        {"gate_name": "milestone_1", "threshold": 1.00, "close_pct": 0.25},
        {"gate_name": "milestone_2", "threshold": 1.80, "close_pct": 0.25},
    ],
    "sniper": [
        {"gate_name": "milestone_0", "threshold": 0.25, "close_pct": 0.25},
        {"gate_name": "milestone_1", "threshold": 0.50, "close_pct": 0.35},
        {"gate_name": "milestone_2", "threshold": 1.00, "close_pct": 0.25},
    ],
    "impulse": [
        {"gate_name": "milestone_0", "threshold": 0.40, "close_pct": 0.20},
        {"gate_name": "milestone_1", "threshold": 0.90, "close_pct": 0.30},
        {"gate_name": "milestone_2", "threshold": 1.60, "close_pct": 0.25},
    ],
    "shadow": [
        {"gate_name": "milestone_0", "threshold": 0.50, "close_pct": 0.25},
        {"gate_name": "milestone_1", "threshold": 1.00, "close_pct": 0.25},
        {"gate_name": "milestone_2", "threshold": 1.80, "close_pct": 0.25},
    ],
}

SYMBOL_EXIT_PROFILE = {
    "BTCUSDT": "macro",
    "ETHUSDT": "macro",
    "SOLUSDT": "impulse",
    "LINKUSDT": "sniper",
    "SUIUSDT": "impulse",
    "HYPEUSDT": "impulse",
    "XAUUSDT": "sniper",
    "NEARUSDT": "macro",
    "BNBUSDT": "sniper",
    "ONDOUSDT": "macro",
    "WLDUSDT": "sniper",
    "ZECUSDT": "shadow",
    "DRIFTUSDT": "shadow",
    "INJUSDT": "impulse",
    "RENDERUSDT": "impulse",
    "ENAUSDT": "shadow",
    "SEIUSDT": "impulse",
}


def get_exit_milestones_for_symbol(symbol: str) -> list[dict]:
    """Return monitor-managed partial-exit milestones for a symbol."""
    profile_name = SYMBOL_EXIT_PROFILE.get(normalize_strategy_symbol(symbol), "macro")
    return copy.deepcopy(EXIT_MILESTONE_PROFILES.get(profile_name, EXIT_MILESTONE_PROFILES["macro"]))

HALT_FILE = os.getenv("HERMES_HALT_FILE", "/home/rick/ozzy-bot/HALT")  # emergency kill switch — touch to halt, remove to resume
HERMES_STATUS_KEY = os.getenv("HERMES_STATUS_KEY", "")
RSI_BUY_MAX = 80.0        # v2026-04-17: raised from 78 to 80 — signal review showed 4/4 blocked winners (8R lost)
RSI_SELL_MIN = 20.0       # v2026-04-17: lowered from 22 to 20 — signal review showed 4/4 blocked winners (8R lost)
EMA_MAX_DISTANCE_PCT = 5.0  # v2026-04-18: reject entries >5% from EMA200 — investigation showed rejected ETH winners clustered at +3.5% to +3.9% vs approved ETH loser at +7.36%

# ── Crypto universe split ──────────────────────────────────────────────────────
# Testnet = broad crypto proofing ground for OpenClaw. Live-micro = narrow,
# higher-conviction subset for growing the small account. Shadow-only symbols
# are observed but never routed live.
TESTNET_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "HYPEUSDT",
    "XAUUSDT",
    "NEARUSDT",
    "BNBUSDT",
    "ONDOUSDT",
    "WLDUSDT",
    "ZECUSDT",
    "DRIFTUSDT",
    "INJUSDT",
    "RENDERUSDT",
    "ENAUSDT",
    "SEIUSDT",
]
LIVE_MICRO_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "HYPEUSDT",
    "XAUUSDT",
    "NEARUSDT",
    "BNBUSDT",
    "ONDOUSDT",
    "WLDUSDT",
    "ZECUSDT",
    "DRIFTUSDT",
    "INJUSDT",
    "RENDERUSDT",
    "ENAUSDT",
    "SEIUSDT",
]
SHADOW_ONLY_SYMBOLS = ["ZECUSDT", "DRIFTUSDT", "ENAUSDT"]

# ── Per-symbol strategy routing (v2026-04-20: breakout for FX/gold, pullback for crypto) ──
# Matches Pine Script: isForexGold→breakout, isCrypto→pullback, else→ST fallback
BREAKOUT_SYMBOLS  = ["XAUUSD", "EURUSD"]  # legacy/forex breakout set, archived
# v2026-06-17 — Pullback universe is now the crypto testnet set + shadow-only observers.
PULLBACK_SYMBOLS  = list(dict.fromkeys(TESTNET_SYMBOLS + SHADOW_ONLY_SYMBOLS))

# Per-symbol RSI thresholds for pullback strategy (crypto)
# Pullback entries fire when RSI is cooling off, not at extremes
PULLBACK_RSI_BUY_MAX  = 65.0  # pullback BUY: reject if RSI > 65 (too hot for pullback)
PULLBACK_RSI_SELL_MIN = 35.0  # pullback SELL: reject if RSI < 35 (too cold for pullback)

# Momentum RSI thresholds (crypto breakout)
# Momentum moves often have RSI 65-80, so we relax the thresholds
MOMENTUM_RSI_BUY_MAX  = 80.0  # momentum BUY: reject only if RSI > 80
MOMENTUM_RSI_SELL_MIN = 20.0  # momentum SELL: reject only if RSI < 20

# Volume confirmation threshold (v2026-04-22: lowered from 0.85 to 0.75)
# Relax to catch more valid entries during low-liquidity periods
VOLUME_MIN_RATIO = 0.75   # require 75% of 20-period average

# EMA proximity for pullback validation
# Pullback signal must have price near EMA200 to confirm the pullback happened
EMA_PULLBACK_MAX_DISTANCE_PCT = 3.0  # entry must be within 3% of EMA200

# ── Crypto sniper active policy (v2026-04-25b — loosen pullback volume after live 0.87 reject) ──
CRYPTO_ENTRY_POLICY_VERSION = "v2026-04-25b"
CRYPTO_PULLBACK_ENABLED = True
CRYPTO_MOMENTUM_ENABLED = True
CRYPTO_MOMENTUM_MIN_VOLUME_RATIO = 1.10
CRYPTO_MOMENTUM_MAX_EMA_DISTANCE_PCT = 8.0
CRYPTO_GRADE_A_MIN_VOLUME_RATIO = 1.20
CRYPTO_GRADE_B_MIN_VOLUME_RATIO = 0.85

# Timeframe
TIMEFRAME = "4H"

# Kill zone windows (SA time UTC+2)
KILL_ZONES = [
    {"start": "08:00", "end": "13:00", "name": "London"},
    {"start": "13:00", "end": "18:00", "name": "New York"},
]

# v2026-06-17 — Crypto runs 24/7; legacy forex pairs kept for historical reference only.
KILL_ZONE_BYPASS_SYMBOLS = (
    ["EURUSD", "GBPUSD", "USDJPY", "US500"]  # legacy/forex
    + list(dict.fromkeys(TESTNET_SYMBOLS + SHADOW_ONLY_SYMBOLS))
)

# Account
DEMO_BALANCE = 5000
CURRENCY = "USD"

# Pause trading during news events (set True manually when needed)
NEWS_PAUSE = False

# ── Sentiment filter (macro-direction confluence layer) ──
# Mode: "off" | "directional" | "extreme_only"
#   off           → sentiment filter disabled
#   directional   → reject signals that oppose the macro view
#   extreme_only  → only reject when sentiment is strong_bullish / strong_bearish
SENTIMENT_FILTER_MODE = "directional"

# Per-symbol macro sentiment. Values: bullish, strong_bullish, bearish, strong_bearish, neutral
SENTIMENT_OVERRIDES = {
    "US500":   "neutral",
    "XAUUSD":  "neutral",
    "EURUSD":  "neutral",
    "GBPUSD":  "neutral",
    "USDJPY":  "neutral",
    "BTCUSD":  "neutral",
    "BTCUSDT": "neutral",
    "ETHUSD":  "neutral",
    "ETHUSDT": "neutral",
    "SUIUSDT": "neutral",
    "HYPEUSDT": "neutral",
}

# ============================================
# HERMES settings
# ============================================

PAPER_MODE = False              # True = log + Telegram only; False = live execution
BREAKEVEN_TRIGGER = 1.0         # Move SL to entry when profit reaches this multiple of SL distance (1.0 = 1:1)
TRAIL_ACTIVATION  = 1.0         # R-multiple to activate simple trailing stop (1.0 for micro accounts, 1.5 for larger)
TRAIL_DISTANCE    = 0.5         # R-multiples to trail behind price (0.5 = half the original SL distance)
CHOCH_AUTO_CLOSE  = False       # If True, monitor closes positions on ChoCh reversal alerts
MAX_TRADE_HOURS   = 8           # Alert if a position is still open after this many hours

# Micro-account protective exits (prevents trades bleeding for days)
TIME_REDUCE_HOURS   = 16        # After this many hours with no 1R, close 50% of position
TIME_EXIT_HOURS     = 24        # After this many hours with no 1R, close remaining position
MOMENTUM_EXIT_R     = 1.0       # Widen to 1.0R to avoid whipsaw exits on normal retracements
MOMENTUM_LOOKBACK_SECONDS = 7200 # Momentum reversal lookback window (2 hours)
PROFIT_PROTECT_R    = 0.3       # If trade hit 1R but reverses to this R-level, close to protect profit
MONITOR_TRAIL_DEBUG_LOGS = _env_bool("HERMES_MONITOR_TRAIL_DEBUG_LOGS", False)
SESSION_WARN_MINS = 15          # Alert this many minutes before a kill zone ends with an open trade
MAX_LOT_SIZE = 1000.0          # Hard cap — never exceed regardless of risk calculation
# NOTE: v2026-05-17 — Raised from 0.1 to 1000.0. The 0.1 value was for legacy lot sizing.
# Binance uses coin quantities; 0.1 SOL = $8.60 which rounds to 0 and breaks execution.
MIN_BALANCE_USD = _env_float("HERMES_MIN_BALANCE_USD", 10.0)          # Minimum equity required to allow a trade

# Dynamic ATR multipliers based on market movement class
# Quiet markets = low ATR relative to min_sl → widen SL to avoid false rejections
# Fast markets  = high ATR relative to min_sl → tighten SL to reduce risk
QUIET_ATR_MULTIPLIER = 1.33     # 1.5 * 1.33 ≈ 2.0x ATR for quiet markets
FAST_ATR_MULTIPLIER = 0.80      # 1.5 * 0.80 = 1.2x ATR for fast markets

# TAAPI.IO — live ATR data (https://taapi.io/my-account/)
TAAPI_SECRET = os.getenv("TAAPI_SECRET", "")
POLYGON_SECRET = os.getenv("POLYGON_SECRET", "")

# Binance API credentials
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Binance DEMO / Testnet credentials (ozzy-demo-trading)
BINANCE_DEMO_API_KEY = os.getenv("BINANCE_DEMO_API_KEY", "")
BINANCE_DEMO_API_SECRET = os.getenv("BINANCE_DEMO_API_SECRET", "")

# Routing Configuration
# v2026-04-25 — Binance-only execution/risk checks for supported crypto pairs.
# v2026-06-17 — TESTNET_SYMBOLS / LIVE_MICRO_SYMBOLS / SHADOW_ONLY_SYMBOLS defined above.
# Default Binance symbol set. Override with HERMES_BINANCE_SYMBOLS per instance.
BINANCE_SYMBOLS = _env_list("HERMES_BINANCE_SYMBOLS", TESTNET_SYMBOLS)
DOGE_SHADOW_ONLY = True  # DOGE is disabled for live routing until it earns its way back in shadow/testnet data.
# v2026-05-18 — READY FOR LIVE. Set False once live API keys are validated.
BINANCE_TESTNET = _env_bool("HERMES_BINANCE_TESTNET", HERMES_MODE == "testnet")  # True = testnet, False = live.
BINANCE_FUTURES_MODE = True   # v2026-04-25 — full execution routing on Binance mode

# Per-symbol strategy personality catalog.
# Keep this as static data only; hot-path callers use helper functions below so
# nested override dictionaries are copied before merge and never mutated in place.
SYMBOL_STRATEGY_OVERRIDES = {
    "BTCUSDT": {
        "default_strategy": "supertrend",
    },
    "NEARUSDT": {
        "default_strategy": "pullback",
    },
    "HYPEUSDT": {
        "default_strategy": "trend_continuation",
        "signal_strategy": "trend_continuation",
        "crypto_entry": {
            "trend_continuation_min_ema_distance_pct": 8.0,
            "trend_continuation_max_ema_distance_pct": 25.0,
            "grade_b_trend_continuation_max_ema_distance_pct": 30.0,
            "trend_continuation_min_volume_ratio": 0.75,
            "trend_continuation_rsi_buy_max": 82.0,
            "trend_continuation_rsi_sell_min": 18.0,
        },
    },
    "SOLUSDT": {
        "default_strategy": "pullback",
    },
    "SUIUSDT": {
        "default_strategy": "pullback",
    },
    "ONDOUSDT": {
        "default_strategy": "momentum",
        "signal_strategy": "momentum",
        "crypto_entry": {
            "momentum_max_ema_distance_pct": 12.0,
            "grade_b_momentum_max_ema_distance_pct": 13.0,
            "momentum_min_volume_ratio": 0.75,
            "grade_a_min_volume_ratio": 1.10,
            "grade_b_min_volume_ratio": 0.75,
            "grade_c_min_volume_ratio": 0.50,
        },
    },
    "ETHUSDT": {
        "default_strategy": "pullback",
    },
    "BNBUSDT": {
        "default_strategy": "pullback",
        "mean_reversion": {
            "live_lanes": ["BUY"],
        },
    },
    "LINKUSDT": {
        "default_strategy": "pullback",
        "mean_reversion": {
            "live_lanes": ["BUY", "SELL"],
            "profile": "tight_15m_reversion",
        },
    },
}

# v2026-06-17 — OpenClaw Personality Hunter catalog.
# Execution routing uses these explicit setup personalities instead of
# treating every macro blueprint as a generic breakout candidate.
OPENCLAW_PERSONALITY_CATALOG = {
    # ── Impulsive trenders: explosive alts, best hunted with BREAKOUT + anti-chase ──
    "SOLUSDT": {
        "openclaw_personality": "impulsive_trender",
        "openclaw_primary_setup": "BREAKOUT",
        "openclaw_secondary_setup": "CONTINUATION",
        "openclaw_personality_reason": "Momentum runner, strong impulse behavior.",
    },
    "HYPEUSDT": {
        "openclaw_personality": "impulsive_trender",
        "openclaw_primary_setup": "BREAKOUT",
        "openclaw_secondary_setup": "CONTINUATION",
        "openclaw_personality_reason": "High momentum, fast moves; requires anti-chase filtering.",
    },
    "SEIUSDT": {
        "openclaw_personality": "impulsive_trender",
        "openclaw_primary_setup": "BREAKOUT",
        "openclaw_secondary_setup": "CONTINUATION",
        "openclaw_personality_reason": "Runs on momentum but needs liquidity watch.",
    },
    "RENDERUSDT": {
        "openclaw_personality": "impulsive_trender",
        "openclaw_primary_setup": "BREAKOUT",
        "openclaw_secondary_setup": "CONTINUATION",
        "openclaw_personality_reason": "Momentum-style alt; keep volume checks tight.",
    },
    "SUIUSDT": {
        "openclaw_personality": "impulsive_trender",
        "openclaw_primary_setup": "BREAKOUT",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Can trend hard; retest helps avoid chase.",
    },
    # ── Steady trend riders: persistent directional moves, best as CONTINUATION/RETEST ──
    "ONDOUSDT": {
        "openclaw_personality": "steady_trend_rider",
        "openclaw_primary_setup": "CONTINUATION",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Persistent trend and flag behavior.",
    },
    "NEARUSDT": {
        "openclaw_personality": "steady_trend_rider",
        "openclaw_primary_setup": "CONTINUATION",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Persistent trend and flag behavior.",
    },
    "BNBUSDT": {
        "openclaw_personality": "steady_trend_rider",
        "openclaw_primary_setup": "RETEST",
        "openclaw_secondary_setup": "PULLBACK",
        "openclaw_personality_reason": "More mature/liquid; less pure breakout.",
    },
    "LINKUSDT": {
        "openclaw_personality": "steady_trend_rider",
        "openclaw_primary_setup": "RETEST",
        "openclaw_secondary_setup": "PULLBACK",
        "openclaw_personality_reason": "Structure and level-respect behavior.",
    },
    "INJUSDT": {
        "openclaw_personality": "steady_trend_rider",
        "openclaw_primary_setup": "CONTINUATION",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Momentum exists but is cleaner as continuation until proven.",
    },
    # ── Large-cap pullbacks: BTC/ETH, don't chase fake breakouts ──
    "BTCUSDT": {
        "openclaw_personality": "mean_reverting_pullback",
        "openclaw_primary_setup": "PULLBACK",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Large cap; avoid chasing fake breakouts.",
    },
    "ETHUSDT": {
        "openclaw_personality": "mean_reverting_pullback",
        "openclaw_primary_setup": "PULLBACK",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Pullback and retest preferred for daily flow.",
    },
    # ── Volatile pullbacks: can snap back hard, use PULLBACK-first ──
    "WLDUSDT": {
        "openclaw_personality": "mean_reverting_pullback",
        "openclaw_primary_setup": "PULLBACK",
        "openclaw_secondary_setup": "BREAKOUT",
        "openclaw_personality_reason": "Volatile; breakout-only focus was too narrow.",
    },
    "XAUUSDT": {
        "openclaw_personality": "mean_reverting_pullback",
        "openclaw_primary_setup": "PULLBACK",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Gold proxy; respect retests, wicks, and support/resistance zones.",
    },
    # ── Bench / shadow-only: observe, don't route live until proven ──
    "ENAUSDT": {
        "openclaw_personality": "bench_watch",
        "openclaw_primary_setup": "SHADOW_ONLY",
        "openclaw_secondary_setup": "BREAKOUT",
        "openclaw_personality_reason": "Observe first; promote only with evidence.",
    },
    "ZECUSDT": {
        "openclaw_personality": "bench_watch",
        "openclaw_primary_setup": "SHADOW_ONLY",
        "openclaw_secondary_setup": "BREAKOUT",
        "openclaw_personality_reason": "Keep observed until evidence improves.",
    },
    "DRIFTUSDT": {
        "openclaw_personality": "bench_watch",
        "openclaw_primary_setup": "SHADOW_ONLY",
        "openclaw_secondary_setup": "RETEST",
        "openclaw_personality_reason": "Low confidence and liquidity sensitive; observe first.",
    },
}

# Telegram notifications (BotFather token + your chat/channel ID)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Asset specs — per-asset config
# contract_size:   used for lot sizing formula: lot = risk$ / (sl_distance * contract_size)
# min_sl / max_sl: valid ATR-based SL distance range in price points — rejects outside this band
# default_offset:  legacy fallback only (paper_tracker reference); Hermes uses ATR
# taapi_exchange:  TAAPI exchange key — "binance" for crypto, "forex" for FX/gold/indices
# taapi_symbol:    TAAPI symbol format — verify US500 symbol in your TAAPI dashboard
# taapi_tf:        ATR timeframe — 1h for crypto, 4h for everything else
# atr_sl_mult:     ATR multiplier for SL distance (TP = SL * MIN_RR = SL * 2.5)
# NOTE: USDJPY lot sizing is approximate — JPY pairs need a USD/JPY rate conversion for precision
ASSETS = {
    "XAUUSD": {
        "contract_size": 100,
        "min_sl": 20,       "max_sl": 500,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 60,
        "taapi_exchange": "forex",   "taapi_symbol": "XAU/USD",
        "taapi_tf": "4h",   "atr_sl_mult": 1.5,
    },
    "XAUUSDT": {
        "contract_size": 1,
        "min_sl": 2.0,      "max_sl": 100.0,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 5.0,
        "taapi_exchange": "binance", "taapi_symbol": "XAU/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
        "paper_only": False,
    },
    "EURUSD": {
        "contract_size": 100000,
        "min_sl": 0.001,    "max_sl": 0.01,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.005,
        "taapi_exchange": "forex",   "taapi_symbol": "EUR/USD",
        "taapi_tf": "4h",   "atr_sl_mult": 1.5,
    },
    "GBPUSD": {
        "contract_size": 100000,
        "min_sl": 0.001,    "max_sl": 0.01,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.005,
        "taapi_exchange": "forex",   "taapi_symbol": "GBP/USD",
        "taapi_tf": "4h",   "atr_sl_mult": 1.5,
    },
    "USDJPY": {
        "contract_size": 100000,
        "min_sl": 0.1,      "max_sl": 5.0,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.5,
        "taapi_exchange": "forex",   "taapi_symbol": "USD/JPY",
        "taapi_tf": "4h",   "atr_sl_mult": 1.5,
    },
    "US500": {
        "contract_size": 5,
        "min_sl": 5,        "max_sl": 150,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 20,
        "taapi_exchange": "forex",   "taapi_symbol": "SPX500/USD",
        "taapi_tf": "4h",   "atr_sl_mult": 1.5,
    },
    "BTCUSD": {
        "contract_size": 1,
        "min_sl": 200,      "max_sl": 3000,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 500,
        "taapi_exchange": "bitstamp", "taapi_symbol": "BTC/USD",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
        "paper_only": False,  # v2026-04-18 rollback: re-enabled live trading — paper_only decision was based on buggy 0W/10L data; corrected review shows 6W/4L paper performance
    },
    "BTCUSDT": {
        "contract_size": 1,
        "min_sl": 200,      "max_sl": 3000,
        "min_sl_tolerance_pct": 0.15,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 500,
        "taapi_exchange": "binance", "taapi_symbol": "BTC/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
        "paper_only": False,  # v2026-04-18 rollback: re-enabled live trading — paper_only decision was based on buggy 0W/10L data; corrected review shows 6W/4L paper performance
    },
    "ETHUSD": {
        "contract_size": 1,
        "min_sl": 20,       "max_sl": 500,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 100,
        "taapi_exchange": "coinbase", "taapi_symbol": "ETH/USD",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "ETHUSDT": {
        "contract_size": 1,
        "min_sl": 20,       "max_sl": 500,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 100,
        "taapi_exchange": "binance", "taapi_symbol": "ETH/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "SOLUSD": {
        "contract_size": 1,
        "min_sl": 1.0,      "max_sl": 30.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 5,
        "taapi_exchange": "binance", "taapi_symbol": "SOL/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "SOLUSDT": {
        "contract_size": 1,
        "min_sl": 1.0,      "max_sl": 30.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 5,
        "taapi_exchange": "binance", "taapi_symbol": "SOL/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "XRPUSD": {
        "contract_size": 1,
        "min_sl": 0.01,     "max_sl": 0.25,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.05,
        "taapi_exchange": "binance", "taapi_symbol": "XRP/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "XRPUSDT": {
        "contract_size": 1,
        "min_sl": 0.01,     "max_sl": 0.25,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.05,
        "taapi_exchange": "binance", "taapi_symbol": "XRP/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "LINKUSDT": {
        "contract_size": 1,
        "min_sl": 0.15,     "max_sl": 5.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.50,
        "taapi_exchange": "binance", "taapi_symbol": "LINK/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "DOGEUSDT": {
        "contract_size": 1,
        "min_sl": 0.005,    "max_sl": 0.15,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.02,
        "taapi_exchange": "binance", "taapi_symbol": "DOGE/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "SUIUSDT": {
        "contract_size": 1,
        "min_sl": 0.02,     "max_sl": 0.50,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.05,
        "taapi_exchange": "binance", "taapi_symbol": "SUI/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "HYPEUSDT": {
        "contract_size": 1,
        "min_sl": 1.0,      "max_sl": 15.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 2.0,
        "taapi_exchange": "binance", "taapi_symbol": "HYPE/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "BNBUSDT": {
        "contract_size": 1,
        "min_sl": 2.0,      "max_sl": 100.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 15.0,
        "taapi_exchange": "binance", "taapi_symbol": "BNB/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "NEARUSDT": {
        "contract_size": 1,
        "min_sl": 0.05,     "max_sl": 2.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.20,
        "taapi_exchange": "binance", "taapi_symbol": "NEAR/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "ONDOUSDT": {
        "contract_size": 1,
        "min_sl": 0.01,     "max_sl": 0.30,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.04,
        "taapi_exchange": "binance", "taapi_symbol": "ONDO/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "WLDUSDT": {
        "contract_size": 1,
        "min_sl": 0.03,     "max_sl": 1.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.10,
        "taapi_exchange": "binance", "taapi_symbol": "WLD/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "ZECUSDT": {
        "contract_size": 1,
        "min_sl": 1.0,      "max_sl": 30.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 5.0,
        "taapi_exchange": "binance", "taapi_symbol": "ZEC/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "DRIFTUSDT": {
        "contract_size": 1,
        "min_sl": 0.01,     "max_sl": 0.30,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.04,
        "taapi_exchange": "binance", "taapi_symbol": "DRIFT/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "INJUSDT": {
        "contract_size": 1,
        "min_sl": 0.20,     "max_sl": 8.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.75,
        "taapi_exchange": "binance", "taapi_symbol": "INJ/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "RENDERUSDT": {
        "contract_size": 1,
        "min_sl": 0.05,     "max_sl": 2.0,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.20,
        "taapi_exchange": "binance", "taapi_symbol": "RENDER/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "ENAUSDT": {
        "contract_size": 1,
        "min_sl": 0.01,     "max_sl": 0.25,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.03,
        "taapi_exchange": "binance", "taapi_symbol": "ENA/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
    "SEIUSDT": {
        "contract_size": 1,
        "min_sl": 0.005,    "max_sl": 0.20,
        "min_sl_tolerance_pct": 0.20,
        "normal_move_bonus_pct": 0.10,
        "fast_move_bonus_pct": 0.20,
        "max_min_sl_tolerance_pct": 0.40,
        "default_offset": 0.02,
        "taapi_exchange": "binance", "taapi_symbol": "SEI/USDT",
        "taapi_tf": "1h",   "atr_sl_mult": 1.5,
    },
}

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# ── Dynamic Thresholds (auto-tuned by rejection_tracker.py) ──
# These are mutable — rejection_tracker writes suggestions here and webhook reads them.
# Initialized from static constants below; updated at runtime based on signal review outcomes.
DYNAMIC_THRESHOLDS = {
    "rsi_exhaustion": {"buy_max": 80.0, "sell_min": 20.0},
    "pullback_rsi_exhaustion": {"buy_max": 65.0, "sell_min": 35.0},
    "momentum_rsi_exhaustion": {"buy_max": 80.0, "sell_min": 20.0},
    "volume_confirmation": {"min_ratio": 0.75},
    "momentum_volume": {"min_ratio": 1.10},
    "grade_a_volume": {"min_ratio": 1.20},
    "grade_b_volume": {"min_ratio": 0.85},
    "ema_overextension": {"max_distance_pct": 5.0},
    "ema_pullback": {"max_distance_pct": 3.0},
    "momentum_ema": {"max_distance_pct": 8.0},
    "min_rr": 2.5,
    "max_positions": 5,
    "daily_drawdown_limit": 15.0,
}


def normalize_strategy_symbol(symbol: str) -> str:
    """Normalize symbol keys for strategy override lookups."""
    return (symbol or "").replace("/", "").upper()


def get_all_openclaw_symbols() -> list[str]:
    """Return the explicit OpenClaw personality universe."""
    return sorted(OPENCLAW_PERSONALITY_CATALOG.keys())


def get_symbol_strategy_profile(symbol: str) -> dict:
    """Return the static per-symbol strategy profile, merged with OpenClaw personality metadata."""
    normalized = normalize_strategy_symbol(symbol)
    profile = copy.deepcopy(SYMBOL_STRATEGY_OVERRIDES.get(normalized, {}))
    openclaw_profile = OPENCLAW_PERSONALITY_CATALOG.get(normalized)
    if openclaw_profile:
        profile.update(copy.deepcopy(openclaw_profile))
    return profile


def get_symbol_strategy_hint(symbol: str) -> str | None:
    """Return a generator-facing strategy hint for symbols with explicit roles."""
    strategy = get_symbol_strategy_profile(symbol).get("signal_strategy")
    return str(strategy) if strategy else None


def get_signal_strategy_for_symbol(symbol: str, fallback: str = "supertrend") -> str:
    """Return the scanner/webhook strategy role for a symbol."""
    profile = get_symbol_strategy_profile(symbol)
    strategy = profile.get("signal_strategy") or profile.get("default_strategy") or fallback
    return str(strategy)


def get_default_strategy_for_symbol(symbol: str, fallback: str = "supertrend") -> str:
    """Return the webhook fallback strategy for a symbol."""
    strategy = get_symbol_strategy_profile(symbol).get("default_strategy")
    return str(strategy) if strategy else fallback


def get_mean_reversion_live_lanes() -> set[tuple[str, str]]:
    """Return default SYMBOL:DIRECTION lanes for the 15m mean-reversion scanner."""
    lanes: set[tuple[str, str]] = set()
    for symbol, profile in SYMBOL_STRATEGY_OVERRIDES.items():
        mean_reversion = profile.get("mean_reversion") or {}
        for direction in mean_reversion.get("live_lanes", []):
            normalized_direction = str(direction).upper()
            if normalized_direction in {"BUY", "SELL"}:
                lanes.add((symbol, normalized_direction))
    return lanes


def build_crypto_entry_config(dynamic_thresholds: dict, symbol: str | None = None) -> dict:
    """Build a copied crypto-entry config with per-symbol overrides applied."""
    cfg = {
        "pullback_max_ema_distance_pct": dynamic_thresholds["ema_pullback"]["max_distance_pct"],
        "pullback_rsi_buy_max": dynamic_thresholds["pullback_rsi_exhaustion"]["buy_max"],
        "pullback_rsi_sell_min": dynamic_thresholds["pullback_rsi_exhaustion"]["sell_min"],
        "momentum_enabled": CRYPTO_MOMENTUM_ENABLED,
        "momentum_max_ema_distance_pct": dynamic_thresholds["momentum_ema"]["max_distance_pct"],
        "momentum_min_volume_ratio": dynamic_thresholds["momentum_volume"]["min_ratio"],
        "momentum_rsi_buy_max": dynamic_thresholds["momentum_rsi_exhaustion"]["buy_max"],
        "momentum_rsi_sell_min": dynamic_thresholds["momentum_rsi_exhaustion"]["sell_min"],
        "grade_a_min_volume_ratio": min(dynamic_thresholds["grade_a_volume"]["min_ratio"], 1.10),
        "grade_b_min_volume_ratio": min(dynamic_thresholds["grade_b_volume"]["min_ratio"], 0.75),
        "grade_c_min_volume_ratio": 0.50,
        "grade_b_pullback_max_ema_distance_pct": 5.0,
        "grade_b_momentum_max_ema_distance_pct": 9.5,
        "trend_continuation_min_ema_distance_pct": 8.0,
        "trend_continuation_max_ema_distance_pct": 25.0,
        "grade_b_trend_continuation_max_ema_distance_pct": 30.0,
        "trend_continuation_min_volume_ratio": 0.75,
        "trend_continuation_rsi_buy_max": 82.0,
        "trend_continuation_rsi_sell_min": 18.0,
    }
    symbol_overrides = (get_symbol_strategy_profile(symbol).get("crypto_entry") or {}) if symbol else {}
    cfg.update(dict(symbol_overrides))
    return cfg


def get_lane_for_signal(source: str, strategy_label: str = "", entry_setup_label: str = "") -> str | None:
    """Return the first enabled lane whose signal source matches any provided label."""
    labels = [source, strategy_label, entry_setup_label]
    for lane_name, lane in LANES.items():
        if not lane.enabled:
            continue
        for src in lane.signal_sources:
            if any(src in label for label in labels if label):
                return lane_name
    return None


def get_lane_config(lane_name: str) -> LaneConfig | None:
    """Return the LaneConfig for a given lane name."""
    return LANES.get(lane_name)


# ── Schema Validation ──
# STRICT_SCHEMA_VALIDATION = True  → Reject payloads that don't match Pine Script contract
# STRICT_SCHEMA_VALIDATION = False → Log schema violations but still process (migration mode)
STRICT_SCHEMA_VALIDATION = True  # v2026-04-19 — Flipped to True after ghost signal at 14:33 was approved with only 4 fields. Migration complete.
