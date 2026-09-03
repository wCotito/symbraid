from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from symbraid.config import Config
from symbraid.indexer import SymbraidIndexer, repo_identity
from symbraid.locking import ProjectLock, WatcherLease, watcher_status
from symbraid.mcp_server import _HttpSecurity, _loopback, _resolve_project
from symbraid.paths import AppPaths, app_paths
from symbraid.registry import Registry, default_registry, normalize_project_path
from symbraid.secrets import env_reference, get_secret
from symbraid.watcher import watch_project


class PlatformPathTests(unittest.TestCase):
    def test_home_override_is_portable_and_separates_data(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"SYMBRAID_HOME": directory}, clear=False
        ):
            paths = app_paths()
            self.assertEqual(paths.config, Path(directory) / "config")
            self.assertEqual(paths.data, Path(directory) / "data")
            self.assertEqual(paths.cache, Path(directory) / "cache")
            self.assertEqual(paths.state, Path(directory) / "state")

    @unittest.skipUnless(os.name == "posix", "Linux path casing contract")
    def test_linux_project_identity_is_case_sensitive(self):
        self.assertNotEqual(
            repo_identity(Path("/tmp/SymbraidProject")),
            repo_identity(Path("/tmp/symbraidproject")),
        )


class SchemaTests(unittest.TestCase):
    def test_old_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            data = default_registry()
            data["schema_version"] = 2
            config_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported Symbraid config schema: 2"):
                Registry(config_path).load()



class SecretTests(unittest.TestCase):
    def test_env_reference_stores_only_variable_name(self):
        with mock.patch.dict(os.environ, {"SYMBRAID_TEST_SECRET": "do-not-serialize"}, clear=False):
            reference = env_reference("SYMBRAID_TEST_SECRET")
            self.assertEqual(reference, "env:SYMBRAID_TEST_SECRET")
            self.assertEqual(get_secret(reference), "do-not-serialize")
            self.assertNotIn("do-not-serialize", json.dumps({"secret_ref": reference}))

    def test_invalid_environment_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            get_secret("env:not valid")


class WatcherTests(unittest.TestCase):
    def test_duplicate_lease_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_dir = Path(directory)
            first = WatcherLease(lock_dir, "fixture")
            first.acquire()
            try:
                state = watcher_status(lock_dir, "fixture")
                self.assertTrue(state["running"])
                self.assertEqual(state["owner"]["pid"], os.getpid())
                self.assertNotIn("probe", state)
                with self.assertRaises(RuntimeError):
                    WatcherLease(lock_dir, "fixture").acquire()
            finally:
                first.release()
            self.assertFalse(watcher_status(lock_dir, "fixture")["running"])

    def test_permanent_open_failure_is_not_reported_as_contention(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            Path, "open", side_effect=PermissionError("access denied")
        ):
            with self.assertRaises(PermissionError):
                ProjectLock(Path(directory), "fixture", 0.0).acquire()

    def test_windows_share_violation_is_lock_contention(self):
        error = PermissionError("sharing violation")
        error.winerror = 32
        with mock.patch("symbraid.locking.os.name", "nt"):
            self.assertTrue(ProjectLock._windows_share_violation(error))
        error.winerror = 5
        with mock.patch("symbraid.locking.os.name", "nt"):
            self.assertFalse(ProjectLock._windows_share_violation(error))

    def test_lock_file_initialization_error_propagates(self):
        handle = mock.MagicMock()
        handle.tell.return_value = 0
        handle.write.side_effect = OSError("disk failure")
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            Path, "open", return_value=handle
        ):
            with self.assertRaisesRegex(OSError, "disk failure"):
                ProjectLock(Path(directory), "fixture", 0.0).acquire()
        handle.close.assert_called_once()

    def test_status_tolerates_unreadable_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_dir = Path(directory)
            owner_path = lock_dir / "watch-fixture.owner.json"
            owner_path.write_text(json.dumps({"pid": 42}), encoding="utf-8")
            with mock.patch(
                "symbraid.locking.ProjectLock.acquire", side_effect=PermissionError("locked")
            ):
                state = watcher_status(lock_dir, "fixture")
            self.assertTrue(state["running"])
            self.assertEqual(state["owner"], {"pid": 42})
            self.assertEqual(state["probe"], "unavailable")
    def test_pre_stopped_watcher_exits_without_indexing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "repo"
            project.mkdir()
            registry = Registry(root / "config.json")
            registry.register_project(str(project))
            stop = threading.Event()
            stop.set()
            paths = AppPaths(root / "config", root / "data", root / "cache", root / "state")
            fake_watchfiles = types.SimpleNamespace(watch=lambda *args, **kwargs: iter(()))
            with mock.patch.dict(sys.modules, {"watchfiles": fake_watchfiles}), mock.patch(
                "symbraid.watcher.app_paths", return_value=paths
            ), mock.patch("symbraid.watcher.SymbraidService") as service:
                watch_project(str(project), registry=registry, stop_event=stop)
            service.return_value.index.assert_not_called()

    def test_interrupted_refresh_leaves_incomplete_metadata(self):
        class Store:
            def __init__(self):
                self.upserts = []
            def ensure_collection(self):
                pass
            def upsert(self, points):
                self.upserts.extend(points)
            def count_chunks(self, repo_id):
                return 1
            def delete_paths(self, repo_id, paths):
                return 0

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "x.py"
            file_path.write_text("print('new')\n", encoding="utf-8")
            cfg = Config.from_mapping({
                "backend": "lancedb",
                "lancedb_path": root / "db",
                "embedding_dimension": 3,
                "lock_dir": root / "locks",
            })
            store = Store()
            indexer = SymbraidIndexer(cfg, store, mock.Mock())
            with mock.patch.object(indexer, "_list_files", return_value=[file_path]), mock.patch.object(
                indexer, "_existing_files", return_value={"x.py": {"old"}}
            ), mock.patch.object(indexer, "chunks_for_file", return_value=[]), mock.patch.object(
                indexer, "_points_for_chunks", side_effect=KeyboardInterrupt
            ):
                with self.assertRaises(KeyboardInterrupt):
                    indexer.refresh_files(str(root), ["x.py"])
            metadata = [point["payload"] for point in store.upserts if point["payload"]["type"] == "metadata"]
            self.assertTrue(metadata)
            self.assertFalse(metadata[-1]["indexing_complete"])


class McpSecurityTests(unittest.TestCase):
    def test_bound_project_rejects_other_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one"
            second = root / "two"
            first.mkdir()
            second.mkdir()
            self.assertEqual(_resolve_project(str(first), None), str(first.resolve()))
            with self.assertRaises(PermissionError):
                _resolve_project(str(first), str(second))

    def test_only_literal_loopback_addresses_are_accepted(self):
        self.assertTrue(_loopback("127.0.0.1"))
        self.assertTrue(_loopback("::1"))
        self.assertFalse(_loopback("0.0.0.0"))
        self.assertFalse(_loopback("192.0.2.1"))

    def test_http_requires_token_host_and_origin(self):
        called = []
        messages = []

        async def app(scope, receive, send):
            called.append(True)

        async def send(message):
            messages.append(message)

        async def exercise(headers):
            await _HttpSecurity(app, "secret-value", 8765)(
                {"type": "http", "headers": headers}, lambda: None, send
            )

        asyncio.run(exercise([
            (b"host", b"127.0.0.1:8765"),
            (b"origin", b"http://127.0.0.1:8765"),
            (b"authorization", b"Bearer secret-value"),
        ]))
        self.assertTrue(called)
        called.clear()
        messages.clear()
        asyncio.run(exercise([
            (b"host", b"attacker.example"),
            (b"authorization", b"Bearer secret-value"),
        ]))
        self.assertFalse(called)
        self.assertEqual(messages[0]["status"], 403)
        messages.clear()
        asyncio.run(exercise([(b"host", b"127.0.0.1:8765")]))
        self.assertEqual(messages[0]["status"], 401)
        self.assertNotIn(b"secret-value", messages[-1]["body"])


if __name__ == "__main__":
    unittest.main()
