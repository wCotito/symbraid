from __future__ import annotations

import json
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from symbraid.config import Config
from symbraid.embeddings import (
    Embedder,
    EmbeddingError,
    TransientEmbeddingError,
    _parse_retry_after,
)
from symbraid.paths import AppPaths
from symbraid.registry import Registry, default_registry, normalize_project_path
from symbraid.watcher import watch_project


class EmbeddingRateLimitTests(unittest.TestCase):
    def config(self) -> Config:
        return Config.from_mapping({
            "embedding_provider": "openai-compatible",
            "embedding_model": "fixture",
            "embedding_dimension": 3,
            "embedding_base_url": "https://embedding.invalid/v1",
        })

    def test_retry_after_seconds_and_http_date(self):
        now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(_parse_retry_after("17", now), 17.0)
        target = now + timedelta(seconds=42)
        self.assertEqual(
            _parse_retry_after(target.strftime("%a, %d %b %Y %H:%M:%S GMT"), now),
            42.0,
        )
        self.assertIsNone(_parse_retry_after("not-a-delay", now))

    def test_429_is_returned_to_watcher_without_fast_retries(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            "https://embedding.invalid/v1/embeddings",
            429,
            "Too Many Requests",
            {"Retry-After": "23"},
            None,
        )
        with mock.patch(
            "symbraid.embeddings.urllib.request.build_opener", return_value=opener
        ), mock.patch("symbraid.embeddings.time.sleep") as sleep, self.assertRaises(
            TransientEmbeddingError
        ) as raised:
            Embedder(self.config()).embed_query("query")
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.retry_after_seconds, 23.0)


class RegistryMigrationTests(unittest.TestCase):
    def test_schema_three_default_is_migrated_without_changing_project_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            project_path = str(Path(directory) / "repo")
            data = default_registry()
            data["schema_version"] = 3
            data["defaults"]["debounce_ms"] = 1500
            data["projects"][normalize_project_path(project_path)] = {
                "path": project_path,
                "project_id": "fixture",
                "auto_watch": True,
                "active_source_id": "managed-lancedb",
                "overrides": {"debounce_ms": 1500},
                "sources": {},
            }
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = Registry(path).load()
            persisted = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(loaded["schema_version"], 4)
            self.assertEqual(loaded["defaults"]["debounce_ms"], 5000)
            self.assertEqual(
                loaded["projects"][normalize_project_path(project_path)]["overrides"]["debounce_ms"],
                1500,
            )
            self.assertEqual(persisted["schema_version"], 4)
            self.assertEqual(persisted["defaults"]["debounce_ms"], 5000)

    def test_schema_three_custom_default_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            data = default_registry()
            data["schema_version"] = 3
            data["defaults"]["debounce_ms"] = 2750
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(Registry(path).load()["defaults"]["debounce_ms"], 2750)


class WatcherBatchingTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / "repo"
        project.mkdir()
        registry = Registry(root / "config.json")
        registry.register_project(str(project))
        paths = AppPaths(root / "config", root / "data", root / "cache", root / "state")
        service = mock.Mock()
        service.index.return_value = {"status": "ok"}
        service.refresh.return_value = {"status": "ok"}
        return root, project, registry, paths, service

    def run_fixture(self, project, registry, paths, service, changes, times, reporter=None, stop=None):
        fake_watchfiles = types.SimpleNamespace(watch=lambda *args, **kwargs: iter(changes))
        with mock.patch.dict(sys.modules, {"watchfiles": fake_watchfiles}), mock.patch(
            "symbraid.watcher.app_paths", return_value=paths
        ), mock.patch(
            "symbraid.watcher.SymbraidService", return_value=service
        ), mock.patch(
            "symbraid.watcher.git_context", return_value=("main", "head")
        ), mock.patch(
            "symbraid.watcher.monotonic", side_effect=times
        ):
            watch_project(
                str(project),
                registry=registry,
                stop_event=stop,
                reporter=reporter,
            )

    def test_changes_are_deduplicated_and_flushed_once_after_quiet(self):
        _, project, registry, paths, service = self.fixture()
        events = []
        self.run_fixture(
            project,
            registry,
            paths,
            service,
            [
                {(1, str(project / "a.py"))},
                {(2, str(project / "a.py")), (1, str(project / "b.py"))},
                {(2, str(project / "a.py"))},
                set(),
                set(),
            ],
            [0.0, 2.0, 4.0, 8.0, 9.0],
            events.append,
        )
        service.refresh.assert_called_once_with(
            str(project.resolve()), ["a.py", "b.py"]
        )
        self.assertEqual([event["event"] for event in events].count("refresh"), 1)

    def test_continuous_changes_do_not_flush_intermediate_state(self):
        _, project, registry, paths, service = self.fixture()
        self.run_fixture(
            project,
            registry,
            paths,
            service,
            [
                {(1, str(project / "a.py"))},
                {(2, str(project / "a.py"))},
                {(2, str(project / "a.py"))},
                {(2, str(project / "a.py"))},
            ],
            [0.0, 4.0, 8.0, 12.0],
        )
        service.refresh.assert_not_called()

    def test_bulk_batch_is_promoted_to_one_reconcile(self):
        _, project, registry, paths, service = self.fixture()
        data = registry.load()
        data["projects"][normalize_project_path(str(project))]["overrides"][
            "bulk_change_threshold"
        ] = 2
        registry.save(data)
        self.run_fixture(
            project,
            registry,
            paths,
            service,
            [
                {(1, str(project / "a.py")), (1, str(project / "b.py"))},
                set(),
            ],
            [0.0, 5.0],
        )
        self.assertEqual(service.index.call_count, 2)
        service.refresh.assert_not_called()

    def test_rate_limited_batch_keeps_new_paths_for_retry(self):
        _, project, registry, paths, service = self.fixture()
        service.refresh.side_effect = [
            TransientEmbeddingError(
                "Embedding endpoint rate limited: HTTP 429",
                status_code=429,
                retry_after_seconds=3,
            ),
            {"status": "ok"},
        ]
        events = []
        self.run_fixture(
            project,
            registry,
            paths,
            service,
            [
                {(1, str(project / "a.py"))},
                set(),
                {(1, str(project / "b.py"))},
                set(),
            ],
            [0.0, 5.0, 5.0, 6.0, 11.0],
            events.append,
        )
        self.assertEqual(
            [call.args[1] for call in service.refresh.call_args_list],
            [["a.py"], ["a.py", "b.py"]],
        )
        retry = next(event for event in events if event["event"] == "embedding_retry")
        self.assertEqual(retry["delay_seconds"], 5.0)

    def test_control_file_promotes_batch_to_reconcile(self):
        _, project, registry, paths, service = self.fixture()
        self.run_fixture(
            project,
            registry,
            paths,
            service,
            [
                {(2, str(project / ".gitignore"))},
                set(),
            ],
            [0.0, 5.0],
        )
        self.assertEqual(service.index.call_count, 2)
        service.refresh.assert_not_called()

    def test_transient_failure_expires_after_five_minutes(self):
        _, project, registry, paths, service = self.fixture()
        service.refresh.side_effect = TransientEmbeddingError(
            "Embedding endpoint rate limited: HTTP 429",
            status_code=429,
        )
        with self.assertRaisesRegex(EmbeddingError, "300 seconds"):
            self.run_fixture(
                project,
                registry,
                paths,
                service,
                [
                    {(1, str(project / "a.py"))},
                    set(),
                    set(),
                ],
                [0.0, 5.0, 5.0, 305.0],
            )

    def test_stopping_discards_pending_batch(self):
        _, project, registry, paths, service = self.fixture()
        stop = threading.Event()

        def changes():
            yield {(1, str(project / "a.py"))}
            stop.set()
            yield set()

        fake_watchfiles = types.SimpleNamespace(watch=lambda *args, **kwargs: changes())
        with mock.patch.dict(sys.modules, {"watchfiles": fake_watchfiles}), mock.patch(
            "symbraid.watcher.app_paths", return_value=paths
        ), mock.patch(
            "symbraid.watcher.SymbraidService", return_value=service
        ), mock.patch(
            "symbraid.watcher.git_context", return_value=("main", "head")
        ), mock.patch("symbraid.watcher.monotonic", return_value=0.0):
            watch_project(str(project), registry=registry, stop_event=stop)
        service.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
