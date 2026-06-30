"""Advisory live evidence for grade health and symbol heat."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import trade_db
from config import (
    DATA_DRIVEN_LIVE_GATING,
    DATA_GATING_DB,
    GRADE_HEALTH_LOOKBACK_TRADES,
    GRADE_HEALTH_MIN_AVG_PNL,
    GRADE_HEALTH_MIN_TRADES,
    GRADE_HEALTH_RED_MAX_AVG_PNL,
    LANE_BLOCK_AVG_R_FLOOR,
    LANE_BLOCK_MIN_TRADES,
    LANE_BLOCK_RECOVERY_AVG_R,
    LANE_BLOCK_RECOVERY_SHADOW_SAMPLES,
    LANE_BLOCK_TOTAL_R_FLOOR,
    LIVE_GATE_REDUCED_RISK_MULTIPLIER,
    LIVE_MIN_OPPORTUNITY_ENABLED,
    LIVE_MIN_OPPORTUNITY_HOURS,
    MIN_CLEAN_SAMPLES_FOR_STRATEGY_REDUCE,
    SYMBOL_HEAT_LOOKBACK_TRADES,
    SYMBOL_HEAT_MIN_AVG_PNL,
    SYMBOL_HEAT_MIN_TRADES,
    SYMBOL_HEAT_RED_MAX_AVG_PNL,
)


@dataclass(frozen=True)
class GateDecision:
    """Decision returned by a data-driven live gate."""

    allowed: bool
    reason: str
    gate_name: str
    details: dict = field(default_factory=dict)
    verdict: str = "allow"
    risk_multiplier: float = 1.0


def _allow(
    gate_name: str,
    reason: str,
    details: dict | None = None,
    *,
    verdict: str = "allow",
    risk_multiplier: float = 1.0,
) -> GateDecision:
    return GateDecision(True, reason, gate_name, details or {}, verdict, risk_multiplier)


def _recent_stats(
    *,
    setup_grade: str | None = None,
    symbol: str | None = None,
    direction: str | None = None,
    strategy: str | None = None,
    execution_state: str | None = None,
    include_shadow: bool = True,
    limit: int = 20,
) -> dict:
    if not DATA_GATING_DB:
        return trade_db.get_recent_closed_trade_stats(
            setup_grade=setup_grade,
            symbol=symbol,
            direction=direction,
            strategy=strategy,
            execution_state=execution_state,
            include_shadow=include_shadow,
            include_dirty=False,
            limit=limit,
        )

    clauses = [
        "pnl IS NOT NULL",
        "exit_price IS NOT NULL",
        "COALESCE(source, 'live') != 'migrated'",
        "COALESCE(accounting_status, 'clean') IN ('clean', 'corrected')",
    ]
    params: list = []
    if setup_grade:
        clauses.append("setup_grade = ?")
        params.append(setup_grade)
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    if strategy:
        clauses.append("strategy = ?")
        params.append(strategy)
    if execution_state:
        clauses.append("execution_state = ?")
        params.append(execution_state)
    elif not include_shadow:
        clauses.append("COALESCE(execution_state, 'confirmed') != 'shadow'")
    else:
        clauses.append("COALESCE(execution_state, 'closed') NOT IN ('shadow', 'fail_closed')")
    params.append(int(limit))

    db_path = Path(DATA_GATING_DB)
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT pnl, risk_dollars, r_multiple
            FROM trades
            WHERE {" AND ".join(clauses)}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    pnls = [float(r["pnl"]) for r in rows if r["pnl"] is not None]
    r_values = []
    for row in rows:
        if row["r_multiple"] is not None:
            r_values.append(float(row["r_multiple"]))
        elif row["pnl"] is not None and row["risk_dollars"] not in (None, 0):
            risk = abs(float(row["risk_dollars"]))
            if risk > 0:
                r_values.append(float(row["pnl"]) / risk)
    sample_size = len(pnls)
    wins = sum(1 for pnl in pnls if pnl > 0)
    losses = sum(1 for pnl in pnls if pnl < 0)
    total_pnl = sum(pnls)
    total_r = sum(r_values)
    return {
        "sample_size": sample_size,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / sample_size if sample_size else None,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / sample_size if sample_size else None,
        "total_r": total_r,
        "avg_r": total_r / len(r_values) if r_values else None,
        "r_sample_size": len(r_values),
        "source_db": str(db_path),
    }


def _lane_state(stats: dict, min_trades: int, green_min_avg_pnl: float, red_max_avg_pnl: float) -> str:
    """Return green/yellow/red/insufficient from recent lane stats."""
    if stats["sample_size"] < min_trades:
        return "insufficient"
    avg_pnl = stats.get("avg_pnl")
    if avg_pnl is None:
        return "insufficient"
    if avg_pnl <= red_max_avg_pnl:
        return "red"
    if avg_pnl >= green_min_avg_pnl:
        return "green"
    return "yellow"


def _live_opportunity_state() -> dict:
    """Return whether live has been idle long enough to keep yellow lanes available."""
    if not LIVE_MIN_OPPORTUNITY_ENABLED:
        return {"enabled": False, "active": False, "hours": LIVE_MIN_OPPORTUNITY_HOURS}
    age_hours = trade_db.get_latest_trade_age_hours()
    active = age_hours is None or age_hours >= LIVE_MIN_OPPORTUNITY_HOURS
    return {
        "enabled": True,
        "active": active,
        "hours": LIVE_MIN_OPPORTUNITY_HOURS,
        "latest_trade_age_hours": age_hours,
    }


def evaluate_grade_health(setup_grade: str | None) -> GateDecision:
    """Return advisory grade evidence that may reduce risk but never rejects LIVE."""
    grade = setup_grade or "A"
    if not DATA_DRIVEN_LIVE_GATING:
        return _allow("grade_health", "data-driven gating disabled", {"setup_grade": grade})

    stats = _recent_stats(
        setup_grade=grade,
        limit=GRADE_HEALTH_LOOKBACK_TRADES,
    )
    lane_state = _lane_state(
        stats,
        GRADE_HEALTH_MIN_TRADES,
        GRADE_HEALTH_MIN_AVG_PNL,
        GRADE_HEALTH_RED_MAX_AVG_PNL,
    )
    details = {"setup_grade": grade, "lane_state": lane_state, **stats}
    if lane_state == "red":
        verdict = "allow_reduced" if stats["sample_size"] >= MIN_CLEAN_SAMPLES_FOR_STRATEGY_REDUCE else "watch"
        multiplier = LIVE_GATE_REDUCED_RISK_MULTIPLIER if verdict == "allow_reduced" else 1.0
        return _allow(
            "grade_health",
            (
                f"Grade {grade} red lane has {stats['sample_size']} samples: "
                f"{verdict}; evidence is advisory"
            ),
            details,
            verdict=verdict,
            risk_multiplier=multiplier,
        )
    if lane_state == "yellow":
        return _allow("grade_health", f"Grade {grade} yellow lane: allowed at controlled risk", details)
    if lane_state == "insufficient":
        return _allow("grade_health", "insufficient grade sample", details)
    return _allow("grade_health", f"Grade {grade} green lane", details)


def evaluate_symbol_heat(symbol: str, direction: str, setup_grade: str | None = None) -> GateDecision:
    """Return advisory symbol evidence that may reduce risk but never rejects LIVE."""
    grade = setup_grade or "A"
    if not DATA_DRIVEN_LIVE_GATING:
        return _allow("symbol_heat", "data-driven gating disabled", {"symbol": symbol, "direction": direction})

    stats = _recent_stats(
        setup_grade=grade,
        symbol=symbol,
        direction=direction,
        limit=SYMBOL_HEAT_LOOKBACK_TRADES,
    )
    lane_state = _lane_state(
        stats,
        SYMBOL_HEAT_MIN_TRADES,
        SYMBOL_HEAT_MIN_AVG_PNL,
        SYMBOL_HEAT_RED_MAX_AVG_PNL,
    )
    details = {"symbol": symbol, "direction": direction, "setup_grade": grade, "lane_state": lane_state, **stats}
    if lane_state == "red":
        verdict = "allow_reduced" if stats["sample_size"] >= MIN_CLEAN_SAMPLES_FOR_STRATEGY_REDUCE else "watch"
        multiplier = LIVE_GATE_REDUCED_RISK_MULTIPLIER if verdict == "allow_reduced" else 1.0
        return _allow(
            "symbol_heat",
            (
                f"{symbol} {direction} grade {grade} red lane has {stats['sample_size']} "
                f"samples: {verdict}; evidence is advisory"
            ),
            details,
            verdict=verdict,
            risk_multiplier=multiplier,
        )
    if lane_state == "yellow":
        return _allow("symbol_heat", f"{symbol} {direction} grade {grade} yellow lane", details)
    if lane_state == "insufficient":
        return _allow("symbol_heat", "insufficient symbol heat sample", details)
    return _allow("symbol_heat", f"{symbol} {direction} grade {grade} green lane", details)


def _block(
    gate_name: str,
    reason: str,
    details: dict | None = None,
    *,
    verdict: str = "blocked",
) -> GateDecision:
    return GateDecision(False, reason, gate_name, details or {}, verdict, 0.0)


def _lane_key(symbol: str, direction: str, setup_grade: str | None, strategy: str | None) -> str:
    return "|".join([
        (symbol or "unknown").upper(),
        (direction or "unknown").upper(),
        (setup_grade or "A").upper(),
        (strategy or "unknown").lower(),
    ])


def evaluate_precise_lane_block(
    symbol: str,
    direction: str,
    setup_grade: str | None,
    strategy: str | None = "unknown",
) -> GateDecision:
    """Block mature negative-expectancy lanes using normalized R, with shadow recovery."""
    grade = setup_grade or "A"
    lane_strategy = strategy or "unknown"
    lane_key = _lane_key(symbol, direction, grade, lane_strategy)
    stats = _recent_stats(
        setup_grade=grade,
        symbol=symbol,
        direction=direction,
        strategy=lane_strategy,
        include_shadow=False,
        limit=max(LANE_BLOCK_MIN_TRADES, 1),
    )
    recovery_stats = _recent_stats(
        setup_grade=grade,
        symbol=symbol,
        direction=direction,
        strategy=lane_strategy,
        execution_state="shadow",
        limit=max(LANE_BLOCK_RECOVERY_SHADOW_SAMPLES, 1),
    )
    details = {
        "lane_key": lane_key,
        "symbol": symbol,
        "direction": direction,
        "setup_grade": grade,
        "strategy": lane_strategy,
        "stats": stats,
        "recovery_stats": recovery_stats,
        "block_thresholds": {
            "min_trades": LANE_BLOCK_MIN_TRADES,
            "avg_r_floor": LANE_BLOCK_AVG_R_FLOOR,
            "total_r_floor": LANE_BLOCK_TOTAL_R_FLOOR,
            "recovery_shadow_samples": LANE_BLOCK_RECOVERY_SHADOW_SAMPLES,
            "recovery_avg_r": LANE_BLOCK_RECOVERY_AVG_R,
        },
    }
    if stats["r_sample_size"] < LANE_BLOCK_MIN_TRADES:
        return _allow("precise_lane_block", "insufficient normalized lane sample", details, verdict="allow")

    avg_r = stats.get("avg_r")
    total_r = stats.get("total_r")
    should_block = (
        avg_r is not None
        and total_r is not None
        and (avg_r <= LANE_BLOCK_AVG_R_FLOOR or total_r <= LANE_BLOCK_TOTAL_R_FLOOR)
    )
    if not should_block:
        return _allow("precise_lane_block", f"Lane {lane_key} normalized expectancy is live-eligible", details)

    recovered = (
        recovery_stats["r_sample_size"] >= LANE_BLOCK_RECOVERY_SHADOW_SAMPLES
        and recovery_stats.get("avg_r") is not None
        and recovery_stats["avg_r"] >= LANE_BLOCK_RECOVERY_AVG_R
    )
    if recovered:
        return _allow(
            "precise_lane_block",
            f"Lane {lane_key} recovered in shadow; live allowed at reduced risk",
            details,
            verdict="recovery_allow_reduced",
            risk_multiplier=LIVE_GATE_REDUCED_RISK_MULTIPLIER,
        )

    return _block(
        "precise_lane_block",
        (
            f"Strategy lane {lane_key} BLOCKED: normalized expectancy "
            f"avgR={avg_r:.2f}, totalR={total_r:.2f}; routed to shadow"
        ),
        details,
    )


def evaluate_live_setup(symbol: str, direction: str, setup_grade: str | None, strategy: str = "unknown") -> GateDecision:
    """Evaluate grade and symbol heat gates for a candidate live setup."""
    opportunity = _live_opportunity_state()
    lane_decision = evaluate_precise_lane_block(symbol, direction, setup_grade, strategy)
    if not lane_decision.allowed:
        return lane_decision
    grade_decision = evaluate_grade_health(setup_grade)
    symbol_decision = evaluate_symbol_heat(symbol, direction, setup_grade)
    risk_multiplier = min(
        grade_decision.risk_multiplier,
        symbol_decision.risk_multiplier,
        lane_decision.risk_multiplier,
    )
    verdict = "allow_reduced" if risk_multiplier < 1.0 else (
        "watch" if "watch" in {grade_decision.verdict, symbol_decision.verdict, lane_decision.verdict} else "allow"
    )
    return _allow(
        "data_driven_live_gate",
        f"grade and symbol heat allowed ({verdict})",
        {
            "precise_lane": lane_decision.details,
            "grade_health": grade_decision.details,
            "symbol_heat": symbol_decision.details,
            "live_opportunity": opportunity,
        },
        verdict=verdict,
        risk_multiplier=risk_multiplier,
    )
