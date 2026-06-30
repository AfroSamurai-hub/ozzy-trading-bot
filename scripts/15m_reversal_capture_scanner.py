#!/usr/bin/env python3
"""Testnet-only 15m reversal-capture scanner."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from binance_indicators import get_live_indicators as get_1h_indicators
from lane_labels import REVERSAL_CAPTURE_15M, webhook_port_from_url
from local_indicators import get_live_indicators_dict
from logger import plain_log
from config import TESTNET_SYMBOLS

WEBHOOK_URL = os.getenv("HERMES_WEBHOOK_URL", "http://127.0.0.1:5001/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
SYMBOLS = [s.strip().upper() for s in os.getenv("HERMES_REVERSAL_CAPTURE_SYMBOLS", "").split(",") if s.strip()]
if not SYMBOLS:
    SYMBOLS = TESTNET_SYMBOLS


def _load_mean_reversion_module():
    path = ROOT / "scripts" / "15m_reversion_scanner.py"
    spec = importlib.util.spec_from_file_location("scanner_15m_reversion_for_reversal_capture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MEAN_REVERSION = _load_mean_reversion_module()


def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _validate_testnet_safety(webhook_url: str = WEBHOOK_URL) -> tuple[bool, str]:
    parsed = urlparse(webhook_url)
    if not _truthy_env("HERMES_BINANCE_TESTNET", "true"):
        return False, "HERMES_BINANCE_TESTNET must be true"
    if parsed.hostname != "127.0.0.1" or parsed.port != 5001:
        return False, "webhook URL must be exactly 127.0.0.1:5001"
    if not WEBHOOK_SECRET:
        return False, "WEBHOOK_SECRET missing"
    return True, "ok"


def _has_open_symbol_position(symbol: str) -> bool:
    try:
        import binance_connector

        positions = binance_connector.get_open_positions() or []
    except Exception as exc:
        plain_log("REVERSAL_CAPTURE_POSITION_CHECK_FAILED", {"symbol": symbol, "error": str(exc)})
        return True
    for position in positions:
        pos_symbol = str(position.get("symbol") or position.get("tv_symbol") or "").upper()
        if pos_symbol == symbol and abs(float(position.get("volume") or 0.0)) > 0:
            return True
    return False


def evaluate_reversal_capture(symbol: str, one_hour: dict, fifteen: dict) -> dict:
    """Evaluate BUY-only bearish-flush reversal capture evidence."""
    reasons = []
    if not (one_hour.get("supertrend_direction") == "short" or one_hour.get("prior_structure_bias") == "bearish"):
        reasons.append("1h backdrop is not bearish")
    range_position = one_hour.get("range_position_pct")
    if range_position is None or float(range_position) > 25.0:
        reasons.append("1h range position not in lower quartile")

    evidence = {
        "liquidity_sweep": one_hour.get("liquidity_sweep"),
        "wick_rejection": one_hour.get("wick_rejection"),
        "retest_quality": one_hour.get("retest_quality"),
        "market_structure": one_hour.get("market_structure"),
    }
    has_reversal_evidence = (
        evidence["liquidity_sweep"] == "bullish_sweep"
        or evidence["wick_rejection"] == "bullish_rejection"
        or evidence["retest_quality"] == "support_retest_hold"
        or evidence["market_structure"] == "bullish_choch"
    )
    if not has_reversal_evidence:
        reasons.append("missing bullish sweep/rejection/reclaim evidence")

    volume_expansion = one_hour.get("volume_expansion")
    if volume_expansion is None or float(volume_expansion) < 1.0:
        reasons.append("1h volume expansion below 1.0")

    mean_reversion_result = MEAN_REVERSION.evaluate_mean_reversion(symbol, fifteen)
    if not mean_reversion_result.get("conditions_met") or mean_reversion_result.get("signal") != "BUY":
        reasons.append("15m mean-reversion BUY confirmation failed")
        reasons.extend(mean_reversion_result.get("reasons") or [])

    return {
        "symbol": symbol,
        "allowed": not reasons,
        "signal": "BUY",
        "reasons": reasons,
        "reversal_evidence": evidence,
        "mean_reversion": mean_reversion_result,
        "one_hour": {
            "range_position_pct": one_hour.get("range_position_pct"),
            "support_distance_pct": one_hour.get("support_distance_pct"),
            "resistance_distance_pct": one_hour.get("resistance_distance_pct"),
            "volume_expansion": one_hour.get("volume_expansion"),
        },
    }


def _send_payload(symbol: str, entry: float, result: dict) -> bool:
    mr = result["mean_reversion"]
    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol,
        "signal": "BUY",
        "entry": round(float(entry), 5),
        "bias": "neutral",
        "structure": "neutral_neutral",
        "regime": "smc_pro",
        "version": "2.2.1",
        "source": "signal_generator",
        "source_service": "testnet_15m_reversal_capture",
        "timeframe": "15",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "strategy": "reversal_capture",
        "strategy_label": REVERSAL_CAPTURE_15M,
        "entry_setup_label": "BULLISH_SWEEP_RECLAIM",
        "regime_label": "SMC_PRO_BEARISH_REVERSAL",
        "webhook_port": webhook_port_from_url(WEBHOOK_URL),
        "execution_mode": "TESTNET",
        "sl": mr["sl"],
        "tp": mr["tp"],
        "rr": mr["rr"],
    }
    response = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    response.raise_for_status()
    body = response.json()
    plain_log("REVERSAL_CAPTURE_SIGNAL_SENT", {"symbol": symbol, "status": body.get("status"), "reason": body.get("reason")})
    return body.get("status") in {"approved", "entry_filled"}


def run_scanner() -> None:
    safe, reason = _validate_testnet_safety()
    if not safe:
        plain_log("REVERSAL_CAPTURE_SAFETY_BLOCKED", {"reason": reason, "webhook_url": WEBHOOK_URL})
        return

    fired = 0
    plain_log("REVERSAL_CAPTURE_SCANNER_START", {"symbols": SYMBOLS, "webhook_url": WEBHOOK_URL, "execution_mode": "TESTNET"})
    for symbol in SYMBOLS:
        if _has_open_symbol_position(symbol):
            plain_log("REVERSAL_CAPTURE_SKIP_OPEN_POSITION", {"symbol": symbol})
            continue
        one_hour = get_1h_indicators(symbol, "1h") or {}
        fifteen = get_live_indicators_dict(symbol, "15m", use_closed=True) or {}
        if not one_hour or not fifteen:
            plain_log("REVERSAL_CAPTURE_SKIP_INDICATORS", {"symbol": symbol})
            continue
        result = evaluate_reversal_capture(symbol, one_hour, fifteen)
        if not result["allowed"]:
            plain_log("REVERSAL_CAPTURE_REJECTED", result)
            continue
        entry = float(fifteen.get("close") or 0.0)
        if entry <= 0:
            plain_log("REVERSAL_CAPTURE_REJECTED", {"symbol": symbol, "reasons": ["invalid entry"]})
            continue
        if _send_payload(symbol, entry, result):
            fired += 1

    plain_log("REVERSAL_CAPTURE_SCANNER_DONE", {"symbols_checked": len(SYMBOLS), "signals_fired": fired})


if __name__ == "__main__":
    run_scanner()
