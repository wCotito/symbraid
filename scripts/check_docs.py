"""Check local Markdown links without requiring network access."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def main() -> None:
    broken: list[str] = []
    for document in ROOT.rglob("*.md"):
        if "node_modules" in document.parts:
            continue
        for raw_target in LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "codex:")):
                continue
            candidate = (document.parent / unquote(target)).resolve()
            if not candidate.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {raw_target}")
    if broken:
        raise SystemExit("Broken local Markdown links:\n" + "\n".join(broken))
    print("Documentation links are valid.")


if __name__ == "__main__":
    main()
