# mergepack Product Spec

## User Persona

Open-source maintainers and AI software engineers who hand pull requests to Codex, Claude Code, Cursor, Copilot, or a human reviewer and need the reviewer to understand the diff, risks, repo conventions, and right verification commands quickly.

## Painful Recurring Problem

PR context is scattered across `git diff`, changed files, test output, CI workflows, repo instructions, reviewer comments, and package metadata. Coding agents often get either too little context or a huge raw dump.

## Current Bad Workflow

1. Copy the PR description.
2. Copy the diff or changed files.
3. Manually find tests, commands, package managers, and repo instructions.
4. Guess risk areas.
5. Write a prompt for the agent.
6. Repeat that for every non-trivial PR.

This is slow and inconsistent. It also causes agents to miss repo rules or run the wrong tests.

## Proposed Better Workflow

Run one command:

```bash
mergepack --base main --head HEAD --output MERGEPACK.md
```

`mergepack` emits a compact packet with:

- PR/change summary
- Changed file map
- Relevant repo instructions
- Likely verification commands
- Risk areas
- Reviewer checklist
- Agent-ready prompt
- Optional JSON or HTML output

## Market Wave

`mergepack` rides:

- PR-to-agent workflows
- agentic code review
- GitHub Actions automation
- Codex/Claude/Copilot skill packaging
- local AI developer tooling

## Adjacent Tools And Alternatives

- AI review bots: Sourcery, OpenReview, Kodus, git-lrc.
- Broad context tools: code2prompt, repomix, gitingest.
- Small PR handoff/context repos: `pr-agent-context`, `pr-context-pack`.

## Clear Gap

Most tools either review code with an LLM or dump broad repository context. `mergepack` does neither. It creates a deterministic, no-key, local-first PR handoff artifact that can be used by a human or pasted directly into a coding agent.

## 20-Second Demo

```bash
mergepack --repo examples/mini-repo --base HEAD~1 --head HEAD --format html --output demo/mini-repo.html
```

Open the HTML report. It shows the changed files, risk flags, commands, checklist, and agent prompt in one screen.

## Product Surfaces To Ship

- CLI
- Markdown packet
- JSON packet
- HTML report
- GitHub Action
- Codex Agent Skill
- Claude Code Skill
- GitHub Copilot / VS Code skill
- Real-repo smoke note

## Core v0.1 Feature Set

- Read local git diff between base and head.
- Accept a pasted diff file for non-git usage.
- Classify changed files by role: source, tests, docs, CI, config, package, migration, generated/asset.
- Detect likely verification commands from repo files.
- Read repo instructions from common files such as `AGENTS.md`, `.github/copilot-instructions.md`, `README.md`, and `CONTRIBUTING.md`.
- Flag risk areas from changed paths and diff text.
- Generate Markdown, JSON, and HTML packets.
- Ship GitHub Action artifact mode without comments by default.
- Ship agent skills that call the CLI.

## Non-Goals

- No LLM calls.
- No automatic PR review comments by default.
- No hosted service.
- No full semantic code graph in v0.1.
- No language-specific perfect test selection in v0.1.

## Why This Is Valuable

It saves maintainers the repetitive context assembly step before agent or human review. It also makes PR handoffs more reproducible because every packet includes repo instructions, commands, risks, and acceptance checks.

## Why This Strengthens Ilia's Profile

It shows product judgment in current AI SWE workflows, practical Git/GitHub automation, deterministic agent tooling, and market-native packaging beyond a plain CLI.

## Publish Criteria

- README makes value obvious in 10 seconds.
- CLI works after clean install.
- Tests pass.
- CI exists.
- GitHub Action validates and uploads an artifact.
- Agent Skills exist and explain when to use the tool.
- Markdown, JSON, and HTML examples exist.
- Real-repo smoke exists and is not fake.
- Safety scan passes.
- Scores before publish:
  - launch readiness >= 9
  - product value >= 9
  - talent signal >= 9
  - demo strength >= 9
  - differentiation >= 8
  - distribution strength >= 8
  - market-native packaging >= 8

## Real-Repo Smoke Plan

Use a shallow clone of a public repository and run `mergepack` against a real recent commit diff:

```bash
git clone --depth 20 https://github.com/pallets/click.git /tmp/mergepack-click
mergepack --repo /tmp/mergepack-click --base HEAD~1 --head HEAD --output /tmp/click-mergepack.md
```

Record the repo, command, output summary, limits, and tuning in `examples/real-repo-smoke.md`.

## Distribution Plan

- GitHub repo topics: `ai-engineering`, `coding-agents`, `code-review`, `developer-tools`, `github-actions`, `pull-requests`, `codex`, `claude-code`, `copilot`, `devex`.
- Share as a no-key alternative to AI review bots: "make a PR packet before handing a diff to a coding agent."
- Use the HTML demo as the first visual proof.
