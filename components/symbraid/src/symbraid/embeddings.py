from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List

from .config import Config


class EmbeddingError(RuntimeError):
    pass


class Embedder:
    def __init__(self, config: Config):
        self.config = config
        self._model = None

    @property
    def dimension(self) -> int:
        return self.config.embedding_dimension

    def _prefix(self, text: str, query: bool) -> str:
        if "e5" in self.config.embedding_model.lower():
            return ("query: " if query else "passage: ") + text
        return text

    def _fastembed_model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self.config.model_cache.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(
                model_name=self.config.embedding_model,
                cache_dir=str(self.config.model_cache),
            )
        return self._model

    def _fastembed(self, texts: List[str], query: bool) -> List[List[float]]:
        model = self._fastembed_model()
        prepared = [self._prefix(text, query) for text in texts]
        vectors = [vector.tolist() for vector in model.embed(prepared, batch_size=self.config.batch_size)]
        self._validate_vectors(vectors)
        return vectors

    def _openai_compatible(self, texts: List[str], query: bool) -> List[List[float]]:
        endpoint = self.config.embedding_base_url
        if not endpoint.endswith("/embeddings"):
            endpoint += "/embeddings"
        payload = json.dumps(
            {
                "model": self.config.embedding_model,
                "input": [self._prefix(text, query) for text in texts],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.config.embedding_api_key}"
        request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with opener.open(request, timeout=120) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise EmbeddingError(f"Embedding endpoint failed: HTTP {exc.code}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(0.25 * (2**attempt))
        else:
            raise EmbeddingError(f"Embedding endpoint failed after 3 attempts: {last_error}") from last_error
        data = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts):
            raise EmbeddingError(f"Embedding endpoint returned {len(vectors)} vectors for {len(texts)} texts")
        self._validate_vectors(vectors)
        return vectors

    def _validate_vectors(self, vectors: Iterable[List[float]]) -> None:
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.config.embedding_provider == "fastembed":
            return self._fastembed(texts, query=False)
        return self._openai_compatible(texts, query=False)

    def embed_query(self, text: str) -> List[float]:
        if self.config.embedding_provider == "fastembed":
            return self._fastembed([text], query=True)[0]
        return self._openai_compatible([text], query=True)[0]
