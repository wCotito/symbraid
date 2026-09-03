from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .paths import app_paths


@dataclass(frozen=True)
class Config:
    backend: str
    qdrant_url: str
    qdrant_api_key: str
    collection: str
    lancedb_path: Path
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    embedding_base_url: str
    embedding_api_key: str
    model_cache: Path
    lock_dir: Path
    lock_timeout_seconds: float
    rg_path: str
    max_file_bytes: int
    chunk_chars: int
    chunk_overlap_chars: int
    batch_size: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "Config":
        paths = app_paths()
        return cls(
            backend=str(values.get("backend", "lancedb")).lower(),
            qdrant_url=str(values.get("qdrant_url", "http://127.0.0.1:18133")).rstrip("/"),
            qdrant_api_key=str(values.get("qdrant_api_key", "")),
            collection=str(values.get("collection", "")),
            lancedb_path=Path(str(values.get("lancedb_path", paths.data / "lancedb/default"))),
            embedding_provider=str(values.get("embedding_provider", "fastembed")).lower(),
            embedding_model=str(values.get("embedding_model", "jinaai/jina-embeddings-v2-base-code")),
            embedding_dimension=int(values.get("embedding_dimension", 768)),
            embedding_base_url=str(values.get("embedding_base_url", "")).rstrip("/"),
            embedding_api_key=str(values.get("embedding_api_key", "")),
            model_cache=Path(str(values.get("model_cache", paths.cache / "models"))),
            lock_dir=Path(str(values.get("lock_dir", paths.locks))),
            lock_timeout_seconds=float(values.get("lock_timeout_seconds", 120)),
            rg_path=str(values.get("rg_path", "rg")),
            max_file_bytes=int(values.get("max_file_bytes", 1048576)),
            chunk_chars=int(values.get("chunk_chars", 1600)),
            chunk_overlap_chars=int(values.get("chunk_overlap_chars", 200)),
            batch_size=int(values.get("batch_size", 32)),
        )

    def validate(self) -> None:
        if self.backend not in {"qdrant", "lancedb"}:
            raise ValueError("backend must be qdrant or lancedb")
        if self.backend == "qdrant" and not self.qdrant_url.startswith(("http://", "https://")):
            raise ValueError("qdrant_url must be an HTTP(S) URL")
        if self.backend == "qdrant" and not self.collection:
            raise ValueError("collection cannot be empty")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        if self.chunk_chars < 400:
            raise ValueError("chunk_chars must be at least 400")
        if not 0 <= self.chunk_overlap_chars < self.chunk_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_chars")
        if self.embedding_provider == "openai-compatible" and not self.embedding_base_url:
            raise ValueError("embedding_base_url is required for openai-compatible embeddings")
        if self.embedding_provider not in {"fastembed", "openai-compatible"}:
            raise ValueError("embedding_provider must be fastembed or openai-compatible")
