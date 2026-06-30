#!/usr/bin/env python3
"""Local CSV journal for approved OzzyBot trades."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

JOURNAL_PATH = Path(os.path.expanduser("~/.hermes/trading-journal/Hermes Trading Journal.csv"))
FIELDS = [
    "Date",
    "Pair",
    "Signal",
    "Entry",
    "SL",
    "TP",
    "Lot",
    "ATR",
    "RR",
    "Outcome",
    "P&L",
    "Notes",
]


def _ensure_journal() -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not JOURNAL_PATH.exists() or JOURNAL_PATH.stat().st_size == 0:
        with JOURNAL_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def _row_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("Date", "")),
        str(row.get("Pair", "")),
        str(row.get("Signal", "")),
        str(row.get("Entry", "")),
        str(row.get("SL", "")),
        str(row.get("TP", "")),
        str(row.get("Lot", "")),
        str(row.get("RR", "")),
    )


def append_approved_trade(trade: Mapping[str, Any]) -> bool:
    """Append an APPROVED trade to the local CSV journal.

    Returns True when a new row was added, False if it was already present.
    """
    _ensure_journal()

    row = {
        "Date": trade.get("ts") or trade.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Pair": trade.get("symbol", ""),
        "Signal": trade.get("signal", ""),
        "Entry": trade.get("entry", ""),
        "SL": trade.get("sl", ""),
        "TP": trade.get("tp", ""),
        "Lot": trade.get("lot", ""),
        "ATR": trade.get("atr", ""),
        "RR": trade.get("rr", ""),
        "Outcome": "PENDING",
        "P&L": "",
        "Notes": trade.get("notes", "APPROVED trade logged automatically by Hermes"),
    }

    existing = set()
    if JOURNAL_PATH.exists():
        with JOURNAL_PATH.open("r", newline="") as f:
            reader = csv.DictReader(f)
            for existing_row in reader:
                existing.add(_row_key(existing_row))

    if _row_key(row) in existing:
        return False

    with JOURNAL_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)
    return True
