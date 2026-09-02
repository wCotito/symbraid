from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
import urllib.request
import uuid
from pathlib import Path

from symbraid.config import Config
from symbraid.indexer import CodeIndexer
from symbraid.lancedb_store import LanceDBStore
from symbraid.locking import ProjectLock
from symbraid.qdrant import QdrantStore


def config(backend, location):
    return Config.from_mapping({
        "backend": backend, "lancedb_path": location,
        "qdrant_url": "http://127.0.0.1:18133", "collection": location,
        "embedding_dimension": 3, "lock_dir": Path(location).parent / "locks" if backend == "lancedb" else Path(tempfile.gettempdir()) / "code-index-tests",
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
        name = "code-index-test-" + uuid.uuid4().hex[:12]
        self.store = QdrantStore(config("qdrant", name))
        try: self.exercise()
        finally: self.store._request("DELETE", f"/collections/{name}", allow_404=True)


class SafetyTests(unittest.TestCase):
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
            files = CodeIndexer(cfg, None, None)._list_files(root)
            self.assertEqual([p.relative_to(root).as_posix() for p in files], ["src/ok.py"])

    def test_mcp_exposes_read_only_tools(self):
        source_path = Path(__file__).parents[1] / "src/symbraid/mcp_server.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertEqual(source.count("@server.tool()"), 3)
        for forbidden in ("index_project", "refresh_files", "remove_project"):
            self.assertNotIn(f"def {forbidden}", source)


if __name__ == "__main__": unittest.main()
