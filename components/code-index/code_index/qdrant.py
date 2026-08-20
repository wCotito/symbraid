from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from .config import Config


class QdrantError(RuntimeError):
    pass


class QdrantStore:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.qdrant_url.rstrip("/")
        self.collection = config.collection
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        allow_404: bool = False,
    ) -> Optional[Dict[str, Any]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.qdrant_api_key:
            headers["api-key"] = self.config.qdrant_api_key
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            if allow_404 and exc.code == 404:
                return None
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise QdrantError(f"Qdrant HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QdrantError(f"Qdrant request failed: {exc}") from exc

    def health(self) -> Dict[str, Any]:
        result = self._request("GET", "/collections")
        return {"ok": True, "collections": len(result["result"]["collections"])}

    def ensure_collection(self) -> None:
        info = self._request("GET", f"/collections/{self.collection}", allow_404=True)
        if info is not None:
            vectors = info["result"]["config"]["params"]["vectors"]
            size = vectors.get("size") if isinstance(vectors, dict) else None
            distance = vectors.get("distance") if isinstance(vectors, dict) else None
            if size != self.config.embedding_dimension or str(distance).lower() != "cosine":
                raise QdrantError(
                    f"Collection {self.collection} has incompatible vectors: size={size}, distance={distance}"
                )
            return
        self._request(
            "PUT",
            f"/collections/{self.collection}",
            {
                "vectors": {
                    "size": self.config.embedding_dimension,
                    "distance": "Cosine",
                    "on_disk": True,
                }
            },
        )
        for field in ("repo_id", "path", "type", "language", "symbol"):
            self._request(
                "PUT",
                f"/collections/{self.collection}/index?wait=true",
                {"field_name": field, "field_schema": "keyword"},
            )

    def scroll_repo(self, repo_id: str, payload_fields: List[str], with_vector: bool = False) -> List[Dict[str, Any]]:
        points: List[Dict[str, Any]] = []
        offset: Any = None
        while True:
            body: Dict[str, Any] = {
                "filter": {"must": [{"key": "repo_id", "match": {"value": repo_id}}]},
                "limit": 256,
                "with_payload": True if with_vector and not payload_fields else payload_fields,
                "with_vector": with_vector,
            }
            if offset is not None:
                body["offset"] = offset
            result = self._request(
                "POST", f"/collections/{self.collection}/points/scroll", body
            )["result"]
            points.extend(result.get("points", []))
            offset = result.get("next_page_offset")
            if offset is None:
                break
        return points

    def delete_paths(self, repo_id: str, paths: Iterable[str]) -> int:
        unique = sorted(set(paths))
        deleted = 0
        for start in range(0, len(unique), 100):
            batch = unique[start : start + 100]
            self._request(
                "POST",
                f"/collections/{self.collection}/points/delete?wait=true",
                {
                    "filter": {
                        "must": [
                            {"key": "repo_id", "match": {"value": repo_id}},
                            {"key": "path", "match": {"any": batch}},
                        ]
                    }
                },
            )
            deleted += len(batch)
        return deleted

    def delete_repo(self, repo_id: str) -> None:
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete?wait=true",
            {"filter": {"must": [{"key": "repo_id", "match": {"value": repo_id}}]}},
        )

    def upsert(self, points: List[Dict[str, Any]]) -> None:
        for start in range(0, len(points), 64):
            self._request(
                "PUT",
                f"/collections/{self.collection}/points?wait=true",
                {"points": points[start : start + 64]},
            )

    def query(
        self,
        vector: List[float],
        repo_id: str,
        limit: int,
        path_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        must: List[Dict[str, Any]] = [
            {"key": "repo_id", "match": {"value": repo_id}},
            {"key": "type", "match": {"value": "chunk"}},
        ]
        if path_filter:
            must.append({"key": "path", "match": {"text": path_filter}})
        body = {
            "query": vector,
            "filter": {"must": must},
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        try:
            response = self._request(
                "POST", f"/collections/{self.collection}/points/query", body
            )
            return response["result"].get("points", [])
        except QdrantError:
            legacy = dict(body)
            legacy["vector"] = legacy.pop("query")
            response = self._request(
                "POST", f"/collections/{self.collection}/points/search", legacy
            )
            return response.get("result", [])

    def count_chunks(self, repo_id: str) -> int:
        result = self._request(
            "POST",
            f"/collections/{self.collection}/points/count",
            {
                "filter": {
                    "must": [
                        {"key": "repo_id", "match": {"value": repo_id}},
                        {"key": "type", "match": {"value": "chunk"}},
                    ]
                },
                "exact": True,
            },
        )
        return int(result["result"]["count"])

    def export_points(self, repo_id: str) -> List[Dict[str, Any]]:
        return self.scroll_repo(repo_id, [], with_vector=True)
