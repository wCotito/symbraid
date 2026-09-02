from __future__ import annotations

import copy
import hashlib
import json
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .embeddings import Embedder
from .indexer import CodeIndexer, canonical_project, repo_identity
from .lancedb_store import LanceDBStore
from .qdrant import QdrantStore
from .locking import watcher_status
from .paths import app_paths
from .registry import INDEX_RECIPE_KEYS, PROJECT_OVERRIDE_KEYS, Registry
from .secrets import SecretUpdate, get_secret


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

    def _config(
        self, project: Dict[str, Any], source: Dict[str, Any], resolve_secrets: bool = True,
    ):
        profile = self._profile(source)
        location = source.get("location") or {}
        return self.registry.resolved_config(
            project,
            source,
            embedding_secret=get_secret(profile.get("secret_ref", "")) if resolve_secrets else "",
            qdrant_secret=get_secret(location.get("secret_ref", "")) if resolve_secrets else "",
        )

    @staticmethod
    def _store(config):
        return QdrantStore(config) if config.backend == "qdrant" else LanceDBStore(config)

    def _active(self, project_path: str):
        project, source = self.registry.active_source(project_path)
        config = self._config(project, source)
        store = self._store(config)
        return project, source, config, CodeIndexer(config, store, Embedder(config))

    def index(self, project_path: str, force: bool = False) -> Dict[str, Any]:
        project, source, _, indexer = self._active(project_path)
        result = indexer.index_project(project["path"], force)
        return {**result, "source_id": source["id"]}

    def refresh(self, project_path: str, files: Sequence[str]) -> Dict[str, Any]:
        project, source, _, indexer = self._active(project_path)
        result = indexer.refresh_files(project["path"], files)
        return {**result, "source_id": source["id"], "backend": source["backend"]}

    def status(self, project_path: str) -> Dict[str, Any]:
        project, source, config, _ = self._active(project_path)
        result = CodeIndexer(config, self._store(config), Embedder(config)).index_status(project["path"])
        return {
            **result, "source_id": source["id"], "backend": source["backend"],
            "auto_watch": bool(project.get("auto_watch")),
            "watcher": watcher_status(app_paths().locks, project["project_id"]),
        }

    def search(
        self, query: str, project_path: str, top_k: int = 10, path_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        project, source, config, _ = self._active(project_path)
        requested = max(1, min(int(top_k), 20))
        results = CodeIndexer(config, self._store(config), Embedder(config)).semantic_search(
            query, project["path"], requested, path_filter
        )["results"]
        for item in results:
            item.update({"source_id": source["id"], "backend": source["backend"]})
        return {
            "status": "ok", "project": project["path"], "source_id": source["id"],
            "backend": source["backend"], "query": query, "results": results,
        }

    def list_sources(self, project_path: str) -> Dict[str, Any]:
        project = self.registry.project(project_path)
        return {
            "status": "ok", "project": project["path"],
            "active_source_id": project["active_source_id"],
            "auto_watch": bool(project.get("auto_watch")),
            "watcher": watcher_status(app_paths().locks, project["project_id"]),
            "overrides": project.get("overrides") or {},
            "sources": [self._public_source(source) for source in project["sources"].values()],
        }

    def use_source(self, project_path: str, source_id: str) -> Dict[str, Any]:
        project = self.registry.project(project_path)
        if source_id not in project["sources"]:
            raise KeyError(f"Source does not exist: {source_id}")
        source = project["sources"][source_id]
        config = self._config(project, source)
        status = CodeIndexer(config, self._store(config), Embedder(config)).index_status(project["path"])
        metadata = status.get("metadata") or {}
        required = {
            "schema_version": 1, "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model, "embedding_dimension": config.embedding_dimension,
        }
        mismatch = {key: (metadata.get(key), value) for key, value in required.items() if metadata.get(key) != value}
        if not status.get("indexed") or not metadata.get("indexing_complete") or mismatch:
            raise RuntimeError(f"Source validation failed: complete={metadata.get('indexing_complete')}, mismatch={mismatch}")
        project["active_source_id"] = source_id
        self.registry.update_project(project_path, project)
        return self.list_sources(project_path)

    @staticmethod
    def _public_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value for key, value in profile.items() if key != "secret_ref"
        } | {"api_key_configured": bool(profile.get("secret_ref"))}

    @staticmethod
    def _public_source(source: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(source)
        location = result.get("location") or {}
        reference = location.pop("secret_ref", "")
        if result.get("backend") == "qdrant":
            location["qdrant_api_key_configured"] = bool(reference)
        return result

    @staticmethod
    def _public_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
        result = {key: value for key, value in settings.items() if key != "qdrant_secret_ref"}
        result["qdrant_api_key_configured"] = bool(settings.get("qdrant_secret_ref"))
        return result

    def settings_state(self, project_path: Optional[str] = None) -> Dict[str, Any]:
        data = self.registry.load()
        result: Dict[str, Any] = {
            "status": "ok", "schema_version": data["schema_version"],
            "defaults": self._public_settings(data["defaults"]),
            "profiles": {key: self._public_profile(value) for key, value in data["profiles"].items()},
        }
        if project_path:
            project, source = self.registry.active_source(project_path)
            result["profiles"] = {
                key: self._public_profile(value)
                for key, value in data["profiles"].items()
                if value.get("scope", "global") == "global" or value.get("project_id") == project["project_id"]
            }
            effective = self.registry.resolved_settings(project)
            result["project"] = {
                "path": project["path"], "project_id": project["project_id"],
                "auto_watch": bool(project.get("auto_watch")),
                "watcher": watcher_status(app_paths().locks, project["project_id"]),
                "overrides": self._public_settings(project.get("overrides") or {}),
                "effective": self._public_settings(effective),
                "active_source_id": project["active_source_id"],
                "active_source": self._public_source(source),
                "sources": [self._public_source(item) for item in project["sources"].values()],
            }
            try:
                result["project"]["index_status"] = self.status(project_path)
            except Exception as exc:
                result["project"]["index_status"] = {"status": "error", "error": str(exc)}
        return result

    def _desired(self, project: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        desired = self.registry.resolved_settings(project)
        defaults = self.registry.load()["defaults"]
        for key in payload.get("clear_overrides", []):
            if key in defaults:
                desired[key] = defaults[key]
        for key in PROJECT_OVERRIDE_KEYS:
            if key in payload and payload[key] is not None:
                desired[key] = payload[key]
        if desired["backend"] not in {"lancedb", "qdrant"}:
            raise ValueError("backend must be qdrant or lancedb")
        data = self.registry.load()
        if desired["embedding_profile"] not in data["profiles"]:
            raise KeyError(f"Profile does not exist: {desired['embedding_profile']}")
        if int(desired["debounce_ms"]) < 100:
            raise ValueError("debounce_ms must be at least 100")
        if int(desired["bulk_change_threshold"]) < 1 or int(desired["batch_size"]) < 1:
            raise ValueError("bulk_change_threshold and batch_size must be positive")
        if int(desired["max_file_bytes"]) < 1024:
            raise ValueError("max_file_bytes must be at least 1024")
        if int(desired["chunk_chars"]) < 400:
            raise ValueError("chunk_chars must be at least 400")
        if not 0 <= int(desired["chunk_overlap_chars"]) < int(desired["chunk_chars"]):
            raise ValueError("chunk_overlap_chars must be smaller than chunk_chars")
        if desired["backend"] == "qdrant" and not str(desired["qdrant_url"]).startswith(("http://", "https://")):
            raise ValueError("qdrant_url must be an HTTP(S) URL")
        return desired

    def plan_settings(self, project_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        project, source = self.registry.active_source(project_path)
        desired = self._desired(project, payload)
        location = source.get("location") or {}
        current_root = str(Path(location.get("directory", ".")).parent) if source["backend"] == "lancedb" else ""
        structural = []
        if source.get("embedding_profile") != desired["embedding_profile"]:
            structural.append("embedding_profile")
        for key in INDEX_RECIPE_KEYS:
            if (source.get("recipe") or {}).get(key) != desired[key]:
                structural.append(key)
        connection = []
        if source["backend"] != desired["backend"]:
            connection.append("backend")
        elif desired["backend"] == "qdrant" and location.get("url") != desired["qdrant_url"]:
            connection.append("qdrant_url")
        elif desired["backend"] == "lancedb" and Path(current_root) != Path(desired["lancedb_root"]):
            connection.append("lancedb_root")
        impact = "reindex" if structural else "transfer" if connection else "configuration-only"
        normalized = {
            "project": project["path"], "desired": desired, "impact": impact,
            "structural_changes": structural, "connection_changes": connection,
            "replace_qdrant_key": bool(payload.get("_replace_qdrant_key", payload.get("qdrant_api_key"))),
            "clear_qdrant_key": bool(payload.get("clear_qdrant_api_key")),
        }
        digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        public = {**normalized, "desired": self._public_settings(desired)}
        return {"status": "ok", **public, "plan_hash": digest}

    def _transfer(self, project: Dict[str, Any], source: Dict[str, Any], target: Dict[str, Any]) -> int:
        source_config = self._config(project, source)
        target_config = self._config(project, target)
        source_store, target_store = self._store(source_config), self._store(target_config)
        source_store.ensure_collection()
        target_store.ensure_collection()
        repo_id = repo_identity(canonical_project(project["path"]))
        points = source_store.export_points(repo_id)
        expected = source_store.count_chunks(repo_id)
        metadata = next((p.get("payload") or {} for p in points if (p.get("payload") or {}).get("type") == "metadata"), None)
        if metadata is None or not metadata.get("indexing_complete"):
            raise RuntimeError("Source index has no complete metadata record")
        required = {
            "schema_version": 1, "embedding_provider": source_config.embedding_provider,
            "embedding_model": source_config.embedding_model,
            "embedding_dimension": source_config.embedding_dimension,
        }
        mismatch = {key: (metadata.get(key), value) for key, value in required.items() if metadata.get(key) != value}
        if mismatch:
            raise RuntimeError(f"Source index metadata mismatch: {mismatch}")
        target_store.delete_repo(repo_id)
        for start in range(0, len(points), 64):
            target_store.upsert(points[start:start + 64])
        actual = target_store.count_chunks(repo_id)
        copied = target_store.export_points(repo_id)
        copied_metadata = next((p.get("payload") or {} for p in copied if (p.get("payload") or {}).get("type") == "metadata"), None)
        if actual != expected or copied_metadata is None or any(copied_metadata.get(k) != v for k, v in required.items()):
            target_store.delete_repo(repo_id)
            raise RuntimeError(f"Source transfer verification failed: expected {expected}, got {actual}")
        return actual

    def apply_project_settings(
        self,
        project_path: str,
        payload: Dict[str, Any],
        secret_update: Optional[SecretUpdate] = None,
    ) -> Dict[str, Any]:
        plan = self.plan_settings(project_path, payload)
        if payload.get("plan_hash") != plan["plan_hash"]:
            raise ValueError("Settings changed after planning; request a new plan")
        project, source = self.registry.active_source(project_path)
        desired = self._desired(project, payload)
        updated = copy.deepcopy(project)
        overrides = updated.setdefault("overrides", {})
        for key in payload.get("clear_overrides", []):
            if key in PROJECT_OVERRIDE_KEYS:
                overrides.pop(key, None)
        for key in PROJECT_OVERRIDE_KEYS:
            if key in payload and payload[key] is not None:
                overrides[key] = payload[key]
        watch_value = payload.get("auto_watch", payload.get("watch_enabled"))
        if watch_value is not None:
            updated["auto_watch"] = bool(watch_value)
        if plan["impact"] == "configuration-only":
            if desired["backend"] == "qdrant" and "qdrant_secret_ref" in desired:
                updated["sources"][source["id"]].setdefault("location", {})["secret_ref"] = desired["qdrant_secret_ref"]
            self._config(updated, updated["sources"][source["id"]], resolve_secrets=False)
            transaction = secret_update if secret_update is not None else nullcontext()
            with transaction:
                self.registry.update_project(project_path, updated)
            return {"status": "ok", "impact": plan["impact"], "active_source_id": source["id"]}

        source_id = f"managed-{desired['backend']}-{uuid.uuid4().hex[:8]}"
        target = self.registry._managed_source(
            self.registry.load(), Path(project["path"]), project["project_id"],
            desired["backend"], source_id=source_id, settings=desired,
        )
        self._config(updated, target, resolve_secrets=False)
        if plan["impact"] == "transfer":
            self._config(updated, source, resolve_secrets=False)
        transaction = secret_update if secret_update is not None else nullcontext()
        with transaction:
            target_store = None
            repo_id = repo_identity(canonical_project(project["path"]))
            try:
                target_config = self._config(updated, target)
                target_store = self._store(target_config)
                if plan["impact"] == "transfer":
                    chunks = self._transfer(updated, source, target)
                else:
                    indexer = CodeIndexer(target_config, target_store, Embedder(target_config))
                    result = indexer.index_project(project["path"], force=True)
                    chunks = int(result.get("chunks_total", result.get("chunks", result.get("chunk_count", 0))))
                    status = indexer.index_status(project["path"])
                    if not status.get("indexed") or not (status.get("metadata") or {}).get("indexing_complete"):
                        raise RuntimeError("New source verification failed")
                updated["sources"][target["id"]] = target
                updated["active_source_id"] = target["id"]
                self.registry.update_project(project_path, updated)
            except BaseException:
                if target_store is not None:
                    try:
                        target_store.delete_repo(repo_id)
                    except Exception:
                        pass
                raise
        return {
            "status": "ok", "impact": plan["impact"], "from": source["id"],
            "to": target["id"], "chunks": chunks, "source_retained": True,
        }

    def migrate_backend(self, project_path: str, backend: str) -> Dict[str, Any]:
        project, source = self.registry.active_source(project_path)
        if source["backend"] == backend:
            return {"status": "ok", "changed": False, "active_source_id": source["id"]}
        payload = {"backend": backend}
        plan = self.plan_settings(project_path, payload)
        result = self.apply_project_settings(project_path, {**payload, "plan_hash": plan["plan_hash"]})
        return {**result, "changed": True}
