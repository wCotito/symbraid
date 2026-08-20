from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .embeddings import Embedder
from .indexer import CodeIndexer, canonical_project, repo_identity
from .kilo import (
    KiloLanceDBSource,
    KiloQdrantSource,
    kilo_lancedb_directory,
    kilo_qdrant_collection,
    validate_profile,
)
from .lancedb_store import LanceDBStore
from .qdrant import QdrantStore
from .registry import Registry, normalize_project_path, safe_name
from .secrets import get_secret


class CodeIndexService:
    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()

    def _profile(self, source: Dict[str, Any]) -> Dict[str, Any]:
        data = self.registry.load()
        profile_id = source.get("embedding_profile") or data["defaults"]["embedding_profile"]
        profile = data["profiles"].get(profile_id)
        if profile is None:
            raise ValueError(f"Embedding profile does not exist: {profile_id}")
        return profile

    def _config(self, project: Dict[str, Any], source: Dict[str, Any]):
        profile = self._profile(source)
        location = source.get("location") or {}
        return self.registry.resolved_config(
            project,
            source,
            embedding_secret=get_secret(profile.get("secret_ref", "")),
            qdrant_secret=get_secret(location.get("secret_ref", "")),
        )

    @staticmethod
    def _store(config):
        return QdrantStore(config) if config.backend == "qdrant" else LanceDBStore(config)

    def _managed(self, project_path: str, require_write: bool = False):
        project, source = self.registry.active_source(project_path)
        if source["owner"] != "code-index":
            if require_write:
                raise PermissionError("Active source is external and read-only")
            return project, source, None, None
        config = self._config(project, source)
        store = self._store(config)
        return project, source, config, CodeIndexer(config, store, Embedder(config))

    def index(self, project_path: str, force: bool = False) -> Dict[str, Any]:
        project, source, _, indexer = self._managed(project_path, require_write=True)
        result = indexer.index_project(project["path"], force)
        return {**result, "source_id": source["id"], "owner": source["owner"]}

    def refresh(self, project_path: str, files: Sequence[str]) -> Dict[str, Any]:
        project, source, _, indexer = self._managed(project_path, require_write=True)
        result = indexer.refresh_files(project["path"], files)
        return {**result, "source_id": source["id"], "owner": source["owner"], "backend": source["backend"]}

    def status(self, project_path: str) -> Dict[str, Any]:
        project, source = self.registry.active_source(project_path)
        if source["owner"] == "code-index":
            config = self._config(project, source)
            result = CodeIndexer(config, self._store(config), Embedder(config)).index_status(project["path"])
            return {**result, "source_id": source["id"], "owner": source["owner"], "backend": source["backend"], "mode": source["mode"]}
        adapter, profile = self._external(project, source)
        metadata = adapter.metadata()
        if str(metadata.get("indexing_complete", "false")).lower() != "true":
            return {
                "status": "ok", "project": project["path"], "source_id": source["id"],
                "owner": "kilo", "backend": source["backend"], "mode": "read-only",
                "indexed": False, "metadata": {"schema": metadata.get("index_schema"), "complete": False},
            }
        stored = validate_profile(metadata, profile["provider"], profile["model"], int(profile["dimension"]))
        return {
            "status": "ok",
            "project": project["path"],
            "source_id": source["id"],
            "owner": "kilo",
            "backend": source["backend"],
            "mode": "read-only",
            "indexed": stored["complete"],
            "metadata": stored,
        }

    def search(self, query: str, project_path: str, top_k: int = 10, path_filter: Optional[str] = None) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        project, source = self.registry.active_source(project_path)
        requested = max(1, min(int(top_k), 20))
        if source["owner"] == "code-index":
            config = self._config(project, source)
            result = CodeIndexer(config, self._store(config), Embedder(config)).semantic_search(
                query, project["path"], requested, path_filter
            )
            results = result["results"]
        else:
            adapter, profile = self._external(project, source)
            validate_profile(adapter.metadata(), profile["provider"], profile["model"], int(profile["dimension"]))
            config = self._config(project, source)
            results = adapter.search(Embedder(config).embed_query(query), requested, path_filter)
        for item in results:
            item.update({"source_id": source["id"], "owner": source["owner"], "backend": source["backend"]})
        return {
            "status": "ok",
            "project": project["path"],
            "source_id": source["id"],
            "owner": source["owner"],
            "backend": source["backend"],
            "query": query,
            "results": results,
        }

    def _external(self, project: Dict[str, Any], source: Dict[str, Any]):
        profile = self._profile(source)
        location = source.get("location") or {}
        if source["backend"] == "qdrant":
            adapter = KiloQdrantSource(
                location["url"], location["collection"], get_secret(location.get("secret_ref", ""))
            )
        else:
            adapter = KiloLanceDBSource(location["directory"])
        return adapter, profile

    def list_sources(self, project_path: str) -> Dict[str, Any]:
        project = self.registry.project(project_path)
        return {
            "status": "ok",
            "project": project["path"],
            "active_source_id": project["active_source_id"],
            "watch_enabled": bool(project.get("watch_enabled")),
            "overrides": project.get("overrides") or {},
            "sources": list(project["sources"].values()),
        }

    def detect_kilo(self, project_path: str) -> Dict[str, Any]:
        project = self.registry.project(project_path, create=True)
        data = self.registry.load()
        candidates: List[Dict[str, Any]] = []
        url = data["defaults"]["qdrant_url"]
        collection = kilo_qdrant_collection(project["path"])
        try:
            adapter = KiloQdrantSource(url, collection)
            metadata = adapter.metadata()
            candidates.append({
                "id": "kilo-qdrant",
                "owner": "kilo",
                "backend": "qdrant",
                "mode": "read-only",
                "location": {"url": url, "collection": collection, "secret_ref": ""},
                "metadata": metadata,
            })
        except Exception:
            pass
        roots = [Path(value) for value in data["defaults"].get("kilo_lancedb_roots", [])]
        roots.extend([
            Path.home() / ".config" / "kilo" / "lancedb",
            Path.home() / ".cache" / "kilo" / "lancedb",
            Path.home() / "AppData" / "Roaming" / "Code" / "User" / "globalStorage" / "kilocode.kilo-code" / "cache" / "lancedb",
        ])
        seen = set()
        for root in roots:
            directory = kilo_lancedb_directory(str(root), project["path"])
            key = str(directory).casefold()
            if key in seen or not directory.is_dir():
                continue
            seen.add(key)
            try:
                metadata = KiloLanceDBSource(str(directory)).metadata()
                candidates.append({
                    "id": f"kilo-lancedb-{len(candidates) + 1}",
                    "owner": "kilo",
                    "backend": "lancedb",
                    "mode": "read-only",
                    "location": {"directory": str(directory)},
                    "metadata": metadata,
                })
            except Exception:
                continue
        return {"status": "ok", "project": project["path"], "candidates": candidates}

    def add_source(self, project_path: str, source: Dict[str, Any], activate: bool = False) -> Dict[str, Any]:
        project = self.registry.project(project_path)
        if source.get("owner") != "kilo" or source.get("mode") != "read-only":
            raise ValueError("Only read-only Kilo sources can be added manually")
        if source.get("backend") not in {"qdrant", "lancedb"}:
            raise ValueError("Unsupported source backend")
        if not source.get("embedding_profile"):
            raise ValueError("Kilo source requires an embedding_profile")
        if activate:
            adapter, profile = self._external(project, source)
            validate_profile(adapter.metadata(), profile["provider"], profile["model"], int(profile["dimension"]))
        project["sources"][source["id"]] = source
        if activate:
            project["active_source_id"] = source["id"]
        self.registry.update_project(project_path, project)
        return self.list_sources(project_path)

    def use_source(self, project_path: str, source_id: str) -> Dict[str, Any]:
        project = self.registry.project(project_path)
        if source_id not in project["sources"]:
            raise KeyError(f"Source does not exist: {source_id}")
        source = project["sources"][source_id]
        if source.get("owner") == "kilo":
            adapter, profile = self._external(project, source)
            validate_profile(adapter.metadata(), profile["provider"], profile["model"], int(profile["dimension"]))
        project["active_source_id"] = source_id
        self.registry.update_project(project_path, project)
        return self.list_sources(project_path)

    def migrate_backend(self, project_path: str, backend: str) -> Dict[str, Any]:
        if backend not in {"qdrant", "lancedb"}:
            raise ValueError("backend must be qdrant or lancedb")
        project, source = self.registry.active_source(project_path)
        if source["owner"] != "code-index":
            raise PermissionError("External sources cannot be migrated")
        if source["backend"] == backend:
            return {"status": "ok", "changed": False, "active_source_id": source["id"]}
        data = self.registry.load()
        target = self.registry._managed_source(data, Path(project["path"]), project["project_id"], backend)
        target["embedding_profile"] = source["embedding_profile"]
        source_config = self._config(project, source)
        target_config = self._config(project, target)
        source_store = self._store(source_config)
        target_store = self._store(target_config)
        source_store.ensure_collection()
        target_store.ensure_collection()
        repo_id = repo_identity(canonical_project(project["path"]))
        points = source_store.export_points(repo_id)
        expected = source_store.count_chunks(repo_id)
        metadata = next((item.get("payload") or {} for item in points if (item.get("payload") or {}).get("type") == "metadata"), None)
        if metadata is None or not metadata.get("indexing_complete"):
            raise RuntimeError("Source index has no complete metadata record")
        required = {
            "schema_version": 1,
            "embedding_provider": source_config.embedding_provider,
            "embedding_model": source_config.embedding_model,
            "embedding_dimension": source_config.embedding_dimension,
        }
        mismatch = {key: (metadata.get(key), value) for key, value in required.items() if metadata.get(key) != value}
        if mismatch:
            raise RuntimeError(f"Source index metadata mismatch: {mismatch}")
        rollback = target_store.export_points(repo_id)
        try:
            target_store.delete_repo(repo_id)
            for start in range(0, len(points), 64):
                target_store.upsert(points[start : start + 64])
            actual = target_store.count_chunks(repo_id)
            copied = target_store.export_points(repo_id)
            copied_metadata = next((item.get("payload") or {} for item in copied if (item.get("payload") or {}).get("type") == "metadata"), None)
            if expected != actual or copied_metadata is None:
                raise RuntimeError(f"Backend migration verification failed: expected {expected}, got {actual}")
            copied_check = {key: copied_metadata.get(key) for key in required}
            if copied_check != required:
                raise RuntimeError(f"Backend migration metadata mismatch: {copied_check}")
        except Exception:
            target_store.delete_repo(repo_id)
            for start in range(0, len(rollback), 64):
                target_store.upsert(rollback[start : start + 64])
            raise
        project = copy.deepcopy(project)
        project["sources"][target["id"]] = target
        project["active_source_id"] = target["id"]
        self.registry.update_project(project_path, project)
        return {
            "status": "ok",
            "changed": True,
            "from": source["id"],
            "to": target["id"],
            "chunks": actual,
            "source_retained": True,
        }
