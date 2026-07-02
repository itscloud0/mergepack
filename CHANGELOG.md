# Changelog

## Unreleased

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
