#!/usr/bin/env python3
"""Explicitly download and verify the pinned CodeSearchNet subset.

No network request is made unless ``--download`` is supplied.  The default
target is isolated below ``benchmarks/external/codesearchnet`` and is ignored
by Git.  This helper never runs as part of ``benchmarks/run.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "benchmarks" / "external" / "codesearchnet-manifest.json"
DEFAULT_TARGET = ROOT / "benchmarks" / "external" / "codesearchnet"


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("dataset") != "CodeSearchNet" or not value.get("commit"):
        raise SystemExit("manifest must identify a pinned CodeSearchNet commit")
    return value


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def checked_target(path: Path) -> Path:
    target = path.resolve()
    allowed = (ROOT / "benchmarks" / "external").resolve()
    try:
        target.relative_to(allowed)
    except ValueError as exc:
        raise SystemExit(f"target must stay under {allowed}") from exc
    return target


def verify(manifest: dict[str, Any], target: Path) -> int:
    errors = []
    for artifact in manifest.get("artifacts", []):
        path = target / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
            continue
        actual = digest(path)
        if actual != artifact["sha256"]:
            errors.append(f"hash mismatch for {path.relative_to(ROOT)}: {actual}")
    if errors:
        print("CodeSearchNet verification failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"Verified {len(manifest.get('artifacts', []))} CodeSearchNet artifacts.")
    return 0


def download(manifest: dict[str, Any], target: Path, timeout: int) -> int:
    target.mkdir(parents=True, exist_ok=True)
    for artifact in manifest.get("artifacts", []):
        output = target / artifact["path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_name(output.name + ".part")
        request = urllib.request.Request(artifact["url"], headers={"User-Agent": "symbraid-benchmark/1"})
        print(f"Downloading {artifact['id']} -> {output.relative_to(ROOT)}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as stream:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    stream.write(block)
            actual = digest(partial)
            if actual != artifact["sha256"]:
                partial.unlink(missing_ok=True)
                raise SystemExit(f"hash mismatch for {artifact['id']}: {actual}")
            os.replace(partial, output)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    return verify(manifest, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--download", action="store_true", help="make the explicit network request")
    parser.add_argument("--check", action="store_true", help="verify already downloaded files")
    args = parser.parse_args(argv)
    if args.download and args.check:
        parser.error("--download and --check are mutually exclusive")
    manifest = load_manifest(args.manifest.resolve())
    target = checked_target(args.target)
    if args.download:
        return download(manifest, target, args.timeout)
    if args.check:
        return verify(manifest, target)
    print("CodeSearchNet is not downloaded. Re-run with --download to opt in.")
    for artifact in manifest.get("artifacts", []):
        print(f"- {artifact['id']}: {artifact['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

