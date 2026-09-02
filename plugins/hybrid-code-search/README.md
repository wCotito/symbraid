# Deprecated Codex plugin alias: hybrid-code-search

This thin, read-only plugin remains for compatibility until the Symbraid 2.0
release. It forwards the historical name to the host-neutral command
symbraid mcp --transport stdio; it contains no indexer, watcher, or backend
logic.

Use symbraid-search for new installations and prompts:

    codex plugin add symbraid-search@semantic-code-index-kit

Documentation:

- [English Codex integration](../../docs/en/integrations/codex.md)
- [Russian Codex integration](../../docs/ru/integrations/codex.md)

The alias and canonical plugin use the MCP server
io.github.symbraid-project/symbraid. Start a new Codex session after changing
plugins.
