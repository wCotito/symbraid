from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Config
from .paths import app_paths, legacy_app_root


SCHEMA_VERSION = 3
INDEX_RECIPE_KEYS = ("max_file_bytes", "chunk_chars", "chunk_overlap_chars", "rg_path")
PROJECT_OVERRIDE_KEYS = (
    "backend", "embedding_profile", "qdrant_url", "qdrant_secret_ref", "lancedb_root",
    "debounce_ms", "bulk_change_threshold", "max_file_bytes", "chunk_chars",
    "chunk_overlap_chars", "batch_size", "rg_path",
)


def app_root() -> Path:
    """Compatibility helper. New code should use app_paths()."""
    return app_paths().data


def normalize_project_path(value: str) -> str:
    resolved = str(Path(value).expanduser().resolve()).replace("\\", "/").rstrip("/")
    return resolved.casefold() if os.name == "nt" else resolved


def project_id(value: str) -> str:
    return hashlib.sha256(normalize_project_path(value).encode("utf-8")).hexdigest()[:16]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "project"


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
            "debounce_ms": 1500,
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
        self._default_path = path is None
        self.path = path or app_paths().registry
        if self._default_path:
            self._import_legacy_registry()

    def _import_legacy_registry(self) -> None:
        """Copy, never move, the legacy registry before schema migration."""
        legacy_root = legacy_app_root()
        legacy = legacy_root / "config.json" if legacy_root else None
        if self.path.exists() or legacy is None or not legacy.is_file():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, self.path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return default_registry()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        version = int(raw.get("schema_version", 1))
        if version == 1:
            raw = self._migrate_v1(raw)
            version = 2
        if version == 2:
            raw = self._migrate_v2(raw)
            version = 3
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported Symbraid config schema: {version}")
        if int(raw.get("schema_version", 0)) != SCHEMA_VERSION:
            raw["schema_version"] = SCHEMA_VERSION
        if not self.path.exists() or json.loads(self.path.read_text(encoding="utf-8")).get("schema_version") != SCHEMA_VERSION:
            self.save(raw)
        merged = default_registry()
        merged["defaults"].update(raw.get("defaults") or {})
        merged["profiles"].update(raw.get("profiles") or {})
        merged["projects"].update(raw.get("projects") or {})
        return merged

    def _backup(self, version: int) -> None:
        backup = self.path.with_name(self.path.name + f".v{version}.bak")
        if not self.path.exists() or backup.exists():
            return
        current = json.loads(self.path.read_text(encoding="utf-8"))
        if int(current.get("schema_version", 1)) == version:
            shutil.copy2(self.path, backup)

    def _migrate_v1(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        self._backup(1)
        data = copy.deepcopy(raw)
        defaults = data.setdefault("defaults", {})
        defaults.pop("kilo_lancedb_roots", None)
        base = default_registry()
        resolved_defaults = {**base["defaults"], **defaults}
        for profile_id, profile in (data.setdefault("profiles", {}) or {}).items():
            profile.setdefault("display_name", profile_id)
            profile.setdefault("scope", "global")
        for project in (data.setdefault("projects", {}) or {}).values():
            root = Path(project["path"])
            identifier = project.get("project_id") or project_id(str(root))
            overrides = {k: v for k, v in (project.get("overrides") or {}).items() if k in PROJECT_OVERRIDE_KEYS}
            effective = {**resolved_defaults, **overrides}
            sources: Dict[str, Any] = {}
            for source_id, source in (project.get("sources") or {}).items():
                owner = source.get("owner", "code-index")
                if owner not in {"code-index", "symbraid"} or source.get("mode", "read-write") == "read-only":
                    continue
                managed = copy.deepcopy(source)
                managed.pop("owner", None)
                managed.pop("mode", None)
                managed.setdefault("id", source_id)
                managed.setdefault("embedding_profile", effective["embedding_profile"])
                managed.setdefault("recipe", {key: effective[key] for key in INDEX_RECIPE_KEYS})
                sources[source_id] = managed
            active = project.get("active_source_id")
            if active not in sources:
                preferred = f"managed-{resolved_defaults['backend']}"
                if preferred in sources:
                    active = preferred
                elif sources:
                    active = sorted(sources)[0]
                else:
                    created = self._managed_source(data, root, identifier, resolved_defaults["backend"])
                    sources[created["id"]] = created
                    active = created["id"]
                project["watch_enabled"] = False
            project.update({
                "project_id": identifier,
                "sources": sources,
                "active_source_id": active,
                "overrides": overrides,
            })
        data["schema_version"] = 2
        return data

    def _migrate_v2(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        self._backup(2)
        data = copy.deepcopy(raw)
        migrated: Dict[str, Any] = {}
        for project in (data.setdefault("projects", {}) or {}).values():
            item = copy.deepcopy(project)
            item["auto_watch"] = bool(item.pop("watch_enabled", item.get("auto_watch", False)))
            key = normalize_project_path(item["path"])
            if key in migrated:
                previous = migrated[key]
                raise ValueError(
                    "Project path collision during schema v3 migration: "
                    f"{previous.get('path')} and {item['path']} both normalize to {key}"
                )
            migrated[key] = item
        data["projects"] = migrated
        data["schema_version"] = SCHEMA_VERSION
        return data

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

    def register_project(self, project_path: str) -> Dict[str, Any]:
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        data = self.load()
        key = normalize_project_path(str(root))
        if key in data["projects"]:
            return data["projects"][key]
        identifier = project_id(str(root))
        source = self._managed_source(data, root, identifier, data["defaults"]["backend"])
        project = {
            "path": str(root), "project_id": identifier, "auto_watch": False,
            "active_source_id": source["id"], "overrides": {}, "sources": {source["id"]: source},
        }
        data["projects"][key] = project
        self.save(data)
        return project

    def _managed_source(
        self, data: Dict[str, Any], root: Path, identifier: str, backend: str,
        source_id: Optional[str] = None, settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        values = {**default_registry()["defaults"], **data.get("defaults", {}), **(settings or {})}
        source_id = source_id or f"managed-{backend}"
        suffix = "" if source_id == f"managed-{backend}" else f"-{source_id.rsplit('-', 1)[-1]}"
        if backend == "qdrant":
            location = {
                "url": values["qdrant_url"],
                "collection": f"symbraid-{identifier}{suffix}",
                "secret_ref": values.get("qdrant_secret_ref", ""),
            }
        else:
            directory = Path(values["lancedb_root"]) / f"{safe_name(root.name)}-{identifier}{suffix}"
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
