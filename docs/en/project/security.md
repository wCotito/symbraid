# Security guidance

Report suspected vulnerabilities privately using the process in the repository
[security policy](../../../SECURITY.md). Do not put credentials, tokens, private
source text, or database data in public issues or logs.

The core must keep one managed source per project and preserve the old source
during a migration. MCP exposes only read-only discovery tools. Optional HTTP
is loopback-only, token-protected, and origin-checked. The plugin and extension
must not write indexes or import backend libraries.

Secrets are accepted through protected input and stored in the OS keyring. An
explicit headless environment reference may name a variable, but the value is
never serialized, passed as a CLI argument, or logged.
