# Architecture

Symbraid is a local-first code index. The portable Python core owns
configuration, indexing, managed stores, and the foreground watcher. Clients
consume a read-only MCP contract; they do not open the vector store directly.

```text
project on disk
      │
      ▼
Symbraid core (CLI / foreground watcher)
  ├─ rg + ignore rules
  ├─ Tree-sitter chunking
  ├─ file/content hashes
  └─ embedding profile
      │
      ▼
one active managed source per project
  ├─ LanceDB (local)
  └─ Qdrant (managed/remote)
      │
      ▼
read-only MCP gateway
      │
      ├─ stdio (default)
      └─ loopback-only Streamable HTTP (opt-in)
      │
      ▼
VS Code, Codex, and other clients
```

## Boundaries

### Core

The core is the only owner of registry state, indexing, migrations, and
watcher lifecycle. A normalized absolute project path maps to a stable
`project_id` (the first 16 characters of its SHA-256 digest). One project has
one active managed source; results from different sources are never mixed.

The watcher is a foreground core process. Service recipes may be provided for
operators, but an installer must not silently create a privileged or
always-running daemon.

### Stores and migration

An index row represents a function, method, class, or small text fragment. A
typical payload is:

```json
{
  "repo_id": "0123456789abcdef",
  "path": "src/auth/session.ts",
  "language": "typescript",
  "symbol": "renewSessionCredentials",
  "kind": "function",
  "start_line": 84,
  "end_line": 126,
  "file_hash": "...",
  "content_hash": "...",
  "text": "..."
}
```

Incremental indexing marks metadata incomplete before work begins, re-embeds
only changed chunks, removes deleted paths, and marks the source complete only
after all checks pass. A backend migration copies vectors and payload in
batches, validates schema/provider/model/dimension/count, and switches the
active source atomically. The previous source remains available for rollback.

### MCP and clients

The MCP gateway exposes exactly three read-only tools:

- `semantic_search`;
- `index_status`;
- `list_index_sources`.

Stdio is the default transport. Streamable HTTP is disabled unless explicitly
enabled and is bound to loopback. The Codex plugin and VS Code integration are
thin clients: they do not import LanceDB/Qdrant, calculate embeddings, or
mutate an index.

Semantic results are candidates, not proof. A safe change workflow confirms a
candidate with exact search, AST/symbol search, and the current file on disk.

## Trust boundaries

- managed sources are written only by the core;
- MCP is read-only;
- clients cannot trigger indexing through MCP;
- credentials are accepted through stdin or an explicitly opted-in environment
  reference and stored through the operating-system keyring;
- paths, keys, model caches, and private source contents stay local unless a
  configured embedding endpoint receives a request.
