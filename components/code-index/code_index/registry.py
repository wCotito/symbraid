from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Config


SCHEMA_VERSION = 1


def app_root() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    return local / "CodeIndex"


def normalize_project_path(value: str) -> str:
    resolved = str(Path(value).expanduser().resolve()).replace("\\", "/").rstrip("/")
    return resolved.casefold() if os.name == "nt" else resolved


def project_id(value: str) -> str:
    return hashlib.sha256(normalize_project_path(value).encode("utf-8")).hexdigest()[:16]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "project"


def default_registry() -> Dict[str, Any]:
    root = app_root()
    return {
        "schema_version": SCHEMA_VERSION,
        "defaults": {
            "backend": "lancedb",
            "embedding_profile": "default-code",
            "qdrant_url": "http://127.0.0.1:18133",
            "qdrant_secret_ref": "",
            "lancedb_root": str(root / "data" / "lancedb"),
            "debounce_ms": 1500,
            "bulk_change_threshold": 100,
            "max_file_bytes": 1048576,
            "chunk_chars": 1600,
            "chunk_overlap_chars": 200,
            "batch_size": 32,
            "rg_path": str(Path.home() / "scoop" / "shims" / "rg.exe"),
            "kilo_lancedb_roots": [],
        },
        "profiles": {
            "default-code": {
                "provider": "fastembed",
                "model": "jinaai/jina-embeddings-v2-base-code",
                "dimension": 768,
                "base_url": "",
                "secret_ref": "",
            }
        },
        "projects": {},
    }


class Registry:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or app_root() / "config.json"

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return default_registry()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported Code Index config schema: {data.get('schema_version')}")
        merged = default_registry()
        merged["defaults"].update(data.get("defaults") or {})
        merged["profiles"].update(data.get("profiles") or {})
        merged["projects"].update(data.get("projects") or {})
        return merged

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = copy.deepcopy(data)
        data["schema_version"] = SCHEMA_VERSION
        handle, temporary = tempfile.mkstemp(prefix="config-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def register_project(self, project_path: str) -> Dict[str, Any]:
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        data = self.load()
        key = normalize_project_path(str(root))
        existing = data["projects"].get(key)
        if existing:
            return existing
        identifier = project_id(str(root))
        backend = data["defaults"]["backend"]
        source_id = f"managed-{backend}"
        project = {
            "path": str(root),
            "project_id": identifier,
            "watch_enabled": False,
            "active_source_id": source_id,
            "overrides": {},
            "sources": {
                source_id: self._managed_source(data, root, identifier, backend),
            },
        }
        data["projects"][key] = project
        self.save(data)
        return project

    def _managed_source(self, data: Dict[str, Any], root: Path, identifier: str, backend: str) -> Dict[str, Any]:
        if backend == "qdrant":
            location = {
                "url": data["defaults"]["qdrant_url"],
                "collection": f"code-index-{identifier}",
                "secret_ref": data["defaults"].get("qdrant_secret_ref", ""),
            }
        else:
            directory = Path(data["defaults"]["lancedb_root"]) / f"{safe_name(root.name)}-{identifier}"
            location = {"directory": str(directory)}
        return {
            "id": f"managed-{backend}",
            "owner": "code-index",
            "backend": backend,
            "mode": "read-write",
            "embedding_profile": data["defaults"]["embedding_profile"],
            "location": location,
        }

    def project(self, project_path: str, create: bool = False) -> Dict[str, Any]:
        data = self.load()
        project = data["projects"].get(normalize_project_path(project_path))
        if project is None and create:
            return self.register_project(project_path)
        if project is None:
            raise KeyError(f"Project is not registered: {Path(project_path).resolve()}")
        return project

    def update_project(self, project_path: str, project: Dict[str, Any]) -> None:
        data = self.load()
        key = normalize_project_path(project_path)
        if key not in data["projects"]:
            raise KeyError(f"Project is not registered: {project_path}")
        data["projects"][key] = project
        self.save(data)

    def active_source(self, project_path: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        project = self.project(project_path)
        source = project["sources"].get(project.get("active_source_id"))
        if source is None:
            raise ValueError("Project has no valid active source")
        return project, source

    def resolved_config(
        self,
        project: Dict[str, Any],
        source: Dict[str, Any],
        embedding_secret: str = "",
        qdrant_secret: str = "",
    ) -> Config:
        data = self.load()
        defaults = dict(data["defaults"])
        defaults.update(project.get("overrides") or {})
        profile_id = source.get("embedding_profile") or defaults["embedding_profile"]
        profile = data["profiles"].get(profile_id)
        if profile is None:
            raise ValueError(f"Embedding profile does not exist: {profile_id}")
        location = source.get("location") or {}
        values = {
            **defaults,
            "backend": source["backend"],
            "qdrant_url": location.get("url", defaults["qdrant_url"]),
            "qdrant_api_key": qdrant_secret if source["backend"] == "qdrant" else "",
            "collection": location.get("collection", ""),
            "lancedb_path": location.get("directory", ""),
            "embedding_provider": profile["provider"],
            "embedding_model": profile["model"],
            "embedding_dimension": profile["dimension"],
            "embedding_base_url": profile.get("base_url", ""),
            "embedding_api_key": embedding_secret if profile.get("secret_ref") else "",
            "model_cache": app_root() / "models",
            "lock_dir": app_root() / "locks",
        }
        config = Config.from_mapping(values)
        config.validate()
        return config
