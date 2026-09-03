from __future__ import annotations

import hashlib
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

from symbraid import __version__
from symbraid.cli import build_parser
from symbraid.config import Config
from symbraid.embeddings import Embedder, EmbeddingError
from symbraid.indexer import SymbraidIndexer
from symbraid.lancedb_store import LanceDBStore
from symbraid.locking import ProjectLock
from symbraid.qdrant import QdrantStore


def config(backend, location):
    return Config.from_mapping({
        "backend": backend, "lancedb_path": location,
        "qdrant_url": "http://127.0.0.1:18133", "collection": location,
        "embedding_dimension": 3, "lock_dir": Path(location).parent / "locks" if backend == "lancedb" else Path(tempfile.gettempdir()) / "symbraid-tests",
    })


def points(repo="fixture"):
    return [
        {"id": str(uuid.uuid4()), "vector": [0.0, 0.0, 0.0], "payload": {"type": "metadata", "repo_id": repo, "indexing_complete": True, "schema_version": 1, "embedding_provider": "fixture", "embedding_model": "fixture", "embedding_dimension": 3}},
        {"id": str(uuid.uuid4()), "vector": [1.0, 0.0, 0.0], "payload": {"type": "chunk", "repo_id": repo, "path": "src/auth.py", "language": "python", "symbol": "refresh", "kind": "function", "start_line": 1, "end_line": 2, "file_hash": "f1", "content_hash": "c1", "text": "refresh access token"}},
        {"id": str(uuid.uuid4()), "vector": [0.0, 1.0, 0.0], "payload": {"type": "chunk", "repo_id": repo, "path": "src/cache.py", "language": "python", "symbol": "cache", "kind": "function", "start_line": 1, "end_line": 2, "file_hash": "f2", "content_hash": "c2", "text": "cache data"}},
    ]


class StoreContract:
    store = None

    def exercise(self):
        self.store.ensure_collection(); self.store.upsert(points())
        self.assertEqual(self.store.count_chunks("fixture"), 2)
        self.assertEqual(self.store.query([1.0, 0.0, 0.0], "fixture", 1)[0]["payload"]["path"], "src/auth.py")
        self.store.delete_paths("fixture", ["src/cache.py"])
        self.assertEqual(self.store.count_chunks("fixture"), 1)
        exported = self.store.export_points("fixture")
        self.assertTrue(any((p.get("payload") or {}).get("type") == "metadata" for p in exported))
        self.store.delete_repo("fixture"); self.assertEqual(self.store.count_chunks("fixture"), 0)


class LanceDBContractTests(unittest.TestCase, StoreContract):
    def test_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            self.store = LanceDBStore(config("lancedb", directory)); self.exercise()


class QdrantContractTests(unittest.TestCase, StoreContract):
    def test_contract(self):
        try: urllib.request.urlopen("http://127.0.0.1:18133/collections", timeout=2)
        except Exception: self.skipTest("local Qdrant unavailable")
        name = "symbraid-test-" + uuid.uuid4().hex[:12]
        self.store = QdrantStore(config("qdrant", name))
        try: self.exercise()
        finally: self.store._request("DELETE", f"/collections/{name}", allow_404=True)


class SafetyTests(unittest.TestCase):
    def test_cli_metadata_commands(self):
        self.assertEqual(build_parser().parse_args(["paths"]).command, "paths")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"symbraid {__version__}")

    def test_project_id_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            first = ProjectLock(Path(directory), "repo", 1); second = ProjectLock(Path(directory), "repo", .1)
            first.acquire()
            try:
                with self.assertRaises(TimeoutError): second.acquire()
            finally: first.release()

    def test_recursive_ignored_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "src").mkdir(); (root / "nested" / "node_modules").mkdir(parents=True)
            (root / "src" / "ok.py").write_text("def ok(): pass\n", encoding="utf-8")
            (root / "nested" / "node_modules" / "bad.js").write_text("bad()", encoding="utf-8")
            cfg = Config.from_mapping({"backend": "lancedb", "lancedb_path": root / "db", "embedding_dimension": 3, "rg_path": "rg"})
            files = SymbraidIndexer(cfg, None, None)._list_files(root)
            self.assertEqual([p.relative_to(root).as_posix() for p in files], ["src/ok.py"])

    def test_transient_embedding_failure_is_retried(self):
        cfg = Config.from_mapping({
            "embedding_provider": "openai-compatible",
            "embedding_model": "fixture",
            "embedding_dimension": 3,
            "embedding_base_url": "http://127.0.0.1:1/v1",
        })
        response = io.BytesIO(b'{"data":[{"index":0,"embedding":[1.0,0.0,0.0]}]}')
        opener = mock.Mock()
        opener.open.side_effect = [urllib.error.URLError("temporary"), response]
        with mock.patch("symbraid.embeddings.urllib.request.build_opener", return_value=opener), mock.patch(
            "symbraid.embeddings.time.sleep"
        ) as sleep:
            self.assertEqual(Embedder(cfg).embed_query("query"), [1.0, 0.0, 0.0])
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once()
    def test_permanent_embedding_http_error_is_not_retried_or_leaked(self):
        cfg = Config.from_mapping({
            "embedding_provider": "openai-compatible",
            "embedding_model": "fixture",
            "embedding_dimension": 3,
            "embedding_base_url": "https://embedding.invalid/v1",
            "embedding_api_key": "never-print-this-secret",
        })
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            cfg.embedding_base_url, 401, "Unauthorized", {}, None
        )
        with mock.patch("symbraid.embeddings.urllib.request.build_opener", return_value=opener), mock.patch(
            "symbraid.embeddings.time.sleep"
        ) as sleep, self.assertRaises(EmbeddingError) as raised:
            Embedder(cfg).embed_query("query")
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()
        self.assertNotIn(cfg.embedding_api_key, str(raised.exception))
        self.assertIn("HTTP 401", str(raised.exception))

    def test_transient_embedding_failure_stops_after_three_attempts(self):
        cfg = Config.from_mapping({
            "embedding_provider": "openai-compatible",
            "embedding_model": "fixture",
            "embedding_dimension": 3,
            "embedding_base_url": "http://127.0.0.1:1/v1",
        })
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.URLError("temporary")
        with mock.patch("symbraid.embeddings.urllib.request.build_opener", return_value=opener), mock.patch(
            "symbraid.embeddings.time.sleep"
        ) as sleep, self.assertRaisesRegex(EmbeddingError, "after 3 attempts"):
            Embedder(cfg).embed_query("query")
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_alias_paths_are_canonicalized_for_containment(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            alias_root = base / "RUNNER~1"
            canonical_root = base / "runner"
            canonical_file = canonical_root / "src" / "ok.py"
            canonical_file.parent.mkdir(parents=True)
            canonical_file.write_text("def ok(): pass\n", encoding="utf-8")
            alias_file = alias_root / "src" / "ok.py"
            original_resolve = Path.resolve

            def resolve(value, *args, **kwargs):
                if value == alias_root:
                    return canonical_root
                if value == alias_file:
                    return canonical_file
                return original_resolve(value, *args, **kwargs)

            cfg = Config.from_mapping({
                "backend": "lancedb", "lancedb_path": base / "db",
                "embedding_dimension": 3, "rg_path": "rg",
            })
            listed = mock.Mock(stdout="src/ok.py\n")
            with mock.patch("symbraid.indexer.subprocess.run", return_value=listed), mock.patch.object(
                Path, "resolve", resolve
            ):
                files = SymbraidIndexer(cfg, None, None)._list_files(alias_root)
            self.assertEqual(files, [alias_file])
    def test_mcp_exposes_read_only_tools(self):
        source_path = Path(__file__).parents[1] / "src/symbraid/mcp_server.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertEqual(source.count("@server.tool()"), 3)
        for forbidden in ("index_project", "refresh_files", "remove_project"):
            self.assertNotIn(f"def {forbidden}", source)


if __name__ == "__main__": unittest.main()
