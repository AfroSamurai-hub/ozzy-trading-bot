#!/usr/bin/env python3
"""Classify closed trade rows as clean, corrected, dirty, or unchecked."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _corrected_trade_ids_from_log(path: Path) -> set[int]:
    corrected: set[int] = set()
    if not path.exists():
        return corrected
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "TRADE_ACCOUNTING_MISMATCH_CORRECTED" not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            trade_id = event.get("trade_id")
            if trade_id is not None:
                corrected.add(int(trade_id))
    return corrected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite DB path. Defaults to trade_db.DB_PATH.")
    parser.add_argument("--log", default=str(ROOT / "trades.log"), help="Structured trades.log path.")
    parser.add_argument("--limit", type=int, default=None, help="Limit most recent rows classified.")
    args = parser.parse_args()

    if args.db:
        os.environ["HERMES_TRADE_DB"] = args.db

    import trade_db

    corrected = _corrected_trade_ids_from_log(Path(args.log))
    summary = trade_db.classify_closed_trade_accounting(corrected_trade_ids=corrected, limit=args.limit)
    print(json.dumps(summary, sort_keys=True))
    return 1 if summary.get("dirty") else 0


if __name__ == "__main__":
    raise SystemExit(main())
