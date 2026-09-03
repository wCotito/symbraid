from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    config: Path
    data: Path
    cache: Path
    state: Path

    @property
    def registry(self) -> Path:
        return self.config / "config.json"

    @property
    def locks(self) -> Path:
        return self.state / "locks"


def _xdg(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


def app_paths() -> AppPaths:
    """Return platform-native application directories without creating them."""
    override = os.environ.get("SYMBRAID_HOME")
    if override:
        root = Path(override).expanduser()
        return AppPaths(root / "config", root / "data", root / "cache", root / "state")
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Symbraid"
        return AppPaths(root, root / "data", root / "cache", root / "state")
    home = Path.home()
    return AppPaths(
        _xdg("XDG_CONFIG_HOME", home / ".config") / "symbraid",
        _xdg("XDG_DATA_HOME", home / ".local" / "share") / "symbraid",
        _xdg("XDG_CACHE_HOME", home / ".cache") / "symbraid",
        _xdg("XDG_STATE_HOME", home / ".local" / "state") / "symbraid",
    )
