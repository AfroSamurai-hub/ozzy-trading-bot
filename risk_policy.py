"""Risk sizing helpers for percentage and micro-bootstrap modes."""

from __future__ import annotations

from dataclasses import dataclass

from config import (
    CONSECUTIVE_LOSS_HALT,
    DAILY_LOSS_PCT,
    LIVE_MAX_DAILY_FULL_LOSSES,
    LIVE_MAX_DAILY_LOSS_USD,
    LIVE_REARM_AFTER_SAFETY_INCIDENT,
    LIVE_RISK_ESTIMATED_FEE_USD,
    LIVE_RISK_SLIPPAGE_BUFFER_USD,
    MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT,
    MAX_TRADES_PER_DAY,
    MICRO_BOOTSTRAP_EQUITY_CEILING_USD,
    MICRO_BOOTSTRAP_MAX_POSITIONS,
    MICRO_BOOTSTRAP_MODE,
    MICRO_BOOTSTRAP_RISK_USD,
    REARM_RISK_MULTIPLIER,
)


@dataclass(frozen=True)
class RiskDecision:
    """Final risk decision used by sizing and execution."""

    risk_dollars: float
    effective_risk_pct: float
    mode: str
    bootstrap_active: bool
    base_risk_dollars: float
    adjusted_multiplier: float
    equity: float
    target_loss_at_sl_usd: float = 0.0
    estimated_fee_usd: float = 0.0
    slippage_buffer_usd: float = 0.0
    effective_risk_usd: float = 0.0
    warning: str | None = None


def is_micro_bootstrap_active(equity: float | None) -> bool:
    """Return True while the account is below the bootstrap ceiling."""
    if equity is None:
        return False
    return bool(MICRO_BOOTSTRAP_MODE and equity > 0 and equity <= MICRO_BOOTSTRAP_EQUITY_CEILING_USD)


def effective_max_positions(configured_max_positions: int, equity: float | None) -> int:
    """Limit live exposure during micro-account bootstrap mode.

    The bootstrap cap is intentionally configurable per runtime instance so the
    tiny live-micro account can scale opportunity count without changing the
    per-trade risk model.
    """
    if is_micro_bootstrap_active(equity):
        bootstrap_cap = max(1, int(MICRO_BOOTSTRAP_MAX_POSITIONS))
        return min(bootstrap_cap, int(configured_max_positions))
    return int(configured_max_positions)


def resolve_trade_risk(equity: float, base_risk_pct: float, adjusted_risk_pct: float) -> RiskDecision:
    """Resolve final dollar risk and effective risk percent.

    Normal mode remains percentage based. Bootstrap mode raises the base A-setup
    risk to MICRO_BOOTSTRAP_RISK_USD while preserving reductions from grade,
    calendar, and context multipliers. Upside multipliers are capped at the
    bootstrap target so a micro account does not exceed the intended dollar risk.
    """
    equity_f = float(equity)
    base_pct = float(base_risk_pct)
    adjusted_pct = float(adjusted_risk_pct)
    if equity_f <= 0:
        return RiskDecision(0.0, 0.0, "invalid_equity", False, 0.0, 0.0, equity_f)

    base_risk_dollars = equity_f * base_pct
    normal_risk_dollars = equity_f * adjusted_pct
    multiplier = adjusted_pct / base_pct if base_pct > 0 else 1.0
    multiplier = max(0.0, multiplier)

    if not is_micro_bootstrap_active(equity_f):
        risk_dollars = max(0.0, normal_risk_dollars)
        return RiskDecision(
            risk_dollars=risk_dollars,
            effective_risk_pct=risk_dollars / equity_f,
            mode="percentage",
            bootstrap_active=False,
            base_risk_dollars=base_risk_dollars,
            adjusted_multiplier=multiplier,
            equity=equity_f,
            target_loss_at_sl_usd=risk_dollars,
            effective_risk_usd=risk_dollars,
        )

    bootstrap_base_risk = max(base_risk_dollars, float(MICRO_BOOTSTRAP_RISK_USD))
    risk_dollars = bootstrap_base_risk * multiplier
    risk_dollars = min(risk_dollars, bootstrap_base_risk)
    risk_dollars = max(0.0, risk_dollars)
    fee = max(0.0, float(LIVE_RISK_ESTIMATED_FEE_USD))
    slippage = max(0.0, float(LIVE_RISK_SLIPPAGE_BUFFER_USD))
    pct = risk_dollars / equity_f

    return RiskDecision(
        risk_dollars=risk_dollars,
        effective_risk_pct=pct,
        mode="micro_bootstrap",
        bootstrap_active=True,
        base_risk_dollars=bootstrap_base_risk,
        adjusted_multiplier=multiplier,
        equity=equity_f,
        target_loss_at_sl_usd=risk_dollars,
        estimated_fee_usd=fee,
        slippage_buffer_usd=slippage,
        effective_risk_usd=risk_dollars + fee + slippage,
        warning=bootstrap_warning(equity_f, risk_dollars),
    )


def bootstrap_warning(equity: float, target_loss_at_sl_usd: float) -> str | None:
    """Return a blunt warning for intentional high-risk live micro bootstrap."""
    equity_f = float(equity or 0)
    target = float(target_loss_at_sl_usd or 0)
    if equity_f <= 0 or target <= 0:
        return None
    pct = target / equity_f * 100
    return (
        f"HIGH-RISK BOOTSTRAP: target loss at SL ${target:.2f} is about "
        f"{pct:.1f}% of equity. This is not normal percentage risk management."
    )


def bootstrap_daily_stop(
    daily_state: dict,
    target_loss_at_sl_usd: float,
    effective_risk_usd: float | None = None,
    equity: float | None = None,
) -> dict:
    """Return the unified daily stop and safety re-arm state.

    The daily loss cap is computed as a percentage of current equity when
    HERMES_LIVE_MAX_DAILY_LOSS_USD is not set explicitly. This makes the safety
    rail scale with the account and applies identically to testnet and live.
    """
    loss_used = max(0.0, float(daily_state.get("daily_realized_loss_usd", 0.0) or 0.0))
    strategy_full_losses = int(daily_state.get("daily_strategy_full_losses", 0) or 0)
    safety_incidents = int(daily_state.get("daily_safety_incidents", 0) or 0)
    rearm_open = int(daily_state.get("rearm_open_authorizations", 0) or 0)
    rearm_used = int(daily_state.get("rearm_used_count", 0) or 0)
    max_full_losses = max(0, int(LIVE_MAX_DAILY_FULL_LOSSES))
    effective = max(0.0, float(effective_risk_usd or target_loss_at_sl_usd or 0.0))

    # Unified daily loss budget: explicit USD cap wins, otherwise equity percentage.
    equity_f = float(equity or 0.0)
    if LIVE_MAX_DAILY_LOSS_USD and float(LIVE_MAX_DAILY_LOSS_USD) > 0:
        max_loss = max(0.0, float(LIVE_MAX_DAILY_LOSS_USD))
    elif equity_f > 0:
        max_loss = max(0.0, equity_f * float(DAILY_LOSS_PCT))
    else:
        max_loss = 0.0

    remaining = max(0.0, max_loss - loss_used)

    consecutive_losses = int(daily_state.get("daily_consecutive_losses", 0) or 0)
    trades_count = int(daily_state.get("daily_trades_count", 0) or 0)

    block_reason = None
    theoretical_block_reason = None
    pause_reason = None
    bypassed_theoretical_block = False
    safety_incident_risk_multiplier = 1.0
    safety_incident_risk_adjust_active = False

    # 1. Realized loss block
    if max_loss > 0 and loss_used >= max_loss:
        block_reason = f"Daily loss ${loss_used:.2f} reached cap ${max_loss:.2f}"

    # 2. Unified frequency / consecutive-loss guards
    if block_reason is None and consecutive_losses >= int(CONSECUTIVE_LOSS_HALT):
        block_reason = f"Consecutive losses {consecutive_losses} reached halt threshold {CONSECUTIVE_LOSS_HALT}"
    if block_reason is None and trades_count >= int(MAX_TRADES_PER_DAY):
        block_reason = f"Daily trades count {trades_count} reached cap {MAX_TRADES_PER_DAY}"

    # 3. Safety-incident risk reduction
    if safety_incidents > 0:
        safety_incident_risk_multiplier = min(1.0, max(0.0, float(REARM_RISK_MULTIPLIER)))
        safety_incident_risk_adjust_active = safety_incident_risk_multiplier < 1.0

    rearm_available = bool(
        LIVE_REARM_AFTER_SAFETY_INCIDENT
        and safety_incidents
        and rearm_open
        and block_reason is None
    )

    # 4. Theoretical daily budget check
    if block_reason is None and not rearm_available:
        if max_loss > 0 and effective > remaining:
            block_reason = (
                f"Remaining daily loss budget ${remaining:.2f} "
                f"is below next trade effective risk ${effective:.2f}"
            )

    live_paused = False
    reason = block_reason or pause_reason or theoretical_block_reason

    return {
        "model": "unified_daily_stop",
        "target_loss_at_sl_usd": float(target_loss_at_sl_usd or 0.0),
        "effective_risk_usd": effective,
        "live_max_daily_loss_usd": max_loss,
        "live_max_daily_loss_pct": DAILY_LOSS_PCT if equity_f > 0 else None,
        "live_max_daily_full_losses": max_full_losses,
        "daily_realized_loss_usd": loss_used,
        "daily_strategy_full_losses": strategy_full_losses,
        "daily_safety_incidents": safety_incidents,
        "live_paused_for_safety": live_paused,
        "live_blocked_for_day": block_reason is not None,
        "rearm_available": rearm_available,
        "rearm_used_count": rearm_used,
        "rearm_risk_multiplier": float(REARM_RISK_MULTIPLIER),
        "safety_incident_risk_multiplier": safety_incident_risk_multiplier,
        "safety_incident_risk_adjust_active": safety_incident_risk_adjust_active,
        "max_rearmed_trades_after_safety_incident": int(MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT),
        "remaining_daily_loss_budget_usd": remaining,
        "live_trading_blocked_for_day": block_reason is not None or live_paused,
        "pause_reason": pause_reason,
        "block_reason": block_reason,
        "theoretical_blocked": theoretical_block_reason is not None,
        "theoretical_block_reason": theoretical_block_reason,
        "reason": reason,
        "bypassed_theoretical_block": bypassed_theoretical_block,
    }


def apply_rearm_risk_multiplier(adjusted_risk_pct: float, daily_stop: dict) -> tuple[float, float]:
    """Apply one-shot safety re-arm risk reduction only when authorization is armed."""
    multiplier = float(REARM_RISK_MULTIPLIER) if daily_stop.get("rearm_available") else 1.0
    return float(adjusted_risk_pct) * multiplier, multiplier


def rearm_authorization_check(
    reconciliation: dict,
    daily_stop: dict,
    daily_state: dict,
    *,
    enabled: bool = LIVE_REARM_AFTER_SAFETY_INCIDENT,
    require_clean_reconcile: bool = True,
) -> tuple[bool, str | None]:
    """Validate whether an operator may persist a one-shot LIVE re-arm."""
    reason = None
    if not enabled:
        reason = "LIVE safety re-arm is disabled by config"
    elif require_clean_reconcile and not reconciliation.get("healthy"):
        reason = "LIVE reconcile is not clean"
    elif reconciliation.get("positions"):
        reason = "LIVE has an open exchange position"
    elif daily_stop.get("live_blocked_for_day"):
        reason = daily_stop.get("block_reason") or "LIVE is blocked for the day"
    elif not daily_state.get("daily_safety_incidents"):
        reason = "no LIVE bootstrap safety incident requires re-arm"
    elif daily_stop.get("rearm_available"):
        reason = "LIVE bootstrap already has an unused re-arm authorization"
    return reason is None, reason
