"""Reject secrets, caches, indexes, and developer-local paths in archives."""

from __future__ import annotations

import argparse
import math
import re
import tarfile
import zipfile
from pathlib import Path


FORBIDDEN_PATH = re.compile(
    r"(?:^|/)(?:\.env(?:\..*)?|\.venv|node_modules|__pycache__|results|model-cache|lancedb|qdrant)(?:/|$)|(?:^|/)(?:credentials|private-key)\.(?:json|pem|key)$",
    re.IGNORECASE,
)
LOCAL_PATH = re.compile(
    r"(?:[A-Z]:" + r"\\Users\\[^\\\r\n]+|/home" + r"/" + r"[^/\s]+|/Users" + r"/"
    + r"[^/\s]+)"
)

# These patterns deliberately require the shape and minimum length of a real
# credential. Documentation normally contains references such as TOKEN_REF,
# angle-bracket placeholders, or provider-specific environment variables;
# those are handled by credential_assignment below and are not findings.
TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "bearer token",
        re.compile(
            r"\bAuthorization\s*:\s*Bearer\s+(?![<$\{])"
            r"[A-Za-z0-9][A-Za-z0-9._~+/=-]{19,}",
            re.IGNORECASE,
        ),
    ),
    (
        "JWT",
        re.compile(
            r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{7,}"
            r"\.[A-Za-z0-9_-]{7,}(?![A-Za-z0-9_-])"
        ),
    ),
    (
        "npm token",
        re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{30,}(?![A-Za-z0-9])"),
    ),
    (
        "GitLab token",
        re.compile(
            r"(?<![A-Za-z0-9])(?:glpat|glrt|gldt|glft|glcbt)-[A-Za-z0-9_-]{20,}"
            r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "GitHub token",
        re.compile(
            r"(?<![A-Za-z0-9])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"
            r"(?![A-Za-z0-9])|github_pat_[A-Za-z0-9_]{20,}(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "AWS access key",
        re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"),
    ),
)

# Keep the old public constant for callers that imported the scanner directly.
SECRET = re.compile(
    "|".join(f"(?:{pattern.pattern})" for _, pattern in TOKEN_PATTERNS),
    re.IGNORECASE,
)

CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?ix)(?<![A-Za-z0-9_.-])"
    r"(?P<key>"
    r"qdrant[_-]?(?:api[_-]?)?key|"
    r"api[_-]?key|apikey|"
    r"password|passwd|passphrase|"
    r"secret(?:[_-]?(?:key|token|value))?|"
    r"access[_-]?token|auth(?:entication)?[_-]?token|"
    r"npm[_-]?token|gitlab[_-]?(?:token|password)"
    r")"
    r"(?![A-Za-z0-9_-])\s*(?:=|:)\s*"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\]]+)",
)
PRIVATE_KEY_PEM = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----",
    re.IGNORECASE,
)

PLACEHOLDER_VALUE = re.compile(
    r"^(?:"
    r"$|null|none|false|true|undefined|"
    r"changeme|change[-_ ]?me|replace[-_ ]?me|"
    r"not[-_ ]?(?:a[-_ ]?)?secret|"
    r"(?:your|the)[-_ ]?(?:api[-_ ]?key|token|password|secret)|"
    r"(?:example|sample|dummy|fake|fixture|test)(?:[-_ ]|$)"
    r")$",
    re.IGNORECASE,
)


def shannon_entropy(value: str) -> float:
    """Return the character entropy used to reject prose/placeholders."""

    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def looks_like_credential_value(raw_value: str) -> bool:
    """Recognize assigned secret material without flagging docs references."""

    value = raw_value.strip().rstrip(",;")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    if not value or len(value) < 12 or PLACEHOLDER_VALUE.fullmatch(value):
        return False
    lowered = value.casefold()
    if (
        value.startswith(("$", "<", "[", "{"))
        or lowered.startswith(("env:", "keyring:", "os.getenv", "getenv("))
        or "$" + "{" in value
        or re.match(r"^[A-Za-z_][A-Za-z0-9_.-]*\s*\(", value)
        or "{{" in value
        or "#" + "{" in value
        or any(
            word in lowered.split()
            for word in ("environment", "provided", "configured")
        )
    ):
        return False
    # Uppercase identifiers with underscores are overwhelmingly env-var
    # references (QDRANT_API_KEY, SYMBRAID_MCP_TOKEN), not serialized values.
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", value) and "_" in value:
        return False
    # A credential assignment should be a compact value, not an explanatory
    # sentence. Entropy also avoids false positives such as password or
    # the-secret-value in prose while retaining random API keys/passwords.
    if any(character.isspace() for character in value):
        return False
    return shannon_entropy(value) >= 2.5 and len(set(value)) >= 5


def find_secret_kinds(text: str) -> list[str]:
    """Return non-sensitive categories of credential-like material in text."""

    findings = [label for label, pattern in TOKEN_PATTERNS if pattern.search(text)]
    if any(
        looks_like_credential_value(match.group("value"))
        for match in CREDENTIAL_ASSIGNMENT.finditer(text)
    ):
        findings.append("credential assignment")
    if PRIVATE_KEY_PEM.search(text):
        findings.append("private-key PEM")
    return findings


def check_member(name: str, data: bytes, violations: list[str]) -> None:
    normalized = name.replace("\\", "/")
    if FORBIDDEN_PATH.search(normalized):
        violations.append(f"forbidden archive path: {name}")
    if len(data) <= 2 * 1024 * 1024:
        text = data.decode("utf-8", errors="ignore")
        if LOCAL_PATH.search(text):
            violations.append(f"developer-local path in: {name}")
        findings = find_secret_kinds(text)
        if findings:
            # Never include the matched value or the assignment key in the
            # diagnostic; release logs must not become a second leak.
            violations.append(
                f"secret-like literal in: {name} ({', '.join(findings)})"
            )


def scan_archive(path: Path, violations: list[str]) -> None:
    if tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                stream = archive.extractfile(member) if member.isfile() else None
                check_member(member.name, stream.read() if stream else b"", violations)
        return
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                check_member(member.filename, archive.read(member), violations)
        return
    raise SystemExit(f"unsupported archive type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, nargs="+")
    args = parser.parse_args()
    violations: list[str] = []
    for archive in args.archive:
        scan_archive(archive, violations)
    if violations:
        raise SystemExit("\n".join(violations))
    print("archive scan OK: " + ", ".join(str(path) for path in args.archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
