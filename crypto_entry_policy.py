# v2026-04-25 — Modular crypto entry classification for pullback + momentum

from setup_score import score_crypto_setup as grade_crypto_setup


def _safe_ratio(volume: float, volume_avg20: float) -> float:
    if not volume_avg20 or volume_avg20 <= 0:
        return 0.0
    return volume / volume_avg20


def _ema_distance_pct(entry: float, ema200: float):
    if ema200 in (None, 0):
        return None
    return ((entry - ema200) / ema200) * 100.0


def _expected_trend(signal: str) -> str:
    return "long" if signal == "BUY" else "short"


def pullback_entry_ok(signal: str, entry: float, live: dict, cfg: dict):
    reasons = []
    details = {}

    trend = live.get("supertrend_direction")
    expected = _expected_trend(signal)
    ema200 = live.get("ema200")
    rsi = live.get("rsi")
    volume = live.get("volume", 0.0)
    volume_avg20 = live.get("volume_avg20", 0.0)
    volume_ratio = _safe_ratio(volume, volume_avg20)
    ema_distance_pct = _ema_distance_pct(entry, ema200)

    details.update({
        "trend_ok": trend == expected,
        "volume_ratio": volume_ratio,
        "ema_distance_pct": ema_distance_pct,
        "trend_direction": trend,
    })

    if trend != expected:
        reasons.append(f"trend conflict — live trend is {trend}, expected {expected}")

    if ema_distance_pct is None:
        reasons.append("ema unavailable")
    elif abs(ema_distance_pct) > cfg["pullback_max_ema_distance_pct"]:
        reasons.append(
            f"pullback too far from EMA200 — {round(abs(ema_distance_pct), 2)}% vs max {cfg['pullback_max_ema_distance_pct']}%"
        )

    if rsi is None:
        reasons.append("rsi unavailable")
    elif signal == "BUY" and rsi > cfg["pullback_rsi_buy_max"]:
        reasons.append(f"pullback rsi too hot — {rsi} > {cfg['pullback_rsi_buy_max']}")
    elif signal == "SELL" and rsi < cfg["pullback_rsi_sell_min"]:
        reasons.append(f"pullback rsi too cold — {rsi} < {cfg['pullback_rsi_sell_min']}")

    if volume_avg20 > 0 and volume_ratio < cfg["grade_b_min_volume_ratio"]:
        reasons.append(
            f"pullback volume too weak — {round(volume_ratio, 2)} < {cfg['grade_b_min_volume_ratio']}"
        )

    return len(reasons) == 0, reasons, details


def momentum_breakout_ok(signal: str, entry: float, live: dict, cfg: dict):
    reasons = []
    details = {}

    trend = live.get("supertrend_direction")
    expected = _expected_trend(signal)
    ema200 = live.get("ema200")
    rsi = live.get("rsi")
    volume = live.get("volume", 0.0)
    volume_avg20 = live.get("volume_avg20", 0.0)
    volume_ratio = _safe_ratio(volume, volume_avg20)
    ema_distance_pct = _ema_distance_pct(entry, ema200)

    details.update({
        "trend_ok": trend == expected,
        "volume_ratio": volume_ratio,
        "ema_distance_pct": ema_distance_pct,
        "trend_direction": trend,
    })

    if trend != expected:
        reasons.append(f"trend conflict — live trend is {trend}, expected {expected}")

    if ema_distance_pct is None:
        reasons.append("ema unavailable")
    elif abs(ema_distance_pct) > cfg["momentum_max_ema_distance_pct"]:
        reasons.append(
            f"momentum too extended — {round(abs(ema_distance_pct), 2)}% vs max {cfg['momentum_max_ema_distance_pct']}%"
        )

    if rsi is None:
        reasons.append("rsi unavailable")
    elif signal == "BUY" and rsi > cfg["momentum_rsi_buy_max"]:
        reasons.append(f"momentum rsi too hot — {rsi} > {cfg['momentum_rsi_buy_max']}")
    elif signal == "SELL" and rsi < cfg["momentum_rsi_sell_min"]:
        reasons.append(f"momentum rsi too cold — {rsi} < {cfg['momentum_rsi_sell_min']}")

    if volume_avg20 > 0 and volume_ratio < cfg["momentum_min_volume_ratio"]:
        reasons.append(
            f"momentum volume too weak — {round(volume_ratio, 2)} < {cfg['momentum_min_volume_ratio']}"
        )

    return len(reasons) == 0, reasons, details


def trend_continuation_ok(signal: str, entry: float, live: dict, cfg: dict):
    reasons = []
    details = {}

    trend = live.get("supertrend_direction")
    expected = _expected_trend(signal)
    ema200 = live.get("ema200")
    rsi = live.get("rsi")
    volume = live.get("volume", 0.0)
    volume_avg20 = live.get("volume_avg20", 0.0)
    volume_ratio = _safe_ratio(volume, volume_avg20)
    ema_distance_pct = _ema_distance_pct(entry, ema200)
    abs_ema_distance = abs(ema_distance_pct) if ema_distance_pct is not None else None

    details.update({
        "trend_ok": trend == expected,
        "volume_ratio": volume_ratio,
        "ema_distance_pct": ema_distance_pct,
        "trend_direction": trend,
    })

    if trend != expected:
        reasons.append(f"trend conflict — live trend is {trend}, expected {expected}")

    if ema_distance_pct is None:
        reasons.append("ema unavailable")
    else:
        min_distance = cfg.get("trend_continuation_min_ema_distance_pct", 0.0)
        max_distance = cfg["trend_continuation_max_ema_distance_pct"]
        if abs_ema_distance < min_distance:
            reasons.append(
                f"trend continuation not extended enough — {round(abs_ema_distance, 2)}% vs min {min_distance}%"
            )
        elif abs_ema_distance > max_distance:
            reasons.append(
                f"trend continuation too extended — {round(abs_ema_distance, 2)}% vs max {max_distance}%"
            )

    if rsi is None:
        reasons.append("rsi unavailable")
    elif signal == "BUY" and rsi > cfg["trend_continuation_rsi_buy_max"]:
        reasons.append(f"trend continuation rsi too hot — {rsi} > {cfg['trend_continuation_rsi_buy_max']}")
    elif signal == "SELL" and rsi < cfg["trend_continuation_rsi_sell_min"]:
        reasons.append(f"trend continuation rsi too cold — {rsi} < {cfg['trend_continuation_rsi_sell_min']}")

    if volume_avg20 > 0 and volume_ratio < cfg["trend_continuation_min_volume_ratio"]:
        reasons.append(
            f"trend continuation volume too weak — {round(volume_ratio, 2)} < {cfg['trend_continuation_min_volume_ratio']}"
        )

    return len(reasons) == 0, reasons, details


def score_crypto_setup(result: dict, cfg: dict) -> str:
    volume_ratio = result.get("volume_ratio", 0.0)
    if volume_ratio >= cfg["grade_a_min_volume_ratio"]:
        return "A"
    if volume_ratio >= cfg["grade_b_min_volume_ratio"]:
        return "B"
    return "reject"


def classify_crypto_entry(signal: str, entry: float, live: dict, cfg: dict, requested_strategy: str = "unknown") -> dict:
    if not live:
        return {
            "mode": "reject",
            "grade": "reject",
            "reasons": ["live data unavailable"],
            "ema_distance_pct": None,
            "volume_ratio": 0.0,
            "trend_ok": False,
            "requested_strategy": requested_strategy,
        }

    modes_to_try = []
    if requested_strategy == "trend_continuation":
        modes_to_try = ["trend_continuation"]
    elif requested_strategy == "momentum":
        modes_to_try = ["momentum"]
    elif requested_strategy == "pullback":
        modes_to_try = ["pullback", "momentum"] if cfg.get("momentum_enabled", True) else ["pullback"]
    else:
        modes_to_try = ["pullback", "momentum"] if cfg.get("momentum_enabled", True) else ["pullback"]

    rejections = []
    for mode in modes_to_try:
        if mode == "pullback":
            ok, reasons, details = pullback_entry_ok(signal, entry, live, cfg)
        elif mode == "trend_continuation":
            ok, reasons, details = trend_continuation_ok(signal, entry, live, cfg)
        else:
            ok, reasons, details = momentum_breakout_ok(signal, entry, live, cfg)

        score = grade_crypto_setup(signal, entry, live, mode, cfg)
        if ok or score["grade"] == "C":
            if score["grade"] != "D":
                return {
                    "mode": mode,
                    "grade": score["grade"],
                    "risk_multiplier": score["risk_multiplier"],
                    "score_reasons": score["reasons"],
                    "reasons": score["reasons"],
                    "ema_distance_pct": score.get("ema_distance_pct"),
                    "volume_ratio": score.get("volume_ratio", 0.0),
                    "trend_ok": details.get("trend_ok", False),
                    "requested_strategy": requested_strategy,
                }
            reasons = reasons + score["reasons"]

        rejections.extend(reasons)

    return {
        "mode": "reject",
        "grade": "reject",
        "reasons": rejections or ["no valid crypto entry mode matched"],
        "ema_distance_pct": _ema_distance_pct(entry, live.get("ema200")),
        "volume_ratio": _safe_ratio(live.get("volume", 0.0), live.get("volume_avg20", 0.0)),
        "trend_ok": live.get("supertrend_direction") == _expected_trend(signal),
        "requested_strategy": requested_strategy,
    }
