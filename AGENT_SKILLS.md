# Agent Skills

`mergepack` includes skills for Codex, Claude Code, and GitHub Copilot / VS Code compatible skill folders.

## What The Skills Do

The skills tell an agent to create a deterministic PR handoff packet before reviewing or editing a pull request. They call the local `mergepack` CLI and use the output as context.

## Install The Codex Skill

Copy or symlink:

```bash
.agents/skills/mergepack/SKILL.md
```

into a repo or user-level Codex skills folder that your Codex client reads.

## Install The Claude Code Skill

Copy or symlink:

```bash
.claude/skills/mergepack/SKILL.md
```

into the Claude Code skills folder for the target project or user profile.

## Use The GitHub Copilot / VS Code Skill

The compatible skill lives at:

```bash
.github/skills/mergepack/SKILL.md
```

Keep it in the repo when you want VS Code/Copilot-compatible agents to find the workflow.

## CLI vs Skill vs GitHub Action

- Use the CLI when you are at a terminal and want `MERGEPACK.md`, JSON, or HTML.
- Use a skill when an agent is about to review or repair a PR and should first gather context.
- Use the GitHub Action when you want a PR artifact that every reviewer can download.

## Limitations

- The skills require the local `mergepack` CLI to be installed or runnable from the repo.
- They do not call an LLM by themselves.
- They should not be used on diffs containing secrets.
