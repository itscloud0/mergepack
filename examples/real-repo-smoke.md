# Real-Repo Smoke: pallets/click

## Repo Used

- Repository: `https://github.com/pallets/click`
- Clone path during smoke: `/tmp/mergepack-click-smoke`
- Command date: 2026-06-18
- Head commit: `8a1b1a33d739be05b7e91251e3c0dde77c5e152f`
- Head summary: `Merge stable into main after CHANGES rST to Markdown conversion (#3563)`
- Base input: `HEAD~1`
- Head input: `HEAD`

## Input Used

A shallow public clone:

```bash
git clone --depth 20 https://github.com/pallets/click.git /tmp/mergepack-click-smoke
```

## Command Run

```bash
mergepack --repo /tmp/mergepack-click-smoke --base HEAD~1 --head HEAD --output /tmp/click-mergepack.md
mergepack --repo /tmp/mergepack-click-smoke --base HEAD~1 --head HEAD --format html --output /tmp/click-mergepack.html
```

## Output Summary

`mergepack` produced a packet with:

- 17 changed files
- 549 additions
- 180 deletions
- 7 source files
- 4 test files
- 1 package file
- 1 CI workflow
- 4 docs files

It suggested:

- `uv run --locked --no-default-groups --group dev tox run`
- `python -m compileall src tests`
- CI workflow review because `.github/workflows/nightly.yaml` changed

It flagged:

- Dependency/package risk because `pyproject.toml` changed
- CI workflow risk because a workflow changed

## What Worked

- The changed-file table was useful on a real Python project.
- Source, test, package, CI, and docs classification worked.
- Command detection recognized Click's tox/uv setup from `pyproject.toml` and `uv.lock`.
- README instruction extraction skipped the HTML hero and avoided later section-heading noise.
- The output gave a compact review checklist and agent-ready prompt.
- HTML generation worked on the same packet.

## What Failed Or Was Limited

- The first smoke falsely flagged sensitive text because the diff contained `tool.tox.env.*`, which matched a broad `.env` substring heuristic.
- v0.1 still does not select the exact tox env for a changed file set; it suggests the repo's broad tox run.

## What Was Tuned After The Smoke

- Sensitive-text detection was tightened from broad substring matching to regexes for likely assignments or actual `.env` file references. The Click smoke no longer reports a secret false positive.
- Python command detection now prefers tox/uv when the repo has tox config and `uv.lock`.
- README instruction extraction now skips HTML hero markup and stops after the introductory prose.

## Does This Prove Real-World Usefulness?

Partially yes.

Yes.

The smoke proves `mergepack` can summarize a real multi-file PR-shaped diff into a useful handoff packet without secrets or APIs. It also drove concrete tuning for command detection, instruction extraction, and sensitive-text false positives.
