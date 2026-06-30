# ============================================
# HERMES — Binance Futures Connector (V2 Architecture)
# ============================================
# Drop-in replacement for connector.py when using Binance Futures.
# PATCHED: separates SL verification from TP verification and uses Hedge Mode-safe order params.
# Core Principle: Strict exchange-side protection brackets with an
# ironclad, deterministic Audit, Repair, and Kill-Switch finalizer.
#
# Testnet mode uses https://testnet.binancefuture.com
# Live mode uses https://fapi.binance.com

import logging
import math
import time
from dataclasses import asdict, dataclass

from binance.client import Client
from binance.exceptions import BinanceAPIException

from config import (
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    BINANCE_DEMO_API_KEY,
    BINANCE_DEMO_API_SECRET,
    BINANCE_ENTRY_MARGIN_UTILIZATION,
    BINANCE_TESTNET,
    MAX_LOT_SIZE,
    MAX_SPREAD_PCT,
    MIN_BALANCE_USD,
    MIN_NOTIONAL_MAX_RISK_MULT,
    MIN_NOTIONAL_RISK_OVERRIDE_MODE,
    PAPER_MODE,
    POST_FILL_PROTECTION_LIVE_MODE,
    POST_FILL_PROTECTION_TESTNET_MODE,
    PROTECTION_TRUTH_REQUIRED,
    PROTECTION_TRUTH_RETRIES,
    PROTECTION_TRUTH_RETRY_DELAY_SECONDS,
    RISK_PCT,
)
from logger import plain_log
import telegram_client
from risk_policy import resolve_trade_risk

# ── API endpoints ──
_BINANCE_FAPI_BASE = "https://fapi.binance.com"
_BINANCE_TESTNET_FAPI_BASE = "https://testnet.binancefuture.com"

# ── Leverage per symbol (default 5x) ──
BINANCE_LEVERAGE = {
    "BTCUSDT": 10,
    "ETHUSDT": 20,
    "SOLUSDT": 10,
    "XRPUSDT": 10,
    "LINKUSDT": 10,
    "DOGEUSDT": 10,
    "SUIUSDT": 10,
    "HYPEUSDT": 10,
    "BNBUSDT": 10,
    "XAUUSDT": 20,
    "WLDUSDT": 10,
    "ZECUSDT": 10,
    "DRIFTUSDT": 10,
    "INJUSDT": 10,
    "NEARUSDT": 10,
    "ONDOUSDT": 10,
    "RENDERUSDT": 10,
    "ENAUSDT": 10,
    "SEIUSDT": 10,
}

# Binance minimum notional per symbol (USD-M futures)
BINANCE_MIN_NOTIONAL = {
    "BTCUSDT": 100,
    "ETHUSDT": 20,
    "SOLUSDT": 5,
    "XRPUSDT": 5,
    "LINKUSDT": 20,
    "DOGEUSDT": 5,
    "SUIUSDT": 5,
    "HYPEUSDT": 5,
    "BNBUSDT": 5,
    "XAUUSDT": 5,
    "WLDUSDT": 5,
    "ZECUSDT": 5,
    "DRIFTUSDT": 5,
    "INJUSDT": 5,
    "NEARUSDT": 5,
    "ONDOUSDT": 5,
    "RENDERUSDT": 5,
    "ENAUSDT": 5,
    "SEIUSDT": 5,
}

PRICE_PRECISION = {
    "BTCUSDT": 1,
    "ETHUSDT": 2,
    "SOLUSDT": 3,
    "XRPUSDT": 4,
    "LINKUSDT": 3,
    "DOGEUSDT": 6,
    "SUIUSDT": 4,
    "HYPEUSDT": 3,
    "BNBUSDT": 2,
    "XAUUSDT": 2,
    "WLDUSDT": 4,
    "ZECUSDT": 2,
    "DRIFTUSDT": 5,
    "INJUSDT": 3,
    "NEARUSDT": 3,
    "ONDOUSDT": 4,
    "RENDERUSDT": 3,
    "ENAUSDT": 4,
    "SEIUSDT": 4,
}

# ── Symbol mapping: TradingView → Binance ──
TV_TO_BINANCE = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "SOLUSD": "SOLUSDT",
    "XRPUSD": "XRPUSDT",
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSDT": "XRPUSDT",
    "LINKUSDT": "LINKUSDT",
    "DOGEUSDT": "DOGEUSDT",
    "SUIUSDT": "SUIUSDT",
    "HYPEUSDT": "HYPEUSDT",
    "BNBUSDT": "BNBUSDT",
    "XAUUSDT": "XAUUSDT",
    "NEARUSDT": "NEARUSDT",
    "ONDOUSDT": "ONDOUSDT",
    "WLDUSDT": "WLDUSDT",
    "ZECUSDT": "ZECUSDT",
    "DRIFTUSDT": "DRIFTUSDT",
    "INJUSDT": "INJUSDT",
    "RENDERUSDT": "RENDERUSDT",
    "ENAUSDT": "ENAUSDT",
    "SEIUSDT": "SEIUSDT",
}
BINANCE_TO_TV = {v: k for k, v in TV_TO_BINANCE.items()}

# Suppress Binance SDK noise
logging.getLogger("binance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

XAU_NOTIONAL_BUFFER = 0.90
XAU_RULES_CACHE_TTL_SECONDS = 300
_xau_rules_cache = {"fetched_at": 0.0, "rules": None}


@dataclass(frozen=True)
class SpreadCheckResult:
    """Structured order-book spread check result with tuple-unpack compatibility."""

    ok: bool
    spread_pct: float
    bid: float
    ask: float
    reason: str = "ok"
    is_entry: bool = False
    fail_open: bool = False

    def __iter__(self):
        yield self.ok
        yield self.spread_pct
        yield self.bid
        yield self.ask

    def as_dict(self) -> dict:
        return asdict(self)


def _get_client() -> Client:
    """Return Binance client (testnet or live)."""
    if BINANCE_TESTNET:
        key, secret = BINANCE_DEMO_API_KEY, BINANCE_DEMO_API_SECRET
        client = Client(key, secret, testnet=True)
    else:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    client.REQUEST_RECVWINDOW = 60000
    return client


def _is_timeout_error(error: Exception) -> bool:
    name = error.__class__.__name__.lower()
    return "timeout" in name or "timed out" in str(error).lower()


def check_order_book_spread(client: Client, symbol: str, is_entry: bool = False) -> SpreadCheckResult:
    """Fetch the order book and compute the bid/ask spread percentage."""
    try:
        book = client.futures_order_book(symbol=symbol, limit=5)
        if not book or not book.get("bids") or not book.get("asks"):
            event = "ORDER_BOOK_ENTRY_EMPTY_FAILED_CLOSED" if is_entry else "ORDER_BOOK_EXIT_EMPTY_FAILED_OPEN"
            plain_log(event, {"symbol": symbol, "is_entry": is_entry})
            return SpreadCheckResult(
                ok=not is_entry,
                spread_pct=0.0,
                bid=0.0,
                ask=0.0,
                reason="empty_order_book",
                is_entry=is_entry,
                fail_open=not is_entry,
            )

        bid_price = float(book["bids"][0][0])
        ask_price = float(book["asks"][0][0])
        if bid_price <= 0 or ask_price <= 0:
            event = "ORDER_BOOK_ENTRY_EMPTY_FAILED_CLOSED" if is_entry else "ORDER_BOOK_EXIT_EMPTY_FAILED_OPEN"
            plain_log(event, {"symbol": symbol, "bid": bid_price, "ask": ask_price, "is_entry": is_entry})
            return SpreadCheckResult(
                ok=not is_entry,
                spread_pct=0.0,
                bid=bid_price,
                ask=ask_price,
                reason="invalid_order_book_price",
                is_entry=is_entry,
                fail_open=not is_entry,
            )

        spread = ask_price - bid_price
        spread_pct = (spread / bid_price) * 100.0

        is_ok = spread_pct <= MAX_SPREAD_PCT
        if not is_ok:
            plain_log(
                "ORDER_BOOK_WIDE_SPREAD_BLOCKED",
                {
                    "symbol": symbol,
                    "is_entry": is_entry,
                    "spread_pct": round(spread_pct, 4),
                    "max_spread_pct": MAX_SPREAD_PCT,
                    "bid": bid_price,
                    "ask": ask_price,
                },
            )
        return SpreadCheckResult(
            ok=is_ok,
            spread_pct=spread_pct,
            bid=bid_price,
            ask=ask_price,
            reason="wide_spread" if not is_ok else "ok",
            is_entry=is_entry,
            fail_open=False,
        )
    except Exception as e:
        failure_kind = "timeout" if _is_timeout_error(e) else "error"
        if is_entry:
            event = (
                "ORDER_BOOK_ENTRY_TIMEOUT_FAILED_CLOSED"
                if failure_kind == "timeout"
                else "ORDER_BOOK_ENTRY_ERROR_FAILED_CLOSED"
            )
            plain_log(event, {"symbol": symbol, "error": str(e)})
            return SpreadCheckResult(False, 0.0, 0.0, 0.0, failure_kind, is_entry=True, fail_open=False)
        event = (
            "ORDER_BOOK_EXIT_TIMEOUT_FAILED_OPEN" if failure_kind == "timeout" else "ORDER_BOOK_EXIT_CHECK_FAILED_OPEN"
        )
        plain_log(event, {"symbol": symbol, "error": str(e)})
        return SpreadCheckResult(True, 0.0, 0.0, 0.0, failure_kind, is_entry=False, fail_open=True)


def get_execution_mode() -> str:
    return "TESTNET" if BINANCE_TESTNET else "LIVE"


def get_post_fill_protection_mode() -> str:
    # Unified repair path; protection truth is enforced regardless of testnet/live.
    if not PROTECTION_TRUTH_REQUIRED:
        return POST_FILL_PROTECTION_TESTNET_MODE
    return POST_FILL_PROTECTION_LIVE_MODE


# ── Automated Account Structure Gates ──
def assert_account_hedge_mode(client: Client) -> bool:
    """Enforces absolute structural alignment with Binance Futures Hedge Mode on startup."""
    try:
        position_mode = client.futures_get_position_mode()
        if not position_mode.get("dualSidePosition"):
            print("⚠️ [SAFETY ALERT] Binance account is in One-Way Mode. Forcing Hedge Mode...")
            client.futures_change_position_mode(dualSidePosition=True)
            print("🛡️ [SECURITY] Remote account successfully locked into dual-side HEDGE MODE.")
        else:
            print("🛡️ [SECURITY] Account structural alignment verified: HEDGE MODE is active.")
        return True
    except Exception as e:
        print(f"❌ [CRITICAL ERROR] Failed to assert Hedge Mode alignment with Binance: {e}")
        return False


def validate_binance_credentials() -> tuple[bool, str]:
    """Validate credentials exist and force account structural safety on startup."""
    if PAPER_MODE:
        return True, "paper mode"

    try:
        startup_client = _get_client()
    except Exception as e:
        return False, f"FAIL-CLOSED: Failed to instantiate client session during startup check: {e}"

    if BINANCE_TESTNET:
        if not (BINANCE_DEMO_API_KEY and BINANCE_DEMO_API_SECRET):
            return False, "missing Binance testnet credentials"
        if not assert_account_hedge_mode(startup_client):
            return False, "FAIL-CLOSED: Hedge Mode structure could not be verified on Testnet account."
        return True, "testnet credentials verified and Hedge Mode locked"
    else:
        if not (BINANCE_API_KEY and BINANCE_API_SECRET):
            return False, "missing Binance live credentials"
        if not assert_account_hedge_mode(startup_client):
            return False, "FAIL-CLOSED: Hedge Mode structure could not be verified on LIVE account."
        return True, "live credentials verified and Hedge Mode locked"


def _map_symbol(tv_symbol: str) -> str:
    return TV_TO_BINANCE.get(tv_symbol, tv_symbol)


def _map_to_tv(binance_symbol: str) -> str:
    return BINANCE_TO_TV.get(binance_symbol, binance_symbol)


def _set_leverage(client: Client, symbol: str):
    leverage = BINANCE_LEVERAGE.get(symbol, 5)
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except BinanceAPIException as e:
        plain_log("LEVERAGE_SKIP", {"symbol": symbol, "error": str(e)})


@dataclass(frozen=True)
class ProtectionOrderRef:
    symbol: str
    kind: str
    order_class: str
    order_id: str | None
    client_order_id: str | None
    algo_id: str | None
    client_algo_id: str | None
    expected_side: str
    expected_position_side: str | None
    expected_stop_price: float
    expected_qty: float | None
    close_position: bool
    reduce_only: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _protection_kind(order_type: str) -> str:
    return "SL" if order_type in {"STOP", "STOP_MARKET"} else "TP"


def _protection_ref(
    order: dict,
    *,
    symbol: str,
    side: str,
    order_type: str,
    stop_price: float,
    quantity: float | None,
    order_class: str,
    position_side: str | None = None,
    close_position: bool = False,
    reduce_only: bool = False,
) -> ProtectionOrderRef:
    return ProtectionOrderRef(
        symbol=symbol,
        kind=_protection_kind(order_type),
        order_class=order_class,
        order_id=str(order.get("orderId")) if order.get("orderId") is not None else None,
        client_order_id=order.get("clientOrderId"),
        algo_id=str(order.get("algoId")) if order.get("algoId") is not None else None,
        client_algo_id=order.get("clientAlgoId"),
        expected_side=side,
        expected_position_side=position_side,
        expected_stop_price=float(stop_price),
        expected_qty=float(quantity) if quantity not in (None, "") else None,
        close_position=bool(close_position),
        reduce_only=bool(reduce_only),
    )


def _format_quantity(symbol: str, raw_qty: float) -> float:
    precision_map = {
        "BTCUSDT": 3,
        "ETHUSDT": 2,
        "SOLUSDT": 0,
        "XRPUSDT": 0,
        "LINKUSDT": 2,
        "DOGEUSDT": 0,
        "SUIUSDT": 1,
        "HYPEUSDT": 2,
        "BNBUSDT": 2,
        "XAUUSDT": 3,
        "WLDUSDT": 0,
        "ZECUSDT": 3,
        "DRIFTUSDT": 0,
        "INJUSDT": 1,
        "NEARUSDT": 1,
        "ONDOUSDT": 1,
        "RENDERUSDT": 1,
        "ENAUSDT": 0,
        "SEIUSDT": 0,
    }
    decimals = precision_map.get(symbol, 3)
    return round(raw_qty, decimals)


def _floor_quantity(symbol: str, raw_qty: float) -> float:
    precision_map = {
        "BTCUSDT": 3,
        "ETHUSDT": 2,
        "SOLUSDT": 0,
        "XRPUSDT": 0,
        "LINKUSDT": 2,
        "DOGEUSDT": 0,
        "SUIUSDT": 1,
        "HYPEUSDT": 2,
        "BNBUSDT": 2,
        "XAUUSDT": 3,
        "WLDUSDT": 0,
        "ZECUSDT": 3,
        "DRIFTUSDT": 0,
        "INJUSDT": 1,
        "NEARUSDT": 1,
        "ONDOUSDT": 1,
        "RENDERUSDT": 1,
        "ENAUSDT": 0,
        "SEIUSDT": 0,
    }
    decimals = precision_map.get(symbol, 3)
    scale = 10**decimals
    return math.floor(max(0.0, float(raw_qty)) * scale) / scale


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _floor_to_step(raw_value: float, step_size: float) -> float:
    step = _safe_float(step_size, 0.0)
    value = max(0.0, _safe_float(raw_value, 0.0))
    if step <= 0:
        return value
    return math.floor(value / step) * step


def _fetch_xau_symbol_rules(client: Client, symbol: str = "XAUUSDT") -> dict:
    now = time.time()
    cached = _xau_rules_cache.get("rules")
    if cached and (now - float(_xau_rules_cache.get("fetched_at", 0.0))) < XAU_RULES_CACHE_TTL_SECONDS:
        return dict(cached)

    exchange_info = client.futures_exchange_info()
    symbol_info = next((s for s in (exchange_info.get("symbols") or []) if s.get("symbol") == symbol), None)
    if not symbol_info:
        raise ValueError(f"{symbol} exchange info not found")

    filters = symbol_info.get("filters") or []
    lot_filter = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), {})
    notional_filter = next((f for f in filters if f.get("filterType") in {"MIN_NOTIONAL", "NOTIONAL"}), {})
    step_size = _safe_float(lot_filter.get("stepSize"), 0.001)
    min_qty = _safe_float(lot_filter.get("minQty"), 0.0)
    min_notional = _safe_float(notional_filter.get("notional") or notional_filter.get("minNotional"), 0.0)

    leverage = max(1, int(BINANCE_LEVERAGE.get(symbol, 5)))
    brackets = client.futures_leverage_bracket(symbol=symbol)
    if isinstance(brackets, dict):
        brackets = [brackets]
    symbol_brackets = []
    for row in brackets or []:
        if row.get("symbol") != symbol:
            continue
        symbol_brackets = row.get("brackets") or []
        break
    if not symbol_brackets and brackets:
        symbol_brackets = (brackets[0] or {}).get("brackets") or []
    if not symbol_brackets:
        raise ValueError(f"{symbol} leverage brackets not found")

    allowed_caps = [
        _safe_float(b.get("notionalCap"), 0.0)
        for b in symbol_brackets
        if _safe_float(b.get("initialLeverage"), 0.0) >= leverage and _safe_float(b.get("notionalCap"), 0.0) > 0
    ]
    if not allowed_caps:
        raise ValueError(f"{symbol} no bracket cap found for leverage={leverage}")

    max_notional = max(allowed_caps)
    safe_cap = max_notional * XAU_NOTIONAL_BUFFER
    rules = {
        "symbol": symbol,
        "leverage": leverage,
        "step_size": step_size,
        "min_qty": min_qty,
        "min_notional": min_notional,
        "max_notional": max_notional,
        "safe_cap_notional": safe_cap,
    }
    _xau_rules_cache["fetched_at"] = now
    _xau_rules_cache["rules"] = dict(rules)
    return rules


def _xau_notional_preflight(client: Client, symbol: str, quantity: float, price: float) -> tuple[float, dict | None]:
    if symbol != "XAUUSDT":
        return quantity, None

    rules = _fetch_xau_symbol_rules(client, symbol)
    proposed_qty = max(0.0, float(quantity))
    entry_price = max(0.0, float(price))
    proposed_notional = proposed_qty * entry_price
    safe_cap = _safe_float(rules.get("safe_cap_notional"), 0.0)
    if safe_cap <= 0:
        raise ValueError(f"{symbol} invalid leverage bracket safe cap")
    if proposed_notional <= safe_cap:
        return quantity, None

    step_size = _safe_float(rules.get("step_size"), 0.001)
    downshift_qty = _floor_to_step(safe_cap / entry_price if entry_price > 0 else 0.0, step_size)
    downshift_qty = _floor_quantity(symbol, downshift_qty)
    min_qty = _safe_float(rules.get("min_qty"), 0.0)
    min_notional = max(
        _safe_float(rules.get("min_notional"), 0.0),
        _safe_float(BINANCE_MIN_NOTIONAL.get(symbol, 0.0), 0.0),
    )
    downshift_notional = downshift_qty * entry_price

    detail = {
        "symbol": symbol,
        "leverage": rules.get("leverage"),
        "buffer": XAU_NOTIONAL_BUFFER,
        "safe_cap_notional": safe_cap,
        "max_notional": rules.get("max_notional"),
        "step_size": step_size,
        "min_qty": min_qty,
        "min_notional": min_notional,
        "proposed_qty": proposed_qty,
        "proposed_notional": proposed_notional,
        "downshift_qty": downshift_qty,
        "downshift_notional": downshift_notional,
    }

    if downshift_qty <= 0 or downshift_qty < min_qty or downshift_notional < min_notional:
        plain_log("XAU_NOTIONAL_CAP_REJECTED", detail)
        raise ValueError(
            f"{symbol} notional preflight rejected: proposed ${proposed_notional:.2f} exceeds safe cap ${safe_cap:.2f}"
        )

    plain_log("XAU_NOTIONAL_DOWNSHIFT", detail)
    return downshift_qty, detail


def _tp_split_quantities(symbol: str, total_qty: float) -> tuple[float, float]:
    """Return TP1/TP2 quantities that never submit a zero-sized TP order.

    For symbols with 0 decimal quantity precision, a tiny position can make 50%
    round to zero. In that case we skip TP1 and put the full amount on TP2.
    """
    total = _format_quantity(symbol, float(total_qty))
    if total <= 0:
        return 0.0, 0.0
    tp1 = _floor_quantity(symbol, total * 0.5)
    tp2 = _format_quantity(symbol, total - tp1)
    if tp1 <= 0 or tp2 <= 0:
        return 0.0, total
    return tp1, tp2


def _margin_capped_quantity(
    symbol: str, quantity: float, *, price: float, available_balance: float | None
) -> tuple[float, dict | None]:
    available = float(available_balance or 0.0)
    price_f = float(price or 0.0)
    leverage = max(1, int(BINANCE_LEVERAGE.get(symbol, 5)))
    utilization = min(1.0, max(0.0, float(BINANCE_ENTRY_MARGIN_UTILIZATION)))
    if available <= 0 or price_f <= 0 or utilization <= 0:
        return quantity, None

    max_notional = available * leverage * utilization
    max_qty = _floor_quantity(symbol, max_notional / price_f)
    if max_qty <= 0 or quantity <= max_qty:
        return quantity, None

    return max_qty, {
        "symbol": symbol,
        "requested_quantity": quantity,
        "capped_quantity": max_qty,
        "available_balance": available,
        "leverage": leverage,
        "margin_utilization": utilization,
        "requested_notional": quantity * price_f,
        "capped_notional": max_qty * price_f,
        "max_initial_margin": available * utilization,
    }


def _place_sl_tp_order(
    client: Client,
    symbol: str,
    side: str,
    order_type: str,
    stop_price: float,
    quantity: float | None = None,
    *,
    position_side: str | None = None,
    close_position: bool = False,
) -> dict:
    """Place a protective STOP/TP order using Binance Futures-safe params.

    Important: this connector forces Hedge Mode. Binance docs state reduceOnly
    cannot be sent in Hedge Mode, and closePosition cannot be combined with
    quantity/reduceOnly. Therefore:
      - full-position SL uses closePosition=true, no quantity, no reduceOnly
      - partial TPs use quantity + positionSide, no reduceOnly
    """
    rounded_stop = str(round(stop_price, PRICE_PRECISION.get(symbol, 2)))

    def normal_payload() -> dict:
        payload = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "stopPrice": rounded_stop,
            "workingType": "MARK_PRICE",
        }
        if position_side:
            payload["positionSide"] = position_side
        if close_position:
            payload["closePosition"] = "true"
        else:
            if quantity is None or float(quantity) <= 0:
                return {"__invalid__": "quantity must be positive when closePosition is false"}
            payload["quantity"] = str(quantity)
        return payload

    def algo_payload() -> dict:
        payload = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "triggerPrice": rounded_stop,
            "workingType": "MARK_PRICE",
        }
        if position_side:
            payload["positionSide"] = position_side
        if close_position:
            payload["closePosition"] = "true"
        else:
            if quantity is None or float(quantity) <= 0:
                return {"__invalid__": "quantity must be positive when closePosition is false"}
            payload["quantity"] = str(quantity)
        return payload

    payload = normal_payload()
    if "__invalid__" in payload:
        return {"success": False, "error": payload["__invalid__"], "code": "LOCAL_VALIDATION"}

    try:
        order = client.futures_create_order(**payload)
        order_class = "ALGO" if order.get("algoId") is not None and order.get("orderId") is None else "NORMAL"
        ref = _protection_ref(
            order,
            symbol=symbol,
            side=side,
            order_type=order_type,
            stop_price=stop_price,
            quantity=None if close_position else quantity,
            order_class=order_class,
            position_side=position_side,
            close_position=close_position,
            reduce_only=False,
        )
        return {
            "success": True,
            "orderId": order.get("orderId") or order.get("algoId"),
            "status": order.get("status") or order.get("algoStatus"),
            "order_class": order_class,
            "protection_ref": ref.to_dict(),
        }
    except BinanceAPIException as e:
        error_text = str(e).lower()
        if "algo" in error_text or "conditional" in error_text or "trigger" in error_text:
            payload = algo_payload()
            if "__invalid__" in payload:
                return {"success": False, "error": payload["__invalid__"], "code": "LOCAL_VALIDATION"}
            try:
                algo = client.futures_create_algo_order(**payload)
                ref = _protection_ref(
                    algo,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    stop_price=stop_price,
                    quantity=None if close_position else quantity,
                    order_class="ALGO",
                    position_side=position_side,
                    close_position=close_position,
                    reduce_only=False,
                )
                return {
                    "success": True,
                    "orderId": algo.get("algoId"),
                    "status": algo.get("algoStatus") or algo.get("status"),
                    "order_class": "ALGO",
                    "protection_ref": ref.to_dict(),
                }
            except BinanceAPIException as algo_error:
                return {"success": False, "error": str(algo_error), "code": algo_error.code}
        return {"success": False, "error": str(e), "code": e.code}


def get_open_positions() -> list:
    if PAPER_MODE:
        return []
    client = _get_client()
    try:
        raw_positions = client.futures_position_information()
        positions = []
        epsilon = 1e-8
        for pos in raw_positions:
            amt = float(pos.get("positionAmt", 0))
            if abs(amt) <= epsilon:
                continue
            symbol = pos["symbol"]
            positions.append(
                {
                    "id": symbol,
                    "symbol": symbol,
                    "tv_symbol": _map_to_tv(symbol),
                    "type": "BUY" if amt > 0 else "SELL",
                    "openPrice": float(pos.get("entryPrice", 0)),
                    "currentPrice": float(pos.get("markPrice", 0)),
                    "volume": abs(amt),
                    "profit": float(pos.get("unRealizedProfit", 0)),
                    "liquidationPrice": float(pos.get("liquidationPrice", 0)),
                    "leverage": int(pos.get("leverage", 5)),
                    "margin": float(pos.get("isolatedMargin", 0) or pos.get("notional", 0)),
                    "updateTime": pos.get("updateTime"),
                    "stopLoss": pos.get("stopLoss"),
                    "takeProfit": pos.get("takeProfit"),
                }
            )
        return positions
    except Exception as e:
        plain_log("BINANCE_POSITIONS_ERROR", {"error": str(e)})
        return None


def get_open_orders(symbol: str | None = None) -> list:
    client = _get_client()
    return client.futures_get_open_orders(symbol=_map_symbol(symbol)) if symbol else client.futures_get_open_orders()


def get_open_algo_orders(symbol: str | None = None) -> list:
    client = _get_client()
    params = {"symbol": _map_symbol(symbol)} if symbol else {}
    return client.futures_get_open_algo_orders(**params)


def _order_type(order: dict) -> str:
    return str(order.get("type") or order.get("orderType") or "").upper()


def _order_status(order: dict) -> str:
    return str(order.get("status") or order.get("algoStatus") or "").upper()


def _is_live_status(order: dict) -> bool:
    return _order_status(order) in {"NEW", "PARTIALLY_FILLED", "WORKING", "ACCEPTED"}


def _truthy(value) -> bool:
    return value is True or str(value).lower() == "true"


def _order_side(order: dict) -> str:
    return str(order.get("side") or "").upper()


def _order_qty(order: dict) -> float:
    for key in ("origQty", "quantity"):
        value = order.get(key)
        if value not in (None, ""):
            try:
                return abs(float(value))
            except Exception:
                return 0.0
    return 0.0


def _order_stop_price(order: dict) -> float:
    value = order.get("stopPrice") or order.get("triggerPrice")
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _normalized_protection_orders(normal_orders: list, algo_orders: list | None = None) -> list[dict]:
    normalized = list(normal_orders or [])
    for order in algo_orders or []:
        normalized.append(
            {
                **order,
                "type": _order_type(order),
                "status": _order_status(order),
                "symbol": order.get("symbol"),
                "reduceOnly": order.get("reduceOnly"),
                "closePosition": order.get("closePosition"),
                "order_class": "ALGO",
            }
        )
    return normalized


def inspect_exchange_protection(
    symbol: str,
    open_orders: list | None = None,
    algo_orders: list | None = None,
    expected_side: str | None = None,
    expected_position_side: str | None = None,
    expected_sl_qty: float | None = None,
    expected_tp_qty: float | None = None,
    expected_sl: float | None = None,
    expected_tp: float | None = None,
    entry_price: float | None = None,
    current_price: float | None = None,
    remaining_exchange_qty: float | None = None,
) -> dict:
    """Return separate exchange-visible SL/TP truth.

    This is the key safety fix: SL presence and TP presence are separate facts.
    A missing TP is a warning if SL exists; a missing SL after retries is fatal.
    """
    binance_symbol = _map_symbol(symbol)
    orders = open_orders if open_orders is not None else get_open_orders(binance_symbol)
    if algo_orders is None:
        try:
            algo_orders = get_open_algo_orders(binance_symbol)
        except Exception:
            algo_orders = []

    symbol_orders = [o for o in _normalized_protection_orders(orders, algo_orders) if o.get("symbol") == binance_symbol]

    def matches(order: dict, expected_type: str, expected_stop: float | None, expected_qty: float | None) -> bool:
        if _order_type(order) != expected_type:
            return False
        if not (_is_live_status(order) or not _order_status(order)):
            return False
        if expected_side and _order_side(order) and _order_side(order) != expected_side.upper():
            return False
            
        # One-way mode positionSide check
        order_ps = str(order.get("positionSide") or "").upper()
        if expected_position_side:
            expected_ps = str(expected_position_side).upper()
            is_one_way_order = order_ps in ("", "BOTH", "NULL", "NONE")
            is_one_way_expected = expected_ps in ("", "BOTH", "NULL", "NONE")
            if not (is_one_way_order and is_one_way_expected):
                if order_ps != expected_ps:
                    return False

        # In Hedge Mode Binance does not allow reduceOnly. Treat closePosition=true
        # or matching positionSide+closing side as exit-like.
        is_close_position = _truthy(order.get("closePosition"))
        is_exit_like = (
            _truthy(order.get("reduceOnly"))
            or is_close_position
            or bool(
                expected_position_side
                and order_ps == str(expected_position_side).upper()
            )
        )
        if not is_exit_like:
            return False

        # For closePosition=true STOP_MARKET orders, do not require qty matching
        if not (is_close_position and expected_type == "STOP_MARKET"):
            actual_qty = _order_qty(order)
            if expected_qty and actual_qty and abs(actual_qty - abs(float(expected_qty))) > 1e-9:
                return False
                
        # For closePosition=true STOP_MARKET orders, do not require strict stop price matching
        if not (is_close_position and expected_type == "STOP_MARKET"):
            actual_stop = _order_stop_price(order)
            if expected_stop and actual_stop:
                tolerance = 10 ** (-PRICE_PRECISION.get(binance_symbol, 2))
                if abs(actual_stop - float(expected_stop)) > tolerance:
                    return False
        return True

    sl_orders: list[dict] = []
    tp_orders: list[dict] = []
    rejected_orders: list[dict] = []

    def reject(order: dict, reason: str) -> None:
        rejected_orders.append({**order, "reason": reason})

    expected_close_side = str(expected_side or "").upper()
    expected_ps = str(expected_position_side or "").upper()
    inferred_position_side = expected_ps
    if inferred_position_side in {"", "BOTH", "NULL", "NONE"}:
        inferred_position_side = "LONG" if expected_close_side == "SELL" else "SHORT" if expected_close_side == "BUY" else ""

    for order in symbol_orders:
        order_type = _order_type(order)
        order_side = _order_side(order)
        order_ps = str(order.get("positionSide") or "").upper()
        status = _order_status(order)
        is_close_position = _truthy(order.get("closePosition"))

        if status and not _is_live_status(order):
            reject(order, "inactive_status")
            continue
        if expected_close_side and order_side and order_side != expected_close_side:
            reject(order, "wrong_close_side")
            continue
        if expected_ps:
            one_way_order = order_ps in {"", "BOTH", "NULL", "NONE"}
            one_way_expected = expected_ps in {"", "BOTH", "NULL", "NONE"}
            if not (one_way_order and one_way_expected) and order_ps != expected_ps:
                reject(order, "wrong_position_side")
                continue
        is_exit_like = (
            _truthy(order.get("reduceOnly"))
            or is_close_position
            or bool(expected_ps and order_ps == expected_ps)
        )
        if not is_exit_like:
            reject(order, "not_reduce_only_or_close_position")
            continue

        actual_qty = _order_qty(order)
        if remaining_exchange_qty and actual_qty and not is_close_position:
            quantity_tolerance = max(1e-9, abs(float(remaining_exchange_qty)) * 1e-6)
            if actual_qty + quantity_tolerance < abs(float(remaining_exchange_qty)):
                reject(order, "insufficient_protective_quantity")
                continue

        if order_type == "STOP_MARKET":
            if matches(order, "STOP_MARKET", expected_sl, expected_sl_qty):
                sl_orders.append({**order, "reason": "explicit_stop_market"})
            else:
                reject(order, "explicit_sl_shape_mismatch")
            continue
        if order_type == "TAKE_PROFIT_MARKET":
            if matches(order, "TAKE_PROFIT_MARKET", expected_tp, expected_tp_qty):
                tp_orders.append({**order, "reason": "explicit_take_profit_market"})
            else:
                reject(order, "explicit_tp_shape_mismatch")
            continue
        if order_type:
            reject(order, f"unsupported_order_type:{order_type}")
            continue

        trigger = _order_stop_price(order)
        anchor = float(entry_price or current_price or 0)
        if trigger <= 0 or anchor <= 0 or inferred_position_side not in {"LONG", "SHORT"}:
            reject(order, "type_null_unclassifiable")
            continue
        if inferred_position_side == "LONG":
            inferred_type = "STOP_MARKET" if trigger < anchor else "TAKE_PROFIT_MARKET"
        else:
            inferred_type = "STOP_MARKET" if trigger > anchor else "TAKE_PROFIT_MARKET"
        candidate = {**order, "reason": "inferred_sl_shape" if inferred_type == "STOP_MARKET" else "inferred_tp_shape"}
        if inferred_type == "STOP_MARKET":
            sl_orders.append(candidate)
        else:
            tp_orders.append(candidate)

    has_sl = bool(sl_orders)
    has_tp = bool(tp_orders)
    exchange_sl_trigger = _order_stop_price(sl_orders[0]) if sl_orders else None
    exchange_tp_trigger = _order_stop_price(tp_orders[0]) if tp_orders else None

    return {
        "symbol": binance_symbol,
        "has_sl": has_sl,
        "has_tp": has_tp,
        "protected": has_sl and has_tp,
        "sl_order_count": len(sl_orders),
        "tp_order_count": len(tp_orders),
        "open_order_count": len(symbol_orders),
        "expected_side": expected_side,
        "expected_position_side": expected_position_side,
        "expected_sl_qty": expected_sl_qty,
        "expected_tp_qty": expected_tp_qty,
        "expected_sl": expected_sl,
        "expected_tp": expected_tp,
        "candidate_sl_orders": sl_orders,
        "candidate_tp_orders": tp_orders,
        "rejected_orders": rejected_orders,
        "exchange_sl_trigger": exchange_sl_trigger,
        "exchange_tp_trigger": exchange_tp_trigger,
        "sl_price_delta": (
            abs(float(expected_sl) - float(exchange_sl_trigger))
            if expected_sl is not None and exchange_sl_trigger is not None
            else None
        ),
    }


def has_exchange_protection(
    symbol: str,
    open_orders: list | None = None,
    algo_orders: list | None = None,
    expected_side: str | None = None,
    expected_qty: float | None = None,
    expected_sl: float | None = None,
    expected_tp: float | None = None,
    expected_position_side: str | None = None,
) -> tuple[bool, dict]:
    """Backward-compatible full-protection check.

    Returns True only when both SL and TP matching the supplied expectations exist.
    Callers that only care about SL must use inspect_exchange_protection(...)["has_sl"].
    """
    detail = inspect_exchange_protection(
        symbol,
        open_orders=open_orders,
        algo_orders=algo_orders,
        expected_side=expected_side,
        expected_position_side=expected_position_side,
        expected_sl_qty=expected_qty,
        expected_tp_qty=expected_qty,
        expected_sl=expected_sl,
        expected_tp=expected_tp,
    )
    return bool(detail.get("has_sl") and detail.get("has_tp")), detail


def confirm_exchange_protection(
    symbol: str, attempts: int | None = None, delay_seconds: float | None = None
) -> tuple[bool, dict]:
    max_attempts = int(attempts or PROTECTION_TRUTH_RETRIES)
    delay = float(PROTECTION_TRUTH_RETRY_DELAY_SECONDS if delay_seconds is None else delay_seconds)
    last_detail = {"symbol": _map_symbol(symbol), "has_sl": False, "has_tp": False, "open_order_count": 0}
    for attempt in range(1, max(1, max_attempts) + 1):
        detail = inspect_exchange_protection(symbol)
        detail["attempt"] = attempt
        last_detail = detail
        if detail.get("protected"):
            return True, detail
        if attempt < max_attempts and delay > 0:
            time.sleep(delay)
    return False, last_detail


def _coerce_ref(symbol: str, kind: str, raw_ref) -> ProtectionOrderRef | None:
    if raw_ref is None:
        return None
    if isinstance(raw_ref, ProtectionOrderRef):
        return raw_ref
    if isinstance(raw_ref, dict):
        normalized_ref = dict(raw_ref)
        normalized_ref.setdefault("expected_position_side", None)
        return ProtectionOrderRef(**normalized_ref)
    if isinstance(raw_ref, (str, int)):
        return ProtectionOrderRef(
            symbol=_map_symbol(symbol),
            kind=kind,
            order_class="NORMAL",
            order_id=str(raw_ref),
            client_order_id=None,
            algo_id=None,
            client_algo_id=None,
            expected_side="",
            expected_position_side=None,
            expected_stop_price=0.0,
            expected_qty=None,
            close_position=False,
            reduce_only=False,
        )
    return None


def verify_protection_order(client: Client, ref: ProtectionOrderRef | None) -> tuple[bool, dict]:
    if ref is None:
        return False, {"reason": "missing protection reference"}
    try:
        if ref.order_class == "ALGO":
            params = (
                {"symbol": ref.symbol, "algoId": ref.algo_id}
                if ref.algo_id
                else {"symbol": ref.symbol, "clientAlgoId": ref.client_algo_id}
            )
            order = client.futures_get_algo_order(**params)
        else:
            params = (
                {"symbol": ref.symbol, "orderId": ref.order_id}
                if ref.order_id
                else {"symbol": ref.symbol, "origClientOrderId": ref.client_order_id}
            )
            order = client.futures_get_order(**params)
    except Exception as e:
        return False, {"reason": "order lookup failed", "error": str(e), "ref": ref.to_dict()}

    expected_type = "STOP_MARKET" if ref.kind == "SL" else "TAKE_PROFIT_MARKET"
    failures = []
    if order.get("symbol") and order.get("symbol") != ref.symbol:
        failures.append("wrong symbol")
    if ref.expected_side and order.get("side") and order.get("side") != ref.expected_side:
        failures.append("wrong side")
    if _order_type(order) != expected_type:
        failures.append("wrong type")
    if not _is_live_status(order):
        failures.append("not live")
    if ref.expected_position_side:
        order_position_side = str(order.get("positionSide") or "").upper()
        if order_position_side and order_position_side != ref.expected_position_side.upper():
            failures.append("wrong positionSide")
    exit_like = (
        _truthy(order.get("reduceOnly")) or _truthy(order.get("closePosition")) or bool(ref.expected_position_side)
    )
    if not exit_like:
        failures.append("not exit-like")

    actual_stop = order.get("stopPrice") or order.get("triggerPrice")
    if ref.expected_stop_price and actual_stop not in (None, ""):
        tolerance = 10 ** (-PRICE_PRECISION.get(ref.symbol, 2))
        if abs(float(actual_stop) - float(ref.expected_stop_price)) > tolerance:
            failures.append("wrong stop price")

    actual_qty = order.get("origQty") or order.get("quantity")
    if ref.expected_qty and actual_qty not in (None, ""):
        if abs(float(actual_qty) - float(ref.expected_qty)) > 1e-12:
            failures.append("wrong quantity")

    return not failures, {
        "ref": ref.to_dict(),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "type": _order_type(order),
        "status": _order_status(order),
        "failures": failures,
    }


def confirm_placed_protection(
    client: Client,
    symbol: str,
    sl_order_id,
    tp_order_id,
    attempts: int | None = None,
    delay_seconds: float | None = None,
) -> tuple[bool, dict]:
    max_attempts = int(attempts or PROTECTION_TRUTH_RETRIES)
    delay = float(PROTECTION_TRUTH_RETRY_DELAY_SECONDS if delay_seconds is None else delay_seconds)
    binance_symbol = _map_symbol(symbol)
    sl_ref = _coerce_ref(binance_symbol, "SL", sl_order_id)
    tp_ref = _coerce_ref(binance_symbol, "TP", tp_order_id)
    last_detail = {"symbol": binance_symbol, "has_sl": False, "has_tp": False}

    for attempt in range(1, max(1, max_attempts) + 1):
        has_sl, sl_detail = verify_protection_order(client, sl_ref)
        has_tp, tp_detail = verify_protection_order(client, tp_ref)
        detail = {
            "attempt": attempt,
            "sl_detail": sl_detail,
            "tp_detail": tp_detail,
            "has_sl": has_sl,
            "has_tp": has_tp,
        }

        lookup_failed = (
            sl_detail.get("reason") == "order lookup failed" or tp_detail.get("reason") == "order lookup failed"
        )
        if lookup_failed or not (has_sl and has_tp):
            normal_orders = client.futures_get_open_orders(symbol=binance_symbol)
            try:
                algo_orders = client.futures_get_open_algo_orders(symbol=binance_symbol)
            except Exception:
                algo_orders = []

            open_detail = inspect_exchange_protection(
                binance_symbol,
                open_orders=normal_orders,
                algo_orders=algo_orders,
                expected_side=sl_ref.expected_side if sl_ref and sl_ref.expected_side else None,
                expected_position_side=sl_ref.expected_position_side
                if sl_ref and sl_ref.expected_position_side
                else None,
                expected_sl_qty=sl_ref.expected_qty if sl_ref and sl_ref.expected_qty else None,
                expected_tp_qty=tp_ref.expected_qty if tp_ref and tp_ref.expected_qty else None,
                expected_sl=sl_ref.expected_stop_price if sl_ref and sl_ref.expected_stop_price else None,
                expected_tp=tp_ref.expected_stop_price if tp_ref and tp_ref.expected_stop_price else None,
            )
            open_protected = bool(open_detail.get("protected"))
            has_sl = has_sl or bool(open_detail.get("has_sl"))
            has_tp = has_tp or bool(open_detail.get("has_tp"))
            detail.update(open_detail)
            if open_protected or (has_sl and has_tp):
                detail["attempt"] = attempt
                return True, detail

        if has_sl and has_tp:
            return True, detail
        if attempt < max_attempts and delay > 0:
            time.sleep(delay)
    return False, last_detail


def get_balance() -> dict:
    if PAPER_MODE:
        return {"balance": 5000, "equity": 5000, "available": 5000, "currency": "USD"}
    client = _get_client()
    try:
        info = client.futures_account()
        return {
            "balance": float(info.get("totalWalletBalance", 0)),
            "equity": float(info.get("totalWalletBalance", 0)) + float(info.get("totalUnrealizedProfit", 0)),
            "available": float(info.get("availableBalance", 0)),
            "currency": "USDT",
        }
    except Exception as e:
        plain_log("BINANCE_BALANCE_ERROR", {"error": str(e)})
        return {"balance": 0, "equity": 0, "available": 0, "currency": "USDT"}


def get_positions_and_balance() -> tuple:
    return get_open_positions(), get_balance()


def place_trade(
    signal: str,
    symbol: str,
    lot: float,
    sl_distance: float,
    rr: float,
    clear_pending_fn=None,
    risk_pct_override: float = None,
    execution_state_fn=None,
) -> dict | None:
    if PAPER_MODE:
        plain_log("PAPER_TRADE", {"symbol": symbol, "signal": signal, "sl_distance": sl_distance, "rr": rr})
        if clear_pending_fn:
            clear_pending_fn(symbol)
        return None
    try:
        return _execute_trade(
            signal, symbol, lot, sl_distance, rr, clear_pending_fn, risk_pct_override, execution_state_fn
        )
    except Exception as e:
        error_text = str(e)
        plain_log("BINANCE_TRADE_ERROR", {"symbol": symbol, "signal": signal, "error": error_text})
        if "code=-1007" in error_text or "Timeout waiting for response" in error_text:
            timeout_detail = _reconcile_unknown_timeout(symbol, signal, error_text)
            if timeout_detail.get("reconciled_state") == "flat_after_timeout":
                return {
                    "status": "timeout_reconciled_flat",
                    "symbol": timeout_detail.get("symbol") or _map_symbol(symbol),
                    "signal": signal,
                    "reconciliation": timeout_detail,
                    "error": error_text,
                }
        if clear_pending_fn:
            clear_pending_fn(symbol)
        return None


def _reconcile_unknown_timeout(symbol: str, signal: str, error_text: str) -> dict:
    binance_symbol = _map_symbol(symbol)
    detail = {
        "symbol": binance_symbol,
        "signal": signal,
        "error": error_text,
        "position_amt": None,
        "has_position": None,
        "has_protection": False,
        "protection_detail": {},
        "reconciled_state": "unknown",
    }
    try:
        client = _get_client()
        positions = client.futures_position_information(symbol=binance_symbol)
        if isinstance(positions, dict):
            positions = [positions]
        position = next((p for p in positions or [] if p.get("symbol") == binance_symbol), {})
        position_amt = float(position.get("positionAmt") or 0.0)
        detail["position_amt"] = position_amt
        detail["has_position"] = abs(position_amt) > 0
        try:
            normal_orders = client.futures_get_open_orders(symbol=binance_symbol)
        except Exception as oe:
            normal_orders = []
            detail["normal_order_error"] = str(oe)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=binance_symbol)
        except Exception as ae:
            algo_orders = []
            detail["algo_order_error"] = str(ae)
        protection_detail = inspect_exchange_protection(
            binance_symbol, open_orders=normal_orders, algo_orders=algo_orders
        )
        detail["has_protection"] = bool(protection_detail.get("protected"))
        detail["has_sl"] = bool(protection_detail.get("has_sl"))
        detail["has_tp"] = bool(protection_detail.get("has_tp"))
        detail["protection_detail"] = protection_detail
        if not detail["has_position"]:
            detail["reconciled_state"] = "flat_after_timeout"
        elif detail["has_sl"] and detail["has_tp"]:
            detail["reconciled_state"] = "open_protected_after_timeout"
        elif detail["has_sl"]:
            detail["reconciled_state"] = "open_sl_protected_tp_warning_after_timeout"
        else:
            detail["reconciled_state"] = "open_unprotected_after_timeout"
    except Exception as re:
        detail["reconcile_error"] = str(re)
    plain_log("BINANCE_TIMEOUT_RECONCILIATION", detail)
    return detail


def _execute_trade(
    signal: str,
    tv_symbol: str,
    lot: float,
    sl_distance: float,
    rr: float,
    clear_pending_fn=None,
    risk_pct_override: float = None,
    execution_state_fn=None,
) -> dict:
    client = _get_client()
    binance_symbol = _map_symbol(tv_symbol)
    balance_info = get_balance()
    equity = balance_info.get("equity", 0)
    if equity < MIN_BALANCE_USD:
        raise ValueError(f"Equity ${equity} below minimum ${MIN_BALANCE_USD}")

    ticker = client.futures_symbol_ticker(symbol=binance_symbol)
    price = float(ticker["price"])
    spread_check = check_order_book_spread(client, binance_symbol, is_entry=True)
    if not spread_check.ok:
        raise ValueError(
            f"Slippage Protection: {binance_symbol} entry spread check failed ({spread_check.reason}, {spread_check.spread_pct:.4f}% vs max {MAX_SPREAD_PCT}%)"
        )

    _set_leverage(client, binance_symbol)
    price_decimals = PRICE_PRECISION.get(binance_symbol, 2)
    side = "BUY" if signal == "BUY" else "SELL"
    close_side = "SELL" if signal == "BUY" else "BUY"
    position_side = "LONG" if signal == "BUY" else "SHORT"

    if risk_pct_override is not None:
        effective_risk_pct = risk_pct_override
        risk_dollars = equity * effective_risk_pct
        risk_mode = "caller_override"
    else:
        risk_decision = resolve_trade_risk(equity, RISK_PCT, RISK_PCT)
        effective_risk_pct = risk_decision.effective_risk_pct
        risk_dollars = risk_decision.risk_dollars
        risk_mode = risk_decision.mode

    if sl_distance <= 0:
        raise ValueError(f"{binance_symbol} invalid sl_distance={sl_distance}")

    quantity = float(lot) if lot and lot > 0 else risk_dollars / sl_distance
    quantity = min(quantity, MAX_LOT_SIZE)
    quantity = _format_quantity(binance_symbol, quantity)
    if quantity <= 0:
        raise ValueError(f"{binance_symbol} formatted quantity is zero")

    target_risk_dollars = risk_dollars
    quantity, margin_cap = _margin_capped_quantity(
        binance_symbol, quantity, price=price, available_balance=balance_info.get("available")
    )
    if margin_cap:
        if quantity <= 0:
            raise ValueError(f"{binance_symbol} available margin cannot fit minimum quantity")
        risk_dollars = quantity * sl_distance

    min_notional = BINANCE_MIN_NOTIONAL.get(binance_symbol, 5)
    notional = quantity * price
    if notional < min_notional:
        floor_qty = _format_quantity(binance_symbol, min_notional / price)
        floor_risk = floor_qty * sl_distance
        risk_mult = floor_risk / risk_dollars if risk_dollars > 0 else float("inf")
        if MIN_NOTIONAL_RISK_OVERRIDE_MODE != "allow_micro_growth" or risk_mult > MIN_NOTIONAL_MAX_RISK_MULT:
            raise ValueError(
                f"{binance_symbol} min notional would exceed target risk ({risk_mult:.2f}x > {MIN_NOTIONAL_MAX_RISK_MULT:.2f}x)"
            )
        quantity = floor_qty

    xau_preflight = None
    quantity, xau_preflight = _xau_notional_preflight(client, binance_symbol, quantity, price)
    if xau_preflight:
        risk_dollars = quantity * sl_distance

    # ── [ENTRY FILLED] ──
    # Hedge Mode requires positionSide. reduceOnly is intentionally not sent.
    order = client.futures_create_order(
        symbol=binance_symbol, side=side, positionSide=position_side, type="MARKET", quantity=quantity
    )
    order_id = order.get("orderId")

    raw_avg_price = float(order.get("avgPrice") or 0.0)
    exec_price = raw_avg_price if raw_avg_price > 0 else price

    try:
        telegram_client.notify_entry_protection_verifying(
            signal,
            binance_symbol,
            exec_price,
            str(order_id) if order_id is not None else None,
        )
    except Exception as notify_error:
        plain_log(
            "PROTECTION_VERIFYING_NOTIFY_ERROR",
            {"symbol": binance_symbol, "error": str(notify_error)},
        )

    if execution_state_fn:
        execution_state_fn(
            "entry_filled",
            {"order_id": order_id, "exec_price": exec_price, "quantity": quantity, "position_side": position_side},
        )

    sl_price = round(exec_price - sl_distance if signal == "BUY" else exec_price + sl_distance, price_decimals)
    tp1_price = round(
        exec_price + (sl_distance * 0.5) if signal == "BUY" else exec_price - (sl_distance * 0.5), price_decimals
    )
    tp2_price = round(
        exec_price + (sl_distance * rr) if signal == "BUY" else exec_price - (sl_distance * rr), price_decimals
    )
    tp1_qty, tp2_qty = _tp_split_quantities(binance_symbol, quantity)

    if execution_state_fn:
        execution_state_fn(
            "protection_pending",
            {
                "sl_price": sl_price,
                "tp1_price": tp1_price,
                "tp2_price": tp2_price,
                "tp1_qty": tp1_qty,
                "tp2_qty": tp2_qty,
            },
        )

    # Best-effort initial protection placement. The finalizer below is the source of truth.
    sl_result = _place_sl_tp_order(
        client,
        binance_symbol,
        close_side,
        "STOP_MARKET",
        sl_price,
        position_side=position_side,
        close_position=True,
    )
    tp1_result = {"success": False, "orderId": None, "skipped": tp1_qty <= 0}
    if tp1_qty > 0:
        tp1_result = _place_sl_tp_order(
            client,
            binance_symbol,
            close_side,
            "TAKE_PROFIT_MARKET",
            tp1_price,
            tp1_qty,
            position_side=position_side,
            close_position=False,
        )
        if tp1_result.get("success"):
            plain_log("MILESTONE_ORDER_PLACED", {
                "symbol": tv_symbol,
                "type": "TP1",
                "price": tp1_price,
                "qty": tp1_qty,
                "order_id": tp1_result.get("orderId")
            })
    tp2_result = {"success": False, "orderId": None, "skipped": tp2_qty <= 0}
    if tp2_qty > 0:
        tp2_result = _place_sl_tp_order(
            client,
            binance_symbol,
            close_side,
            "TAKE_PROFIT_MARKET",
            tp2_price,
            tp2_qty,
            position_side=position_side,
            close_position=False,
        )
        if tp2_result.get("success"):
            plain_log("MILESTONE_ORDER_PLACED", {
                "symbol": tv_symbol,
                "type": "TP2",
                "price": tp2_price,
                "qty": tp2_qty,
                "order_id": tp2_result.get("orderId")
            })

    # ── [PROTECTION FINALIZER LOOP] ──
    # Fatal condition is only: SL missing after bounded repair.
    sl_detail = {}
    open_orders, algo_orders = [], []
    max_attempts = max(1, int(PROTECTION_TRUTH_RETRIES or 3))
    delay = float(PROTECTION_TRUTH_RETRY_DELAY_SECONDS or 0.5)

    for attempt in range(1, max_attempts + 1):
        open_orders = client.futures_get_open_orders(symbol=binance_symbol)
        try:
            algo_orders = client.futures_get_open_algo_orders(symbol=binance_symbol)
        except Exception:
            algo_orders = []

        sl_detail = inspect_exchange_protection(
            binance_symbol,
            open_orders=open_orders,
            algo_orders=algo_orders,
            expected_side=close_side,
            expected_position_side=position_side,
            expected_sl=sl_price,
        )
        sl_detail["attempt"] = attempt

        # Open order lists can lag on Binance. If the SL placement returned
        # a concrete order/algo reference, verify that specific order before
        # treating the position as naked.
        if not sl_detail.get("has_sl"):
            sl_ref = _coerce_ref(
                binance_symbol,
                "SL",
                (sl_result or {}).get("protection_ref") if isinstance(sl_result, dict) else None,
            )
            if sl_ref is not None:
                sl_by_ref, ref_detail = verify_protection_order(client, sl_ref)
                sl_detail["ref_verify"] = ref_detail
                if sl_by_ref:
                    sl_detail["has_sl"] = True
                    sl_detail["verified_by"] = "order_ref"

        if sl_detail.get("has_sl"):
            break

        plain_log("PROTECTION_SL_REPAIR_ATTEMPT", {"symbol": binance_symbol, "attempt": attempt, "detail": sl_detail})
        sl_result = _place_sl_tp_order(
            client,
            binance_symbol,
            close_side,
            "STOP_MARKET",
            sl_price,
            position_side=position_side,
            close_position=True,
        )
        if attempt < max_attempts and delay > 0:
            time.sleep(delay)

    if not sl_detail.get("has_sl"):
        close_result = close_position(binance_symbol, position_side=position_side)
        if clear_pending_fn:
            clear_pending_fn(tv_symbol)
        plain_log(
            "PROTECTION_FAIL_CLOSED",
            {
                "symbol": binance_symbol,
                "position_side": position_side,
                "sl_detail": sl_detail,
                "close_result": close_result,
            },
        )
        try:
            telegram_client.notify_execution_fail_closed(
                signal,
                binance_symbol,
                exec_price,
                sl_price,
                close_result,
            )
        except TypeError:
            # Backward-compatible fallback if notifier has a shorter signature.
            telegram_client.notify_execution_fail_closed(
                signal,
                binance_symbol,
                exec_price,
            )
        except Exception as notify_error:
            plain_log(
                "PROTECTION_FAIL_CLOSED_NOTIFY_ERROR",
                {"symbol": binance_symbol, "error": str(notify_error)},
            )
        raise ValueError(
            f"FAIL-CLOSED: {binance_symbol} {position_side} security breach — SL missing after repair attempts; position terminated."
        )

    # TPs are useful, but missing TP is not fatal when SL is verified. Repair once and report warning.
    tp1_detail = {"has_tp": True, "skipped": tp1_qty <= 0}
    tp2_detail = {"has_tp": True, "skipped": tp2_qty <= 0}
    if tp1_qty > 0:
        tp1_detail = inspect_exchange_protection(
            binance_symbol,
            open_orders=open_orders,
            algo_orders=algo_orders,
            expected_side=close_side,
            expected_position_side=position_side,
            expected_tp_qty=tp1_qty,
            expected_tp=tp1_price,
        )
    if tp2_qty > 0:
        tp2_detail = inspect_exchange_protection(
            binance_symbol,
            open_orders=open_orders,
            algo_orders=algo_orders,
            expected_side=close_side,
            expected_position_side=position_side,
            expected_tp_qty=tp2_qty,
            expected_tp=tp2_price,
        )

    # Open order lists can lag for TP orders too. If TP placement returned
    # concrete order/algo refs, verify those refs before attempting repair.
    def _verify_tp_result(label, result, detail):
        if detail.get("has_tp"):
            return detail
        tp_ref = _coerce_ref(
            binance_symbol,
            "TP",
            (result or {}).get("protection_ref") if isinstance(result, dict) else None,
        )
        if tp_ref is None:
            detail[f"{label}_ref_missing"] = True
            return detail

        tp_by_ref, tp_ref_detail = verify_protection_order(client, tp_ref)
        detail[f"{label}_ref_verify"] = tp_ref_detail
        if tp_by_ref:
            detail["has_tp"] = True
            detail["verified_by"] = label
        return detail

    tp1_detail = _verify_tp_result("initial_order_ref", tp1_result, tp1_detail) if tp1_qty > 0 else tp1_detail
    tp2_detail = _verify_tp_result("initial_order_ref", tp2_result, tp2_detail) if tp2_qty > 0 else tp2_detail

    # If TP is still missing, repair it and verify the repair before warning.
    if tp1_qty > 0 and not tp1_detail.get("has_tp"):
        tp1_repair_result = _place_sl_tp_order(
            client,
            binance_symbol,
            close_side,
            "TAKE_PROFIT_MARKET",
            tp1_price,
            tp1_qty,
            position_side=position_side,
            close_position=False,
        )
        if isinstance(tp1_repair_result, dict):
            tp1_detail["repair_result"] = {
                "success": tp1_repair_result.get("success"),
                "orderId": tp1_repair_result.get("orderId"),
                "status": tp1_repair_result.get("status"),
                "order_class": tp1_repair_result.get("order_class"),
                "code": tp1_repair_result.get("code"),
                "error": tp1_repair_result.get("error"),
            }
        tp1_detail = _verify_tp_result("repair_order_ref", tp1_repair_result, tp1_detail)

    if tp2_qty > 0 and not tp2_detail.get("has_tp"):
        tp2_repair_result = _place_sl_tp_order(
            client,
            binance_symbol,
            close_side,
            "TAKE_PROFIT_MARKET",
            tp2_price,
            tp2_qty,
            position_side=position_side,
            close_position=False,
        )
        if isinstance(tp2_repair_result, dict):
            tp2_detail["repair_result"] = {
                "success": tp2_repair_result.get("success"),
                "orderId": tp2_repair_result.get("orderId"),
                "status": tp2_repair_result.get("status"),
                "order_class": tp2_repair_result.get("order_class"),
                "code": tp2_repair_result.get("code"),
                "error": tp2_repair_result.get("error"),
            }
        tp2_detail = _verify_tp_result("repair_order_ref", tp2_repair_result, tp2_detail)

    tp_warning = False
    if tp1_qty > 0 and not tp1_detail.get("has_tp"):
        tp_warning = True
    if tp2_qty > 0 and not tp2_detail.get("has_tp"):
        tp_warning = True

    protection_status = "sl_verified_tp_warning" if tp_warning else "protection_verified"
    if execution_state_fn:
        execution_state_fn(
            "protection_verified",
            {"status": protection_status, "sl_detail": sl_detail, "tp1_detail": tp1_detail, "tp2_detail": tp2_detail},
        )

    if protection_status == "protection_verified":
        try:
            telegram_client.notify_protection_confirmed(
                signal,
                binance_symbol,
                exec_price,
                sl_price,
                tp2_price,
            )
        except Exception as notify_error:
            plain_log(
                "PROTECTION_CONFIRMED_NOTIFY_ERROR",
                {"symbol": binance_symbol, "error": str(notify_error)},
            )
    else:
        try:
            telegram_client.notify_confirmed_with_protection_warning(
                signal,
                binance_symbol,
                exec_price,
                sl_price,
                tp2_price,
            )
        except TypeError:
            # Backward-compatible fallback if the warning notifier has a shorter signature.
            telegram_client.notify_confirmed_with_protection_warning(
                signal,
                binance_symbol,
                exec_price,
            )
        except Exception as notify_error:
            plain_log(
                "PROTECTION_WARNING_NOTIFY_ERROR",
                {"symbol": binance_symbol, "error": str(notify_error)},
            )

    try:
        import trade_db

        trade_db.upsert_binance_order_state(
            symbol=binance_symbol,
            tv_symbol=tv_symbol,
            side=side,
            entry_order_id=str(order_id),
            sl_order_id=str(sl_result.get("orderId")) if sl_result.get("success") else None,
            tp_order_id=str(tp2_result.get("orderId")) if tp2_result.get("success") else None,
            original_qty=quantity,
            remaining_qty=quantity,
            entry_price=exec_price,
            original_sl=sl_price,
            current_sl=sl_price,
            current_tp=tp2_price,
            original_sl_distance=sl_distance,
            runner_status="open",
            raw_state={
                "execution_mode": get_execution_mode(),
                "risk_pct": effective_risk_pct,
                "risk_mode": risk_mode,
                "risk_dollars": risk_dollars,
                "target_risk_dollars": target_risk_dollars,
                "margin_cap": margin_cap,
                "position_side": position_side,
                "protection_status": protection_status,
                "tp1_price": tp1_price,
                "tp1_qty": tp1_qty,
                "tp2_price": tp2_price,
                "tp2_qty": tp2_qty,
                "sl_detail": sl_detail,
                "tp1_detail": tp1_detail,
                "tp2_detail": tp2_detail,
            },
        )
    except Exception as dbe:
        plain_log("BINANCE_ORDER_STATE_ERROR", {"symbol": binance_symbol, "error": str(dbe)})

    if clear_pending_fn:
        clear_pending_fn(tv_symbol)
    return {
        "status": protection_status,
        "symbol": binance_symbol,
        "order_id": order_id,
        "exec_price": exec_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "tp_price": tp2_price,
        "quantity": quantity,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "risk_dollars": risk_dollars,
        "target_risk_dollars": target_risk_dollars,
        "effective_risk_pct": effective_risk_pct,
        "margin_cap": margin_cap,
        "position_side": position_side,
        "sl_detail": sl_detail,
        "tp_warning": tp_warning,
    }


def close_position(position_id: str, position_side: str | None = None) -> dict:
    """Close open Binance Futures position(s) for a symbol.

    Hedge Mode: pass positionSide and omit reduceOnly. If no position_side is
    supplied, closes every non-zero side for the symbol.
    """
    if PAPER_MODE:
        return {"status": "paper_close", "symbol": position_id, "position_side": position_side}
    client = _get_client()
    symbol = _map_symbol(position_id)
    results = []
    try:
        positions = client.futures_position_information(symbol=symbol)
        if isinstance(positions, dict):
            positions = [positions]
        for pos in positions:
            if pos.get("symbol") != symbol:
                continue
            raw_pos_side = str(pos.get("positionSide") or "BOTH").upper()
            amt = float(pos.get("positionAmt", 0))
            inferred_pos_side = "LONG" if amt > 0 else "SHORT"
            pos_side = raw_pos_side if raw_pos_side in {"LONG", "SHORT"} else inferred_pos_side
            if position_side and pos_side != position_side.upper():
                continue
            if amt == 0:
                continue
            side = "SELL" if amt > 0 else "BUY"
            close_qty = _format_quantity(symbol, abs(amt))
            if close_qty <= 0:
                results.append(
                    {
                        "status": "error",
                        "symbol": symbol,
                        "position_side": pos_side,
                        "error": "formatted quantity is zero",
                    }
                )
                continue
            payload = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": close_qty}
            if raw_pos_side in {"LONG", "SHORT"}:
                payload["positionSide"] = raw_pos_side
            else:
                payload["reduceOnly"] = True
            order = client.futures_create_order(**payload)
            results.append(
                {
                    "status": "closed",
                    "symbol": symbol,
                    "position_side": pos_side,
                    "order_id": order.get("orderId"),
                    "quantity": close_qty,
                }
            )
        if not results:
            return {"status": "no_position", "symbol": symbol, "position_side": position_side}
        if len(results) == 1:
            return results[0]
        return {"status": "closed_multiple", "symbol": symbol, "results": results}
    except Exception as e:
        return {"status": "error", "symbol": symbol, "position_side": position_side, "error": str(e)}


def close_position_qty(
    position_id: str, quantity: float, reason: str = "protective_exit", position_side: str | None = None
) -> dict:
    if PAPER_MODE:
        return {"status": "closed", "symbol": position_id, "quantity": quantity, "position_side": position_side}
    client = _get_client()
    symbol = _map_symbol(position_id)
    try:
        positions = client.futures_position_information(symbol=symbol)
        if isinstance(positions, dict):
            positions = [positions]
        for pos in positions:
            if pos.get("symbol") != symbol:
                continue
            raw_pos_side = str(pos.get("positionSide") or "BOTH").upper()
            amt = float(pos.get("positionAmt", 0))
            if amt == 0:
                continue
            inferred_pos_side = "LONG" if amt > 0 else "SHORT"
            pos_side = raw_pos_side if raw_pos_side in {"LONG", "SHORT"} else inferred_pos_side
            if position_side and pos_side != position_side.upper():
                continue
            if amt == 0:
                continue
            close_qty = _format_quantity(symbol, min(abs(quantity), abs(amt)))
            if close_qty <= 0:
                return {
                    "status": "error",
                    "symbol": symbol,
                    "position_side": pos_side,
                    "error": "formatted quantity is zero",
                }
            side = "SELL" if amt > 0 else "BUY"
            payload = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": close_qty}
            if raw_pos_side in {"LONG", "SHORT"}:
                payload["positionSide"] = raw_pos_side
            else:
                payload["reduceOnly"] = True
            order = client.futures_create_order(**payload)
            return {
                "status": "partial_closed",
                "symbol": symbol,
                "position_side": pos_side,
                "order_id": order.get("orderId"),
                "quantity": close_qty,
                "reason": reason,
            }
        return {"status": "not_found", "symbol": symbol, "position_side": position_side}
    except Exception as e:
        return {"status": "error", "symbol": symbol, "position_side": position_side, "error": str(e)}


def move_sl_to_breakeven(position_id: str, new_sl: float):
    if PAPER_MODE:
        return
    client = _get_client()
    symbol = _map_symbol(position_id)
    try:
        positions = client.futures_position_information(symbol=symbol)
        if isinstance(positions, dict):
            positions = [positions]
        for pos in positions:
            if pos.get("symbol") != symbol:
                continue
            amt = float(pos.get("positionAmt", 0))
            if amt == 0:
                continue
            pos_side = str(pos.get("positionSide") or ("LONG" if amt > 0 else "SHORT")).upper()
            side = "SELL" if amt > 0 else "BUY"
            # Place new SL first, then cancel old STOP_MARKETs to avoid a naked window.
            _place_sl_tp_order(client, symbol, side, "STOP_MARKET", new_sl, position_side=pos_side, close_position=True)
            open_orders = client.futures_get_open_orders(symbol=symbol)
            for o in open_orders:
                if o.get("type") == "STOP_MARKET" and str(o.get("positionSide") or pos_side).upper() == pos_side:
                    client.futures_cancel_order(symbol=symbol, orderId=o["orderId"])
    except Exception as e:
        plain_log("BINANCE_BREAKEVEN_ERROR", {"symbol": symbol, "error": str(e)})


def get_account_info() -> dict:
    if PAPER_MODE:
        return {"paper_mode": True}
    client = _get_client()
    try:
        info = client.futures_account()
        return {
            "totalWalletBalance": float(info.get("totalWalletBalance", 0)),
            "totalUnrealizedProfit": float(info.get("totalUnrealizedProfit", 0)),
            "availableBalance": float(info.get("availableBalance", 0)),
            "asset": "USDT",
        }
    except Exception as e:
        plain_log("BINANCE_ACCOUNT_ERROR", {"error": str(e)})
        return {}
