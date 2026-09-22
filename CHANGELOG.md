# Changelog

All notable changes to Symbraid are documented here. The project is still in
active development; entries describe repository changes, not a promise that a
release has been published.

## [Unreleased]

### Added

- Cross-platform Symbraid core with standalone CLI, watcher, and read-only MCP
  server.
- Explicit `--allow-all-projects` mode for a bearer-protected, loopback-only HTTP MCP
  server, plus an idempotent Windows Codex setup/status/remove helper with
  optional per-user logon startup.
- Locale-first English and Russian documentation trees with parity and
  translation-staleness checks.
- Build-only GitHub Actions, issue forms, pull-request guidance, and dependency
  update configuration.

### Verification status

- Release automation creates local build artifacts only; publication remains a
  deliberate maintainer action outside these workflows.

