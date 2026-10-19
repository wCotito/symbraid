"""Isolated core state/plan/apply bridge for the real Manage browser test.

Run with Python -S: configuration preview and registration need only stdlib,
and must not require a database, model, keyring, or watcher.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

repository = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repository / "components" / "symbraid" / "src"))
fixture = Path(sys.argv[1]).resolve()
os.environ["SYMBRAID_HOME"] = str(fixture / "home")

from symbraid.registry import Registry, default_registry
from symbraid.service import SymbraidService

project_root = fixture / "workspace"
registry = Registry(fixture / "config.json")
service = SymbraidService(registry)
operation = sys.argv[2]
if operation == "init":
    project_root.mkdir()
    data = default_registry()
    data["profiles"]["configured-global"] = {
        "display_name": "Configured global model", "scope": "global",
        "provider": "openai-compatible", "model": "fixture-model", "dimension": 3,
        "base_url": "http://127.0.0.1:1/v1", "secret_ref": "",
    }
    data["defaults"].update({
        "embedding_profile": "configured-global",
        "lancedb_root": str(fixture / ("d" * 150)),
        "max_file_bytes": 2097152, "chunk_chars": 2400,
        "chunk_overlap_chars": 120, "batch_size": 7,
    })
    registry.save(data)
    result = {"project": str(project_root), "short_root": str(fixture / "indexes"), "defaults": data["defaults"]}
elif operation == "state":
    result = service.settings_state(str(project_root))
elif operation == "globals":
    result = service.settings_state()
elif operation == "plan":
    result = service.plan_settings(str(project_root), json.load(sys.stdin))
elif operation == "apply":
    result = service.apply_project_settings(str(project_root), json.load(sys.stdin))
elif operation == "project":
    project = registry.project(str(project_root))
    result = {"project": project, "effective": registry.resolved_settings(project)}
else:
    raise ValueError(f"Unknown fixture operation: {operation}")
print(json.dumps(result))
