# Changelog

All notable changes to Symbraid are documented here. The project is still in
active development; entries describe repository changes, not a promise that a
release has been published.

## [Unreleased]

### Fixed

- New directories stay unregistered when opened in VS Code or viewed in Manage.
  The status icon explicitly enables a project with global defaults; Manage
  previews those defaults and confirms registration with global or custom
  storage and model settings before starting the watcher. Project loading
  failures preserve global settings and model profiles in Manage.
- Re-registering a removed project creates a unique managed source and preserves
  retained indexes. Registration plans reject changes to the selected embedding
  profile after planning, including provider, model, dimension, endpoint, and
  credential reference.
- Global defaults reject project-scoped embedding profiles, and new project
  registration validates profile ownership before saving its configuration.

## [0.4.0] - 2026-09-22

### Added

- Cross-platform Symbraid core with standalone CLI, watcher, and read-only MCP
  server.
- Explicit `--allow-all-projects` mode for a bearer-protected, loopback-only HTTP MCP
  server, plus an idempotent Windows Codex setup/status/remove helper with
  optional per-user logon startup.
- Watcher changes are accumulated by unique path and indexed once after five
  seconds of complete inactivity, so rapid edits do not trigger one embedding
  request per file event.
- Temporary embedding failures, including HTTP 429 responses, preserve the
  pending batch and retry with backoff while honoring `Retry-After`; repeated
  failures stop the watcher after the bounded recovery window.
- Locale-first English and Russian documentation trees with parity and
  translation-staleness checks.
- Build-only GitHub Actions, issue forms, pull-request guidance, and dependency
  update configuration.

### Verification status

- Release automation creates local build artifacts only; publication remains a
  deliberate maintainer action outside these workflows.

