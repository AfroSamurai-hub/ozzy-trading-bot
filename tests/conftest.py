"""
conftest.py — Global test isolation safety net
================================================

This module is imported automatically by both pytest and the unittest
runner before any test module executes.  It provides a last-ditch
guarantee that unit tests can NEVER write to production log files,
live-micro databases, or fire real Telegram messages — even if a
``HERMES_*`` environment variable pointing at a live path is present
in the shell environment when the test runner is invoked.

Individual test classes SHOULD still set up their own setUp/tearDown
patches (as test_binance_safety.py and test_audit_upgrades.py do), but
this module is the safety net underneath them.

Design rationale
----------------
The incident on 2026-05-25 demonstrated that running ``pytest`` inside a
shell that had inherited ``HERMES_LOG_FILE=/home/rick/ozzy-bot/live_micro/
trades_live.log`` (from a previous ``source config/live-micro.env``) caused
``plain_log`` calls inside tested code to write fake-client artefacts
(FakeClient BTCUSDT entries with order_id=1, price=75000) into the live
trade log, creating a false Fail-Close Death Loop alarm and complicating
incident diagnosis.

The fix: forcibly clear all live-path env vars at import time and
monkey-patch logger.LOG_FILE / trade_db.DB_PATH / telegram_client
before any test code can touch them.
"""

import os
import sys
import tempfile
import atexit
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1. Ensure the project root is always on sys.path regardless of invocation
#    directory so that all project modules resolve correctly.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# 2. Clear HERMES env vars that point at live paths BEFORE any module that
#    reads them at import time (logger.py, trade_db.py) is imported.
#    We replace them with explicit "test sentinel" values.
# ---------------------------------------------------------------------------
_TEST_TMPDIR = tempfile.mkdtemp(prefix="ozzybot_test_")

_SAFE_ENV_OVERRIDES = {
    # Never write to ANY real log file (esp. live_micro/trades_live.log).
    "HERMES_LOG_FILE":    str(Path(_TEST_TMPDIR) / "trades_test.log"),
    # Never touch the live or live-micro SQLite databases.
    "HERMES_TRADE_DB":    str(Path(_TEST_TMPDIR) / "trades_test.db"),
    # Keep testnet flag explicitly True — tests must not hit live Binance.
    "HERMES_BINANCE_TESTNET": "true",
    # Do not fire real Telegram in test process.
    "HERMES_TELEGRAM_TOKEN": "test_token_sentinel",
}

for _key, _val in _SAFE_ENV_OVERRIDES.items():
    os.environ[_key] = _val

# ---------------------------------------------------------------------------
# 3. Now import (or re-import) logger and trade_db so they pick up the
#    sanitised env, then patch their module-level path variables in-place.
#    Any test that imports these modules afterwards will see the safe paths.
# ---------------------------------------------------------------------------
import logger  # noqa: E402  (must come after env override)
import trade_db  # noqa: E402

logger.LOG_FILE = str(Path(_TEST_TMPDIR) / "trades_test.log")
trade_db.DB_PATH = Path(_TEST_TMPDIR) / "trades_test.db"

# ---------------------------------------------------------------------------
# 4. Patch telegram_client.send_message globally so tests never fire
#    real Telegram API calls.  We keep the patch live for the entire
#    test session.
# ---------------------------------------------------------------------------
import telegram_client  # noqa: E402

_telegram_patcher = patch.object(telegram_client, "send_message", return_value=None)
_telegram_patcher.start()

# Clean up patcher on interpreter exit (belt-and-suspenders).
atexit.register(_telegram_patcher.stop)

# ---------------------------------------------------------------------------
# 5. Pytest session-scoped fixtures (no-op if running under plain unittest).
# ---------------------------------------------------------------------------
try:
    import pytest  # noqa: E402

    @pytest.fixture(autouse=True, scope="session")
    def _enforce_test_isolation():
        """Session-wide fixture that asserts the safety overrides are active."""
        assert logger.LOG_FILE != "/home/rick/ozzy-bot/trades.log", (
            "logger.LOG_FILE still points at the default production path!"
        )
        assert "live_micro" not in str(logger.LOG_FILE), (
            "logger.LOG_FILE points at a live_micro path — isolation has failed!"
        )
        yield

except ImportError:
    # Running under plain `python -m unittest` — pytest fixtures are not needed.
    pass
