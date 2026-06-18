---
name: mergepack
description: Generate a PR-to-agent merge packet before reviewing or editing a pull request.
---

# mergepack

## When To Use This Skill

Use this skill when a user asks you to review, repair, summarize, or hand off a pull request and the repository has a local checkout or a pasted diff.

## Required Inputs

- Repository path.
- Either a git base/head range, a diff file, or a GitHub PR spec.
- Desired output path, usually `MERGEPACK.md` or `mergepack.html`.

## Workflow

1. Confirm `mergepack` is installed with `mergepack --help`.
2. If reviewing a local PR branch, run:

   ```bash
   mergepack --base origin/main --head HEAD --output MERGEPACK.md
   ```

3. If using a pasted diff, run:

   ```bash
   mergepack --diff-file pr.diff --repo . --output MERGEPACK.md
   ```

4. For visual review, generate HTML:

   ```bash
   mergepack --base origin/main --head HEAD --format html --output mergepack.html
   ```

5. Read the generated packet before editing files.
6. Use the packet's changed-file map, risk areas, commands, and agent-ready prompt as the review context.
7. Keep changes scoped to the PR intent.

## Examples

Generate Markdown:

```bash
mergepack --base main --head HEAD --output MERGEPACK.md
```

Generate JSON for automation:

```bash
mergepack --base main --head HEAD --format json --output mergepack.json
```

Generate from GitHub CLI:

```bash
mergepack --pr owner/repo#123 --repo . --output MERGEPACK.md
```

## Boundaries

- Do not use this skill as an automated code reviewer.
- Do not post PR comments unless the user explicitly asks.
- Do not run it on diffs containing secrets.
- Do not treat risk detection as a security audit.

## Expected Outputs

- Markdown, JSON, or HTML merge packet.
- A concise review prompt for the coding agent.
- Verification commands to run after edits.

## How This Skill Calls The CLI

The skill delegates all packet generation to the local `mergepack` executable. If the CLI is not installed, install it from the project root with:

```bash
python -m pip install .
```
