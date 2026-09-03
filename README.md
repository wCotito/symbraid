# Symbraid

[English](https://github.com/symbraid-project/symbraid/blob/main/docs/en/README.md) | [Русский](https://github.com/symbraid-project/symbraid/blob/main/docs/ru/README.md)

Symbraid is a local-first semantic index for software repositories. It turns a
project into a searchable knowledge source for developers, IDEs, and any
MCP-compatible AI client without making VS Code or a specific agent responsible
for indexing.

The Python core owns configuration, indexing, incremental updates, storage, and
the read-only MCP server. VS Code and Codex integrations are optional thin
clients over the same CLI.

## Why Symbraid

- Search code by intent when you do not know the filename or symbol.
- Keep one reusable index for multiple editors and AI clients.
- Run on Windows 10/11 x64 or Linux glibc x86_64.
- Store vectors locally in LanceDB or in a configured Qdrant instance.
- Watch a repository and reconcile creates, edits, deletes, ignore rules, and
  Git branch changes.
- Expose only three read-only MCP tools: `semantic_search`, `index_status`,
  and `list_index_sources`.
- Change backend or embedding model through validated plans while retaining the
  previous source for rollback.

## How it works

1. The CLI registers a canonical project path and creates one active managed
   source.
2. The indexer discovers files with `ripgrep`, splits supported source and text
   formats into chunks, creates embeddings, and stores metadata with vectors.
3. `symbraid watch` incrementally reconciles filesystem and Git changes.
4. Search requests go through the CLI or MCP server and return bounded candidate
   chunks with project/source metadata.
5. The calling editor or agent verifies candidates against the current checkout
   before using them.

Configuration and secrets live outside the repository. API keys are referenced
through the OS keyring or environment variables and are not returned by CLI,
MCP, HTTP, or the Manage view.

## Quick start

Prerequisites: Python 3.10 or newer and `rg` on `PATH`.

~~~text
git clone <repository-url> symbraid
cd symbraid
python -m pip install -e ./components/symbraid

symbraid project register /absolute/path/to/project
symbraid index /absolute/path/to/project
symbraid status /absolute/path/to/project
symbraid search /absolute/path/to/project "where are access tokens renewed"
~~~

Keep the index current in a foreground process:

~~~text
symbraid watch /absolute/path/to/project
~~~

Start the default stdio MCP server for a client:

~~~text
symbraid mcp --project /absolute/path/to/project
~~~

For Windows convenience installation, Linux shell installation, Qdrant,
embedding profiles, and upgrades, see the
[installation guide](https://github.com/symbraid-project/symbraid/blob/main/docs/en/installation.md)
and [configuration guide](https://github.com/symbraid-project/symbraid/blob/main/docs/en/configuration.md).

## Integrations

Symbraid is not tied to one host. Standard MCP transports and example
configurations cover Codex, Claude Code/Desktop, VS Code, Cursor, Windsurf, and
OpenCode. Stdio is the default. Opt-in Streamable HTTP is restricted to loopback
and requires bearer-token, Origin, and Host validation.

- [MCP clients and transports](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/mcp.md)
- [VS Code extension](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/vscode.md)
- [Codex plugin](https://github.com/symbraid-project/symbraid/blob/main/docs/en/integrations/codex.md)
- [CLI reference](https://github.com/symbraid-project/symbraid/blob/main/docs/en/cli.md)

## Strengths and tradeoffs

Strengths:

- a host-neutral core and a single index shared by integrations;
- local-first operation with a choice of embedded or service storage;
- incremental watcher, project locking, interruption recovery, and source
  validation;
- explicit secret redaction and a deliberately read-only MCP surface;
- safe backend/model transitions that preserve the prior source;
- symmetric English and Russian documentation and cross-platform tests.

Tradeoffs:

- the first full index can be CPU-, network-, and embedding-cost intensive;
- semantic quality and latency depend on the selected embedding provider,
  chunking, hardware, and backend;
- Qdrant requires a separately operated service;
- macOS, Linux ARM64, external HTTP binding, TLS termination, and multi-user
  remote deployment are not release targets yet;
- search results are candidates and must be verified against current files
  before automated edits.

## Benchmark snapshot

A controlled local run on the committed polyglot fixture (six judged queries, one excluded warm-up and five measured CLI invocations,
Windows 11 x64) produced this first regression baseline:

| Metric | Symbraid 0.3.0 | ripgrep 15.2.0 |
| --- | ---: | ---: |
| nDCG@10 | 0.830 | 0.634 |
| Recall@10 | 0.886 | 0.622 |
| Warmed CLI invocation p50 | 5,435 ms | 52 ms |

Symbraid ranked semantic results better on this small fixture; ripgrep remained
far faster. This is a partial comparison, not a universal claim or a full
competitor ranking. Cold indexing and resource metrics were not collected, and
version-pinned Codanna, open-codebase-index, and Zilliz Claude Context runs are
still pending. The [benchmark report](https://github.com/symbraid-project/symbraid/blob/main/docs/en/benchmarks.md) records the complete metric
table, hardware, limitations, provenance hashes, and reproduction commands.
## Documentation

- [Architecture](https://github.com/symbraid-project/symbraid/blob/main/docs/en/architecture.md)
- [Installation](https://github.com/symbraid-project/symbraid/blob/main/docs/en/installation.md)
- [Configuration and secrets](https://github.com/symbraid-project/symbraid/blob/main/docs/en/configuration.md)
- [Embedding profiles](https://github.com/symbraid-project/symbraid/blob/main/docs/en/embeddings.md)
- [Operations and troubleshooting](https://github.com/symbraid-project/symbraid/blob/main/docs/en/operations/troubleshooting.md)
- [Security](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/security.md)
- [Name availability review](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/naming.md)
- [Contributing](https://github.com/symbraid-project/symbraid/blob/main/docs/en/project/contributing.md)
- [Release readiness review](https://github.com/symbraid-project/symbraid/blob/main/docs/en/reviews/release-readiness.md)

Symbraid is distributed under the [MIT License](https://github.com/symbraid-project/symbraid/blob/main/LICENSE).
