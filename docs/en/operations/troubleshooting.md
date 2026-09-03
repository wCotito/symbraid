# Troubleshooting

Start with `symbraid status <project>` and inspect the active source, backend,
embedding profile, dimension, and chunk count. Redact paths, tokens, and source
text before sharing diagnostics.

## Common cases

- **No results:** verify that the project is registered, indexing completed,
  and the query is sent to the active managed source. Check provider, model,
  and dimension compatibility before reindexing.
- **Watcher is not running:** confirm the workspace path and watcher lease.
  The watcher is a foreground core-owned process; the extension is only a
  client. Start it from the core CLI or use an OS service recipe when a
  long-running process is explicitly required.
- **MCP handshake fails:** use stdio first. For HTTP, confirm a literal
  loopback bind, token, host, and origin; public or wildcard binds are rejected.
- **Migration looks unsafe:** stop and review the impact plan. The original
  source remains available until schema, provider, model, dimension, and count
  checks pass. Never delete an old or external collection without explicit
  approval.
- **Secret is missing:** restore the keyring entry or the allowed environment
  reference. Configuration stores references, never secret values.

For deployment steps see [agent deployment](agent-deployment.md). For client
boundaries see the [MCP](../integrations/mcp.md), [VS Code](../integrations/vscode.md),
and [Codex](../integrations/codex.md) guides.
## Transient local failures

A read-only status request does not fail merely because Windows temporarily
refuses a watcher-lock probe. The response keeps the watcher owner when it can
be read and marks the probe as `unavailable`. The VS Code overview also requests
`symbraid status` when the settings payload has no index status, and displays
command errors instead of an empty object.

OpenAI-compatible embedding requests retry transient network failures, timeouts,
invalid transient responses, and HTTP 408, 429, and 5xx gateway/service errors up
to three attempts. Authentication and other permanent HTTP errors fail
immediately. If all attempts fail, check endpoint reachability, firewall policy,
proxy policy, credentials, and provider health.
