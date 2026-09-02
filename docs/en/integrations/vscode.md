# VS Code integration

The VS Code extension is a thin workspace-scoped client. It starts and stops
the Symbraid core watcher for the open workspace and presents status and
configuration controls; it does not own indexing, embeddings, databases, or
migration logic.

## Workspace boundary

Only the current workspace is eligible for watching. The extension must not
scan an unrelated folder, merge projects, or mutate an external collection.
The core remains the authority for one active managed source and for migration
impact plans.

## Setup

Install the extension artifact built from `extensions/vscode-symbraid`, then
set `symbraid.executablePath` only when the `symbraid` command is not on `PATH`.
Leave it empty to use the normal launcher and its documented compatibility
fallback. Keep credentials out of settings and workspace files.

Use the extension's manage and watcher commands for a human-readable status.
For indexing, backend changes, or recovery, follow the [CLI guide](../cli.md)
and [operations guide](../operations/agent-deployment.md).

