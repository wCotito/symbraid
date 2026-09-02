# Agent deployment

This checklist is for an agent or maintainer changing Symbraid in a checkout.
It keeps source changes, runtime installation, and validation separate.

## Safe sequence

1. Read [architecture](../architecture.md) and the guide for the component you
   will change.
2. Inspect `git status --short` and preserve unrelated work.
3. Change the canonical source in this repository. Do not edit an installed
   runtime, plugin cache, model cache, database, or credential store directly.
4. Update `docs/en` first and the identical `docs/ru` path in the same change.
5. Run the local documentation parity check and the relevant tests. Keep
   benchmark status honest: a dry plan is not a measurement.
6. Build the core, extension, and plugin artifacts using the repository's
   supported scripts. Review the resulting diff before installation.
7. Install only after review, then verify the MCP handshake, active source, and
   client inventory in a new session.
8. Keep the original managed source for rollback until a verified migration is
   accepted.

The core owns indexing and the foreground watcher. VS Code and Codex are thin
clients. Secrets arrive through protected input or an approved environment
reference, never command-line arguments or logs.

