# Release readiness review

Review date: 2026-09-03
Scope: current Symbraid working tree
Reviewer: independent agent that did not author the reviewed changes
Verdict: **ready**

## Review contract

Findings use severity P0 (release-blocking critical), P1 (release-blocking high),
P2 (must be fixed or explicitly rejected), and P3 (registered follow-up). The
release cannot be accepted with open P0/P1 findings or a `not ready` verdict.

The review covered Windows/Linux path behavior, host independence, watcher
locking and interruption recovery, the read-only MCP contract, HTTP
authentication and project isolation, source retention, schema handling,
secret redaction, locale parity, packaging inventory, and benchmark
reproducibility.

## Findings and corrections

No P0 or P1 finding was reported.

| ID | Severity | Finding | Correction | Verification |
| --- | --- | --- | --- | --- |
| RR-01 | P2 | An unused transition-only `store` parameter remained in project payload preparation. | Removed the parameter and transitional comment. | Static call-site inspection and Python suite. |
| RR-02 | P2 | Readiness documentation described obsolete migration behavior and an old test count. | Replaced the report with this current record. | Locale/hash/link checks and reviewer re-review. |
| RR-03 | P2 | The public README described metrics but contained no measured result. | Ran and documented a six-query, five-repeat Symbraid/ripgrep controlled snapshot with limitations and provenance. | Raw ignored JSON plus mirrored benchmark reports. |
| RR-04 | P1 | The first snapshot counted repeated chunks as separate file-level gains and mislabeled subprocess time as warm query latency. | Deduplicated hits by file, added `[0, 1]` bounds tests, excluded one warm-up, renamed the measure to warmed CLI invocation latency, and reran both adapters together. | One combined raw report, identical provenance, per-query bounds audit, and benchmark tests. |

A separate simple-artifact audit found three non-product compatibility shims:
a payload argument, a release-scanner constant, and a benchmark wrapper. All
three were removed. The old plugin tree, old console commands, old marketplace
identity, old executable fallback, old schema migration, and old keyring
fallback were also removed because this is a new, unpublished project.

## Evidence

- Python: 31 tests passed; one Linux-only path-casing test was skipped on the
  Windows review host.
- VS Code: extension contract and Manage webview tests passed. The service
  status panel reads `project.index_status` and no indexing logic lives in the
  extension.
- MCP: exactly three read-only tools; tests cover loopback-only HTTP, bearer
  token, Origin/Host checks, and bound-project isolation.
- Watcher: tests cover duplicate leases, clean pre-stop, and interrupted refresh
  metadata.
- Storage: tests require new Qdrant collections to start with `symbraid-` and
  verify source activation only after successful indexing.
- Documentation: 18 English/Russian file pairs passed tree parity, translation
  hash, root projection, and link checks.
- Packaging: wheel/sdist build and archive-secret scans passed; wheel entry
  points are only `symbraid` and `symbraid-mcp`.
- Benchmark: two metric regression tests passed. One combined Symbraid 0.3.0 /
  ripgrep 15.2.0 report used one harness hash; all per-query normalized metrics
  passed the `[0, 1]` audit and missing values remain `not_collected`.

## Remaining release gates

The same independent reviewer re-checked RR-01 through RR-04 and found no open
P0, P1, or P2 findings. Hosted Windows and Ubuntu CI, the Linux-only test, the
full isolated competitor shortlist, and a clean-checkout artifact build remain
registered P3 release workflow gates; this local review does not represent them
as completed.

## Final verdict

**Ready.** There are no open P0, P1, or P2 findings. Publication remains gated
by the registered P3 release workflow checks above.