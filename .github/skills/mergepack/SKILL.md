---
name: mergepack
description: Generate a PR context packet for Copilot or VS Code agent workflows.
---

# mergepack

## When To Use This Skill

Use this skill when a VS Code or Copilot-compatible agent needs PR context before reviewing, fixing, or explaining a change.

## Required Inputs

- Local repository path.
- Base/head refs, diff file, or GitHub PR spec.
- Output path.

## Workflow

1. Install the CLI:

   ```bash
   python -m pip install .
   ```

2. Generate a packet:

   ```bash
   mergepack --base origin/main --head HEAD --output MERGEPACK.md
   ```

3. Generate HTML when a visual artifact helps:

   ```bash
   mergepack --base origin/main --head HEAD --format html --output mergepack.html
   ```

4. Use the changed-file map, risk areas, commands, and agent prompt from the output.

## Examples

```bash
mergepack --diff-file pr.diff --repo . --output MERGEPACK.md
```

```bash
mergepack --pr owner/repo#123 --repo . --format json --output mergepack.json
```

## Boundaries

- No LLM calls.
- No auto-comments.
- No secret-bearing diffs.
- No guarantee of perfect test selection.

## Expected Outputs

- `MERGEPACK.md`
- `mergepack.json`
- `mergepack.html`

## How It Calls The Local CLI

The skill expects `mergepack` on PATH and runs it with the base/head or diff-file inputs supplied by the user.
