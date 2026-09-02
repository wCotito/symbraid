"""Backward-compatible entrypoint for the canonical documentation check."""

from __future__ import annotations

from sync_docs import main


if __name__ == "__main__":
    raise SystemExit(main(["--check"]))
