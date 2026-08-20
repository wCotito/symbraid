---
name: hybrid-code-search
description: Use read-only semantic code search plus exact and AST verification. Trigger when Codex needs to understand an unfamiliar or large repository, locate behavior without knowing identifiers, trace implementations by concept, or verify semantic candidates before editing source code.
---

# Hybrid Code Search

Use the active managed LanceDB or Qdrant source selected by the independent Code Index application for discovery, then prove every result against the current checkout.

## Route the request

- Exact identifier, filename, error text, or literal known: start with `rg`; semantic search is optional.
- Behavior, architecture, or implementation described in natural language: call `semantic_search` first.
- All definitions, calls, imports, or structural constructs requested: start with `ast-grep` or the language symbol tool, then confirm with `rg`.
- Index missing or stale: report the reason. Do not start or mutate indexing from this plugin.

## Semantic workflow

1. Call `index_status(project_path)`.
2. If no usable active source is available, continue with bounded `rg` and AST search.
3. Call `semantic_search(query, project_path, top_k=10)` with a behavior-focused query.
4. Extract candidate paths, symbols, line ranges, and content hashes.
5. Verify symbols and distinctive literals with bounded `rg -n` searches in candidate files.
6. Verify definitions, calls, inheritance, or imports with `ast-grep` or a language symbol tool. Read [verification-patterns.md](references/verification-patterns.md) when AST syntax is needed.
7. Read the current source file around the returned range. Treat shifted lines or changed content as a stale candidate.
8. Inspect callers and tests before editing.

## Integrity rules

- Never edit a file based only on semantic similarity.
- Never treat an indexed preview as current source; always read the file from disk.
- Keep semantic results compact: normally request 5-15 candidates, never more than 20.
- Prefer a path filter when the subsystem is known.
- Never call mutating index tools: this MCP intentionally exposes only `semantic_search`, `index_status`, and `list_index_sources`.
- Code Index and its VS Code extension own indexing and watcher lifecycle. This skill does not assume the watcher is active.
- Do not use semantic search to enumerate every occurrence; use `rg` or AST search.

## Failure handling

- Code Index application, active source, or backend unavailable: report the specific failure and continue with bounded `rg`/AST search.
- Embedding model unavailable: do not replace it silently; report the configured provider and model.
- `indexing_complete=false`: do not claim repository-wide coverage and do not repair the index from Codex.
- No semantic hits: try one clearer behavior query, then fall back to file, symbol, or text search.
- Candidate verification fails: discard it rather than forcing the semantic result.
