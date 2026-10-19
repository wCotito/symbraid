from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Config
from .paths import app_paths


SCHEMA_VERSION = 4
PREVIOUS_SCHEMA_VERSION = 3
OLD_DEBOUNCE_DEFAULT_MS = 1500
DEFAULT_DEBOUNCE_MS = 5000
# Leave 100 UTF-16 code units under MAX_PATH for Lance table, data,
# transaction (including a u64 version), and temporary file names.
WINDOWS_LANCEDB_DIRECTORY_LIMIT = 160
INDEX_RECIPE_KEYS = ("max_file_bytes", "chunk_chars", "chunk_overlap_chars", "rg_path")
PROJECT_OVERRIDE_KEYS = (
    "backend", "embedding_profile", "qdrant_url", "qdrant_secret_ref", "lancedb_root",
    "debounce_ms", "bulk_change_threshold", "max_file_bytes", "chunk_chars",
    "chunk_overlap_chars", "batch_size", "rg_path",
)


def normalize_project_path(value: str) -> str:
    resolved = str(Path(value).expanduser().resolve()).replace("\\", "/").rstrip("/")
    return resolved.casefold() if os.name == "nt" else resolved


def project_id(value: str) -> str:
    return hashlib.sha256(normalize_project_path(value).encode("utf-8")).hexdigest()[:16]


def default_registry() -> Dict[str, Any]:
    paths = app_paths()
    return {
        "schema_version": SCHEMA_VERSION,
        "defaults": {
            "backend": "lancedb",
            "embedding_profile": "default-code",
            "qdrant_url": "http://127.0.0.1:18133",
            "qdrant_secret_ref": "",
            "lancedb_root": str(paths.data / "lancedb"),
            "debounce_ms": DEFAULT_DEBOUNCE_MS,
            "bulk_change_threshold": 100,
            "max_file_bytes": 1048576,
            "chunk_chars": 1600,
            "chunk_overlap_chars": 200,
            "batch_size": 32,
            "rg_path": "rg",
        },
        "profiles": {
            "default-code": {
                "display_name": "Default code",
                "scope": "global",
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
        self.path = path or app_paths().registry

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return default_registry()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        version = int(raw.get("schema_version", 0))
        if version == PREVIOUS_SCHEMA_VERSION:
            raw = copy.deepcopy(raw)
            defaults = raw.setdefault("defaults", {})
            if defaults.get("debounce_ms") == OLD_DEBOUNCE_DEFAULT_MS:
                defaults["debounce_ms"] = DEFAULT_DEBOUNCE_MS
            raw["schema_version"] = SCHEMA_VERSION
            self.save(raw)
            version = SCHEMA_VERSION
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported Symbraid config schema: {version}")
        merged = default_registry()
        merged["defaults"].update(raw.get("defaults") or {})
        merged["profiles"].update(raw.get("profiles") or {})
        merged["projects"].update(raw.get("projects") or {})
        return merged

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = copy.deepcopy(data)
        value["schema_version"] = SCHEMA_VERSION
        handle, temporary = tempfile.mkstemp(prefix="config-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def preview_project(self, project_path: str) -> Dict[str, Any]:
        """Describe an unregistered project without preparing or validating storage."""
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        return {
            "path": str(root), "project_id": project_id(str(root)), "auto_watch": False,
            "active_source_id": None, "overrides": {}, "sources": {},
        }

    def prepare_project(
        self, project_path: str, overrides: Optional[Dict[str, Any]] = None, auto_watch: bool = False,
    ) -> Dict[str, Any]:
        """Build a new project's configuration without persisting or opening a store."""
        project = self.preview_project(project_path)
        data = self.load()
        overrides = {key: value for key, value in (overrides or {}).items() if key in PROJECT_OVERRIDE_KEYS}
        settings = {**data["defaults"], **overrides}
        source_id = f"managed-{settings['backend']}-{uuid.uuid4().hex}"
        source = self._managed_source(data, project["project_id"], settings["backend"], source_id=source_id, settings=settings)
        return {
            **project, "auto_watch": bool(auto_watch),
            "active_source_id": source["id"], "overrides": overrides, "sources": {source["id"]: source},
        }

    def register_project(
        self, project_path: str, overrides: Optional[Dict[str, Any]] = None, auto_watch: bool = False,
    ) -> Dict[str, Any]:
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        data = self.load()
        key = normalize_project_path(str(root))
        if key in data["projects"]:
            return data["projects"][key]
        project = self.prepare_project(project_path, overrides, auto_watch)
        source = project["sources"][project["active_source_id"]]
        profile = data["profiles"].get(source["embedding_profile"])
        if profile is None:
            raise ValueError(f"Embedding profile does not exist: {source['embedding_profile']}")
        if profile.get("scope") == "project" and profile.get("project_id") != project["project_id"]:
            raise ValueError("Embedding profile belongs to another project")
        self.resolved_config(project, source)
        data["projects"][key] = project
        self.save(data)
        return project

    def _managed_source(
        self, data: Dict[str, Any], identifier: str, backend: str,
        source_id: Optional[str] = None, settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        values = {**default_registry()["defaults"], **data.get("defaults", {}), **(settings or {})}
        source_id = source_id or f"managed-{backend}-{uuid.uuid4().hex}"
        token = source_id.rsplit("-", 1)[-1]
        if backend == "qdrant":
            location = {
                "url": values["qdrant_url"],
                "collection": f"symbraid-{identifier}-{token}",
                "secret_ref": values.get("qdrant_secret_ref", ""),
            }
        else:
            # A full UUID preserves source isolation without repeating the
            # potentially long project basename and project hash on disk.
            directory = Path(values["lancedb_root"]).expanduser() / uuid.UUID(hex=token).hex
            if os.name == "nt":
                length = len(str(directory.resolve()).encode("utf-16-le")) // 2
                if length > WINDOWS_LANCEDB_DIRECTORY_LIMIT:
                    raise ValueError(
                        f"Resolved LanceDB directory is too long for Windows "
                        f"({length} > {WINDOWS_LANCEDB_DIRECTORY_LIMIT} UTF-16 code units); "
                        "choose a shorter lancedb_root"
                    )
            location = {"directory": str(directory)}
        return {
            "id": source_id,
            "backend": backend,
            "embedding_profile": values["embedding_profile"],
            "location": location,
            "recipe": {key: values[key] for key in INDEX_RECIPE_KEYS},
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

    def resolved_settings(self, project: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load()
        return {**data["defaults"], **(project.get("overrides") or {})}

    def resolved_config(
        self, project: Dict[str, Any], source: Dict[str, Any],
        embedding_secret: str = "", qdrant_secret: str = "",
    ) -> Config:
        data = self.load()
        values = self.resolved_settings(project)
        values.update(source.get("recipe") or {})
        profile_id = source.get("embedding_profile") or values["embedding_profile"]
        profile = data["profiles"].get(profile_id)
        if profile is None:
            raise ValueError(f"Embedding profile does not exist: {profile_id}")
        location = source.get("location") or {}
        paths = app_paths()
        config_values = {
            **values,
            "backend": source["backend"],
            "qdrant_url": location.get("url", values["qdrant_url"]),
            "qdrant_api_key": qdrant_secret if source["backend"] == "qdrant" else "",
            "collection": location.get("collection", ""),
            "lancedb_path": location.get("directory", ""),
            "embedding_provider": profile["provider"],
            "embedding_model": profile["model"],
            "embedding_dimension": profile["dimension"],
            "embedding_base_url": profile.get("base_url", ""),
            "embedding_api_key": embedding_secret if profile.get("secret_ref") else "",
            "model_cache": paths.cache / "models",
            "lock_dir": paths.locks,
        }
        config = Config.from_mapping(config_values)
        config.validate()
        return config
