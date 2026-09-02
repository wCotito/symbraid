#!/usr/bin/env python3
"""Run or plan the reproducible Symbraid benchmark.

The default is a dry plan. An actual subprocess run requires ``--execute`` so
the benchmark cannot unexpectedly download a model or contact an external
service. The runner is standard-library only and reports unavailable measures
as explicit ``not_collected`` values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - resource is not available on Windows
    resource = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks" / "config" / "benchmark.json"
NOT_COLLECTED = "not_collected"
NOT_COMPARABLE = "not_comparable"
QUALITY_FIELDS = (
    "ndcg@10",
    "mrr@10",
    "recall@1",
    "recall@5",
    "recall@10",
    "precision@5",
    "precision@10",
    "file_recall",
    "context_efficiency",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def deterministic_digest(named_files: list[tuple[str, Path]]) -> str:
    """Hash logical file labels and file contents deterministically."""
    hasher = hashlib.sha256()
    for label, path in sorted(named_files, key=lambda item: item[0]):
        hasher.update(label.encode("utf-8"))
        hasher.update(b"\0")
        if path.is_file():
            hasher.update(sha256_file(path).encode("ascii"))
        else:
            hasher.update(b"<missing>")
        hasher.update(b"\0")
    return hasher.hexdigest()

def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')
    return sha256_bytes(encoded)

def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return NOT_COLLECTED

def harness_sha256(
    config: dict[str, Any], config_path: Path, query_path: Path,
    competitor_path: Path,
) -> str:
    external_manifest = config.get('external_corpus_manifest')
    external_path = (
        (ROOT / external_manifest).resolve()
        if external_manifest
        else ROOT / 'benchmarks' / 'external' / 'codesearchnet-manifest.json'
    )
    return deterministic_digest(
        [
            ('benchmarks/run.py', ROOT / 'benchmarks' / 'run.py'),
            ('benchmark-config', config_path),
            ('queries', query_path),
            ('competitors', competitor_path),
            ('external-corpus-manifest', external_path),
            ('benchmarks/download_codesearchnet.py', ROOT / 'benchmarks' / 'download_codesearchnet.py'),
        ]
    )

def adapter_config_records(
    adapters: list[dict[str, Any]], adapter_paths: dict[str, Path] | None = None,
) -> list[dict[str, str]]:
    records = []
    for adapter in sorted(adapters, key=lambda item: str(item.get('id', ''))):
        adapter_id = str(adapter.get('id', NOT_COLLECTED))
        path = (adapter_paths or {}).get(adapter_id)
        if path is not None and path.is_file():
            digest = sha256_file(path)
            display_path = repo_relative(path)
        else:
            digest = canonical_json_sha256(adapter)
            display_path = NOT_COLLECTED
        records.append({'id': adapter_id, 'path': display_path, 'sha256': digest})
    return records

def tree_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "LICENSE"):
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def load_queries(path: Path) -> list[dict[str, Any]]:
    queries = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid query JSON at {path}:{line_number}: {exc}") from exc
        if not value.get("id") or not value.get("query") or not value.get("relevant"):
            raise SystemExit(f"Query {path}:{line_number} needs id, query, and relevant")
        if not isinstance(value["relevant"], list):
            raise SystemExit(f"Query {path}:{line_number} relevant must be a list")
        queries.append(value)
    return queries


def substitute(parts: list[str], *, fixture: Path, query: str, k: int) -> list[str]:
    replacements = {"{fixture}": str(fixture), "{query}": query, "{k}": str(k)}
    return [replacements.get(part, part) for part in parts]


def parse_hits(value: Any, result_format: str = "json") -> list[dict[str, Any]]:
    if result_format == "paths":
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if not isinstance(value, str):
            raise ValueError("path adapter output must be text")
        return [{"path": line.strip()} for line in value.splitlines() if line.strip()]
    if isinstance(value, dict):
        value = value.get("results", value.get("hits", []))
    if not isinstance(value, list):
        raise ValueError("adapter output must be a JSON list or an object with results/hits")
    hits = []
    for item in value:
        if isinstance(item, str):
            hits.append({"path": item})
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            hits.append(item)
    return hits


def normalize_hit_paths(hits: list[dict[str, Any]], fixture: Path) -> list[dict[str, Any]]:
    root = fixture.resolve()
    normalized: list[dict[str, Any]] = []
    for hit in hits:
        item = dict(hit)
        raw_path = str(item.get("path", "")).replace("\\", "/")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            try:
                raw_path = candidate.resolve().relative_to(root).as_posix()
            except ValueError:
                raw_path = candidate.as_posix()
        item["path"] = raw_path
        normalized.append(item)
    return normalized

def reciprocal_rank(paths: list[str], relevant: set[str], limit: int | None = None) -> float:
    ranked = paths if limit is None else paths[:limit]
    for rank, path in enumerate(ranked, 1):
        if path in relevant:
            return 1.0 / rank
    return 0.0


def ndcg(paths: list[str], relevant: set[str], k: int) -> float:
    ranked = paths[:k]
    dcg = sum(1.0 / math.log2(rank + 1) for rank, path in enumerate(ranked, 1) if path in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def evaluate(paths: list[str], relevant: set[str], k: int) -> dict[str, float]:
    """Keep the original per-k API for small adapter tests and callers."""
    top = paths[:k]
    found = len(set(top) & relevant)
    return {
        f"recall@{k}": found / len(relevant) if relevant else 0.0,
        "mrr": reciprocal_rank(paths, relevant),
        f"ndcg@{k}": ndcg(paths, relevant, k),
    }


def context_efficiency(hits: list[dict[str, Any]], relevant: set[str]) -> float | str:
    total = 0
    useful = 0
    for hit in hits[:10]:
        content = hit.get("text", hit.get("content"))
        if not isinstance(content, str):
            continue
        size = len(content.encode("utf-8"))
        total += size
        if hit.get("path") in relevant:
            useful += size
    return useful / total if total else NOT_COLLECTED


def quality_metrics(hits: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, float | str]:
    paths = [hit["path"].replace("\\", "/") for hit in hits]
    relevant = set(query["relevant"])
    file_relevant = set(query.get("relevant_files", query["relevant"]))
    metrics: dict[str, float | str] = {
        "ndcg@10": ndcg(paths, relevant, 10),
        "mrr@10": reciprocal_rank(paths, relevant, 10),
        "recall@1": len(set(paths[:1]) & relevant) / len(relevant) if relevant else 0.0,
        "recall@5": len(set(paths[:5]) & relevant) / len(relevant) if relevant else 0.0,
        "recall@10": len(set(paths[:10]) & relevant) / len(relevant) if relevant else 0.0,
        "precision@5": len(set(paths[:5]) & relevant) / 5,
        "precision@10": len(set(paths[:10]) & relevant) / 10,
        "file_recall": len(set(paths[:10]) & file_relevant) / len(file_relevant) if file_relevant else 0.0,
        "context_efficiency": context_efficiency(hits, relevant),
    }
    return metrics


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def percentiles(values: list[float]) -> dict[str, float | str]:
    if not values:
        return {"p50": NOT_COLLECTED, "p95": NOT_COLLECTED, "p99": NOT_COLLECTED}
    return {"p50": percentile(values, 0.50), "p95": percentile(values, 0.95), "p99": percentile(values, 0.99)}


def empty_quality() -> dict[str, str]:
    return {field: NOT_COLLECTED for field in QUALITY_FIELDS}


def empty_performance(warm_repeats: int) -> dict[str, Any]:
    empty = {
        "warm_repeats": warm_repeats,
        "warm_query_latency_ms": percentiles([]),
        "response_size_bytes": percentiles([]),
        "cold_index_wall_ms": NOT_COLLECTED,
        "cold_index_cpu_ms": NOT_COLLECTED,
        "files_per_second": NOT_COLLECTED,
        "loc_per_second": NOT_COLLECTED,
        "peak_rss_bytes": NOT_COLLECTED,
        "disk_bytes_per_chunk": NOT_COLLECTED,
        "startup_ms": NOT_COLLECTED,
        "incremental_convergence_ms": NOT_COLLECTED,
        "idle_memory_bytes": NOT_COLLECTED,
    }
    empty["cold_index"] = {
        "wall_ms": NOT_COLLECTED,
        "cpu_ms": NOT_COLLECTED,
        "files_per_second": NOT_COLLECTED,
        "loc_per_second": NOT_COLLECTED,
        "peak_rss_bytes": NOT_COLLECTED,
        "disk_bytes_per_chunk": NOT_COLLECTED,
    }
    return empty


def numeric_average(records: list[dict[str, Any]], field: str) -> float | str:
    values = [record[field] for record in records if isinstance(record.get(field), (int, float))]
    return sum(values) / len(values) if values else NOT_COLLECTED


def aggregate_quality(records: list[dict[str, Any]]) -> dict[str, float | str]:
    return {field: numeric_average(records, field) for field in QUALITY_FIELDS}


def adapter_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def environment_metadata() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "os": platform.system() or NOT_COLLECTED,
        "os_release": platform.release() or NOT_COLLECTED,
        "platform": platform.platform() or NOT_COLLECTED,
        "architecture": platform.machine() or NOT_COLLECTED,
        "processor": platform.processor() or NOT_COLLECTED,
    }


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return NOT_COLLECTED


def git_provenance() -> dict[str, Any]:
    """Capture revision, dirty state, and deterministic repository digests."""
    try:
        status = subprocess.check_output(
            ['git', 'status', '--porcelain=v1', '--untracked-files=all'],
            cwd=ROOT, stderr=subprocess.DEVNULL, timeout=5,
        )
        diff = subprocess.check_output(
            ['git', 'diff', 'HEAD', '--no-ext-diff', '--binary'],
            cwd=ROOT, stderr=subprocess.DEVNULL, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {
            'revision': git_revision(),
            'dirty': NOT_COLLECTED,
            'status': NOT_COLLECTED,
            'git_diff_sha256': NOT_COLLECTED,
            'repo_state_sha256': NOT_COLLECTED,
        }
    return {
        'revision': git_revision(),
        'dirty': bool(status),
        'status': 'dirty' if status else 'clean',
        'git_diff_sha256': sha256_bytes(diff),
        'repo_state_sha256': sha256_bytes(
            b'status\0' + status + b'\0diff\0' + diff
        ),
    }

def child_usage() -> tuple[float, int] | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    rss = int(usage.ru_maxrss)
    if sys.platform != "darwin":
        rss *= 1024
    return ((usage.ru_utime + usage.ru_stime) * 1000, rss)


def run_process(args: list[str], timeout: int, env: dict[str, str], allow_no_match: bool = False) -> dict[str, Any]:
    before = child_usage()
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=False,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "reason": f"executable not found: {args[0]}", "stderr": b""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "adapter timed out", "stderr": b""}
    elapsed_ms = (time.perf_counter() - started) * 1000
    after = child_usage()
    cpu_ms = NOT_COLLECTED
    peak_rss = NOT_COLLECTED
    if before is not None and after is not None:
        cpu_ms = max(0.0, after[0] - before[0])
        peak_rss = after[1]
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if completed.returncode not in ((0, 1) if allow_no_match else (0,)):
        return {
            "ok": False,
            "reason": f"exit code {completed.returncode}",
            "stderr": stderr[-2000:],
            "wall_ms": elapsed_ms,
            "cpu_ms": cpu_ms,
            "peak_rss_bytes": peak_rss,
            "response_size_bytes": len(stdout),
        }
    return {
        "ok": True,
        "stdout": stdout,
        "stderr": stderr[-2000:],
        "wall_ms": elapsed_ms,
        "cpu_ms": cpu_ms,
        "peak_rss_bytes": peak_rss,
        "response_size_bytes": len(stdout),
    }


def observe_version(adapter: dict[str, Any], config: dict[str, Any]) -> str:
    executable = adapter.get("executable")
    command = adapter.get("version_command", [])
    if not executable or not command:
        return NOT_COLLECTED
    env = {**os.environ, "PYTHONHASHSEED": str(config.get("seed", 0))}
    try:
        completed = subprocess.run(
            [executable, *command], cwd=ROOT, capture_output=True, text=True,
            check=False, timeout=int(adapter.get("timeout_seconds", 120)), env=env,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return NOT_COLLECTED
    if completed.returncode != 0:
        return NOT_COLLECTED
    line = (completed.stdout or completed.stderr).strip().splitlines()
    return line[0][:300] if line else NOT_COLLECTED


def phase_measure(adapter: dict[str, Any], config: dict[str, Any], fixture: Path, phase: str) -> dict[str, Any]:
    result: dict[str, Any]
    if phase == "index":
        result = {
            "wall_ms": NOT_COLLECTED,
            "cpu_ms": NOT_COLLECTED,
            "files_per_second": NOT_COLLECTED,
            "loc_per_second": NOT_COLLECTED,
            "peak_rss_bytes": NOT_COLLECTED,
            "disk_bytes_per_chunk": NOT_COLLECTED,
        }
    elif phase == "startup":
        result = {"wall_ms": NOT_COLLECTED}
    elif phase == "incremental":
        result = {"convergence_ms": NOT_COLLECTED}
    else:
        result = {"bytes": NOT_COLLECTED}
    command = adapter.get(f"{phase}_command")
    executable = adapter.get("executable")
    if not command or not executable:
        return result
    args = [executable, *substitute(command, fixture=fixture, query="", k=max(config.get("k", [10])))]
    env = {**os.environ, "PYTHONHASHSEED": str(config.get("seed", 0))}
    measured = run_process(args, int(adapter.get("timeout_seconds", 120)), env)
    if not measured.get("ok"):
        return result
    if phase == "startup":
        return {"wall_ms": measured["wall_ms"]}
    if phase == "incremental":
        return {"convergence_ms": measured["wall_ms"]}
    if phase == "idle":
        return {"bytes": measured.get("peak_rss_bytes", NOT_COLLECTED)}
    result["wall_ms"] = measured["wall_ms"]
    result["cpu_ms"] = measured.get("cpu_ms", NOT_COLLECTED)
    result["peak_rss_bytes"] = measured.get("peak_rss_bytes", NOT_COLLECTED)
    try:
        payload = json.loads(measured.get("stdout", b"").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    if isinstance(payload, dict):
        files = payload.get("files", payload.get("files_indexed"))
        loc = payload.get("loc", payload.get("lines", payload.get("lines_of_code")))
        chunks = payload.get("chunks", payload.get("chunks_indexed"))
        disk = payload.get("disk_bytes", payload.get("index_bytes"))
        if isinstance(files, (int, float)) and result["wall_ms"]:
            result["files_per_second"] = files / (result["wall_ms"] / 1000)
        if isinstance(loc, (int, float)) and result["wall_ms"]:
            result["loc_per_second"] = loc / (result["wall_ms"] / 1000)
        if isinstance(disk, (int, float)) and isinstance(chunks, (int, float)) and chunks:
            result["disk_bytes_per_chunk"] = disk / chunks
    return result


def plan_report(
    config: dict[str, Any], queries: list[dict[str, Any]], adapters: list[dict[str, Any]],
    mode: str, fixture: Path, query_path: Path, competitor_path: Path,
    config_path: Path | None = None, adapter_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    warm_repeats = max(5, int(config.get("warm_repeats", config.get("repetitions", 5))))
    environment = environment_metadata()
    git = git_provenance()
    environment["git_revision"] = git["revision"]
    environment["git_dirty"] = git["dirty"]
    adapter_records = adapter_config_records(adapters, adapter_paths)
    adapter_records_by_id = {record["id"]: record for record in adapter_records}
    return {
        "schema_version": 2,
        "status": "not_executed",
        "reason": "Dry plan only; no benchmark command was executed.",
        "mode": mode,
        "provenance": {
            "fixture_sha256": tree_digest(fixture),
            "queries_sha256": sha256_file(query_path),
            "competitor_manifest_sha256": sha256_file(competitor_path),
            "external_corpus_manifest_sha256": sha256_file(ROOT / config["external_corpus_manifest"]) if config.get("external_corpus_manifest") else NOT_COLLECTED,
            "harness_sha256": harness_sha256(config, config_path or DEFAULT_CONFIG, query_path, competitor_path),
            "adapter_configs_sha256": canonical_json_sha256(adapter_records),
            "adapter_configs": adapter_records,
            "git_revision": git["revision"],
            "git_dirty": git["dirty"],
            "git_status": git["status"],
            "git_diff_sha256": git["git_diff_sha256"],
            "repo_state_sha256": git["repo_state_sha256"],
            "environment": environment,
            "network_requested": bool(config.get("network", False)),
        },
        "parameters": {
            "k": config.get("k", [1, 5, 10]),
            "warm_repeats": warm_repeats,
            "seed": config.get("seed", 0),
            "mode": mode,
            "network": bool(config.get("network", False)),
        },
        "metric_schema": {
            "quality": list(QUALITY_FIELDS),
            "performance": list(empty_performance(warm_repeats)),
        },
        "queries": [query["id"] for query in queries],
        "adapters": [
            {
                "id": adapter["id"],
                "config_path": adapter_records_by_id.get(adapter["id"], {}).get("path", NOT_COLLECTED),
                "config_sha256": adapter_records_by_id.get(adapter["id"], {}).get("sha256", NOT_COLLECTED),
                "executable": adapter.get("executable", NOT_COLLECTED),
                "declared_version": adapter.get("version", NOT_COLLECTED),
                "observed_version": NOT_COLLECTED,
                "supports_controlled": adapter.get("supports_controlled", False),
                "version_command": adapter.get("version_command", []),
                "planned_command": " ".join(
                    shlex.quote(part)
                    for part in substitute(
                        adapter.get("search_command", []), fixture=fixture,
                        query="<query>", k=max(config.get("k", [10])),
                    )
                ),
                "phases": {
                    "cold_index": "planned" if adapter.get("index_command") else NOT_COLLECTED,
                    "startup": "planned" if adapter.get("startup_command") else NOT_COLLECTED,
                    "incremental_convergence": "planned" if adapter.get("incremental_command") else NOT_COLLECTED,
                    "idle_memory": "planned" if adapter.get("idle_command") else NOT_COLLECTED,
                },
                "quality": empty_quality(),
                "performance": empty_performance(warm_repeats),
            }
            for adapter in adapters
        ],
        "results": [],
    }


def run_adapter(
    adapter: dict[str, Any], config: dict[str, Any], queries: list[dict[str, Any]],
    mode: str, fixture: Path,
) -> dict[str, Any]:
    warm_repeats = max(5, int(config.get("warm_repeats", config.get("repetitions", 5))))
    performance = empty_performance(warm_repeats)
    observed_version = observe_version(adapter, config)
    base = {
        "adapter": adapter["id"],
        "declared_version": adapter.get("version", NOT_COLLECTED),
        "observed_version": observed_version,
        "quality": empty_quality(),
        "performance": performance,
    }
    if mode == "controlled" and not adapter.get("supports_controlled", False):
        return {**base, "status": NOT_COMPARABLE, "reason": "Adapter does not declare controlled-track support.", "queries": []}
    executable = adapter.get("executable")
    if not executable:
        return {**base, "status": "not_run", "reason": "adapter has no executable", "queries": []}
    query_results = []
    all_latencies: list[float] = []
    all_response_sizes: list[float] = []
    env = {**os.environ, "PYTHONHASHSEED": str(config.get("seed", 0))}
    for query in queries:
        samples: list[float] = []
        response_sizes: list[float] = []
        last_hits: list[dict[str, Any]] = []
        query_text = query.get(adapter.get("query_field", "query"), query["query"])
        for _ in range(warm_repeats):
            args = [
                executable,
                *substitute(
                    adapter.get("search_command", []), fixture=fixture,
                    query=str(query_text), k=max(config.get("k", [10])),
                ),
            ]
            measured = run_process(args, int(adapter.get("timeout_seconds", 120)), env, allow_no_match=(1 in adapter.get("allowed_exit_codes", []) or bool(adapter.get("allow_no_match_exit"))))
            if not measured.get("ok"):
                return {
                    **base,
                    "status": "not_run",
                    "reason": measured.get("reason", "command failed"),
                    "queries": [],
                }
            try:
                raw = measured.get("stdout", b"")
                value: Any
                if adapter.get("result_format", "json") == "paths":
                    value = raw
                else:
                    value = json.loads(raw.decode("utf-8"))
                hits = parse_hits(value, adapter.get("result_format", "json"))
                hits = normalize_hit_paths(hits, fixture)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                return {**base, "status": "not_run", "reason": f"invalid adapter output: {exc}", "queries": []}
            last_hits = hits
            samples.append(float(measured["wall_ms"]))
            response_sizes.append(float(measured["response_size_bytes"]))
        metrics = quality_metrics(last_hits, query)
        query_results.append({
            "id": query["id"],
            "warm_repeats": warm_repeats,
            "latency_ms": percentiles(samples),
            "response_size_bytes": percentiles(response_sizes),
            "metrics": metrics,
            "paths": [hit["path"].replace("\\", "/") for hit in last_hits],
        })
        all_latencies.extend(samples)
        all_response_sizes.extend(response_sizes)
    performance["warm_query_latency_ms"] = percentiles(all_latencies)
    performance["response_size_bytes"] = percentiles(all_response_sizes)
    index = phase_measure(adapter, config, fixture, "index")
    performance["cold_index"] = index
    performance["cold_index_wall_ms"] = index.get("wall_ms", NOT_COLLECTED)
    performance["cold_index_cpu_ms"] = index.get("cpu_ms", NOT_COLLECTED)
    performance["files_per_second"] = index.get("files_per_second", NOT_COLLECTED)
    performance["loc_per_second"] = index.get("loc_per_second", NOT_COLLECTED)
    performance["peak_rss_bytes"] = index.get("peak_rss_bytes", NOT_COLLECTED)
    performance["disk_bytes_per_chunk"] = index.get("disk_bytes_per_chunk", NOT_COLLECTED)
    performance["startup_ms"] = phase_measure(adapter, config, fixture, "startup").get("wall_ms", NOT_COLLECTED)
    performance["incremental_convergence_ms"] = phase_measure(adapter, config, fixture, "incremental").get("convergence_ms", NOT_COLLECTED)
    performance["idle_memory_bytes"] = phase_measure(adapter, config, fixture, "idle").get("bytes", NOT_COLLECTED)
    quality = aggregate_quality([result["metrics"] for result in query_results])
    return {
        **base,
        "status": "executed",
        "queries": query_results,
        "quality": quality,
        "performance": performance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=("out-of-box", "controlled"), default="out-of-box")
    parser.add_argument("--adapter", action="append", help="limit to one or more adapter IDs")
    parser.add_argument("--execute", action="store_true", help="actually invoke adapter commands")
    parser.add_argument("--dry-run", action="store_true", help="print a not_executed plan (the default)")
    parser.add_argument("--allow-network", action="store_true", help="allow a config that explicitly requests network")
    parser.add_argument("--output", type=Path, help="optional JSON report path; prefer ignored benchmarks/results")
    args = parser.parse_args(argv)
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run are mutually exclusive")

    config = load_json(args.config.resolve())
    if config.get("network", False) and not args.allow_network:
        parser.error("config requests network; repeat with --allow-network")
    fixture = (ROOT / config["fixture"]).resolve()
    query_path = (ROOT / config["queries"]).resolve()
    competitor_path = (ROOT / config["competitors"]).resolve()
    adapters_dir = (ROOT / config["adapters"]).resolve()
    queries = load_queries(query_path)
    adapter_config_paths: dict[str, Path] = {}
    adapters = []
    for path in adapter_files(adapters_dir):
        adapter = load_json(path)
        adapters.append(adapter)
        if adapter.get('id'):
            adapter_config_paths[str(adapter['id'])] = path
    if args.adapter:
        allowed = set(args.adapter)
        adapters = [adapter for adapter in adapters if adapter.get("id") in allowed]
        missing = allowed - {adapter.get("id") for adapter in adapters}
        if missing:
            parser.error(f"unknown adapter(s): {', '.join(sorted(missing))}")

    report = plan_report(
        config, queries, adapters, args.mode, fixture, query_path, competitor_path,
        config_path=args.config.resolve(), adapter_paths=adapter_config_paths,
    )
    if args.execute:
        report["status"] = "executed"
        report["reason"] = "Explicit --execute requested; inspect each adapter status before comparing metrics."
        report["results"] = [run_adapter(adapter, config, queries, args.mode, fixture) for adapter in adapters]
        report["versions"] = {result["adapter"]: result.get("observed_version", NOT_COLLECTED) for result in report["results"]}

    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(f"Wrote {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
