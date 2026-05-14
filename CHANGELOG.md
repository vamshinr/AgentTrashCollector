# Changelog

All notable changes to driftwatch are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-13

Initial release.

### Added
- Claude Code hook (`driftwatch.hook`) that captures `PreToolUse`,
  `PostToolUse`, and `Stop` events to `~/.driftwatch/events/<session>.jsonl`.
- Lightweight git snapshots (head sha, dirty flag, insertions/deletions) taken
  on edit/write/bash PostToolUse events.
- Three metrics over a captured session:
  - **Convergence** — weighted blend of git movement, test pass rate, and
    edit-churn penalty.
  - **Thrash** — detects repeated edits to one file since the last commit, or
    repeated failures of the same bash command.
  - **Momentum** — direction-of-travel signal comparing the last 10 events
    against the previous 10.
- CLI: `driftwatch init`, `uninstall`, `sessions`, `report` (text and
  `--json`), and `watch` (live TUI).
