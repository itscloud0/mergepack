# Contributing

Thanks for considering a contribution.

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install . --force-reinstall
python -m unittest discover -s tests
```

## Useful Commands

```bash
python -m compileall src tests
mergepack --diff-file examples/sample-pr.diff --repo examples/mini-repo --output /tmp/MERGEPACK.md
mergepack --diff-file examples/sample-pr.diff --repo examples/mini-repo --format json --output /tmp/mergepack.json
python -m json.tool /tmp/mergepack.json
```

## Project Direction

Keep `mergepack` deterministic, local-first, and useful without API keys. New features should improve PR handoffs for humans and coding agents, not turn the tool into a broad AI reviewer.

## Pull Requests

- Keep changes focused.
- Add tests for behavior changes.
- Update README or examples when user-facing output changes.
- Do not add dependencies unless they clearly improve maintainability or correctness.
