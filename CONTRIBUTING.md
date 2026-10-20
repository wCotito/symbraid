# Contributing

Contributions should keep indexing and data ownership in the Symbraid core.
Client integrations remain thin and must use the documented read-only MCP
surface.

For documentation, edit the English file under `docs/en` first, update the
identical relative path under `docs/ru`, and run `python scripts/sync_docs.py
--check`. Do not leave a flat legacy filename when a page belongs in an
integration, operations, project, or review section.

Build and test the extension with Node.js 22.12.0+ and Python 3.10+ on `PATH`.
Run the Manage browser regression:

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
The extension CI matrix checks both Node.js 22.12.0 and the latest Node.js 22.

The security workflow audits the complete Python lockfile, including every
platform variant and optional extra, and all npm development dependencies.
It exports `uv.lock` to a temporary `pylock.toml` for `pip-audit` with OSV;
the export is not a second maintained lockfile. Vulnerabilities and audit
service errors fail the job. Run `npm audit --package-lock-only` from the
extension directory, and use the commands in
[the security workflow](/.github/workflows/security.yml) for Python.
See the [dependency security update](/docs/en/reviews/dependency-security.md) for
the original alert inventory and compatibility requirements.

See the repository [contribution guide](../../../CONTRIBUTING.md) for pull-request
checks and [release readiness](../reviews/release-readiness.md) for build
requirements.
