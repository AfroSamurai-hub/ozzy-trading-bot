"""Setup grading for controlled risk instead of binary accept/reject."""


_GRADE_ORDER = ("A", "B", "C", "D")
_GRADE_RISK = {"A": 1.0, "B": 0.5, "C": 0.0, "D": 0.0}


def _as_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _volume_ratio(live: dict) -> float:
    vol_avg = float(live.get("volume_avg20") or 0)
    if vol_avg <= 0:
        return 0.0
    return float(live.get("volume") or 0) / vol_avg


def _ema_distance_pct(entry: float, ema200: float | None) -> float | None:
    if not ema200:
        return None
    return ((float(entry) - float(ema200)) / float(ema200)) * 100.0


def _expected_trend(signal: str) -> str:
    return "long" if signal == "BUY" else "short"


def _downgrade_grade(grade: str, steps: int) -> str:
    try:
        current_index = _GRADE_ORDER.index(str(grade).upper())
    except ValueError:
        return "D"
    return _GRADE_ORDER[min(current_index + max(int(steps), 0), len(_GRADE_ORDER) - 1)]


def _chart_quality_adjustment(signal: str, live: dict, mode: str, base_grade: str, volume_ratio: float) -> dict:
    """Penalise obvious candle/context traps without creating another strategy layer."""
    normalized_signal = str(signal).upper()
    normalized_mode = str(mode or "")
    flags: list[str] = []
    confirmations: list[str] = []
    penalty = 0

    def add_flag(name: str, weight: int = 1) -> None:
        nonlocal penalty
        flags.append(name)
        penalty += weight

    range_position = _as_float(live.get("range_position_pct"))
    support_distance = _as_float(live.get("support_distance_pct"))
    resistance_distance = _as_float(live.get("resistance_distance_pct"))
    displacement = _as_float(live.get("displacement_score"))
    volume_expansion = _as_float(live.get("volume_expansion"))
    close_position = _as_float(live.get("close_position_pct"))
    actual_volume_ratio = volume_expansion if volume_expansion is not None else volume_ratio
    wick_rejection = str(live.get("wick_rejection") or "none")
    liquidity_sweep = str(live.get("liquidity_sweep") or "none")
    retest_quality = str(live.get("retest_quality") or "none")
    market_structure = str(live.get("market_structure") or "unknown")
    prior_structure_bias = str(live.get("prior_structure_bias") or "unknown")

    if actual_volume_ratio < 1.0:
        add_flag(f"sub_1x_volume:{round(actual_volume_ratio, 2)}", weight=0)
    else:
        confirmations.append(f"volume_expansion:{round(actual_volume_ratio, 2)}")

    if displacement is not None:
        if displacement < 0.75:
            add_flag(f"weak_displacement:{round(displacement, 2)}")
        elif displacement >= 1.5:
            confirmations.append(f"strong_displacement:{round(displacement, 2)}")

    if normalized_signal == "SELL":
        if support_distance is not None and abs(support_distance) <= 0.35:
            add_flag(f"sell_near_support:{round(support_distance, 3)}")
        if range_position is not None:
            if range_position <= 25.0:
                add_flag(f"sell_low_in_range:{round(range_position, 1)}", weight=2)
            elif normalized_mode in {"momentum", "trend_continuation"} and range_position <= 45.0:
                add_flag(f"sell_mid_low_range:{round(range_position, 1)}")
        if close_position is not None:
            if close_position >= 60.0:
                add_flag(f"sell_weak_close_position:{round(close_position, 1)}")
            elif close_position <= 35.0:
                confirmations.append(f"bearish_close_position:{round(close_position, 1)}")
        if retest_quality == "support_retest_hold":
            add_flag("sell_into_support_retest_hold", weight=2)
        if wick_rejection == "bullish_rejection":
            add_flag("sell_into_bullish_rejection", weight=2)
        elif wick_rejection == "bearish_rejection":
            confirmations.append("bearish_rejection_wick")
        if liquidity_sweep == "bullish_sweep":
            add_flag("sell_after_bullish_sweep", weight=2)
        if market_structure.startswith("bullish"):
            add_flag(f"sell_against_structure:{market_structure}", weight=2)
        elif market_structure == "bearish_choch" and prior_structure_bias == "bullish":
            add_flag("sell_choch_from_prior_bullish_bias")
    else:
        if resistance_distance is not None and abs(resistance_distance) <= 0.35:
            add_flag(f"buy_near_resistance:{round(resistance_distance, 3)}")
        if range_position is not None:
            if range_position >= 75.0:
                add_flag(f"buy_high_in_range:{round(range_position, 1)}", weight=2)
            elif normalized_mode in {"momentum", "trend_continuation"} and range_position >= 55.0:
                add_flag(f"buy_mid_high_range:{round(range_position, 1)}")
        if close_position is not None:
            if close_position <= 40.0:
                add_flag(f"buy_weak_close_position:{round(close_position, 1)}")
            elif close_position >= 65.0:
                confirmations.append(f"bullish_close_position:{round(close_position, 1)}")
        if retest_quality == "resistance_retest_hold":
            add_flag("buy_into_resistance_retest_hold", weight=2)
        if wick_rejection == "bearish_rejection":
            add_flag("buy_into_bearish_rejection", weight=2)
        elif wick_rejection == "bullish_rejection":
            confirmations.append("bullish_rejection_wick")
        if liquidity_sweep == "bearish_sweep":
            add_flag("buy_after_bearish_sweep", weight=2)
        if market_structure.startswith("bearish"):
            add_flag(f"buy_against_structure:{market_structure}", weight=2)
        elif market_structure == "bullish_choch" and prior_structure_bias == "bearish":
            add_flag("buy_choch_from_prior_bearish_bias")

    downgrade_steps = 0
    if penalty >= 4 or (penalty >= 3 and str(base_grade).upper() != "A"):
        downgrade_steps = 3
    elif penalty >= 3:
        downgrade_steps = 2
    elif penalty >= 1:
        downgrade_steps = 1

    adjusted_grade = _downgrade_grade(base_grade, downgrade_steps)
    chart_score = max(0, min(100, 100 - penalty * 15 + min(len(confirmations), 3) * 5))
    return {
        "grade": adjusted_grade,
        "risk_multiplier": _GRADE_RISK[adjusted_grade],
        "chart_quality_score": chart_score,
        "chart_quality_penalty": penalty,
        "chart_quality_flags": flags,
        "chart_quality_confirmations": confirmations,
    }


def score_crypto_setup(signal: str, entry: float, live: dict, mode: str, cfg: dict) -> dict:  # noqa: PLR0911, PLR0912
    """Return grade A/B/C/D plus reasons and risk multiplier for a crypto setup."""
    if not live:
        return {"grade": "D", "risk_multiplier": 0.0, "reasons": ["live data unavailable"]}

    trend = live.get("supertrend_direction")
    expected = _expected_trend(signal)
    if trend != expected:
        return {
            "grade": "D",
            "risk_multiplier": 0.0,
            "reasons": [f"trend conflict — live trend is {trend}, expected {expected}"],
        }

    rsi = live.get("rsi")
    ema200 = live.get("ema200")
    volume_ratio = _volume_ratio(live)
    ema_distance = _ema_distance_pct(entry, ema200)
    if rsi is None or ema_distance is None:
        return {"grade": "D", "risk_multiplier": 0.0, "reasons": ["required indicator unavailable"]}

    abs_ema_distance = abs(ema_distance)
    reasons = []

    if mode == "pullback":
        a_ema = cfg["pullback_max_ema_distance_pct"]
        b_ema = cfg.get("grade_b_pullback_max_ema_distance_pct", a_ema + 2.0)
        buy_max = cfg["pullback_rsi_buy_max"]
        sell_min = cfg["pullback_rsi_sell_min"]
        b_buy_max = cfg.get("grade_b_pullback_rsi_buy_max", buy_max + 5.0)
        b_sell_min = cfg.get("grade_b_pullback_rsi_sell_min", sell_min - 5.0)
        if abs_ema_distance > b_ema:
            return {
                "grade": "D",
                "risk_multiplier": 0.0,
                "reasons": [f"pullback too far from EMA200 — {round(abs_ema_distance, 2)}% > {b_ema}%"],
                "volume_ratio": volume_ratio,
                "ema_distance_pct": ema_distance,
            }
        if abs_ema_distance > a_ema:
            reasons.append(f"pullback EMA stretch — {round(abs_ema_distance, 2)}% > {a_ema}%")
        if signal == "BUY" and rsi > b_buy_max:
            return {"grade": "D", "risk_multiplier": 0.0, "reasons": [f"pullback rsi too hot — {rsi} > {b_buy_max}"]}
        if signal == "SELL" and rsi < b_sell_min:
            return {"grade": "D", "risk_multiplier": 0.0, "reasons": [f"pullback rsi too cold — {rsi} < {b_sell_min}"]}
        if signal == "BUY" and rsi > buy_max:
            reasons.append(f"pullback RSI warm — {rsi} > {buy_max}")
        if signal == "SELL" and rsi < sell_min:
            reasons.append(f"pullback RSI cold — {rsi} < {sell_min}")
    elif mode == "trend_continuation":
        a_ema = cfg["trend_continuation_max_ema_distance_pct"]
        b_ema = cfg.get("grade_b_trend_continuation_max_ema_distance_pct", a_ema)
        min_ema = cfg.get("trend_continuation_min_ema_distance_pct", 0.0)
        buy_max = cfg.get("trend_continuation_rsi_buy_max", cfg.get("momentum_rsi_buy_max", 80.0))
        sell_min = cfg.get("trend_continuation_rsi_sell_min", cfg.get("momentum_rsi_sell_min", 20.0))
        if abs_ema_distance < min_ema:
            return {
                "grade": "D",
                "risk_multiplier": 0.0,
                "reasons": [f"trend continuation not extended enough — {round(abs_ema_distance, 2)}% < {min_ema}%"],
                "volume_ratio": volume_ratio,
                "ema_distance_pct": ema_distance,
            }
        if abs_ema_distance > b_ema:
            return {
                "grade": "D",
                "risk_multiplier": 0.0,
                "reasons": [f"trend continuation too extended — {round(abs_ema_distance, 2)}% > {b_ema}%"],
                "volume_ratio": volume_ratio,
                "ema_distance_pct": ema_distance,
            }
        if abs_ema_distance > a_ema:
            reasons.append(f"trend continuation stretch — {round(abs_ema_distance, 2)}% > {a_ema}%")
        if signal == "BUY" and rsi > buy_max:
            return {"grade": "D", "risk_multiplier": 0.0, "reasons": [f"trend continuation rsi too hot — {rsi} > {buy_max}"]}
        if signal == "SELL" and rsi < sell_min:
            return {"grade": "D", "risk_multiplier": 0.0, "reasons": [f"trend continuation rsi too cold — {rsi} < {sell_min}"]}
    else:
        a_ema = cfg["momentum_max_ema_distance_pct"]
        b_ema = cfg.get("grade_b_momentum_max_ema_distance_pct", a_ema + 1.5)
        if abs_ema_distance > b_ema:
            return {
                "grade": "D",
                "risk_multiplier": 0.0,
                "reasons": [f"momentum too extended — {round(abs_ema_distance, 2)}% > {b_ema}%"],
                "volume_ratio": volume_ratio,
                "ema_distance_pct": ema_distance,
            }
        if abs_ema_distance > a_ema:
            reasons.append(f"momentum EMA stretch — {round(abs_ema_distance, 2)}% > {a_ema}%")

    a_volume = cfg.get("grade_a_min_volume_ratio", 1.10)
    b_volume = cfg.get("grade_b_min_volume_ratio", 0.75)
    c_volume = cfg.get("grade_c_min_volume_ratio", 0.50)
    if volume_ratio >= a_volume and not reasons:
        grade = "A"
    elif volume_ratio >= b_volume:
        grade = "B"
        if volume_ratio < a_volume:
            reasons.append(f"volume below A threshold — {round(volume_ratio, 2)} < {a_volume}")
    elif volume_ratio >= c_volume:
        grade = "C"
        reasons.append(f"shadow volume — {round(volume_ratio, 2)} < {b_volume}")
    else:
        return {
            "grade": "D",
            "risk_multiplier": 0.0,
            "reasons": [f"volume too weak — {round(volume_ratio, 2)} < {c_volume}"],
            "volume_ratio": volume_ratio,
            "ema_distance_pct": ema_distance,
        }

    chart_quality = _chart_quality_adjustment(signal, live, mode, grade, volume_ratio)
    grade = chart_quality["grade"]
    if chart_quality["chart_quality_flags"]:
        reasons.extend([f"chart quality penalty — {flag}" for flag in chart_quality["chart_quality_flags"]])
    if grade == "D":
        reasons.append("chart quality failed — stacked trap evidence")

    return {
        "grade": grade,
        "risk_multiplier": chart_quality["risk_multiplier"],
        "reasons": reasons or [f"accepted as grade {grade}"],
        "volume_ratio": volume_ratio,
        "ema_distance_pct": ema_distance,
        "chart_quality_score": chart_quality["chart_quality_score"],
        "chart_quality_penalty": chart_quality["chart_quality_penalty"],
        "chart_quality_flags": chart_quality["chart_quality_flags"],
        "chart_quality_confirmations": chart_quality["chart_quality_confirmations"],
    }
