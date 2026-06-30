#!/usr/bin/env python3
"""Generate a read-only Gemini Hermes evidence brief."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hermes_advisor  # noqa: E402
import hermes_evidence  # noqa: E402


def main() -> int:
    """Build the Hermes evidence pack and optionally ask Gemini to analyze it."""
    parser = argparse.ArgumentParser(description="Read-only Hermes Gemini evidence brief")
    parser.add_argument("--question", help="Operator question for the Hermes evidence brief")
    parser.add_argument("--backfill", action="store_true", help="Label due Ozzy Memory outcome windows first")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the bounded evidence prompt without calling Gemini",
    )
    parser.add_argument("--json-evidence", action="store_true", help="Print only the Evidence Pack v2 JSON")
    args = parser.parse_args()

    evidence_pack = hermes_evidence.build_evidence_pack(args.question, memory_backfill=args.backfill)
    if args.json_evidence:
        print(json.dumps(evidence_pack, indent=2, sort_keys=True, default=str))
        return 0
    if args.dry_run:
        print(hermes_advisor.build_prompt(evidence_pack))
        return 0

    try:
        brief = hermes_advisor.generate_brief(evidence_pack)
    except hermes_advisor.AdvisorUnavailableError as exc:
        print(f"Hermes Advisor unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(brief, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
