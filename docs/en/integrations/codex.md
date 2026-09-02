# Codex integration

The Codex plugin is a thin adapter around Symbraid's MCP server. It discovers
the server through stdio by default and forwards read-only search and status
requests. It contains no indexer, vector store, embedding provider, or
database dependency.

## Boundary

The plugin may call only `semantic_search`, `index_status`, and
`list_index_sources`. It must not add indexing, refresh, delete, transfer, or
source-switch commands. The core owns project identity, source selection,
embedding compatibility, and all writes.

The historical `hybrid-code-search` name is a one-major compatibility alias
for migration. New documentation and configuration use `symbraid-search`.

## Setup

Install the plugin from the repository checkout or a reviewed build artifact,
then start a new Codex session. Confirm the MCP handshake and check the active
source before searching. If the server is unavailable, use the [troubleshooting
guide](../operations/troubleshooting.md); do not reset an index or add a
second source to work around a client error.

MCP server identifier: `io.github.symbraid-project/symbraid`.
