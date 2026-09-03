from __future__ import annotations

import errno
import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional


class ProjectLock:
    """Cross-process lock backed by one locked byte."""

    def __init__(self, lock_dir: Path, repo_id: str, timeout_seconds: float):
        self.path = lock_dir / f"{repo_id}.lock"
        self.timeout_seconds = max(0.0, timeout_seconds)
        self._file: Optional[BinaryIO] = None

    @staticmethod
    def _windows_share_violation(error: OSError) -> bool:
        return os.name == "nt" and getattr(error, "winerror", None) in {32, 33}

    @staticmethod
    def _lock_contention(error: OSError) -> bool:
        if os.name == "nt":
            winerror = getattr(error, "winerror", None)
            if winerror is not None:
                return winerror in {32, 33}
        return error.errno in {errno.EACCES, errno.EAGAIN}

    def _wait_or_timeout(self, deadline: float, error: OSError) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for project lock: {self.path}") from error
        time.sleep(min(0.2, max(0.01, self.timeout_seconds)))

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                handle = self.path.open("a+b")
            except OSError as exc:
                if not self._windows_share_violation(exc):
                    raise
                self._wait_or_timeout(deadline, exc)
                continue
            try:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
            except OSError:
                handle.close()
                raise
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                if not self._lock_contention(exc):
                    raise
                self._wait_or_timeout(deadline, exc)
                continue
            self._file = handle
            return

    def __enter__(self) -> "ProjectLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._file = None


class WatcherLease:
    """Lifetime lock and inspectable owner metadata for one project watcher."""

    def __init__(self, lock_dir: Path, repo_id: str):
        self.lock = ProjectLock(lock_dir, f"watch-{repo_id}", 0.0)
        self.owner_path = lock_dir / f"watch-{repo_id}.owner.json"
        self.owner: dict[str, Any] | None = None

    def acquire(self) -> dict[str, Any]:
        try:
            self.lock.acquire()
        except TimeoutError as exc:
            owner = watcher_status(self.lock.path.parent, self.lock.path.stem.removeprefix("watch-"))["owner"]
            raise RuntimeError(f"A watcher is already running for this project: {owner}") from exc
        self.owner = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.owner_path.write_text(json.dumps(self.owner, sort_keys=True) + "\n", encoding="utf-8")
        return self.owner

    def release(self) -> None:
        try:
            if self.owner_path.exists():
                recorded = json.loads(self.owner_path.read_text(encoding="utf-8"))
                if self.owner and recorded.get("pid") == self.owner.get("pid"):
                    self.owner_path.unlink()
        except (OSError, ValueError):
            pass
        finally:
            self.lock.release()

    def __enter__(self) -> "WatcherLease":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def watcher_status(lock_dir: Path, repo_id: str) -> dict[str, Any]:
    probe = ProjectLock(lock_dir, f"watch-{repo_id}", 0.0)
    try:
        probe.acquire()
    except (TimeoutError, OSError) as exc:
        owner_path = lock_dir / f"watch-{repo_id}.owner.json"
        try:
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            owner = {"state": "unknown"}
        result = {"running": True, "owner": owner}
        if not isinstance(exc, TimeoutError):
            result["probe"] = "unavailable"
        return result
    else:
        probe.release()
        return {"running": False, "owner": None}
