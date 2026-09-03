"""Create checksums, an SPDX inventory, and build provenance for CI artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def version() -> str:
    text = (ROOT / "components" / "symbraid" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "unknown")


def artifact_files(dist: Path) -> list[Path]:
    return sorted(path for path in dist.rglob("*") if path.is_file() and path.name != "SHA256SUMS")


def write_sbom(dist: Path, files: list[Path], stamp: str, commit: str) -> Path:
    output = dist / "symbraid.sbom.spdx.json"
    entries = []
    for path in files:
        entries.append(
            {
                "SPDXID": "SPDXRef-File-" + hashlib.sha256(path.relative_to(dist).as_posix().encode()).hexdigest()[:16],
                "fileName": path.relative_to(dist).as_posix(),
                "checksums": [{"algorithm": "SHA256", "checksumValue": sha256(path)}],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
    payload = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "symbraid-release-artifacts",
        "documentNamespace": f"https://spdx.org/spdxdocs/symbraid-{commit}",
        "creationInfo": {
            "created": stamp,
            "creators": ["Tool: scripts/release_metadata.py"],
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-symbraid",
                "name": "symbraid",
                "versionInfo": version(),
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": "MIT",
                "licenseDeclared": "MIT",
            }
        ],
        "files": entries,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package-symbraid",
            }
        ],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_provenance(dist: Path, files: list[Path], stamp: str, commit: str) -> Path:
    output = dist / "symbraid.provenance.json"
    payload = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": path.relative_to(dist).as_posix(), "digest": {"sha256": sha256(path)}} for path in files],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/actions/runner",
                "externalParameters": {
                    "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
                    "ref": os.environ.get("GITHUB_REF", "local"),
                },
                "resolvedDependencies": [{"uri": "git+https://github.com/wCotito/symbraid", "digest": {"sha1": commit}}],
            },
            "runDetails": {
                "builder": {"id": os.environ.get("GITHUB_WORKFLOW_REF", "local")},
                "metadata": {"invocationId": os.environ.get("GITHUB_RUN_ID", "local"), "startedOn": stamp},
            },
        },
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    dist = args.dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    commit = revision()
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        stamp = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        stamp = "1970-01-01T00:00:00Z"
    files = artifact_files(dist)
    write_sbom(dist, files, stamp, commit)
    files = artifact_files(dist)
    write_provenance(dist, files, stamp, commit)
    files = artifact_files(dist)
    checksums = dist / "SHA256SUMS"
    checksums.write_text("".join(f"{sha256(path)}  {path.relative_to(dist).as_posix()}\n" for path in files), encoding="utf-8")
    print(f"release metadata written for {len(files)} artifacts on {platform.system()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
