# Symbraid

[English](https://github.com/symbraid-project/symbraid/blob/main/docs/en/README.md) | [Русский](https://github.com/symbraid-project/symbraid/blob/main/docs/ru/README.md)


Symbraid is a local-first code indexing and semantic discovery toolkit. The
English documentation is the canonical source; the Russian tree at
[`../ru/README.md`](https://github.com/symbraid-project/symbraid/blob/main/docs/ru/README.md) has the same relative paths and is kept in
parity by [`scripts/sync_docs.py`](https://github.com/symbraid-project/symbraid/blob/main/scripts/sync_docs.py).

## Guides

- [Architecture](https://github.com/symbraid-project/symbraid/blob/main/docs/en/architecture.md)
- [Installation and upgrades](https://github.com/symbraid-project/symbraid/blob/main/docs/en/installation.md)
- [Configuration and secrets](https://github.com/symbraid-project/symbraid/blob/main/docs/en/configuration.md)
- [Embedding profiles](https://github.com/symbraid-project/symbraid/blob/main/docs/en/embeddings.md)
- [CLI](https://github.com/symbraid-project/symbraid/blob/main/docs/en/cli.md)
- [MCP integration](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/mcp.md)
- [VS Code integration and watcher](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/vscode.md)
- [Codex integration](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/codex.md)
- [Troubleshooting](https://github.com/symbraid-project/symbraid/blob/main/docs/en/operations/troubleshooting.md)
- [Agent deployment](https://github.com/symbraid-project/symbraid/blob/main/docs/en/operations/agent-deployment.md)
- [Benchmarks](https://github.com/symbraid-project/symbraid/blob/main/docs/en/benchmarks.md)
- [Agent instructions](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/agents.md)
- [Contributing](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/contributing.md)
- [Security](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/security.md)
- [License](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/license.md)
- [Release readiness](https://github.com/symbraid-project/symbraid/blob/main/docs/en/reviews/release-readiness.md)

The repository root contains short English entrypoints for GitHub discovery:
[`README.md`](https://github.com/symbraid-project/symbraid/blob/main/README.md), [`CONTRIBUTING.md`](https://github.com/symbraid-project/symbraid/blob/main/CONTRIBUTING.md),
[`SECURITY.md`](https://github.com/symbraid-project/symbraid/blob/main/SECURITY.md), and [`AGENTS.md`](https://github.com/symbraid-project/symbraid/blob/main/AGENTS.md).

## Language policy

When a guide changes, update English first, translate the corresponding Russian
file, then run:

```powershell
python scripts/sync_docs.py --check
```

The checker verifies relative-path parity, recorded source hashes, stale
translations, and local Markdown links without making network requests.
