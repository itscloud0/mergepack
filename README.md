# mergepack

Turn a pull request diff into an agent-ready merge packet.

`mergepack` is for maintainers and AI software engineers who hand PRs to Codex, Claude Code, Cursor, Copilot, or a human reviewer. It gathers the diff, changed-file roles, repo instructions, likely commands, risk areas, and a ready prompt into one artifact.

It does not call an LLM. It does not post PR comments by default.

## Problem

PR context is scattered:

- `git diff`
- changed files
- repo instructions
- test commands
- CI workflows
- package metadata
- reviewer intent

When that context is missing, coding agents make broad edits, skip repo rules, or run the wrong checks.

## Why This Exists

AI review bots are useful when you want an automated reviewer. Sometimes you only need a clean handoff packet before a human or coding agent starts work.

`mergepack` makes that packet deterministic and local-first.

## 20-Second Demo

```bash
python -m pip install .
mergepack --diff-file examples/sample-pr.diff --repo examples/mini-repo --output MERGEPACK.md
mergepack --diff-file examples/sample-pr.diff --repo examples/mini-repo --format html --output examples/mini-mergepack.html
```

Open `examples/mini-mergepack.html`.

The report shows changed files, risk flags, verification commands, repo instructions, checklist items, and a prompt you can paste into a coding agent.

Non-Python fixtures are available under `examples/language-fixtures/` for Go,
Rust, and Node command-detection coverage.

## Installation

Requires Python 3.10 or newer. If `python3` is older on your machine, use a newer
interpreter such as `python3.11` or `python3.12`.

From a checkout:

```bash
python -m pip install .
```

For an isolated tryout:

```bash
PYTHON=python3.11  # or python3.12 / any Python 3.10+ interpreter
$PYTHON -m venv /tmp/mergepack-venv
/tmp/mergepack-venv/bin/python -m pip install .
/tmp/mergepack-venv/bin/mergepack --help
```

## Quickstart

From a local git repo:

```bash
mergepack --base main --head HEAD --output MERGEPACK.md
```

Generate JSON:

```bash
mergepack --base main --head HEAD --format json --output mergepack.json
```

Generate HTML:

```bash
mergepack --base main --head HEAD --format html --output mergepack.html
```

Use a pasted diff:

```bash
mergepack --diff-file pr.diff --repo . --output MERGEPACK.md
```

Use a changed-file list when CI cannot fetch full diff history:

```bash
printf "src/app.py\ntests/test_app.py\n" > changed-files.txt
mergepack --changed-files changed-files.txt --repo . --output MERGEPACK.md
```

Changed-files mode still classifies files and detects likely commands, but it marks
the missing diff preview and line-level delta as a limitation.

Use GitHub CLI for a public PR:

```bash
mergepack --pr owner/repo#123 --repo . --output MERGEPACK.md
```

`--pr` requires `gh` and uses `gh pr view` plus `gh pr diff`.

## Output Example

```markdown
# Merge packet for diff file examples/sample-pr.diff

## Changed Files

| File | Role | Status | Delta |
| --- | --- | --- | ---: |
| `src/checkout.py` | source | modified | +5/-1 |
| `tests/test_checkout.py` | test | added | +16/-0 |
| `.github/workflows/ci.yml` | ci | modified | +2/-0 |

## Verification Commands

- `python -m unittest discover -s tests`
- `python -m compileall src tests`

## Agent-Ready Prompt

You are reviewing this pull request...
```

## Real Workflow

1. Checkout a PR branch.
2. Run `mergepack --base origin/main --head HEAD --format html --output mergepack.html`.
3. Read the risk areas and commands.
4. Paste the agent-ready prompt into Codex, Claude Code, Cursor, or Copilot.
5. Ask the agent to fix only the focused issues.
6. Run the commands listed in the packet.

## GitHub Action

`mergepack` ships a composite action. It uploads a Markdown packet as an artifact and does not comment on PRs.

```yaml
name: Mergepack

on:
  pull_request:

permissions:
  contents: read

jobs:
  packet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: itscloud0/mergepack@v0.2.0
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          output: MERGEPACK.md
```

If your workflow already writes a newline-delimited changed-file list, pass it
instead of `base` / `head`:

```yaml
      - uses: itscloud0/mergepack@v0.2.0
        with:
          changed-files: changed-files.txt
          output: MERGEPACK.md
```

For local development in this repo, `.github/workflows/mergepack.yml` shows the same pattern with `uses: ./`.

## Agent Skills

This repo includes:

- Codex skill: `.agents/skills/mergepack/SKILL.md`
- Claude Code skill: `.claude/skills/mergepack/SKILL.md`
- GitHub Copilot / VS Code skill: `.github/skills/mergepack/SKILL.md`

Read `AGENT_SKILLS.md` for install and usage notes.

## When To Use

- Reviewing a non-trivial PR.
- Handing a PR to a coding agent.
- Preparing a focused repair prompt after CI fails.
- Sharing deterministic review context without an LLM key.
- Uploading PR context as a GitHub Actions artifact.

## When Not To Use

- You want an AI bot to review and comment automatically.
- You need perfect semantic test selection.
- The diff contains secrets that should not be copied into artifacts.
- You need a full code graph or ownership system.

## Comparison

| Tool type | What it does | How mergepack differs |
| --- | --- | --- |
| AI review bots | Generate review comments with an LLM | No LLM calls, no auto-comments, local-first artifact |
| Repo context dumpers | Pack many repo files for an LLM | PR-specific diff handoff with risks and commands |
| CI log summarizers | Explain failing logs | Starts from the PR diff and repo conventions |
| Manual prompts | Handwritten context | Repeatable packet with the same structure every time |

## Limitations

- v0.1 uses heuristics for file roles and risk areas.
- GitHub PR mode requires `gh`.
- Command detection is best-effort.
- Changed-files mode has no diff hunks, so additions/deletions are `0` and the packet tells reviewers to inspect the PR diff separately.
- Python command detection prefers tox/uv and pytest when repo config is present; Go, Rust, and Node command detection uses `go.mod`, `Cargo.toml`, and `package.json` scripts.
- It does not inspect code ownership or coverage data.
- It does not redact secrets from arbitrary diffs; do not run it on sensitive patches.

## Roadmap

- Config file for custom command and path rules.
- SARIF or GitHub annotations mode.
- Better monorepo package detection.
- Comment mode behind an explicit opt-in flag.
- Real PR metadata and review-comment packing.

## Contributing

See `CONTRIBUTING.md`.

## License

MIT. See `LICENSE`.
