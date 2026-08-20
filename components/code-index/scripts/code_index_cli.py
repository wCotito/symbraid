from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from code_index.embeddings import Embedder
from code_index.locking import ProjectLock
from code_index.registry import Registry, app_root, normalize_project_path, project_id
from code_index.secrets import set_secret
from code_index.service import CodeIndexService


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def profile_set(registry: Registry, args) -> Dict[str, Any]:
    data = registry.load()
    profile = dict(data["profiles"].get(args.profile_id) or {})
    for name in ("provider", "model", "dimension", "base_url"):
        value = getattr(args, name)
        if value is not None:
            profile[name] = value
    if args.api_key_stdin:
        reference = f"embedding:{args.profile_id}"
        set_secret(reference, sys.stdin.read().rstrip("\r\n"))
        profile["secret_ref"] = reference
    profile.setdefault("provider", "fastembed")
    profile.setdefault("model", "jinaai/jina-embeddings-v2-base-code")
    profile.setdefault("dimension", 768)
    profile.setdefault("base_url", "")
    profile.setdefault("secret_ref", "")
    data["profiles"][args.profile_id] = profile
    registry.save(data)
    return {"status": "ok", "profile_id": args.profile_id, "profile": profile}


def add_kilo(service: CodeIndexService, args, backend: str) -> Dict[str, Any]:
    secret_ref = ""
    if backend == "qdrant" and args.qdrant_api_key_stdin:
        secret_ref = f"kilo-qdrant:{args.source_id}"
        set_secret(secret_ref, sys.stdin.read().rstrip("\r\n"))
    location = (
        {"url": args.url, "collection": args.collection, "secret_ref": secret_ref}
        if backend == "qdrant"
        else {"directory": args.directory}
    )
    source = {
        "id": args.source_id,
        "owner": "kilo",
        "backend": backend,
        "mode": "read-only",
        "embedding_profile": args.profile,
        "location": location,
    }
    return service.add_source(args.project, source, args.activate)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-index", description="Independent semantic code index")
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    register = project_commands.add_parser("register")
    register.add_argument("path")
    project_commands.add_parser("list")
    remove = project_commands.add_parser("remove")
    remove.add_argument("path")
    watch = project_commands.add_parser("watch")
    watch.add_argument("path")
    watch.add_argument("enabled", choices=("on", "off"))
    override = project_commands.add_parser("override")
    override.add_argument("path")
    override.add_argument("--embedding-profile")
    override.add_argument("--clear-embedding-profile", action="store_true")
    override.add_argument("--debounce-ms", type=int)
    override.add_argument("--bulk-change-threshold", type=int)
    source = commands.add_parser("source")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    for name in ("list", "detect"):
        child = source_commands.add_parser(name)
        child.add_argument("project")
    use = source_commands.add_parser("use")
    use.add_argument("project")
    use.add_argument("source_id")
    add_qdrant = source_commands.add_parser("add-kilo-qdrant")
    add_qdrant.add_argument("project")
    add_qdrant.add_argument("source_id")
    add_qdrant.add_argument("url")
    add_qdrant.add_argument("collection")
    add_qdrant.add_argument("--profile", required=True)
    add_qdrant.add_argument("--qdrant-api-key-stdin", action="store_true")
    add_qdrant.add_argument("--activate", action="store_true")
    add_lance = source_commands.add_parser("add-kilo-lancedb")
    add_lance.add_argument("project")
    add_lance.add_argument("source_id")
    add_lance.add_argument("directory")
    add_lance.add_argument("--profile", required=True)
    add_lance.add_argument("--activate", action="store_true")
    profile = commands.add_parser("profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_commands.add_parser("list")
    set_profile = profile_commands.add_parser("set")
    set_profile.add_argument("profile_id")
    set_profile.add_argument("--provider", choices=("fastembed", "openai-compatible"))
    set_profile.add_argument("--model")
    set_profile.add_argument("--dimension", type=int)
    set_profile.add_argument("--base-url")
    set_profile.add_argument("--api-key-stdin", action="store_true")
    test_profile = profile_commands.add_parser("test")
    test_profile.add_argument("profile_id")
    defaults = commands.add_parser("defaults")
    defaults_commands = defaults.add_subparsers(dest="defaults_command", required=True)
    defaults_commands.add_parser("show")
    set_defaults = defaults_commands.add_parser("set")
    set_defaults.add_argument("--backend", choices=("lancedb", "qdrant"))
    set_defaults.add_argument("--qdrant-url")
    set_defaults.add_argument("--qdrant-api-key-stdin", action="store_true")
    set_defaults.add_argument("--lancedb-root")
    set_defaults.add_argument("--embedding-profile")
    set_defaults.add_argument("--debounce-ms", type=int)
    set_defaults.add_argument("--bulk-change-threshold", type=int)
    index = commands.add_parser("index")
    index.add_argument("project")
    index.add_argument("--force", action="store_true")
    refresh = commands.add_parser("refresh")
    refresh.add_argument("project")
    refresh.add_argument("files", nargs="+")
    status = commands.add_parser("status")
    status.add_argument("project")
    search = commands.add_parser("search")
    search.add_argument("project")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--path-filter")
    migrate = commands.add_parser("migrate-backend")
    migrate.add_argument("project")
    migrate.add_argument("backend", choices=("lancedb", "qdrant"))
    commands.add_parser("mcp")
    return parser


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
            removed = data["projects"].pop(key, None) is not None
            registry.save(data)
            return {"status": "ok", "removed": removed, "index_retained": True}
        project = registry.project(args.path)
        if args.project_command == "watch":
            project["watch_enabled"] = args.enabled == "on"
            registry.update_project(args.path, project)
            return {"status": "ok", "watch_enabled": project["watch_enabled"]}
        if args.embedding_profile and args.embedding_profile not in data["profiles"]:
            raise KeyError(f"Profile does not exist: {args.embedding_profile}")
        if args.clear_embedding_profile:
            project.setdefault("overrides", {}).pop("embedding_profile", None)
            managed_profile = data["defaults"]["embedding_profile"]
        else:
            managed_profile = args.embedding_profile
        if managed_profile:
            for source_item in project.get("sources", {}).values():
                if source_item.get("owner") == "code-index":
                    source_item["embedding_profile"] = managed_profile
        mapping = {
            "embedding_profile": args.embedding_profile,
            "debounce_ms": args.debounce_ms,
            "bulk_change_threshold": args.bulk_change_threshold,
        }
        project.setdefault("overrides", {}).update(
            {key: value for key, value in mapping.items() if value is not None}
        )
        registry.update_project(args.path, project)
        return {"status": "ok", "overrides": project["overrides"]}
    if args.command == "source":
        if args.source_command == "list":
            return service.list_sources(args.project)
        if args.source_command == "detect":
            return service.detect_kilo(args.project)
        if args.source_command == "use":
            return service.use_source(args.project, args.source_id)
        return add_kilo(service, args, "qdrant" if args.source_command == "add-kilo-qdrant" else "lancedb")
    if args.command == "profile":
        if args.profile_command == "list":
            return {"status": "ok", "profiles": registry.load()["profiles"]}
        if args.profile_command == "set":
            return profile_set(registry, args)
        data = registry.load()
        profile = data["profiles"].get(args.profile_id)
        if profile is None:
            raise KeyError(f"Profile does not exist: {args.profile_id}")
        synthetic = {"path": str(PROJECT_ROOT), "project_id": "profile-test", "overrides": {}}
        source = {
            "backend": "lancedb",
            "embedding_profile": args.profile_id,
            "location": {"directory": str(PROJECT_ROOT / ".profile-test")},
        }
        from code_index.secrets import get_secret
        config = registry.resolved_config(
            synthetic, source, embedding_secret=get_secret(profile.get("secret_ref", ""))
        )
        vector = Embedder(config).embed_query("Code Index profile connectivity test")
        return {"status": "ok", "profile_id": args.profile_id, "dimension": len(vector)}
    if args.command == "defaults":
        data = registry.load()
        if args.defaults_command == "show":
            return {"status": "ok", "defaults": data["defaults"]}
        mapping = {
            "backend": args.backend,
            "qdrant_url": args.qdrant_url,
            "lancedb_root": args.lancedb_root,
            "embedding_profile": args.embedding_profile,
            "debounce_ms": args.debounce_ms,
            "bulk_change_threshold": args.bulk_change_threshold,
        }
        if args.qdrant_api_key_stdin:
            reference = "qdrant:default"
            set_secret(reference, sys.stdin.read().rstrip("\r\n"))
            data["defaults"]["qdrant_secret_ref"] = reference
        data["defaults"].update({key: value for key, value in mapping.items() if value is not None})
        registry.save(data)
        return {"status": "ok", "defaults": data["defaults"]}
    if args.command == "index":
        return service.index(args.project, args.force)
    if args.command == "refresh":
        return service.refresh(args.project, args.files)
    if args.command == "status":
        return service.status(args.project)
    if args.command == "search":
        return service.search(args.query, args.project, args.top_k, args.path_filter)
    if args.command == "migrate-backend":
        return service.migrate_backend(args.project, args.backend)
    if args.command == "mcp":
        from mcp_gateway import run_mcp
        run_mcp()
        return None
    raise RuntimeError("Unknown command")


def main() -> int:
    args = build_parser().parse_args()
    try:
        lock_key = None
        lock_path = None
        if args.command == "project" and args.project_command != "list":
            lock_path = args.path
        elif args.command == "source" and args.source_command not in {"list", "detect"}:
            lock_path = args.project
        elif args.command == "migrate-backend":
            lock_path = args.project
        elif args.command == "profile" and args.profile_command == "set":
            lock_key = "global-profile-config"
        elif args.command == "defaults" and args.defaults_command == "set":
            lock_key = "global-default-config"
        lock_key = lock_key or (project_id(lock_path) if lock_path else None)
        if lock_key:
            with ProjectLock(app_root() / "locks", lock_key, 120):
                result = run(args)
        else:
            result = run(args)
        if result is not None:
            emit(result)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
