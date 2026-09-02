# Codex plugin symbraid-search

symbraid-search is a thin, read-only Codex integration. It starts the
host-neutral MCP command symbraid mcp --transport stdio and provides the
symbraid-search skill for semantic discovery followed by exact and AST
verification.

A minimal hybrid-code-search compatibility plugin remains available with a
deprecation warning until the Symbraid 2.0 release. Use symbraid-search for all
new installations and prompts.

Install the portable Symbraid CLI first with scripts/install.ps1 or
scripts/install.sh, then install this plugin from the repository marketplace:

    codex plugin marketplace add .
    codex plugin add symbraid-search@semantic-code-index-kit

Documentation:

- [English Codex integration](../../docs/en/integrations/codex.md)
- [Russian Codex integration](../../docs/ru/integrations/codex.md)

The MCP server identifier is io.github.symbraid-project/symbraid. Start a new
Codex session after installation so the MCP server and skill are loaded.
