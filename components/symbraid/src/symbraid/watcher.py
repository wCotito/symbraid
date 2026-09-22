from __future__ import annotations

import signal
import threading
from time import monotonic
from pathlib import Path
from typing import Any, Callable

from .embeddings import EmbeddingError, TransientEmbeddingError
from .indexer import git_context
from .locking import WatcherLease
from .paths import app_paths
from .registry import Registry, project_id
from .service import SymbraidService


Reporter = Callable[[dict[str, Any]], None]
_CONTROL_FILES = {".gitignore", ".ignore"}
_WATCH_DEBOUNCE_MS = 100
_WATCH_STEP_MS = 50
_WATCH_TIMEOUT_MS = 250
_GIT_POLL_SECONDS = 5.0
_RETRY_BACKOFF_SECONDS = (5.0, 10.0, 20.0, 40.0, 60.0)
_RETRY_TIMEOUT_SECONDS = 300.0


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


def _retry_delay(error: TransientEmbeddingError, attempt: int, remaining: float) -> float:
    backoff = _RETRY_BACKOFF_SECONDS[min(attempt - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
    requested = error.retry_after_seconds or 0.0
    return min(max(backoff, requested), max(0.0, remaining))


def _retry_event(
    operation: str,
    attempt: int,
    delay: float,
    elapsed: float,
    error: TransientEmbeddingError,
) -> dict[str, Any]:
    return {
        "event": "embedding_retry",
        "operation": operation,
        "attempt": attempt,
        "delay_seconds": round(delay, 3),
        "elapsed_seconds": round(elapsed, 3),
        "error": str(error),
    }


def _initial_reconcile(
    service: SymbraidService,
    root: Path,
    stop: threading.Event,
    report: Reporter,
) -> bool:
    started: float | None = None
    attempt = 0
    while not stop.is_set():
        try:
            result = service.index(str(root))
        except TransientEmbeddingError as error:
            now = monotonic()
            started = now if started is None else started
            elapsed = now - started
            remaining = _RETRY_TIMEOUT_SECONDS - elapsed
            if remaining <= 0:
                raise EmbeddingError(
                    "Embedding endpoint did not recover within 300 seconds"
                ) from error
            attempt += 1
            delay = _retry_delay(error, attempt, remaining)
            report(_retry_event("reconcile", attempt, delay, elapsed, error))
            if stop.wait(delay):
                return False
        else:
            report({"event": "reconcile", "result": result})
            return True
    return False


def watch_project(
    project_path: str,
    *,
    registry: Registry | None = None,
    stop_event: threading.Event | None = None,
    reporter: Reporter | None = None,
) -> None:
    """Run initial reconciliation followed by quiet-period batched updates."""
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
            service = SymbraidService(registry)
            report({"event": "watcher_started", "project": str(root), "owner": lease.owner})
            if stop.is_set():
                return
            if not _initial_reconcile(service, root, stop, report):
                return

            old_head = git_context(root)
            idle_seconds = int(settings["debounce_ms"]) / 1000.0
            bulk_threshold = int(settings["bulk_change_threshold"])
            pending_paths: set[str] = set()
            pending_reconcile = False
            last_change_at: float | None = None
            retry_started_at: float | None = None
            retry_not_before = 0.0
            retry_attempt = 0
            retry_error: TransientEmbeddingError | None = None
            next_git_check = 0.0

            for changes in watch(
                root,
                debounce=_WATCH_DEBOUNCE_MS,
                step=_WATCH_STEP_MS,
                stop_event=stop,
                yield_on_timeout=True,
                rust_timeout=_WATCH_TIMEOUT_MS,
            ):
                if stop.is_set():
                    break

                now = monotonic()
                paths, reconcile = _interesting(root, changes)
                if now >= next_git_check:
                    head = git_context(root)
                    if head != old_head:
                        reconcile = True
                        old_head = head
                    next_git_check = now + _GIT_POLL_SECONDS
                if paths or reconcile:
                    pending_paths.update(paths)
                    pending_reconcile = pending_reconcile or reconcile
                    if len(pending_paths) >= bulk_threshold:
                        pending_reconcile = True
                    last_change_at = now

                if retry_started_at is not None:
                    elapsed = now - retry_started_at
                    if elapsed >= _RETRY_TIMEOUT_SECONDS:
                        raise EmbeddingError(
                            "Embedding endpoint did not recover within 300 seconds"
                        ) from retry_error

                if not pending_paths and not pending_reconcile:
                    continue
                if last_change_at is not None and now - last_change_at < idle_seconds:
                    continue
                if now < retry_not_before:
                    continue

                operation = "reconcile" if pending_reconcile else "refresh"
                paths_to_refresh = sorted(pending_paths)
                try:
                    if pending_reconcile:
                        result = service.index(str(root))
                    else:
                        result = service.refresh(str(root), paths_to_refresh)
                except TransientEmbeddingError as error:
                    failed_at = monotonic()
                    retry_started_at = failed_at if retry_started_at is None else retry_started_at
                    elapsed = failed_at - retry_started_at
                    remaining = _RETRY_TIMEOUT_SECONDS - elapsed
                    if remaining <= 0:
                        raise EmbeddingError(
                            "Embedding endpoint did not recover within 300 seconds"
                        ) from error
                    retry_attempt += 1
                    delay = _retry_delay(error, retry_attempt, remaining)
                    retry_not_before = failed_at + delay
                    retry_error = error
                    report(_retry_event(operation, retry_attempt, delay, elapsed, error))
                    continue

                payload: dict[str, Any] = {"event": operation, "result": result}
                if operation == "refresh":
                    payload["paths"] = paths_to_refresh
                report(payload)
                pending_paths.clear()
                pending_reconcile = False
                last_change_at = None
                retry_started_at = None
                retry_not_before = 0.0
                retry_attempt = 0
                retry_error = None
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        report({"event": "watcher_stopped", "project": str(root)})
