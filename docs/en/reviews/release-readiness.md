# Release readiness

Use this checklist before asking a maintainer to publish a release. The
repository workflows build and upload review artifacts only; publication to a
registry, marketplace, or release page is a separate deliberate action.

## Required checks

- [ ] `docs/en` and `docs/ru` have identical Markdown relative paths and the
      translation manifest reports current source hashes.
- [ ] Core tests pass on the supported Windows and Linux runners.
- [ ] Extension and plugin artifacts are built from their renamed Symbraid
      directories and contain no credentials or generated indexes.
- [ ] MCP still exposes exactly three read-only tools and HTTP remains opt-in
      loopback-only.
- [ ] Migration checks cover schema, provider, model, dimension, and count;
      the original source remains available for rollback.
- [ ] `python benchmarks/run.py --dry-run` succeeds and any executed benchmark
      records adapter versions, fixture/query hashes, configuration, and raw
      artifacts.

## Honest reporting

Do not claim a competitor result when an adapter was not executed or is not
comparable. The initial repository state is `not_executed`; update it only from
reproducible harness output.


## Independent re-review record (2026-09-02)

`Verdict: ready`

This verdict covers the current release-candidate working tree after an independent review, remediation, and re-review cycle. All initial P0-P2 findings are closed. The P3 items below are publication follow-ups, not open implementation blockers.

### Initial findings and disposition

| Priority | Initial finding | Final disposition and evidence |
| --- | --- | --- |
| P0 | No P0 issue was found. | Rejected: no candidate survived review; credential, destructive-operation, project-isolation, transport, and artifact boundaries were rechecked. |
| P1 | A workspace-configured Windows `.cmd` path could inject shell metacharacters. | Fixed/closed: `spawnSymbraid` rejects executable and argument metacharacters before shell-backed launch; the payload is rejected and safe `npm.cmd --version` succeeds. |
| P1 | The English root documentation projection was stale. | Fixed/closed: Python 3.12 `scripts/sync_docs.py --check` reports parity for 17 files with valid links and hashes. |
| P2 | Failed validation, stale plan hashes, registry saves, or reindexing could leave a replacement keyring credential. | Fixed/closed: `SecretUpdate` restores old/empty credentials or removes a new one; tests cover invalid input, stale hashes, save/reindex failure, and preservation of the old source. |
| P2 | VS Code watcher shutdown could race with apply/restart. | Fixed/closed: shutdown awaits graceful exit with bounded forced-kill fallback; delayed and stubborn-child tests pass. |
| P2 | Schema-v3 migration could silently overwrite equal-ID entries whose paths normalize to one key. | Fixed/closed: every normalized-path collision is rejected while the original schema-v2 registry and backup are preserved. |
| P2 | The archive scanner covered too few credential formats. | Fixed/closed: expanded bearer, JWT, npm, GitLab, GitHub, AWS, assignment, and private-key patterns have self-tests; fresh wheel, sdist, and VSIX scans pass. |
| P2 | Benchmark provenance omitted dirty-tree, harness, and adapter state. | Fixed/closed: dry-run includes dirty/status/diff/repository-state hashes, the harness hash, and all five adapter hashes. |
| P3 | No P3 implementation defect was retained from the initial pass. | Deferred publication checks are below; no P0-P2 finding remains open. |

### Verification evidence

- Windows core: `uv run --project components/symbraid python -m unittest discover -s components/symbraid/tests -p test_*.py -v` ran 33 tests successfully with one Linux-only skip, including live Qdrant and LanceDB checks.
- Ubuntu 24.04 under WSL: the current-tree core suite ran 33 tests successfully with one Windows-only skip; Linux path-case and both live backend checks passed.
- VS Code: `npm.cmd test --prefix extensions/vscode-symbraid` passed extension and webview tests, including executable-string injection and awaited watcher-shutdown regressions.
- MCP: `scripts/verify_mcp.py` completed a real stdio handshake on Windows and Ubuntu and returned exactly `index_status`, `list_index_sources`, and `semantic_search`. HTTP authentication, origin, host, loopback, and project-isolation tests passed in both core runs.
- Archives: `py -3.12 -m unittest scripts/test_release_archive.py -v` ran four tests successfully. The scanner accepted the fresh `symbraid-0.3.0` wheel/sdist and current VSIX after inspecting members.
- Benchmark: `py -3.12 benchmarks/run.py --dry-run` remained honestly `not_executed`; it reported a dirty tree, non-empty diff/repository-state hashes, the harness hash, five adapter hashes, and zero uncollected adapter hashes.
- Hygiene/version checks: a case-insensitive fixed-string sweep found zero occurrences of the prohibited local username. `py -3.12 scripts/check_versions.py` reported core/extension `0.3.0` and the timestamped canonical-plugin version.

### Deferred P3 and publication follow-up

- Rebuild publication artifacts from a hosted clean checkout and retain CI logs and checksums; the reviewed dry-run correctly records the current tree as dirty.
- The scanner content-checks members up to 2 MiB. Stream-scan or separately review a larger bundled member before one is introduced.
- No competitor adapter was executed. Keep `not_executed` until `--execute` produces retained raw artifacts under the documented reproducible procedure.
- Repeat exact-name availability and legal/trademark review immediately before publication; the dated technical notes below remain preserved and are not legal clearance.

## Exact-name availability check (2026-09-02)

A technical availability check on 2026-09-02 found no exact-name listing for
the new public identity: GitHub repository search returned 0 exact matches,
https://pypi.org/project/symbraid/ returned HTTP 404, npm exact package lookup
https://www.npmjs.com/package/symbraid returned HTTP 404, the VS Marketplace
exact search returned 0, and the MCP Registry lookup for
io.github.symbraid-project/symbraid returned HTTP 404.

This is technical availability information only, not trademark or legal
clearance. Re-check these services immediately before choosing a release,
package, extension, or MCP identifier.
