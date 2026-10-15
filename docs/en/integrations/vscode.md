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

Opening a directory in VS Code or viewing Manage only reads configuration.
For an unregistered directory, Manage shows the global storage and embedding
settings as a preview, without creating a project, source, index, or watcher.

To enable a new project, either click the status-bar icon to register and start
with global defaults, or open Manage > Project. Its fields are prefilled with
global values: keep them or change the backend, storage location, and model,
then choose **Register and start**, review the plan, and confirm. Registration
creates the first managed source directly with the selected settings and enables
auto-watch. Cancelling the plan or confirmation leaves the directory unregistered.

Each registration uses a unique managed storage location. Registering a directory
again after removing its registry entry leaves the retained old index untouched
and builds a fresh index. A plan also binds the selected embedding provider,
model, dimension, endpoint, and credential reference; changing the profile requires
a new plan before registration.

Global defaults accept global embedding profiles. A project-scoped profile can
be chosen explicitly only for its owning project, including during registration.

Reopening an existing project preserves its active source, local overrides,
and auto-watch preference. An enabled auto-watch resumes automatically.

If project settings cannot be loaded, Manage still attempts to show global
defaults and global model profiles, with the project error in Overview.

Update both the core and VS Code extension for this workflow; the core provides
the read-only preview and validates the registration plan.

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
