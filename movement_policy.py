import json
from datetime import datetime
from pathlib import Path
from typing import Any

STATS_FILE = "/home/rick/ozzy-bot/signal_stats.json"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_movement(movement_ratio: float | None) -> str:
    if movement_ratio is None:
        return "unknown"
    if movement_ratio < 0.95:
        return "quiet"
    if movement_ratio < 1.25:
        return "normal"
    return "fast"


def get_adjusted_sl_mult(
    atr: float | None,
    min_sl: float,
    base_sl_mult: float,
    quiet_mult: float = 1.33,
    fast_mult: float = 0.80,
) -> tuple[float, str | None]:
    """Return (adjusted_sl_mult, movement_class_or_None) based on ATR/min_sl ratio."""
    if atr is None or min_sl <= 0:
        return base_sl_mult, None

    movement_class = classify_movement(atr / min_sl)
    if movement_class == "quiet":
        return base_sl_mult * quiet_mult, movement_class
    if movement_class == "fast":
        return base_sl_mult * fast_mult, movement_class
    return base_sl_mult, None


def build_movement_snapshot(symbol: str, asset: dict, live: dict | None, sl_distance: float | None) -> dict:
    min_sl = _safe_float(asset.get("min_sl")) or 0.0
    default_offset = _safe_float(asset.get("default_offset")) or 0.0
    atr = _safe_float((live or {}).get("atr"))
    volume = _safe_float((live or {}).get("volume"))
    volume_avg20 = _safe_float((live or {}).get("volume_avg20"))

    movement_ratio = round(atr / min_sl, 4) if atr and min_sl > 0 else None
    offset_ratio = round(atr / default_offset, 4) if atr and default_offset > 0 else None
    volume_ratio = round(volume / volume_avg20, 4) if volume and volume_avg20 and volume_avg20 > 0 else None
    movement_class = classify_movement(movement_ratio)

    tolerance_pct = float(asset.get("min_sl_tolerance_pct", 0.10) or 0.10)
    if movement_class == "normal":
        tolerance_pct += float(asset.get("normal_move_bonus_pct", 0.05) or 0.05)
    elif movement_class == "fast":
        tolerance_pct += float(asset.get("fast_move_bonus_pct", 0.15) or 0.15)

    strong_volume_ratio = float(asset.get("strong_volume_ratio", 1.20) or 1.20)
    if volume_ratio is not None and volume_ratio >= strong_volume_ratio:
        tolerance_pct += float(asset.get("volume_bonus_pct", 0.05) or 0.05)

    max_tolerance_pct = float(asset.get("max_min_sl_tolerance_pct", 0.30) or 0.30)
    tolerance_pct = min(tolerance_pct, max_tolerance_pct)
    min_sl_buffer = round(min_sl * (1.0 - tolerance_pct), 5) if min_sl > 0 else 0.0

    allowed_with_tolerance = False
    if sl_distance is not None and min_sl > 0:
        allowed_with_tolerance = float(sl_distance) >= min_sl_buffer

    return {
        "symbol": symbol,
        "atr": atr,
        "min_sl": min_sl,
        "default_offset": default_offset,
        "movement_ratio": movement_ratio,
        "offset_ratio": offset_ratio,
        "volume_ratio": volume_ratio,
        "movement_class": movement_class,
        "tolerance_pct": round(tolerance_pct, 4),
        "min_sl_buffer": min_sl_buffer,
        "sl_distance": round(float(sl_distance), 5) if sl_distance is not None else None,
        "allowed_with_tolerance": allowed_with_tolerance,
    }


def _reason_key(reason: str | None) -> str:
    if not reason:
        return "unknown"
    return reason.strip()[:80]


def record_signal_outcome(symbol: str, status: str, movement: dict | None, reason: str | None = None,
                          stats_path: str = STATS_FILE) -> None:
    path = Path(stats_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    data.setdefault("updated_at", None)
    symbols = data.setdefault("symbols", {})
    bucket = symbols.setdefault(symbol, {
        "signals": 0,
        "approved": 0,
        "rejected": 0,
        "errors": 0,
        "allowed_with_tolerance": 0,
        "quiet_rejections": 0,
        "movement_classes": {},
        "reasons": {},
        "movement_ratio_samples": 0,
        "movement_ratio_total": 0.0,
        "avg_movement_ratio": None,
        "last_status": None,
        "last_reason": None,
        "last_seen": None,
    })

    bucket["signals"] += 1
    if status == "approved":
        bucket["approved"] += 1
    elif status == "rejected":
        bucket["rejected"] += 1
    else:
        bucket["errors"] += 1

    movement_class = (movement or {}).get("movement_class", "unknown")
    bucket["movement_classes"][movement_class] = bucket["movement_classes"].get(movement_class, 0) + 1

    movement_ratio = (movement or {}).get("movement_ratio")
    if movement_ratio is not None:
        bucket["movement_ratio_samples"] += 1
        bucket["movement_ratio_total"] += float(movement_ratio)
        bucket["avg_movement_ratio"] = round(
            bucket["movement_ratio_total"] / bucket["movement_ratio_samples"], 4
        )

    if (movement or {}).get("allowed_with_tolerance"):
        bucket["allowed_with_tolerance"] += 1

    if status == "rejected" and movement_class == "quiet":
        bucket["quiet_rejections"] += 1

    if reason:
        reason_key = _reason_key(reason)
        bucket["reasons"][reason_key] = bucket["reasons"].get(reason_key, 0) + 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bucket["last_status"] = status
    bucket["last_reason"] = reason
    bucket["last_seen"] = now
    data["updated_at"] = now

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
