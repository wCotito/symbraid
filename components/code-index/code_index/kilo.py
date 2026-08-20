from __future__ import annotations

import fnmatch
import hashlib
import json
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


KILO_SCHEMA = 2
KILO_METADATA_ID = "f946a536-9af4-4f1f-9f95-7d6efb4647d5"


def kilo_workspace_hash(project_path: str) -> str:
    return hashlib.sha256(str(Path(project_path).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]


def kilo_qdrant_collection(project_path: str) -> str:
    return f"ws-{kilo_workspace_hash(project_path)}"


def kilo_lancedb_directory(base: str, project_path: str) -> Path:
    root = Path(project_path).expanduser().resolve()
    return Path(base) / f"{root.name}-{kilo_workspace_hash(str(root))}"


def _profile(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": int(metadata.get("index_schema", 0)),
        "complete": str(metadata.get("indexing_complete", "false")).lower() == "true",
        "provider": str(metadata.get("embedding_provider", "")),
        "model": str(metadata.get("embedding_model_id", "")),
        "dimension": int(metadata.get("embedding_dimension", 0)),
    }


def validate_profile(metadata: Dict[str, Any], provider: str, model: str, dimension: int) -> Dict[str, Any]:
    stored = _profile(metadata)
    if stored["schema"] != KILO_SCHEMA:
        raise ValueError(f"Unsupported Kilo index schema: {stored['schema']}")
    if not stored["complete"]:
        raise ValueError("Kilo index is incomplete")
    if (stored["provider"], stored["model"], stored["dimension"]) != (provider, model, dimension):
        raise ValueError(
            "Kilo embedding profile mismatch: "
            f"stored={stored['provider']}:{stored['model']}:{stored['dimension']} "
            f"configured={provider}:{model}:{dimension}"
        )
    return stored


class KiloQdrantSource:
    def __init__(self, url: str, collection: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.collection = collection
        self.api_key = api_key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        request = urllib.request.Request(
            self.url + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Kilo Qdrant request failed: {exc}") from exc

    def metadata(self) -> Dict[str, Any]:
        result = self._request(
            "POST",
            f"/collections/{self.collection}/points",
            {"ids": [KILO_METADATA_ID], "with_payload": True, "with_vector": False},
        ).get("result", [])
        if not result:
            raise ValueError("Kilo metadata point not found")
        return result[0].get("payload") or {}

    def search(self, vector: List[float], limit: int, path_filter: Optional[str]) -> List[Dict[str, Any]]:
        body = {
            "query": vector,
            "limit": min(100, limit * 5 if path_filter else limit),
            "with_payload": True,
            "with_vector": False,
            "filter": {"must_not": [{"key": "type", "match": {"value": "metadata"}}]},
        }
        result = self._request(
            "POST", f"/collections/{self.collection}/points/query", body
        )["result"].get("points", [])
        return _normalize_kilo_rows(result, limit, path_filter, qdrant=True)


class KiloLanceDBSource:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.db = None

    def _connect(self):
        if self.db is None:
            if not self.directory.is_dir():
                raise ValueError(f"Kilo LanceDB directory does not exist: {self.directory}")
            import lancedb

            self.db = lancedb.connect(str(self.directory), read_consistency_interval=timedelta(0))
        return self.db

    def metadata(self) -> Dict[str, Any]:
        db = self._connect()
        if not {"vector", "metadata"}.issubset(set(db.list_tables().tables)):
            raise ValueError("Kilo LanceDB vector/metadata tables not found")
        rows = db.open_table("metadata").search().to_list()
        return {str(row["key"]): row["value"] for row in rows}

    def search(self, vector: List[float], limit: int, path_filter: Optional[str]) -> List[Dict[str, Any]]:
        table = self._connect().open_table("vector")
        rows = table.search(vector).metric("cosine").limit(min(100, limit * 5 if path_filter else limit)).to_list()
        return _normalize_kilo_rows(rows, limit, path_filter, qdrant=False)


def _normalize_kilo_rows(rows: List[Dict[str, Any]], limit: int, path_filter: Optional[str], qdrant: bool) -> List[Dict[str, Any]]:
    results = []
    for row in rows:
        payload = (row.get("payload") or {}) if qdrant else row
        path = str(payload.get("filePath", ""))
        if path_filter and not (
            fnmatch.fnmatch(path.casefold(), path_filter.casefold())
            or path_filter.casefold() in path.casefold()
        ):
            continue
        text = str(payload.get("codeChunk", ""))
        score = float(row.get("score", 1.0 - float(row.get("_distance", 1.0))))
        results.append({
            "score": round(score, 6),
            "path": path,
            "language": "",
            "symbol": "",
            "kind": "kilo-chunk",
            "start_line": payload.get("startLine"),
            "end_line": payload.get("endLine"),
            "content_hash": payload.get("segmentHash", ""),
            "file_hash": payload.get("fileHash", ""),
            "preview": " ".join(text.strip().split())[:600],
        })
        if len(results) >= limit:
            break
    return results
