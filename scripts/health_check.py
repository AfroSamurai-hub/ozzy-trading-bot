#!/usr/bin/env python3
"""Environment validation script for the AI trading system."""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:  # pragma: no cover - defensive
        pass


_load_env_file()

REQUIRED_PYTHON = (3, 13)
REQUIRED_PACKAGES = [
    "openai",
    "chromadb",
    "pandas",
    "numpy",
    "httpx",
    "streamlit",
]
REQUIRED_MODULES = [
    "agent.trader",
    "agent.safety",
    "agent.pattern_builder",
    "intelligence.rolling_window_db",
    "mcp.trading_server",
    "stream.engine",
    "stream.market_feed",
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str


def check_python_version() -> CheckResult:
    version = sys.version_info
    if version >= REQUIRED_PYTHON:
        return CheckResult(
            name="Python version",
            passed=True,
            message=f"Python {version.major}.{version.minor}.{version.micro}",
        )
    return CheckResult(
        name="Python version",
        passed=False,
        message=f"Requires {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+, found {version.major}.{version.minor}.{version.micro}",
    )


def check_packages() -> List[CheckResult]:
    results: List[CheckResult] = []
    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
            results.append(CheckResult(package, True, "Installed"))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(CheckResult(package, False, f"Missing or broken: {exc}"))
    return results


def check_modules() -> List[CheckResult]:
    results: List[CheckResult] = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
            results.append(CheckResult(module, True, "Imported"))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(CheckResult(module, False, f"Import failed: {exc}"))
    return results


def check_openai_api_key() -> CheckResult:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return CheckResult("OPENAI_API_KEY", False, "Environment variable not set")
    if not key.startswith("sk-") or len(key) < 20:
        return CheckResult("OPENAI_API_KEY", False, "Key format looks invalid")
    return CheckResult("OPENAI_API_KEY", True, "Set and looks valid")


def check_chromadb() -> CheckResult:
    try:
        module = importlib.import_module("intelligence.rolling_window_db")
        db_class = getattr(module, "RollingWindowPatternDB")
        db = db_class()
        count = db.count()
        return CheckResult("ChromaDB", True, f"Connected, patterns: {count}")
    except Exception as exc:  # pragma: no cover - defensive
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return CheckResult("ChromaDB", False, f"Connection failed: {details}")


def run_checks() -> List[CheckResult]:
    results: List[CheckResult] = []
    results.append(check_python_version())
    results.extend(check_packages())
    results.extend(check_modules())
    results.append(check_openai_api_key())
    results.append(check_chromadb())
    return results


def render_report(results: List[CheckResult]) -> None:
    print("ENVIRONMENT HEALTH REPORT")
    print("==========================")
    for result in results:
        icon = "✅" if result.passed else "❌"
        print(f"{icon} {result.name}: {result.message}")


def main() -> int:
    results = run_checks()
    render_report(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
