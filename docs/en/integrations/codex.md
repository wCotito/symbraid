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

## Setup

Install `symbraid-search` from the repository checkout or a reviewed build
artifact, then start a new Codex session. Confirm the MCP handshake and check
the active source before searching. If the server is unavailable, use the
[troubleshooting guide](../operations/troubleshooting.md); do not reset an
index or add a second source to work around a client error.

MCP server identifier: `io.github.wcotito/symbraid`.

## External HTTP MCP for a sandboxed client

When the embedding profile uses a remote OpenAI-compatible endpoint, a stdio
server started by a sandboxed client can inherit its outbound network policy.
On Windows, configure one external loopback server for all projects registered
in the Symbraid registry. Run the script from an ordinary external PowerShell,
not from a sandboxed Codex shell:

```powershell
.\scripts\configure-codex-http-mcp.ps1
```

The helper resolves Codex state from `-CodexHome`, then `CODEX_HOME`, then the
normal user profile. It refuses an apparent `CodexSandbox*` profile so that a
sandbox shadow directory is not modified accidentally. The helper verifies
that the installed `symbraid` supports `--allow-all-projects` and
`--auth-token-env` before changing anything.

The script creates or reuses a bearer token in a user environment variable,
disables only the bundled stdio MCP entries for installed Symbraid plugins,
and adds one global Streamable HTTP entry to `<CodexHome>\config.toml`. The
token is never written to Codex config, state JSON, task arguments, or logs.
The listener is always bound to `127.0.0.1` and requires the token.

For an explicit per-user logon task:

```powershell
.\scripts\configure-codex-http-mcp.ps1 -InstallStartupTask
```

Inspect or remove only the integration owned by the helper:

```powershell
.\scripts\configure-codex-http-mcp.ps1 -Action Status
.\scripts\configure-codex-http-mcp.ps1 -Action Remove
```

`-Action Remove` leaves the token environment variable unless
`-RemoveManagedToken` is explicitly supplied. `-NoStart` configures Codex but
does not claim that the endpoint is running. Restart Codex after configuration
so it reloads both `config.toml` and the user environment.

The server starts without `--project`; every tool request must supply a
registered `project_path`. It can therefore address any project in the shared
registry while retaining the same three read-only tools.

## Optional HTTP transport

For a manual local integration, provide the bearer token through the
environment. Bind the server to one project by default and never commit the
bearer value:

```text
symbraid mcp --transport streamable-http --project /absolute/project --host 127.0.0.1 --port 8765 --auth-token-env SYMBRAID_MCP_TOKEN
```

To serve every registered project from one process, replace `--project ...`
with `--allow-all-projects`. This broader scope is always explicit; requests
must still provide `project_path`. `--token-env` remains a compatible alias for
`--auth-token-env`.

The endpoint is typically `http://127.0.0.1:8765/mcp`. A client must send a
Bearer Authorization header and an appropriate Streamable HTTP Accept header.

## Transport safety

Stdio is the recommended transport for local clients. Enable HTTP only for an
explicit local integration, bind to `127.0.0.1` or `::1`, require the token,
and restrict the accepted `Origin`. Do not bind to `0.0.0.0`, a LAN address,
or a public interface. Token material is kept in the OS environment and is
never serialized or logged.

See [configuration](../configuration.md) and [security guidance](../project/security.md)
for the complete contract.
