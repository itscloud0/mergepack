# mergepack Launch Notes

## GitHub Repo Name

mergepack

## GitHub Description

Turn pull request diffs into agent-ready merge packets for code review.

## GitHub Topics

- ai-engineering
- coding-agents
- code-review
- developer-tools
- devex
- github-actions
- pull-requests
- codex
- claude-code
- copilot

## README Hero Tagline

Turn a pull request diff into an agent-ready merge packet.

## X / Twitter

I built `mergepack`: a no-key CLI + GitHub Action that turns a PR diff into a review packet for humans and coding agents.

It includes changed-file roles, repo instructions, likely commands, risk areas, a checklist, and a prompt you can paste into Codex/Claude/Copilot.

## LinkedIn

I built `mergepack`, a local-first developer tool for PR handoffs.

Instead of asking a coding agent to inspect a raw diff, `mergepack` creates a deterministic merge packet: changed files, repo instructions, verification commands, risk areas, checklist, and an agent-ready prompt.

It ships as a CLI, GitHub Action, HTML report, and Agent Skills for Codex, Claude Code, and Copilot-compatible workflows.

## Hacker News Title

Show HN: mergepack - turn PR diffs into agent-ready review packets

## Reddit Post

I built `mergepack`, a small local-first CLI/GitHub Action for PR review handoffs.

It does not call an LLM. It reads a local git diff, diff file, or GitHub PR via `gh`, then emits Markdown/JSON/HTML with changed-file roles, repo instructions, likely verification commands, risks, a checklist, and a prompt for coding agents.

The goal is to make PR-to-agent handoffs less ad hoc.

## Demo Captions

1. Generate `MERGEPACK.md` from a local PR branch.
2. Open the HTML report and see source/test/CI files grouped by role.
3. Copy the agent-ready prompt into Codex or Claude Code.
4. Upload `MERGEPACK.md` as a GitHub Actions artifact.
5. Use the Codex/Claude/Copilot skills before PR repair work.

## Good First Issues

1. Add config support for custom command detection.
2. Add fixtures for Go, Rust, and Node monorepo PRs.
3. Add a `--changed-files` input mode for CI systems without full git history.

## Roadmap Issues

1. Add SARIF or GitHub annotation output for risk areas.
2. Add optional comment mode guarded by an explicit opt-in flag.
3. Add package-aware monorepo grouping for npm workspaces, Python packages, and Cargo workspaces.

## Suggested First Release Title

mergepack v0.1.0 - PR-to-agent merge packets

## Maintainer Note

Keep the project focused on deterministic PR context packaging. Avoid becoming an AI review bot or broad repo scanner.
