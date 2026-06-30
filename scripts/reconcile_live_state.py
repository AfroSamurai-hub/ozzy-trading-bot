#!/usr/bin/env python3
"""Print a read-only LIVE reconcile snapshot."""

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
    """Load the no-secret LIVE micro overrides before config imports."""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'").strip('"')


def main() -> int:
    """Run the read-only reconciliation command."""
    parser = argparse.ArgumentParser(description="Read-only LIVE DB/exchange reconciliation")
    parser.add_argument("--dry-run", action="store_true", help="Required explicit read-only marker")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("--dry-run is required; this command is read-only by design")
    _load_env_file(LIVE_ENV)
    from live_reconcile import reconcile_live_state  # noqa: PLC0415

    result = reconcile_live_state(dry_run=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
