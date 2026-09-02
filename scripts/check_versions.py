"""Check that the public package, extension, and plugin share a release version."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)")


def python_version() -> str:
    text = (ROOT / "components" / "symbraid" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    if not match:
        raise ValueError("components/symbraid/pyproject.toml has no project version")
    return match.group(1)


def json_version(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8")).get("version")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path.as_posix()} has no version")
    return value


def main() -> int:
    paths = {
        "python": ROOT / "components" / "symbraid" / "pyproject.toml",
        "vscode": ROOT / "extensions" / "vscode-symbraid" / "package.json",
        "codex": ROOT / "plugins" / "symbraid-search" / ".codex-plugin" / "plugin.json",
    }
    versions = {
        "python": python_version(),
        "vscode": json_version(paths["vscode"]),
        "codex": json_version(paths["codex"]),
    }
    bases = {name: VERSION_RE.match(value).group(1) if VERSION_RE.match(value) else value for name, value in versions.items()}
    if len(set(bases.values())) != 1:
        raise SystemExit(f"version mismatch: {versions}")
    mcp = json.loads((ROOT / "plugins" / "symbraid-search" / ".mcp.json").read_text(encoding="utf-8"))
    if "io.github.symbraid-project/symbraid" not in mcp.get("mcpServers", {}):
        raise SystemExit("MCP manifest is missing io.github.symbraid-project/symbraid")
    print(f"version consistency OK: {bases['python']} (plugin={versions['codex']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"version check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
