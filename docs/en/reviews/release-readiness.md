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
secret redaction, locale parity, and packaging inventory.

## Findings and corrections

No P0 or P1 finding was reported.

| ID | Severity | Finding | Correction | Verification |
| --- | --- | --- | --- | --- |
| RR-01 | P2 | An unused transition-only `store` parameter remained in project payload preparation. | Removed the parameter and transitional comment. | Static call-site inspection and Python suite. |
| RR-02 | P2 | Readiness documentation described obsolete migration behavior and an old test count. | Replaced the report with this current record. | Locale/hash/link checks and reviewer re-review. |

A separate simple-artifact audit found two non-product compatibility shims:
a payload argument and a release-scanner constant. Both were removed. The old plugin tree, old console commands, old marketplace
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
- Documentation: 17 English/Russian file pairs passed tree parity, translation
  hash, root projection, and link checks.
- Packaging: wheel/sdist build and archive-secret scans passed; wheel entry
  points are only `symbraid` and `symbraid-mcp`.


## Remaining release gates

The same independent reviewer re-checked RR-01 and RR-02 and found no open
P0, P1, or P2 findings. Hosted Windows and Ubuntu CI, the Linux-only test, and a clean-checkout artifact build remain
registered P3 release workflow gates; this local review does not represent them
as completed.

## Final verdict

**Ready.** There are no open P0, P1, or P2 findings. Publication remains gated
by the registered P3 release workflow checks above.
## Post-review correction cycle

A separate reviewer examined the Windows status/search and Manage UI fixes.
The initial verdict reported two P2 findings: a top-level settings failure could
leave the webview without a renderable state, and the regression checks did not
execute all failure-policy branches. The UI state loader was extracted into a
pure module, all settings/status outcomes gained behavioral tests, and core tests
were added for Windows path aliases, permanent HTTP failures, retry exhaustion,
and secret redaction.

The same reviewer re-checked the corrected diff. The final verdict is **ready**,
with no open P0, P1, P2, or P3 findings. The corrected suite has 36 passing Python
tests with one platform-specific skip on the Windows host, plus passing VS Code,
documentation parity/hash/link, version, and diff checks.
