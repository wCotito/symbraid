# Dependency security update

Baseline: 2026-10-20, commit `3ede82d48cc82dc33fcfcfe27e9cd9413a2966cc`.
GitHub listed 32 open Dependabot alerts: one critical, 14 high, 14 moderate,
and three low. Eighteen affect the Python lockfile; fourteen affect npm
development dependencies used to build the VSIX.

## Alert inventory and fixes

| Package | Dependabot alert numbers | Change |
| --- | --- | --- |
| PyJWT | 7–17, 21, 22, 39 | 2.13.0 → 2.15.0 |
| urllib3 | 18–20 | 2.7.0 → 2.8.0 |
| mcp | 40 | 1.29.1 → 1.30.0 |
| fast-uri | 1–4, 23 | Removed with the vsce 4 dependency tree |
| js-yaml | 5 | Removed with the vsce 4 dependency tree |
| markdown-it | 24 | Removed with the vsce 4 dependency tree |
| undici | 26–29, 32, 33 | Removed with the vsce 4 dependency tree |
| brace-expansion | 36 | 5.0.9 → 5.0.12 |

Individual alerts are available in the
[Dependabot inventory](https://github.com/wCotito/symbraid/security/dependabot).
Critical [alert 13](https://github.com/wCotito/symbraid/security/dependabot/13)
is [CVE-2026-102268 / GHSA-ffc3-869f-jxw9](https://github.com/advisories/GHSA-ffc3-869f-jxw9).
Full lockfile audits detect eight advisory records beyond those 32 open alerts;
the same update removes all 40 detected records without suppressions.

## Security and compatibility

The published MCP, PyJWT, and urllib3 version floors also protect pip, pipx,
and `uv tool install`, which do not use the repository's `uv.lock`. Python 3.10,
the other pinned versions, and platform branches are preserved.

HTTP bearer authentication compares opaque tokens in constant time and does not
configure SDK JWT authentication. The PyJWT issue is a transitive dependency
risk, not evidence of a bypass of that bearer check. Regression coverage
rejects HMAC forgeries with CR-only and indented PEM public keys, while normal
RSA signatures remain valid.

MCP remains stateful. SDK 1.30 bounds sessions and reclaims ended sessions.
The product app is tested with a two-session limit: overflow returns 503,
DELETE frees capacity, and a deleted ID returns 404. Bearer, origin, request
body, read-only tool, and project-isolation checks remain enforced.

vsce 4 requires Node.js 22+ for development and packaging. Both installers
check this before building; skipping the extension does not require Node.js.
VS Code 1.90 remains supported. Build dependencies are excluded from the VSIX.

## Verification and closure

The security workflow audits all Python variants/extras through a temporary
PEP 751 export and `pip-audit==2.10.1` with OSV, and audits the full npm lockfile.
Any vulnerability or service error fails the job. Core, MCP transport,
extension, browser, documentation, and artifact checks remain release gates.

GitHub closes alerts after the fixed graph reaches the default branch and
Dependabot processes it. A green patch or pull request is a prepared fix;
it is not a claim that GitHub has already closed the alerts.
