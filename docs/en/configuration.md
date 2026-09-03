# Configuration and secrets

## Locations

Configuration is kept outside indexed repositories. The platform default is
used unless `SYMBRAID_CONFIG` is set explicitly:

- Windows: `%LOCALAPPDATA%\Symbraid\config.json`;
- Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/symbraid/config.json`.

Indexes, locks, and model caches likewise use platform data directories. The
exact paths are printed by `symbraid paths` and are not committed to a
repository.

The registry stores a `secret_ref`, never a secret value. Interactive setups
use the OS keyring. Headless Linux may opt into an environment-backed reference
such as `env://SYMBRAID_EMBEDDING_KEY`; the value is read at runtime and is not
written to JSON or logs.

## Defaults and project overrides

```text
symbraid defaults show
symbraid defaults set --backend lancedb
symbraid project override /absolute/project --debounce-ms 2000
symbraid project override /absolute/project --embedding-profile local-code
```

Common settings include:

- `backend`: `lancedb` or `qdrant`;
- `embedding_profile`;
- Qdrant URL and `secret_ref`;
- local store root;
- debounce and bulk-change thresholds;
- maximum file size; and
- chunk size, overlap, batch size, and `rg` path.

Project configuration stores only overrides plus the normalized path,
`project_id`, watcher state, managed sources, and one `active_source_id`.

## Safe secret input

Pass a key through stdin and let the core save it to the OS keyring:

```powershell
Read-Host 'Embedding API key' -AsSecureString |
  symbraid profile set remote-code --api-key-stdin
```

Do not put secrets in shell history, process arguments, tests, issue reports,
or `config.json`. Before changing a provider, run the profile test and verify
the returned dimension. A changed provider, model, or dimension creates a new
managed source rather than mutating an incompatible one.

## Locks and safety

Writes use a per-project lock so watcher, index, refresh, and migration cannot
mutate one project concurrently. `status` and `search` are read-only.

Symbraid changes only managed sources it created. It never alters unknown
Qdrant collections or external LanceDB directories without an explicit,
operator-confirmed action.

## Collection names

Managed Qdrant sources use the `symbraid-<project-id>` collection prefix.
Structural settings changes create a new `symbraid-*` source and retain the
previous source for rollback. A generated source never reuses a collection
owned by another project.
