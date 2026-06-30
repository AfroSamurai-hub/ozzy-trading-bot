#!/usr/bin/env python3
"""Print the live micro instance config and account view without placing trades."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "config" / "live-micro.env"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env_file(path: Path) -> None:
    """Load simple KEY=value lines into the current process."""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def main() -> None:
    """Show selected runtime config and Binance account state."""
    load_env_file(ENV_FILE)

    import config  # noqa: PLC0415
    from binance_connector import get_balance, get_execution_mode, get_open_positions, validate_binance_credentials  # noqa: PLC0415

    ok, reason = validate_binance_credentials()
    print(f"mode: {get_execution_mode()}")
    print(f"credentials: {'ok' if ok else 'bad'} ({reason})")
    print(f"symbols: {config.BINANCE_SYMBOLS}")
    print(f"risk_pct: {config.RISK_PCT}")
    print(f"max_positions: {config.MAX_POSITIONS}")
    print(f"max_positions_per_symbol: {config.MAX_POSITIONS_PER_SYMBOL}")
    print(f"grade_multipliers: {config.SETUP_GRADE_RISK_MULTIPLIERS}")
    print(f"db: {os.environ['HERMES_TRADE_DB']}")
    print(f"log: {os.environ['HERMES_LOG_FILE']}")
    if ok:
        print(f"balance: {get_balance()}")
        print(f"positions: {get_open_positions()}")


if __name__ == "__main__":
    main()
