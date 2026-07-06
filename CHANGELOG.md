# Changelog

## Unreleased

## v0.5.0 - 2026-07-06

- Added package/workspace grouping for npm workspaces, nested Python packages, and Cargo workspace members.
- Added package-scoped verification commands to Markdown, HTML, JSON, and agent prompts.

## v0.4.0 - 2026-07-06

- Added SARIF output with machine-readable merge risks for GitHub code scanning upload.
- Added CLI/action docs and CI smoke coverage for SARIF packets.

## v0.3.0 - 2026-07-04

- Added Go, Rust, and Node PR fixtures with expected packet fields for command-detection coverage.
- Classified common Go and Node test filenames such as `*_test.go` and `*.test.ts` as tests.
- Added JSON config support for repo-specific verification commands and path role rules.
- Added CLI `--config`, composite action `config`, and Python/Node config fixtures.

## v0.2.0 - 2026-07-02

- Added `--changed-files` input mode for CI systems that can provide a newline-delimited changed-file list but not a full git diff.
- Added composite action `changed-files` input and README guidance for changed-files mode.
- Changed packets from changed-file lists to explicitly mark the missing diff preview and line-level deltas as a limitation.

## v0.1.0 - 2026-06-18

- Added CLI for Markdown, JSON, and HTML merge packets.
- Added local git diff, pasted diff file, and GitHub PR input modes.
- Added changed-file classification, command detection, repo instruction extraction, risk heuristics, reviewer checklist, and agent-ready prompt generation.
- Added GitHub Action artifact mode.
- Added Codex, Claude Code, and GitHub Copilot / VS Code compatible skills.
- Added sample diff, mini repo, tests, CI, and launch material.
- Tuned Python command detection for tox/uv and pytest repos.
- Cleaned README instruction extraction so HTML hero markup and later section headings do not pollute agent prompts.
