from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from code_index.config import Config
from code_index.embeddings import Embedder
from code_index.locking import ProjectLock
from code_index.registry import PROJECT_OVERRIDE_KEYS, Registry, app_root, normalize_project_path, project_id
from code_index.secrets import get_secret, set_secret
from code_index.service import CodeIndexService


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def stdin_json() -> Dict[str, Any]:
    value = json.loads(sys.stdin.read() or "{}")
    if not isinstance(value, dict):
        raise ValueError("stdin JSON must be an object")
    return value


def profile_set(registry: Registry, args, values: Dict[str, Any] | None = None) -> Dict[str, Any]:
    values = values or {}
    profile_id = values.get("profile_id") or args.profile_id
    data = registry.load()
    profile = dict(data["profiles"].get(profile_id) or {})
    for name in ("display_name", "scope", "project_id", "provider", "model", "dimension", "base_url"):
        value = values.get(name, getattr(args, name, None))
        if value is not None:
            profile[name] = value
    api_key = values.get("api_key")
    if getattr(args, "api_key_stdin", False):
        api_key = sys.stdin.read().rstrip("\r\n")
    if api_key is not None:
        reference = f"embedding:{profile_id}"
        set_secret(reference, str(api_key))
        profile["secret_ref"] = reference if api_key else ""
    profile.setdefault("display_name", profile_id)
    profile.setdefault("scope", "global")
    profile.setdefault("provider", "fastembed")
    profile.setdefault("model", "jinaai/jina-embeddings-v2-base-code")
    profile.setdefault("dimension", 768)
    profile.setdefault("base_url", "")
    profile.setdefault("secret_ref", "")
    if profile["scope"] == "project" and not profile.get("project_id"):
        raise ValueError("project-scoped profile requires project_id")
    if profile["provider"] not in {"fastembed", "openai-compatible"}:
        raise ValueError("Unsupported embedding provider")
    if int(profile["dimension"]) <= 0:
        raise ValueError("dimension must be positive")
    if profile["provider"] == "openai-compatible" and not profile.get("base_url"):
        raise ValueError("base_url is required for openai-compatible profiles")
    data["profiles"][profile_id] = profile
    registry.save(data)
    public = {k: v for k, v in profile.items() if k != "secret_ref"}
    public["api_key_configured"] = bool(profile.get("secret_ref"))
    return {"status": "ok", "profile_id": profile_id, "profile": public}


def prepare_project_payload(registry: Registry, path: str, payload: Dict[str, Any], store: bool) -> Dict[str, Any]:
    value = dict(payload)
    if "qdrant_api_key" in value or value.get("clear_qdrant_api_key"):
        reference = f"qdrant:project:{project_id(path)}"
        if store and "qdrant_api_key" in value:
            set_secret(reference, str(value["qdrant_api_key"]))
        value["qdrant_secret_ref"] = "" if value.get("clear_qdrant_api_key") else reference
    value.pop("qdrant_api_key", None)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-index", description="Independent semantic code index")
    commands = parser.add_subparsers(dest="command", required=True)

    project = commands.add_parser("project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    register = project_commands.add_parser("register"); register.add_argument("path")
    project_commands.add_parser("list")
    remove = project_commands.add_parser("remove"); remove.add_argument("path")
    watch = project_commands.add_parser("watch"); watch.add_argument("path"); watch.add_argument("enabled", choices=("on", "off"))
    override = project_commands.add_parser("override"); override.add_argument("path")
    for key in PROJECT_OVERRIDE_KEYS:
        option = "--" + key.replace("_", "-")
        if key in {"debounce_ms", "bulk_change_threshold", "max_file_bytes", "chunk_chars", "chunk_overlap_chars", "batch_size"}:
            override.add_argument(option, type=int)
        elif key != "qdrant_secret_ref":
            override.add_argument(option)
    override.add_argument("--clear", action="append", choices=PROJECT_OVERRIDE_KEYS, default=[])
    override.add_argument("--clear-embedding-profile", action="store_true")

    source = commands.add_parser("source")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    listing = source_commands.add_parser("list"); listing.add_argument("project")
    use = source_commands.add_parser("use"); use.add_argument("project"); use.add_argument("source_id")

    profile = commands.add_parser("profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_commands.add_parser("list")
    set_profile = profile_commands.add_parser("set"); set_profile.add_argument("profile_id")
    set_profile.add_argument("--display-name"); set_profile.add_argument("--scope", choices=("global", "project")); set_profile.add_argument("--project-id")
    set_profile.add_argument("--provider", choices=("fastembed", "openai-compatible")); set_profile.add_argument("--model")
    set_profile.add_argument("--dimension", type=int); set_profile.add_argument("--base-url"); set_profile.add_argument("--api-key-stdin", action="store_true")
    test_profile = profile_commands.add_parser("test"); test_profile.add_argument("profile_id")
    profile_commands.add_parser("test-config")
    delete_profile = profile_commands.add_parser("delete"); delete_profile.add_argument("profile_id")

    defaults = commands.add_parser("defaults")
    defaults_commands = defaults.add_subparsers(dest="defaults_command", required=True)
    defaults_commands.add_parser("show")
    set_defaults = defaults_commands.add_parser("set")
    set_defaults.add_argument("--backend", choices=("lancedb", "qdrant")); set_defaults.add_argument("--qdrant-url")
    set_defaults.add_argument("--qdrant-api-key-stdin", action="store_true"); set_defaults.add_argument("--lancedb-root")
    set_defaults.add_argument("--embedding-profile"); set_defaults.add_argument("--debounce-ms", type=int)
    set_defaults.add_argument("--bulk-change-threshold", type=int); set_defaults.add_argument("--max-file-bytes", type=int)
    set_defaults.add_argument("--chunk-chars", type=int); set_defaults.add_argument("--chunk-overlap-chars", type=int)
    set_defaults.add_argument("--batch-size", type=int); set_defaults.add_argument("--rg-path")

    settings = commands.add_parser("settings")
    settings_commands = settings.add_subparsers(dest="settings_command", required=True)
    show = settings_commands.add_parser("show"); show.add_argument("--project")
    plan = settings_commands.add_parser("plan"); plan.add_argument("project")
    apply_project = settings_commands.add_parser("apply-project"); apply_project.add_argument("project")
    settings_commands.add_parser("apply-defaults")
    settings_commands.add_parser("test-backend")

    index = commands.add_parser("index"); index.add_argument("project"); index.add_argument("--force", action="store_true")
    refresh = commands.add_parser("refresh"); refresh.add_argument("project"); refresh.add_argument("files", nargs="+")
    status = commands.add_parser("status"); status.add_argument("project")
    search = commands.add_parser("search"); search.add_argument("project"); search.add_argument("query")
    search.add_argument("--top-k", type=int, default=10); search.add_argument("--path-filter")
    migrate = commands.add_parser("migrate-backend"); migrate.add_argument("project"); migrate.add_argument("backend", choices=("lancedb", "qdrant"))
    commands.add_parser("mcp")
    return parser


def test_profile_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    config = Config.from_mapping({
        "backend": "lancedb", "lancedb_path": PROJECT_ROOT / ".profile-test",
        "embedding_provider": payload.get("provider", "fastembed"),
        "embedding_model": payload.get("model", "jinaai/jina-embeddings-v2-base-code"),
        "embedding_dimension": int(payload.get("dimension", 768)),
        "embedding_base_url": payload.get("base_url", ""),
        "embedding_api_key": payload.get("api_key", ""),
    })
    config.validate()
    vector = Embedder(config).embed_query("Code Index profile connectivity test")
    return {"status": "ok", "dimension": len(vector)}


def validate_defaults(data: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    profile = data["profiles"].get(candidate.get("embedding_profile"))
    if profile is None:
        raise KeyError(f"Profile does not exist: {candidate.get('embedding_profile')}")
    config = Config.from_mapping({
        **candidate,
        "collection": "settings-validation",
        "lancedb_path": Path(candidate["lancedb_root"]) / "settings-validation",
        "embedding_provider": profile["provider"], "embedding_model": profile["model"],
        "embedding_dimension": profile["dimension"], "embedding_base_url": profile.get("base_url", ""),
    })
    config.validate()
    if int(candidate["debounce_ms"]) < 100:
        raise ValueError("debounce_ms must be at least 100")
    if int(candidate["bulk_change_threshold"]) < 1 or int(candidate["batch_size"]) < 1:
        raise ValueError("bulk_change_threshold and batch_size must be positive")


def run(args) -> Any:
    registry = Registry()
    service = CodeIndexService(registry)
    if args.command == "project":
        if args.project_command == "register":
            return {"status": "ok", "project": registry.register_project(args.path)}
        data = registry.load()
        if args.project_command == "list":
            return {"status": "ok", "projects": list(data["projects"].values())}
        key = normalize_project_path(args.path)
        if args.project_command == "remove":
            removed = data["projects"].pop(key, None) is not None; registry.save(data)
            return {"status": "ok", "removed": removed, "index_retained": True}
        project = registry.project(args.path)
        if args.project_command == "watch":
            project["watch_enabled"] = args.enabled == "on"; registry.update_project(args.path, project)
            return {"status": "ok", "watch_enabled": project["watch_enabled"]}
        overrides = project.setdefault("overrides", {})
        clears = set(args.clear)
        if args.clear_embedding_profile:
            clears.add("embedding_profile")
        for name in clears:
            overrides.pop(name, None)
        for name in PROJECT_OVERRIDE_KEYS:
            value = getattr(args, name, None)
            if value is not None:
                overrides[name] = value
        registry.update_project(args.path, project)
        return {"status": "ok", "overrides": overrides}

    if args.command == "source":
        return service.list_sources(args.project) if args.source_command == "list" else service.use_source(args.project, args.source_id)

    if args.command == "profile":
        data = registry.load()
        if args.profile_command == "list":
            return {"status": "ok", "profiles": service.settings_state()["profiles"]}
        if args.profile_command == "set":
            return profile_set(registry, args)
        if args.profile_command == "test-config":
            return test_profile_config(stdin_json())
        if args.profile_command == "delete":
            if args.profile_id == data["defaults"]["embedding_profile"]:
                raise ValueError("Cannot delete the default profile")
            used = [p["path"] for p in data["projects"].values() if any(s.get("embedding_profile") == args.profile_id for s in p["sources"].values())]
            if used:
                raise ValueError(f"Profile is used by projects: {used}")
            removed = data["profiles"].pop(args.profile_id, None) is not None; registry.save(data)
            return {"status": "ok", "removed": removed}
        profile = data["profiles"].get(args.profile_id)
        if profile is None:
            raise KeyError(f"Profile does not exist: {args.profile_id}")
        return test_profile_config({**profile, "api_key": get_secret(profile.get("secret_ref", ""))})

    if args.command == "defaults":
        data = registry.load()
        if args.defaults_command == "show":
            return {"status": "ok", "defaults": service.settings_state()["defaults"]}
        mapping = {name: getattr(args, name) for name in (
            "backend", "qdrant_url", "lancedb_root", "embedding_profile", "debounce_ms",
            "bulk_change_threshold", "max_file_bytes", "chunk_chars", "chunk_overlap_chars", "batch_size", "rg_path",
        )}
        if args.qdrant_api_key_stdin:
            reference = "qdrant:default"; set_secret(reference, sys.stdin.read().rstrip("\r\n")); data["defaults"]["qdrant_secret_ref"] = reference
        candidate = {**data["defaults"], **{k: v for k, v in mapping.items() if v is not None}}
        validate_defaults(data, candidate)
        data["defaults"] = candidate; registry.save(data)
        return {"status": "ok", "defaults": service.settings_state()["defaults"]}

    if args.command == "settings":
        if args.settings_command == "show":
            return service.settings_state(args.project)
        payload = stdin_json()
        if args.settings_command == "plan":
            return service.plan_settings(args.project, prepare_project_payload(registry, args.project, payload, False))
        if args.settings_command == "apply-project":
            prepared = prepare_project_payload(registry, args.project, payload, True)
            return service.apply_project_settings(args.project, prepared)
        if args.settings_command == "apply-defaults":
            data = registry.load()
            if "qdrant_api_key" in payload:
                reference = "qdrant:default"; set_secret(reference, str(payload.pop("qdrant_api_key"))); payload["qdrant_secret_ref"] = reference
            if payload.pop("clear_qdrant_api_key", False):
                payload["qdrant_secret_ref"] = ""
            allowed = set(data["defaults"])
            candidate = {**data["defaults"], **{k: v for k, v in payload.items() if k in allowed}}
            validate_defaults(data, candidate)
            data["defaults"] = candidate
            registry.save(data)
            return {"status": "ok", "defaults": service.settings_state()["defaults"]}
        backend = payload.get("backend", "lancedb")
        if backend == "lancedb":
            root = Path(payload.get("lancedb_root", app_root() / "data/lancedb")).expanduser()
            parent = root if root.exists() else root.parent
            if not parent.exists():
                raise ValueError(f"LanceDB parent directory does not exist: {parent}")
            return {"status": "ok", "backend": backend, "path": str(root.resolve())}
        url = str(payload.get("qdrant_url", "")).rstrip("/")
        request = urllib.request.Request(url + "/collections")
        if payload.get("qdrant_api_key"):
            request.add_header("api-key", str(payload["qdrant_api_key"]))
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"status": "ok", "backend": backend, "http_status": response.status}

    if args.command == "index": return service.index(args.project, args.force)
    if args.command == "refresh": return service.refresh(args.project, args.files)
    if args.command == "status": return service.status(args.project)
    if args.command == "search": return service.search(args.query, args.project, args.top_k, args.path_filter)
    if args.command == "migrate-backend": return service.migrate_backend(args.project, args.backend)
    if args.command == "mcp":
        from mcp_gateway import run_mcp
        run_mcp(); return None
    raise RuntimeError("Unknown command")


def main() -> int:
    args = build_parser().parse_args()
    try:
        lock_key = None; lock_path = None
        if args.command == "project" and args.project_command != "list": lock_path = args.path
        elif args.command == "source" and args.source_command == "use": lock_path = args.project
        elif args.command == "migrate-backend": lock_path = args.project
        elif args.command == "settings" and args.settings_command in {"apply-project"}: lock_path = args.project
        elif args.command == "profile" and args.profile_command in {"set", "delete"}: lock_key = "global-profile-config"
        elif args.command == "defaults" and args.defaults_command == "set": lock_key = "global-default-config"
        elif args.command == "settings" and args.settings_command == "apply-defaults": lock_key = "global-default-config"
        lock_key = lock_key or (project_id(lock_path) if lock_path else None)
        if lock_key:
            with ProjectLock(app_root() / "locks", lock_key, 120): result = run(args)
        else: result = run(args)
        if result is not None: emit(result)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
