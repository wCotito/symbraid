from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Protocol, Sequence, Tuple

from .config import Config
from .embeddings import Embedder
from .locking import ProjectLock
from .registry import normalize_project_path


class VectorStore(Protocol):
    def ensure_collection(self) -> None: ...
    def scroll_repo(self, repo_id: str, payload_fields: List[str]) -> List[Dict[str, Any]]: ...
    def delete_paths(self, repo_id: str, paths: Iterable[str]) -> int: ...
    def upsert(self, points: List[Dict[str, Any]]) -> None: ...
    def query(self, vector: List[float], repo_id: str, limit: int, path_filter: Optional[str] = None) -> List[Dict[str, Any]]: ...
    def count_chunks(self, repo_id: str) -> int: ...
    def delete_repo(self, repo_id: str) -> None: ...
    def export_points(self, repo_id: str) -> List[Dict[str, Any]]: ...


LANGUAGES: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
}

TEXT_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sql",
    ".graphql",
    ".gql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".vue",
    ".svelte",
    ".ps1",
    ".bat",
    ".cmd",
    ".dockerfile",
}

SYMBOL_NODE_TYPES = {
    "function_definition": "function",
    "function_declaration": "function",
    "function_item": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "method": "method",
    "constructor_declaration": "constructor",
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "interface_declaration": "interface",
    "trait_item": "trait",
    "struct_item": "struct",
    "struct_specifier": "struct",
    "enum_item": "enum",
    "enum_declaration": "enum",
    "impl_item": "implementation",
    "module": "module",
    "module_declaration": "module",
}

EXCLUDED_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/vendor/**",
    "!**/dist/**",
    "!**/build/**",
    "!**/target/**",
    "!**/coverage/**",
    "!**/.next/**",
    "!**/.nuxt/**",
    "!**/.venv/**",
    "!**/venv/**",
    "!**/__pycache__/**",
    "!*.min.js",
    "!*.map",
    "!**/package-lock.json",
    "!**/pnpm-lock.yaml",
    "!**/yarn.lock",
)


@dataclass(frozen=True)
class Chunk:
    repo_id: str
    path: str
    language: str
    symbol: str
    kind: str
    start_line: int
    end_line: int
    file_hash: str
    content_hash: str
    text: str

    def embedding_text(self) -> str:
        header = [f"path: {self.path}", f"language: {self.language}", f"kind: {self.kind}"]
        if self.symbol:
            header.append(f"symbol: {self.symbol}")
        return "\n".join(header) + "\ncode:\n" + self.text


def canonical_project(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Project directory does not exist: {root}")
    return root


def repo_identity(root: Path) -> str:
    return hashlib.sha256(normalize_project_path(str(root)).encode("utf-8")).hexdigest()[:16]


def git_context(root: Path) -> Tuple[str, str]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    return run("branch", "--show-current"), run("rev-parse", "HEAD")


class SymbraidIndexer:
    def __init__(self, config: Config, store: VectorStore, embedder: Embedder):
        self.config = config
        self.store = store
        self.embedder = embedder
        self._lock = threading.Lock()

    def _list_files(self, root: Path) -> List[Path]:
        command = [
            self.config.rg_path,
            "--files",
            "--hidden",
            "--no-ignore-global",
            "--no-ignore-parent",
        ]
        for glob in EXCLUDED_GLOBS:
            command.extend(["--glob", glob])
        try:
            result = subprocess.run(
                command,
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            relative_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Unable to list project files with ripgrep: {exc}") from exc
        files: List[Path] = []
        canonical_root = root.resolve()
        for relative in relative_paths:
            path = root / relative
            canonical_path = path.resolve()
            try:
                canonical_path.relative_to(canonical_root)
            except ValueError:
                continue
            if canonical_path.is_file() and self._supported(path) and canonical_path.stat().st_size <= self.config.max_file_bytes:
                files.append(path)
        return sorted(files)

    @staticmethod
    def _supported(path: Path) -> bool:
        suffix = path.suffix.lower()
        return suffix in LANGUAGES or suffix in TEXT_EXTENSIONS or path.name.lower() == "dockerfile"

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            return None
        for encoding in ("utf-8", "utf-8-sig"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                pass
        return data.decode("utf-8", "replace")

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _symbol_name(node: Any, source: bytes) -> str:
        for field in ("name", "declarator"):
            child = node.child_by_field_name(field)
            if child is not None:
                raw = source[child.start_byte : child.end_byte].decode("utf-8", "replace").strip()
                if raw:
                    return raw[:200]
        return ""

    @staticmethod
    def _extend_comments(lines: Sequence[str], start_line: int) -> int:
        index = start_line - 2
        extended = start_line
        blank_seen = False
        while index >= 0 and start_line - index <= 8:
            stripped = lines[index].strip()
            if not stripped and not blank_seen:
                blank_seen = True
                extended = index + 1
                index -= 1
                continue
            if stripped.startswith(("#", "//", "/*", "*", "///", "//!", "'''", '\"\"\"')):
                extended = index + 1
                index -= 1
                continue
            break
        return extended

    def _line_chunks(
        self,
        lines: Sequence[str],
        start_line: int,
        end_line: int,
        metadata: Dict[str, str],
        repo_id: str,
        relative: str,
        file_hash: str,
    ) -> Iterator[Chunk]:
        if not lines:
            return
        start_line = max(1, min(start_line, len(lines)))
        end_line = max(start_line, min(end_line, len(lines)))
        cursor = start_line
        while cursor <= end_line:
            char_count = 0
            stop = cursor - 1
            while stop < end_line:
                next_len = len(lines[stop]) + 1
                if stop >= cursor and char_count + next_len > self.config.chunk_chars:
                    break
                char_count += next_len
                stop += 1
            stop = max(cursor, stop)
            text = "\n".join(lines[cursor - 1 : stop]).strip()
            if text:
                content_hash = self._hash_text(text)
                yield Chunk(
                    repo_id=repo_id,
                    path=relative,
                    language=metadata["language"],
                    symbol=metadata.get("symbol", ""),
                    kind=metadata.get("kind", "text"),
                    start_line=cursor,
                    end_line=stop,
                    file_hash=file_hash,
                    content_hash=content_hash,
                    text=text,
                )
            if stop >= end_line:
                break
            overlap_chars = 0
            next_cursor = stop + 1
            while next_cursor > cursor and overlap_chars < self.config.chunk_overlap_chars:
                next_cursor -= 1
                overlap_chars += len(lines[next_cursor - 1]) + 1
            cursor = max(cursor + 1, next_cursor)

    def _tree_sitter_chunks(
        self, root: Path, path: Path, text: str, language: str, repo_id: str, file_hash: str
    ) -> List[Chunk]:
        try:
            from tree_sitter_language_pack import get_parser

            parser = get_parser(language)
            source = text.encode("utf-8")
            tree = parser.parse(source)
        except Exception:
            return []
        lines = text.splitlines()
        relative = path.resolve().relative_to(root).as_posix()
        chunks: List[Chunk] = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(reversed(node.children))
            kind = SYMBOL_NODE_TYPES.get(node.type)
            if not kind:
                continue
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            start_line = self._extend_comments(lines, start_line)
            symbol = self._symbol_name(node, source)
            chunks.extend(
                self._line_chunks(
                    lines,
                    start_line,
                    end_line,
                    {"language": language, "symbol": symbol, "kind": kind},
                    repo_id,
                    relative,
                    file_hash,
                )
            )
        unique: Dict[Tuple[int, int, str, str], Chunk] = {}
        for chunk in chunks:
            unique[(chunk.start_line, chunk.end_line, chunk.symbol, chunk.content_hash)] = chunk
        return sorted(unique.values(), key=lambda chunk: (chunk.start_line, chunk.end_line, chunk.symbol))

    def chunks_for_file(self, root: Path, path: Path, repo_id: str) -> List[Chunk]:
        text = self._read_text(path)
        if text is None or not text.strip():
            return []
        file_hash = self._hash_text(text)
        suffix = path.suffix.lower()
        language = LANGUAGES.get(suffix, "text")
        if path.name.lower() == "dockerfile":
            language = "dockerfile"
        chunks: List[Chunk] = []
        if suffix in LANGUAGES:
            chunks = self._tree_sitter_chunks(root, path, text, language, repo_id, file_hash)
        if not chunks:
            lines = text.splitlines()
            chunks = list(
                self._line_chunks(
                    lines,
                    1,
                    max(1, len(lines)),
                    {"language": language, "symbol": "", "kind": "text"},
                    repo_id,
                    path.resolve().relative_to(root).as_posix(),
                    file_hash,
                )
            )
        return chunks

    @staticmethod
    def _point_id(chunk: Chunk) -> str:
        key = f"{chunk.repo_id}:{chunk.path}:{chunk.start_line}:{chunk.end_line}:{chunk.content_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))

    def _points_for_chunks(self, chunks: List[Chunk]) -> List[Dict[str, Any]]:
        points_by_id: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(chunks), self.config.batch_size):
            batch = chunks[start : start + self.config.batch_size]
            vectors = self.embedder.embed_documents([chunk.embedding_text() for chunk in batch])
            for chunk, vector in zip(batch, vectors):
                payload = asdict(chunk)
                payload["type"] = "chunk"
                point_id = self._point_id(chunk)
                points_by_id[point_id] = {"id": point_id, "vector": vector, "payload": payload}
        return list(points_by_id.values())

    def _metadata_point(
        self,
        root: Path,
        repo_id: str,
        complete: bool,
        files: int,
        chunks: int,
    ) -> Dict[str, Any]:
        branch, commit = git_context(root)
        payload = {
            "type": "metadata",
            "repo_id": repo_id,
            "repo_root": str(root),
            "branch": branch,
            "commit": commit,
            "indexing_complete": complete,
            "file_count": files,
            "chunk_count": chunks,
            "embedding_provider": self.config.embedding_provider,
            "embedding_model": self.config.embedding_model,
            "embedding_dimension": self.config.embedding_dimension,
            "schema_version": 1,
        }
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo_id}:metadata")),
            "vector": [0.0] * self.config.embedding_dimension,
            "payload": payload,
        }

    def _existing_files(self, repo_id: str) -> Dict[str, set[str]]:
        existing: Dict[str, set[str]] = {}
        for point in self.store.scroll_repo(repo_id, ["type", "path", "file_hash"]):
            payload = point.get("payload") or {}
            if payload.get("type") != "chunk" or not payload.get("path"):
                continue
            existing.setdefault(payload["path"], set()).add(payload.get("file_hash", ""))
        return existing

    def index_project(self, project_path: str, force: bool = False) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Another indexing operation is already running")
        process_lock: Optional[ProjectLock] = None
        try:
            root = canonical_project(project_path)
            repo_id = repo_identity(root)
            process_lock = ProjectLock(
                self.config.lock_dir, repo_id, self.config.lock_timeout_seconds
            )
            process_lock.acquire()
            self.store.ensure_collection()
            files = self._list_files(root)
            existing = self._existing_files(repo_id)
            manifests: Dict[str, Tuple[Path, str]] = {}
            skipped_unreadable = 0
            for path in files:
                text = self._read_text(path)
                if text is None:
                    skipped_unreadable += 1
                    continue
                relative = path.resolve().relative_to(root).as_posix()
                manifests[relative] = (path, self._hash_text(text))
            changed = [
                relative
                for relative, (_, file_hash) in manifests.items()
                if force or existing.get(relative) != {file_hash}
            ]
            removed = sorted(set(existing) - set(manifests))
            self.store.upsert([self._metadata_point(root, repo_id, False, len(manifests), 0)])
            indexed_chunks = 0
            for relative in changed:
                path = manifests[relative][0]
                chunks = self.chunks_for_file(root, path, repo_id)
                points = self._points_for_chunks(chunks)
                self.store.delete_paths(repo_id, [relative])
                self.store.upsert(points)
                indexed_chunks += len(points)
            if removed:
                self.store.delete_paths(repo_id, removed)
            total_chunks = self.store.count_chunks(repo_id)
            self.store.upsert(
                [self._metadata_point(root, repo_id, True, len(manifests), total_chunks)]
            )
            return {
                "status": "ok",
                "project": str(root),
                "repo_id": repo_id,
                "backend": self.config.backend,
                "index": self.config.collection if self.config.backend == "qdrant" else str(self.config.lancedb_path),
                "files_seen": len(files),
                "files_changed": len(changed),
                "files_removed": len(removed),
                "files_skipped": skipped_unreadable,
                "chunks_written": indexed_chunks,
                "chunks_total": total_chunks,
                "embedding_model": self.config.embedding_model,
            }
        finally:
            if process_lock is not None:
                process_lock.release()
            self._lock.release()

    def refresh_files(self, project_path: str, files: Sequence[str]) -> Dict[str, Any]:
        if not files:
            return {"status": "ok", "files_refreshed": 0, "chunks_written": 0}
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Another indexing operation is already running")
        process_lock: Optional[ProjectLock] = None
        try:
            root = canonical_project(project_path)
            repo_id = repo_identity(root)
            process_lock = ProjectLock(
                self.config.lock_dir, repo_id, self.config.lock_timeout_seconds
            )
            process_lock.acquire()
            self.store.ensure_collection()
            indexable = {
                path.resolve().relative_to(root).as_posix(): path for path in self._list_files(root)
            }
            existing = self._existing_files(repo_id)
            requested_paths: List[str] = []
            for requested in files:
                candidate = (
                    (root / requested).resolve()
                    if not Path(requested).is_absolute()
                    else Path(requested).resolve()
                )
                try:
                    relative = candidate.relative_to(root).as_posix()
                except ValueError as exc:
                    raise ValueError(f"File is outside project root: {candidate}") from exc
                requested_paths.append(relative)
            requested_paths = sorted(set(requested_paths))
            paths_to_replace: List[str] = []
            chunks: List[Chunk] = []
            unchanged = 0
            removed = 0
            for relative in requested_paths:
                candidate = indexable.get(relative)
                if candidate is None:
                    if relative in existing:
                        paths_to_replace.append(relative)
                        removed += 1
                    continue
                text = self._read_text(candidate)
                if text is None:
                    paths_to_replace.append(relative)
                    continue
                file_hash = self._hash_text(text)
                if existing.get(relative) == {file_hash}:
                    unchanged += 1
                    continue
                paths_to_replace.append(relative)
                chunks.extend(self.chunks_for_file(root, candidate, repo_id))
            self.store.upsert([
                self._metadata_point(root, repo_id, False, len(indexable), self.store.count_chunks(repo_id))
            ])
            points = self._points_for_chunks(chunks)
            self.store.delete_paths(repo_id, paths_to_replace)
            self.store.upsert(points)
            total_chunks = self.store.count_chunks(repo_id)
            self.store.upsert(
                [self._metadata_point(root, repo_id, True, len(indexable), total_chunks)]
            )
            return {
                "status": "ok",
                "project": str(root),
                "repo_id": repo_id,
                "files_refreshed": len(requested_paths),
                "files_changed": len(paths_to_replace) - removed,
                "files_removed": removed,
                "files_unchanged": unchanged,
                "chunks_written": len(points),
                "chunks_total": total_chunks,
            }
        finally:
            if process_lock is not None:
                process_lock.release()
            self._lock.release()

    def index_status(self, project_path: str) -> Dict[str, Any]:
        root = canonical_project(project_path)
        repo_id = repo_identity(root)
        self.store.ensure_collection()
        metadata = None
        for point in self.store.scroll_repo(repo_id, ["type", "repo_root", "branch", "commit", "indexing_complete", "file_count", "chunk_count", "embedding_provider", "embedding_model", "embedding_dimension", "schema_version"]):
            payload = point.get("payload") or {}
            if payload.get("type") == "metadata":
                metadata = payload
                break
        return {
            "status": "ok",
            "project": str(root),
            "repo_id": repo_id,
            "backend": self.config.backend,
            "index": self.config.collection if self.config.backend == "qdrant" else str(self.config.lancedb_path),
            "indexed": metadata is not None,
            "metadata": metadata,
            "chunks": self.store.count_chunks(repo_id) if metadata else 0,
        }

    def semantic_search(
        self, query: str, project_path: str, top_k: int = 10, path_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        root = canonical_project(project_path)
        repo_id = repo_identity(root)
        self.store.ensure_collection()
        vector = self.embedder.embed_query(query)
        requested = max(1, min(int(top_k), 20))
        fetch_limit = min(100, requested * 5) if path_filter else requested
        points = self.store.query(vector, repo_id, fetch_limit)
        results = []
        for point in points:
            payload = point.get("payload") or {}
            path = payload.get("path", "")
            if path_filter and not (
                fnmatch.fnmatch(path.casefold(), path_filter.casefold())
                or path_filter.casefold() in path.casefold()
            ):
                continue
            text = payload.get("text", "")
            preview = " ".join(text.strip().split())[:600]
            results.append(
                {
                    "score": round(float(point.get("score", 0.0)), 6),
                    "path": path,
                    "language": payload.get("language", ""),
                    "symbol": payload.get("symbol", ""),
                    "kind": payload.get("kind", ""),
                    "start_line": payload.get("start_line"),
                    "end_line": payload.get("end_line"),
                    "content_hash": payload.get("content_hash", ""),
                    "preview": preview,
                }
            )
            if len(results) >= requested:
                break
        return {
            "status": "ok",
            "project": str(root),
            "repo_id": repo_id,
            "query": query,
            "results": results,
        }
