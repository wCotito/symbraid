# CLI

The core CLI is the automation boundary. Commands emit structured JSON on
stdout; errors are sent to stderr with a non-zero exit code. Use the launcher
provided by the platform package, or run the Python entrypoint from a checkout.

```text
symbraid --help
symbraid paths
```

## Projects and sources

```text
symbraid project register /absolute/project
symbraid project list
symbraid project autowatch /absolute/project on
symbraid source list /absolute/project
symbraid source use /absolute/project <source-id-from-list>
```

`project remove` removes only registry metadata by default. Physical managed
indexes are retained. There is exactly one active managed source for a project.

New LanceDB sources use `<lancedb_root>/<full-source-uuid>` without the project
directory name. Existing source locations are preserved. On Windows, the resolved
managed directory is limited to 160 UTF-16 code units, leaving room for Lance's
internal data, transaction, and temporary files. An oversized `lancedb_root` is
rejected during registration planning and before registration is saved, without
opening a store. Choose a shorter global root or override it for the project in
Manage; the full UUID still keeps registrations and retained indexes separate.

## Settings and profiles

```text
symbraid settings show --project /absolute/project
printf '{"backend":"qdrant"}' | symbraid settings plan /absolute/project
symbraid defaults show
symbraid profile list
symbraid profile test local-code
```

Settings payloads and secret values are accepted through stdin. A settings plan
classifies a change as `configuration-only`, `transfer`, or `reindex`; applying
an old plan hash is rejected.

For an unregistered directory, `settings show --project` returns a read-only
preview with `project.registered=false`, global effective settings, and no
active source. `settings plan` returns a `register` plan for that directory;
only `settings apply-project` with its matching hash creates the initial
managed source. The registration payload can keep global defaults or override
storage and embedding settings; `auto_watch=true` saves the enabled preference.

## Indexing and search

```text
symbraid index /absolute/project
symbraid index /absolute/project --force
symbraid refresh /absolute/project src/auth/session.py
symbraid status /absolute/project
symbraid search /absolute/project "where are access tokens renewed" --top-k 10
```

`index` reconciles the project and re-embeds changed files. `--force` rebuilds
all chunks. `refresh` is intended for a small changed/deleted path set; use a
full reconcile after a branch switch or ignore-rule change. Search results must
be checked against the current file before edits.

## Backend migration

```text
symbraid migrate-backend /absolute/project qdrant
symbraid migrate-backend /absolute/project lancedb
```

Migration copies vectors without recomputing embeddings. The core validates
schema, provider, model, dimension, and count before switching the active source;
the prior source remains a rollback option.

## MCP

```text
symbraid mcp                 # stdio, the default
symbraid mcp --transport streamable-http --project /absolute/project --host 127.0.0.1 --port 8765 --auth-token-env SYMBRAID_MCP_TOKEN  # explicit loopback opt-in
symbraid mcp --transport streamable-http --allow-all-projects --host 127.0.0.1 --port 8765 --auth-token-env SYMBRAID_MCP_TOKEN  # all registered projects
```

Do not print diagnostics to the stdio process. The gateway exposes only
`semantic_search`, `index_status`, and `list_index_sources`.
