"""Validate and record the mirrored documentation locales.

English under docs/en is canonical. The command validates the mirrored
locales, updates the English root projections, and records source/translation
hashes. It never overwrites a human-reviewed translation.


Usage::

    python scripts/sync_docs.py --check
    python scripts/sync_docs.py --write-manifest
    python scripts/sync_docs.py --check-links
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "docs" / "locales.json"
MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")


ROOT_PROJECTIONS = {
    "README.md": "docs/en/README.md",
    "AGENTS.md": "docs/en/project/agents.md",
    "CONTRIBUTING.md": "docs/en/project/contributing.md",
    "SECURITY.md": "docs/en/project/security.md",
}


def load_config() -> dict:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {CONFIG_PATH}: {exc}") from exc
    locales = value.get("locales")
    canonical = value.get("canonical_locale")
    if not isinstance(locales, list) or not locales or canonical not in locales:
        raise SystemExit("docs/locales.json must define canonical_locale in locales")
    return value


def digest(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def relative_markdown(locale_dir: Path) -> set[str]:
    return {
        path.relative_to(locale_dir).as_posix()
        for path in locale_dir.rglob("*.md")
        if path.is_file()
    }


def link_target(raw: str) -> str:
    target = raw.strip().strip("<>")
    # Markdown permits an optional title after the destination.
    if " " in target and not target.startswith(("http://", "https://")):
        target = target.split()[0]
    return unquote(target.split("#", 1)[0])


def check_links(locales: list[str], docs_root: Path) -> list[str]:
    errors: list[str] = []
    for locale in locales:
        locale_dir = docs_root / locale
        for document in locale_dir.rglob("*.md"):
            if not document.is_file():
                continue
            try:
                text = document.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"{document.relative_to(ROOT)} is not UTF-8: {exc}")
                continue
            for raw in MARKDOWN_LINK.findall(text):
                target = link_target(raw)
                if not target or target.startswith(("#", "/", "mailto:", "codex:")):
                    continue
                if "://" in target:
                    continue
                candidate = (document.parent / target).resolve()
                try:
                    candidate.relative_to(ROOT)
                except ValueError:
                    errors.append(f"{document.relative_to(ROOT)} -> {raw} escapes repository")
                    continue
                if not candidate.exists():
                    errors.append(f"{document.relative_to(ROOT)} -> {raw}")
    return errors


def manifest_path(config: dict) -> Path:
    return ROOT / config.get("manifest", "docs/translation-manifest.json")


def build_manifest(config: dict, source_paths: list[str]) -> dict:
    docs_root = ROOT / config.get("docs_root", "docs")
    canonical = config["canonical_locale"]
    locales = config["locales"]
    files: list[dict] = []
    for relative in source_paths:
        source = docs_root / canonical / relative
        translations = {}
        for locale in locales:
            if locale == canonical:
                continue
            translated = docs_root / locale / relative
            translations[locale] = {
                "path": translated.relative_to(ROOT).as_posix(),
                "sha256": digest(translated),
                "status": "current",
            }
        files.append(
            {
                "path": source.relative_to(ROOT).as_posix(),
                "source_sha256": digest(source),
                "translations": translations,
            }
        )
    return {
        "schema_version": 1,
        "canonical_locale": canonical,
        "locales": locales,
        "files": files,
    }


def projection_errors() -> list[str]:
    errors: list[str] = []
    for destination, source in ROOT_PROJECTIONS.items():
        target = ROOT / destination
        canonical = ROOT / source
        if not canonical.exists():
            errors.append(f"Missing projection source: {source}")
        elif not target.exists():
            errors.append(f"Missing root projection: {destination}")
        elif target.read_bytes() != canonical.read_bytes():
            errors.append(f"Root projection out of sync: {destination} <- {source}")
    return errors

def sync_projections() -> None:
    for destination, source in ROOT_PROJECTIONS.items():
        target = ROOT / destination
        canonical = ROOT / source
        target.write_bytes(canonical.read_bytes())
    print("Updated root English projections: " + ", ".join(ROOT_PROJECTIONS))

def parity_errors(config: dict) -> tuple[list[str], list[str], list[str]]:
    docs_root = ROOT / config.get("docs_root", "docs")
    canonical = config["canonical_locale"]
    canonical_dir = docs_root / canonical
    if not canonical_dir.is_dir():
        return [f"Missing canonical locale directory: {canonical_dir.relative_to(ROOT)}"], [], []

    source_paths = sorted(relative_markdown(canonical_dir))
    errors: list[str] = []
    for locale in config["locales"]:
        locale_dir = docs_root / locale
        if not locale_dir.is_dir():
            errors.append(f"Missing locale directory: {locale_dir.relative_to(ROOT)}")
            continue
        paths = relative_markdown(locale_dir)
        missing = sorted(set(source_paths) - paths)
        extra = sorted(paths - set(source_paths))
        errors.extend(f"{locale}: missing {relative}" for relative in missing)
        errors.extend(f"{locale}: extra {relative}" for relative in extra)
    return errors, source_paths, check_links(config["locales"], docs_root)


def check_manifest(config: dict, source_paths: list[str]) -> list[str]:
    path = manifest_path(config)
    if not path.exists():
        return [f"Missing translation manifest: {path.relative_to(ROOT)} (run --write-manifest)"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read {path.relative_to(ROOT)}: {exc}"]

    errors: list[str] = []
    if manifest.get("canonical_locale") != config["canonical_locale"]:
        errors.append("Manifest canonical_locale does not match docs/locales.json")
    if manifest.get("locales") != config["locales"]:
        errors.append("Manifest locales do not match docs/locales.json")
    entries = {entry.get("path"): entry for entry in manifest.get("files", [])}
    docs_root = ROOT / config.get("docs_root", "docs")
    canonical = config["canonical_locale"]
    expected_paths = {
        (docs_root / canonical / relative).relative_to(ROOT).as_posix()
        for relative in source_paths
    }
    if set(entries) != expected_paths:
        errors.append("Manifest file paths do not match canonical locale paths")

    for relative in sorted(expected_paths):
        entry = entries.get(relative)
        source = ROOT / relative
        if not entry:
            continue
        actual_source_hash = digest(source)
        if entry.get("source_sha256") != actual_source_hash:
            errors.append(f"stale translation source: {relative} (English changed)")
        for locale in config["locales"]:
            if locale == canonical:
                continue
            translation = docs_root / locale / (ROOT / relative).relative_to(docs_root / canonical)
            translated_entry = entry.get("translations", {}).get(locale)
            if not translated_entry:
                errors.append(f"{locale}: missing manifest entry for {relative}")
                continue
            actual_translation_hash = digest(translation)
            if translated_entry.get("sha256") != actual_translation_hash:
                errors.append(f"{locale}: manifest hash mismatch for {translation.relative_to(ROOT)}")
            if translated_entry.get("status") != "current":
                errors.append(f"{locale}: stale translation {translation.relative_to(ROOT)}")
    return errors


def write_manifest(config: dict, source_paths: list[str]) -> None:
    path = manifest_path(config)
    manifest = build_manifest(config, source_paths)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)} ({len(source_paths)} mirrored files).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="validate parity, manifest, staleness, and links")
    action.add_argument("--write-manifest", action="store_true", help="record current hashes after parity/link checks")
    action.add_argument("--check-links", action="store_true", help="validate local links only")
    args = parser.parse_args(argv)
    config = load_config()
    docs_root = ROOT / config.get("docs_root", "docs")
    if args.check_links:
        errors = check_links(config["locales"], docs_root)
        if errors:
            print("Broken local Markdown links:\n" + "\n".join(errors), file=sys.stderr)
            return 1
        print("Documentation links are valid.")
        return 0

    parity, source_paths, links = parity_errors(config)
    if parity or links:
        print("Documentation locale/link errors:", file=sys.stderr)
        for error in [*parity, *links]:
            print(f"- {error}", file=sys.stderr)
        return 1

    if args.write_manifest or not args.check:
        sync_projections()
        write_manifest(config, source_paths)
        return 0

    projections = projection_errors()
    if projections:
        print("Documentation projection errors:", file=sys.stderr)
        for error in projections:
            print(f"- {error}", file=sys.stderr)
        return 1

    errors = check_manifest(config, source_paths)
    if errors:
        print("Documentation manifest errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Documentation locales are in parity ({len(source_paths)} files); links and hashes are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
