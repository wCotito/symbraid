# MCP integration

Symbraid's MCP server is a read-only discovery surface. The default transport
is local stdio. Streamable HTTP is opt-in and must bind only to a literal
loopback address with a configured bearer token and matching origin.

## Exposed tools

The server exposes exactly these tools:

- `semantic_search` searches the active managed source for relevant chunks;
- `index_status` reports index metadata and readiness; and
- `list_index_sources` lists the configured source identities without exposing
  credentials.

The MCP server never indexes, refreshes, deletes, transfers, or switches a
source. Use the Symbraid core CLI for lifecycle operations. A client must not
import an index backend, calculate embeddings, or write index data.

## Client configuration examples

The examples below use the stable server id and a local stdio process. Client
configuration filenames and field names can vary by client release; keep the
command and arguments unchanged and place the equivalent entry in the client
configuration documented for your version.

### Codex

In the MCP server section of the Codex configuration (TOML shape):

```toml
[mcp_servers."io.github.wcotito/symbraid"]
command = "symbraid"
args = ["mcp", "--transport", "stdio"]
```

### Claude Code and Claude Desktop

Claude Desktop uses an `mcpServers` JSON object. Claude Code can register the
same command with its CLI:

```text
claude mcp add io.github.wcotito/symbraid -- symbraid mcp --transport stdio
```

Equivalent JSON shape for a Desktop configuration is:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### VS Code

For a workspace `.vscode/mcp.json`, use the VS Code `servers` shape:

```json
{
  "servers": {
    "io.github.wcotito/symbraid": {
      "type": "stdio",
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### Cursor

Cursor's `.cursor/mcp.json` uses the familiar `mcpServers` shape:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### Windsurf

In the Windsurf MCP configuration, use the same stdio command:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### OpenCode

OpenCode releases may call this section `mcp` and represent a local command as
an argument array. The following is the generic shape; follow the installed
release's configuration schema if its field names differ:

```json
{
  "mcp": {
    "symbraid": {
      "type": "local",
      "command": ["symbraid", "mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

## Optional HTTP transport

Start HTTP only for an explicit local integration, using a token supplied via
the environment. Never commit a bearer value:

```text
symbraid mcp --transport streamable-http --host 127.0.0.1 --port 8765 --token-env SYMBRAID_MCP_TOKEN
```

The endpoint is typically `http://127.0.0.1:8765/mcp`. A generic HTTP client
entry is shown below; URL, transport, and header field names vary by client and
release, so confirm them in that client's documentation. The `${SYMBRAID_MCP_TOKEN}`
notation means “read this environment variable”, not a value to paste into a
committed file.

```json
{
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp",
  "headers": {"Authorization": "Bearer ${SYMBRAID_MCP_TOKEN}"}
}
```

## Transport safety

Stdio is the recommended transport for local clients. Enable HTTP only for an
explicit local integration, bind to `127.0.0.1` or `::1`, require the generated
token, and restrict the accepted `Origin`. Do not bind to `0.0.0.0`, a LAN
address, or a public interface. Store token material in the OS keyring; a
headless deployment may use an environment-backed reference whose value is
never serialized or logged.

See [configuration](../configuration.md) and [security guidance](../project/security.md)
for the complete contract.
