# Installation, upgrades, and removal

## Supported baseline

- Windows 10/11 x64;
- Linux glibc x86_64 (the native release baseline);
- Python 3.10 or newer;
- `ripgrep` (`rg`); and
- Node.js/VS Code and Codex CLI only when their optional integrations are used.

LanceDB works locally. Qdrant is optional and is used only when a managed or
remote backend is deliberately configured. The core does not require Docker.

## From a checkout

```powershell
git clone <repository-url> symbraid
cd symbraid
python -m pip install -e ./components/symbraid
python -m symbraid --help
```

On Windows, the repository installer remains the supported convenience path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

The installer keeps runtime data outside the checkout and does not publish
packages. Use `-SkipExtension` or `-SkipCodexPlugin` when those integrations
are not needed. Never copy credentials into command-line arguments or a config
file.

## First project

The command names are stable across platforms; use the launcher supplied by
your installation where one is available:

```text
symbraid project register /absolute/path/to/project
symbraid index /absolute/path/to/project
symbraid status /absolute/path/to/project
```

Open a new VS Code or Codex session after installing an integration so its MCP
and skill metadata is reloaded.

## Upgrade

1. Review the [release notes](../../CHANGELOG.md).
2. Run the repository verification appropriate for your platform.
3. Install the new core and optional integrations from the checkout.
4. Check `status` and confirm the active source metadata before indexing.

The registry, model cache, and managed indexes are preserved. A model or
dimension change requires a new source and full reindex; a backend migration
does not recompute embeddings.

## Removal

Remove integrations first, then remove runtime data only after confirming the
exact paths. Existing managed indexes and external collections are not deleted
automatically. Destructive cleanup requires a separate, explicit operator
action.

## GitHub marketplace/plugin

After the repository is made available to your Codex installation:

```powershell
codex plugin marketplace add symbraid-project/symbraid --ref main
codex plugin add symbraid-search@symbraid
```

This adds only the thin client. The core, its dependencies, and its configured
backend must be installed separately.
