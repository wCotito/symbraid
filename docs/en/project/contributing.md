# Contributing

Contributions should keep indexing and data ownership in the Symbraid core.
Client integrations remain thin and must use the documented read-only MCP
surface.

For documentation, edit the English file under `docs/en` first, update the
identical relative path under `docs/ru`, and run `python scripts/sync_docs.py
--check`. Do not leave a flat legacy filename when a page belongs in an
integration, operations, project, or review section.

Run the Manage browser regression with Python 3.10+ on `PATH`:

```sh
cd extensions/vscode-symbraid
npm ci
npx playwright install chromium
npm run test:browser
```

Set `SYMBRAID_TEST_PYTHON` to choose another Python executable. The test runs
the real core preview/plan/apply in an isolated temporary directory without
database or model dependencies, and verifies the real Manage form in EN/RU.
CI runs this check alongside the extension tests.

See the repository [contribution guide](../../../CONTRIBUTING.md) for pull-request
checks and [release readiness](../reviews/release-readiness.md) for build
requirements.
