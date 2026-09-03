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
set `symbraid.executablePath` only when the `symbraid` command is not on
`PATH`. An empty value resolves `symbraid` through `PATH`. Keep credentials
out of settings and workspace files.

Use the extension's Manage and watcher commands for a human-readable status.
For indexing, backend changes, or recovery, follow the [CLI guide](../cli.md)
and [operations guide](../operations/agent-deployment.md).

The Manage Overview reads the current `project.index_status` payload from the
CLI, including index completeness, counts, active backend, and watcher
ownership.

## Existing watcher processes and startup errors

Before spawning a watcher, the extension asks the core for the current watcher
status. If another terminal, editor instance, or OS service already owns the
project lease, the extension adopts that state as an external running watcher
instead of starting a duplicate. Stop an external watcher through the process
or service that owns it.

The extension periodically rechecks an adopted watcher and, if it exits,
restarts it when auto-watch is enabled.

A startup failure keeps the structured CLI error, writes it to the **Symbraid**
output channel, and displays a notification with a **Show Output** action. The
status-bar tooltip shows the same error.
