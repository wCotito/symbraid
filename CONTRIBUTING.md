# Contributing

Contributions should keep indexing and data ownership in the Symbraid core.
Client integrations remain thin and must use the documented read-only MCP
surface.

For documentation, edit the English file under `docs/en` first, update the
identical relative path under `docs/ru`, and run `python scripts/sync_docs.py
--check`. Do not leave a flat legacy filename when a page belongs in an
integration, operations, project, or review section.

See the repository [contribution guide](../../../CONTRIBUTING.md) for pull-request
checks and [release readiness](../reviews/release-readiness.md) for build
requirements.
