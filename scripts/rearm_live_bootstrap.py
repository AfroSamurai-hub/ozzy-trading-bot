#!/usr/bin/env python3
"""Authorize one reduced-risk LIVE trade after a bootstrap safety pause."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_ENV = ROOT / "config" / "live-micro.env"
sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    """Load LIVE micro non-secret overrides before config-dependent imports."""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'").strip('"')


def main() -> int:
    """Run explicit audited LIVE bootstrap re-arm."""
    parser = argparse.ArgumentParser(description="Authorize one reduced-risk LIVE bootstrap trade")
    parser.add_argument("--reason", required=True, help="Operator reason stored with the authorization")
    args = parser.parse_args()
    _load_env_file(LIVE_ENV)

    import trade_db  # noqa: PLC0415
    from config import (  # noqa: PLC0415
        LIVE_REARM_AFTER_SAFETY_INCIDENT,
        REQUIRE_CLEAN_RECONCILE_FOR_REARM,
        RISK_PCT,
    )
    from live_reconcile import reconcile_live_state  # noqa: PLC0415
    from logger import plain_log  # noqa: PLC0415
    from risk_policy import (  # noqa: PLC0415
        bootstrap_daily_stop,
        rearm_authorization_check,
        resolve_trade_risk,
    )

    reconcile = reconcile_live_state(dry_run=True)
    risk = resolve_trade_risk(float(reconcile.get("equity_usd") or 0), RISK_PCT, RISK_PCT)
    daily_state = trade_db.get_live_daily_loss_state(risk.target_loss_at_sl_usd)
    stop = bootstrap_daily_stop(
        daily_state,
        target_loss_at_sl_usd=risk.target_loss_at_sl_usd,
        effective_risk_usd=risk.effective_risk_usd,
    )
    result = {"authorized": False, "reconciliation": reconcile, "daily_stop": stop}

    allowed, rejection = rearm_authorization_check(
        reconcile,
        stop,
        daily_state,
        enabled=LIVE_REARM_AFTER_SAFETY_INCIDENT,
        require_clean_reconcile=REQUIRE_CLEAN_RECONCILE_FOR_REARM,
    )
    if not allowed:
        result["reason"] = rejection
        plain_log("LIVE_REARM_REJECTED", {"reason": rejection, "daily_stop": stop, "reconciliation": reconcile})
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    payload = {"reconciliation": reconcile, "daily_stop_before_rearm": stop}
    inserted = trade_db.authorize_live_rearm(args.reason, payload=payload)
    daily_state = trade_db.get_live_daily_loss_state(risk.target_loss_at_sl_usd)
    result["daily_stop"] = bootstrap_daily_stop(
        daily_state,
        target_loss_at_sl_usd=risk.target_loss_at_sl_usd,
        effective_risk_usd=risk.effective_risk_usd,
    )
    result["authorized"] = inserted
    result["reason"] = args.reason if inserted else "re-arm authorization already recorded for today"
    plain_log(
        "LIVE_REARM_AUTHORIZED",
        {"authorized": inserted, "reason": result["reason"], "daily_stop": result["daily_stop"]},
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if inserted else 2


if __name__ == "__main__":
    raise SystemExit(main())
