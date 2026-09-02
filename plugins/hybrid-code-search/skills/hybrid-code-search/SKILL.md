---
name: hybrid-code-search
description: Deprecated compatibility alias for host-neutral Symbraid semantic code search with exact and AST verification.
---

# Hybrid Code Search (Deprecated Alias)

This skill preserves the historical hybrid-code-search name until the Symbraid
2.0 release. New prompts should use $symbraid-search. Both names discover the
active Symbraid source through the read-only MCP server
io.github.symbraid-project/symbraid.

Use the portable symbraid executable supplied by PATH, pipx, uv tool, or
explicit user configuration. Do not assume a particular operating system,
shell launcher, user profile path, or storage backend.

For behavior or architecture questions, call semantic_search after checking
index_status, then verify candidate paths and symbols with bounded rg and AST
search. For exact identifiers or literals, start with rg; for structural
definitions and calls, start with ast-grep or a language symbol tool.

Never mutate the index from this plugin. It exposes only semantic_search,
index_status, and list_index_sources; Symbraid and the VS Code extension own
indexing and watcher lifecycle.
