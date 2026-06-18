---
name: mergepack
description: Create a deterministic PR handoff packet before Claude Code reviews or edits a pull request.
---

# mergepack

## When To Use This Skill

Use this skill before PR review, PR repair, or CI-failure repair work when Claude Code needs focused diff context.

## Required Inputs

- Repo path.
- Base/head refs, diff file, or GitHub PR spec.
- Output format: Markdown, JSON, or HTML.

## Step-By-Step Workflow

1. Run `mergepack --help`.
2. Generate a packet:

   ```bash
   mergepack --base origin/main --head HEAD --output MERGEPACK.md
   ```

3. If no local git range is available, use a diff file:

   ```bash
   mergepack --diff-file pr.diff --repo . --output MERGEPACK.md
   ```

4. Read `MERGEPACK.md`.
5. Use the packet's agent-ready prompt as the primary review context.
6. Run the listed verification commands after changes.

## Examples

```bash
mergepack --base main --head HEAD --format html --output mergepack.html
```

```bash
mergepack --pr owner/repo#123 --repo . --output MERGEPACK.md
```

## Boundaries / When Not To Use

- Do not use this as a substitute for tests.
- Do not use on secret-bearing diffs.
- Do not post comments automatically.
- Do not expand scope beyond the PR unless the packet shows a direct risk.

## Expected Outputs

- A deterministic merge packet.
- Changed-file roles.
- Risk areas.
- Verification commands.
- Agent-ready prompt.

## CLI Usage

The skill calls the installed `mergepack` CLI. From this repo:

```bash
python -m pip install .
mergepack --base main --head HEAD --output MERGEPACK.md
```
