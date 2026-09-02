# Agent instructions

Symbraid has one source of truth for the core, VS Code integration, Codex
plugin, documentation, and benchmark harness. Agents may edit repository
sources but must not edit installed runtimes or plugin caches directly.

The architectural boundaries are:

- `components/symbraid` owns indexing, stores, configuration, migrations, and
  the read-only MCP server;
- `extensions/vscode-symbraid` is a workspace-scoped thin client;
- `plugins/symbraid-search` is a thin Codex adapter;
- one project has one active managed source; and
- source/provider/model/dimension/count checks protect every backend change.

Do not serialize secrets, mix projects, or delete an old/external collection
without explicit approval. Update the English canonical docs and the matching
Russian path whenever behaviour changes.
