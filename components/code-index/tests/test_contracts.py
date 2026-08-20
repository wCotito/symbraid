from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
import urllib.request
import uuid
from pathlib import Path

from code_index.config import Config
from code_index.indexer import CodeIndexer
from code_index.kilo import KILO_METADATA_ID, KiloLanceDBSource, KiloQdrantSource, validate_profile
from code_index.lancedb_store import LanceDBStore
from code_index.locking import ProjectLock
from code_index.qdrant import QdrantStore


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

    def test_kilo_profile_validation(self):
        metadata = {"index_schema": "2", "indexing_complete": "true", "embedding_provider": "openai-compatible", "embedding_model_id": "m", "embedding_dimension": "3"}
        self.assertTrue(validate_profile(metadata, "openai-compatible", "m", 3)["complete"])
        with self.assertRaises(ValueError): validate_profile({**metadata, "indexing_complete": "false"}, "openai-compatible", "m", 3)
        with self.assertRaises(ValueError): validate_profile(metadata, "openai-compatible", "wrong", 3)

    def test_recursive_ignored_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "src").mkdir(); (root / "nested" / "node_modules").mkdir(parents=True)
            (root / "src" / "ok.py").write_text("def ok(): pass\n", encoding="utf-8")
            (root / "nested" / "node_modules" / "bad.js").write_text("bad()", encoding="utf-8")
            cfg = Config.from_mapping({"backend": "lancedb", "lancedb_path": root / "db", "embedding_dimension": 3, "rg_path": str(Path.home() / "scoop" / "shims" / "rg.exe")})
            files = CodeIndexer(cfg, None, None)._list_files(root)
            self.assertEqual([p.relative_to(root).as_posix() for p in files], ["src/ok.py"])

    def test_kilo_lancedb_fixture_is_read_only(self):
        import lancedb
        with tempfile.TemporaryDirectory() as directory:
            db = lancedb.connect(directory)
            db.create_table("metadata", data=[
                {"key": "index_schema", "value": "2"}, {"key": "indexing_complete", "value": "true"},
                {"key": "embedding_provider", "value": "openai-compatible"}, {"key": "embedding_model_id", "value": "m"},
                {"key": "embedding_dimension", "value": "3"},
            ])
            db.create_table("vector", data=[{"vector": [1.0, 0.0, 0.0], "filePath": "src/a.py", "fileHash": "f", "codeChunk": "refresh token", "startLine": 1, "endLine": 2, "segmentHash": "s"}])
            source = KiloLanceDBSource(directory)
            self.assertTrue(validate_profile(source.metadata(), "openai-compatible", "m", 3)["complete"])
            self.assertEqual(source.search([1.0, 0.0, 0.0], 1, None)[0]["path"], "src/a.py")
            self.assertFalse(hasattr(source, "upsert"))

    def test_kilo_qdrant_fixture_is_read_only(self):
        try: urllib.request.urlopen("http://127.0.0.1:18133/collections", timeout=2)
        except Exception: self.skipTest("local Qdrant unavailable")
        name = "code-index-kilo-test-" + uuid.uuid4().hex[:10]; store = QdrantStore(config("qdrant", name))
        metadata = {"index_schema": "2", "indexing_complete": "true", "embedding_provider": "openai-compatible", "embedding_model_id": "m", "embedding_dimension": "3"}
        try:
            store.ensure_collection(); store.upsert([
                {"id": KILO_METADATA_ID, "vector": [0.0, 0.0, 0.0], "payload": metadata},
                {"id": str(uuid.uuid4()), "vector": [1.0, 0.0, 0.0], "payload": {"filePath": "src/a.py", "fileHash": "f", "codeChunk": "refresh token", "startLine": 1, "endLine": 2, "segmentHash": "s"}},
            ])
            source = KiloQdrantSource("http://127.0.0.1:18133", name)
            self.assertTrue(validate_profile(source.metadata(), "openai-compatible", "m", 3)["complete"])
            self.assertEqual(source.search([1.0, 0.0, 0.0], 1, None)[0]["path"], "src/a.py")
            self.assertFalse(hasattr(source, "upsert"))
        finally: store._request("DELETE", f"/collections/{name}", allow_404=True)

    def test_mcp_exposes_read_only_tools(self):
        source = Path("mcp_gateway.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("@mcp.tool()"), 3)
        for forbidden in ("index_project", "refresh_files", "remove_project"):
            self.assertNotIn(f"def {forbidden}", source)


if __name__ == "__main__": unittest.main()
