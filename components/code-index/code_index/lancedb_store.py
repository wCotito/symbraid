from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Iterable, List, Optional

from .config import Config


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class LanceDBStore:
    def __init__(self, config: Config):
        self.config = config
        self.path = config.lancedb_path
        self.db = None
        self.vector = None
        self.metadata = None

    def _connect(self):
        if self.db is None:
            import lancedb

            self.path.mkdir(parents=True, exist_ok=True)
            self.db = lancedb.connect(str(self.path))
        return self.db

    def ensure_collection(self) -> None:
        import pyarrow as pa

        db = self._connect()
        names = set(db.list_tables().tables)
        if "vector" not in names:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.config.embedding_dimension)),
                pa.field("repo_id", pa.string()),
                pa.field("path", pa.string()),
                pa.field("language", pa.string()),
                pa.field("symbol", pa.string()),
                pa.field("kind", pa.string()),
                pa.field("start_line", pa.int64()),
                pa.field("end_line", pa.int64()),
                pa.field("file_hash", pa.string()),
                pa.field("content_hash", pa.string()),
                pa.field("text", pa.string()),
                pa.field("type", pa.string()),
            ])
            db.create_table("vector", schema=schema)
        if "metadata" not in names:
            db.create_table("metadata", data=[{"key": "schema_version", "value": "1", "payload": "{}"}])
        self.vector = db.open_table("vector")
        self.metadata = db.open_table("metadata")

    def scroll_repo(self, repo_id: str, payload_fields: List[str]) -> List[Dict[str, Any]]:
        self.ensure_collection()
        rows = self.vector.search().where(f"repo_id = {_quoted(repo_id)}").to_list()
        points = [{"id": row["id"], "payload": {key: row.get(key) for key in payload_fields}} for row in rows]
        metadata = self.metadata.search().where(f"key = {_quoted('project:' + repo_id)}").to_list()
        for row in metadata:
            payload = json.loads(row["payload"])
            points.append({"id": row["key"], "payload": {key: payload.get(key) for key in payload_fields}})
        return points

    def delete_paths(self, repo_id: str, paths: Iterable[str]) -> int:
        self.ensure_collection()
        unique = sorted(set(paths))
        if unique:
            values = ",".join(_quoted(value) for value in unique)
            self.vector.delete(f"repo_id = {_quoted(repo_id)} AND path IN ({values})")
        return len(unique)

    def delete_repo(self, repo_id: str) -> None:
        self.ensure_collection()
        self.vector.delete(f"repo_id = {_quoted(repo_id)}")
        self.metadata.delete(f"key = {_quoted('project:' + repo_id)}")

    def upsert(self, points: List[Dict[str, Any]]) -> None:
        self.ensure_collection()
        vectors_by_id: Dict[str, Dict[str, Any]] = {}
        for point in points:
            payload = point["payload"]
            if payload.get("type") == "metadata":
                key = "project:" + payload["repo_id"]
                self.metadata.delete(f"key = {_quoted(key)}")
                self.metadata.add([{"key": key, "value": "project", "payload": json.dumps(payload, ensure_ascii=False)}])
                continue
            vectors_by_id[str(point["id"])] = {
                "id": str(point["id"]),
                "vector": point["vector"],
                "repo_id": payload.get("repo_id", ""),
                "path": payload.get("path", ""),
                "language": payload.get("language", ""),
                "symbol": payload.get("symbol", ""),
                "kind": payload.get("kind", ""),
                "start_line": payload.get("start_line", 0),
                "end_line": payload.get("end_line", 0),
                "file_hash": payload.get("file_hash", ""),
                "content_hash": payload.get("content_hash", ""),
                "text": payload.get("text", ""),
                "type": "chunk",
            }
        vectors = list(vectors_by_id.values())
        if vectors:
            ids = ",".join(_quoted(row["id"]) for row in vectors)
            self.vector.delete(f"id IN ({ids})")
            self.vector.add(vectors)

    def query(self, vector: List[float], repo_id: str, limit: int, path_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_collection()
        query = self.vector.search(vector).metric("cosine").where(f"repo_id = {_quoted(repo_id)}").limit(limit)
        rows = query.to_list()
        return [
            {
                "id": row["id"],
                "score": max(-1.0, min(1.0, 1.0 - float(row.get("_distance", 1.0)))),
                "payload": {key: value for key, value in row.items() if key not in {"id", "vector", "_distance"}},
            }
            for row in rows
        ]

    def count_chunks(self, repo_id: str) -> int:
        self.ensure_collection()
        return int(self.vector.count_rows(f"repo_id = {_quoted(repo_id)}"))

    def export_points(self, repo_id: str) -> List[Dict[str, Any]]:
        self.ensure_collection()
        rows = self.vector.search().where(f"repo_id = {_quoted(repo_id)}").to_list()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "vector": row["vector"],
                "payload": {key: value for key, value in row.items() if key not in {"id", "vector", "_distance"}},
            })
        metadata = self.metadata.search().where(f"key = {_quoted('project:' + repo_id)}").to_list()
        if metadata:
            payload = json.loads(metadata[0]["payload"])
            result.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo_id}:metadata")),
                "vector": [0.0] * self.config.embedding_dimension,
                "payload": payload,
            })
        return result
