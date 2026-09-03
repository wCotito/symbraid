from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any, TextIO


REDACTED = "[REDACTED]"

_SAFE_STATUS_KEYS = {
    "api_key_configured",
    "qdrant_api_key_configured",
}
_SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "secret_ref",
    "token",
}
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s/@]+(@)")
_AUTHORIZATION_SCHEME = re.compile(
    r"""(?ix)
    (\bauthorization\b["']?\s*[:=]\s*["']?)
    (?:basic|bearer)\s+[^\s,;}"']+
    """
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;\"']+")
_LABELED_SECRET = re.compile(
    r"""(?ix)
    (\b
      (?:api[-_ ]?key|x[-_ ]?api[-_ ]?key|authorization|
         (?:access|refresh)[-_ ]?token|client[-_ ]?secret|
         credential|password|private[-_ ]?key|secret|token)
      \b["']?\s*[:=]\s*
    )
    (?:"[^"]*"|'[^']*'|[^\s,;}]+)
    """
)


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SAFE_STATUS_KEYS or normalized.endswith("_configured"):
        return False
    compact = normalized.replace("_", "")
    for part in _SENSITIVE_KEY_PARTS:
        compact_part = part.replace("_", "")
        if (
            normalized == part
            or f"_{part}_" in f"_{normalized}_"
            or compact.endswith(compact_part)
        ):
            return True
    return False


def redact_text(value: str) -> str:
    """Remove common credential representations from an error message."""
    value = _URL_CREDENTIALS.sub(r"\1" + REDACTED + r"\2", value)
    value = _AUTHORIZATION_SCHEME.sub(r"\1" + REDACTED, value)
    value = _BEARER.sub(r"\1" + REDACTED, value)
    return _LABELED_SECRET.sub(r"\1" + REDACTED, value)


def redact_for_output(value: Any) -> Any:
    """Return a recursively key-redacted, JSON-compatible copy of public output."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _sensitive_key(key) else redact_for_output(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_for_output(item) for item in value]
    return value


def error_payload(error: BaseException) -> dict[str, str]:
    return {"status": "error", "error": redact_text(str(error))}


def write_json(value: Any, *, stream: TextIO | None = None, indent: int | None = None) -> None:
    destination = stream or sys.stdout
    destination.write(json.dumps(redact_for_output(value), ensure_ascii=False, indent=indent) + "\n")
