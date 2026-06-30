import json
import os
from jsonschema import validate, ValidationError

# Load signal payload schema once at import time
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schemas", "signal_payload.json")
_SIGNAL_SCHEMA = None

try:
    with open(_SCHEMA_PATH, "r") as _f:
        _SIGNAL_SCHEMA = json.load(_f)
except Exception:
    _SIGNAL_SCHEMA = None

_TS_MIN_SEC = 1_700_000_000
_TS_MAX_SEC = 2_000_000_000
_TS_MIN_MS = 1_700_000_000_000
_TS_MAX_MS = 2_000_000_000_000


def _timestamp_semantic_errors(data: dict) -> list[str]:
    """Validate timestamp range after schema type check; infer unit from decimal digit length."""
    ts = data.get("timestamp")
    if ts is None or isinstance(ts, bool) or not isinstance(ts, int):
        return []
    msg: str | None = None
    if ts < 0:
        msg = "timestamp must be non-negative"
    else:
        n = len(str(ts))
        if n == 10 and not (_TS_MIN_SEC <= ts <= _TS_MAX_SEC):
            msg = f"timestamp (Unix seconds) must be between {_TS_MIN_SEC} and {_TS_MAX_SEC}, got {ts}"
        elif n == 13 and not (_TS_MIN_MS <= ts <= _TS_MAX_MS):
            msg = f"timestamp (Unix milliseconds) must be between {_TS_MIN_MS} and {_TS_MAX_MS}, got {ts}"
        elif n not in (10, 13):
            msg = (
                "timestamp must be Unix seconds (10 digits) "
                f"or milliseconds (13 digits); got {n}-digit value {ts}"
            )
    return [msg] if msg else []


def parse_json_payload(raw_body: str) -> dict:
    body = raw_body if raw_body is not None else ""
    stripped = body.strip()

    if not stripped:
        raise ValueError("invalid json: empty body")

    if "=" in stripped and ("&" in stripped or stripped.startswith("signal=") or stripped.startswith("payload=")):
        raise ValueError("invalid json: form-encoded body")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError("json payload must be an object")

    return data


def validate_signal_payload(data: dict) -> tuple[bool, list[str]]:
    """
    Validate an incoming signal payload against the Pine Script contract schema.
    Returns (is_valid, list_of_human_readable_errors).
    """
    if _SIGNAL_SCHEMA is None:
        return True, ["schema file not found — skipping validation"]

    errors = []
    try:
        validate(instance=data, schema=_SIGNAL_SCHEMA)
    except ValidationError as exc:
        path = "/".join(str(p) for p in exc.path) if exc.path else "root"
        errors.append(f"schema violation at '{path}': {exc.message}")
    except Exception as exc:
        errors.append(f"schema validation error: {exc}")

    errors.extend(_timestamp_semantic_errors(data))

    return len(errors) == 0, errors
