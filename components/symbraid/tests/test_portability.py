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
from symbraid.indexer import CodeIndexer, repo_identity
from symbraid.locking import WatcherLease, watcher_status
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


class MigrationTests(unittest.TestCase):
    def test_v2_to_v3_preserves_source_and_old_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "repo"
            project_root.mkdir()
            source_dir = root / "legacy-source"
            source_dir.mkdir()
            data = default_registry()
            data["schema_version"] = 2
            key = normalize_project_path(str(project_root))
            data["projects"][key] = {
                "path": str(project_root),
                "project_id": "0123456789abcdef",
                "watch_enabled": True,
                "active_source_id": "managed-lancedb",
                "overrides": {},
                "sources": {
                    "managed-lancedb": {
                        "id": "managed-lancedb",
                        "backend": "lancedb",
                        "embedding_profile": "default-code",
                        "location": {"directory": str(source_dir)},
                        "recipe": {
                            "max_file_bytes": 1048576,
                            "chunk_chars": 1600,
                            "chunk_overlap_chars": 200,
                            "rg_path": "rg",
                        },
                    }
                },
            }
            registry_path = root / "config.json"
            original = json.dumps(data)
            registry_path.write_text(original, encoding="utf-8")
            migrated = Registry(registry_path).load()
            project = migrated["projects"][key]
            self.assertEqual(migrated["schema_version"], 3)
            self.assertTrue(project["auto_watch"])
            self.assertNotIn("watch_enabled", project)
            self.assertEqual(project["sources"]["managed-lancedb"]["location"]["directory"], str(source_dir))
            self.assertTrue(source_dir.is_dir())
            self.assertEqual((root / "config.json.v2.bak").read_text(encoding="utf-8"), original)

    def test_default_registry_copy_keeps_legacy_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "CodeIndex"
            legacy.mkdir()
            old = default_registry()
            old["schema_version"] = 2
            legacy_file = legacy / "config.json"
            legacy_text = json.dumps(old)
            legacy_file.write_text(legacy_text, encoding="utf-8")
            paths = AppPaths(root / "new-config", root / "new-data", root / "new-cache", root / "new-state")
            with mock.patch("symbraid.registry.app_paths", return_value=paths), mock.patch(
                "symbraid.registry.legacy_app_root", return_value=legacy
            ):
                registry = Registry()
                self.assertEqual(registry.load()["schema_version"], 3)
            self.assertEqual(legacy_file.read_text(encoding="utf-8"), legacy_text)
            self.assertTrue((paths.config / "config.json.v2.bak").is_file())


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
                with self.assertRaises(RuntimeError):
                    WatcherLease(lock_dir, "fixture").acquire()
            finally:
                first.release()
            self.assertFalse(watcher_status(lock_dir, "fixture")["running"])

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
            ), mock.patch("symbraid.watcher.CodeIndexService") as service:
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
            indexer = CodeIndexer(cfg, store, mock.Mock())
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
