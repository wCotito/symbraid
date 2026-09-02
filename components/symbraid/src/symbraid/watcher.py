from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any, Callable

from .indexer import git_context
from .locking import WatcherLease
from .paths import app_paths
from .registry import Registry, project_id
from .service import CodeIndexService


Reporter = Callable[[dict[str, Any]], None]
_CONTROL_FILES = {".gitignore", ".ignore"}


def _interesting(root: Path, changed: set[tuple[Any, str]]) -> tuple[list[str], bool]:
    paths: list[str] = []
    reconcile = False
    for _, raw in changed:
        candidate = Path(raw).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative in _CONTROL_FILES or relative.endswith("/.gitignore"):
            reconcile = True
        if relative == ".git/HEAD" or relative.startswith(".git/refs/"):
            reconcile = True
            continue
        if relative.startswith(".git/"):
            continue
        paths.append(relative)
    return sorted(set(paths)), reconcile


def watch_project(
    project_path: str,
    *,
    registry: Registry | None = None,
    stop_event: threading.Event | None = None,
    reporter: Reporter | None = None,
) -> None:
    """Run initial reconciliation followed by incremental updates until stopped."""
    from watchfiles import watch

    registry = registry or Registry()
    project = registry.project(project_path, create=True)
    root = Path(project["path"]).resolve()
    settings = registry.resolved_settings(project)
    stop = stop_event or threading.Event()
    report = reporter or (lambda value: None)
    lease = WatcherLease(app_paths().locks, project_id(str(root)))
    previous_handlers: dict[int, Any] = {}

    def request_stop(signum, frame) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        for name in ("SIGINT", "SIGTERM"):
            signum = getattr(signal, name, None)
            if signum is not None:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)
    try:
        with lease:
            service = CodeIndexService(registry)
            report({"event": "watcher_started", "project": str(root), "owner": lease.owner})
            if stop.is_set():
                return
            report({"event": "reconcile", "result": service.index(str(root))})
            old_head = git_context(root)
            timeout_ms = max(250, min(5000, int(settings["debounce_ms"])))
            for changes in watch(
                root,
                debounce=int(settings["debounce_ms"]),
                step=max(50, min(500, int(settings["debounce_ms"]) // 4)),
                stop_event=stop,
                yield_on_timeout=True,
                rust_timeout=timeout_ms,
            ):
                if stop.is_set():
                    break
                paths, reconcile = _interesting(root, changes)
                head = git_context(root)
                if head != old_head:
                    reconcile = True
                    old_head = head
                if reconcile or len(paths) >= int(settings["bulk_change_threshold"]):
                    report({"event": "reconcile", "result": service.index(str(root))})
                elif paths:
                    report({"event": "refresh", "paths": paths, "result": service.refresh(str(root), paths)})
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        report({"event": "watcher_stopped", "project": str(root)})
