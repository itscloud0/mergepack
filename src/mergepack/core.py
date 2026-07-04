from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class MergepackError(Exception):
    """User-facing mergepack failure."""


@dataclass(frozen=True)
class DiffSource:
    label: str
    diff_text: str
    base: str | None = None
    head: str | None = None
    url: str | None = None
    title: str | None = None
    body: str | None = None
    changed_paths: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    role: str
    additions: int = 0
    deletions: int = 0


@dataclass(frozen=True)
class InstructionFile:
    path: str
    summary: str


@dataclass
class MergePacket:
    title: str
    source: str
    repo: str
    base: str | None
    head: str | None
    url: str | None
    changed_files: list[ChangedFile]
    commands: list[str]
    risk_areas: list[str]
    instructions: list[InstructionFile]
    checklist: list[str]
    agent_prompt: str
    diff_preview: str
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def high_risk(self) -> bool:
        high_markers = ("migration", "auth", "security", "dependency", "ci workflow")
        lowered = " ".join(self.risk_areas).lower()
        return any(marker in lowered for marker in high_markers)

    def to_json(self) -> dict[str, object]:
        return {
            "title": self.title,
            "source": self.source,
            "repo": self.repo,
            "base": self.base,
            "head": self.head,
            "url": self.url,
            "stats": self.stats,
            "changed_files": [file.__dict__ for file in self.changed_files],
            "commands": self.commands,
            "risk_areas": self.risk_areas,
            "instructions": [item.__dict__ for item in self.instructions],
            "checklist": self.checklist,
            "agent_prompt": self.agent_prompt,
            "diff_preview": self.diff_preview,
            "high_risk": self.high_risk,
        }


def run_command(args: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise MergepackError(f"required command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "command failed"
        raise MergepackError(f"{' '.join(args)} failed: {detail}") from exc
    return completed.stdout


def load_diff_from_git(repo: Path, base: str, head: str) -> DiffSource:
    if not repo.exists():
        raise MergepackError(f"repo path does not exist: {repo}")
    if not (repo / ".git").exists() and not _inside_git_worktree(repo):
        raise MergepackError(f"repo path is not a git worktree: {repo}")

    diff_text = run_command(["git", "diff", "--find-renames", f"{base}...{head}"], cwd=repo)
    if not diff_text.strip():
        diff_text = run_command(["git", "diff", "--find-renames", f"{base}..{head}"], cwd=repo)
    if not diff_text.strip():
        raise MergepackError(f"no diff found for {base}..{head}")
    return DiffSource(label=f"git diff {base}...{head}", diff_text=diff_text, base=base, head=head)


def load_diff_from_file(path: Path) -> DiffSource:
    if not path.exists():
        raise MergepackError(f"diff file does not exist: {path}")
    diff_text = path.read_text(encoding="utf-8")
    if not diff_text.strip():
        raise MergepackError(f"diff file is empty: {path}")
    return DiffSource(label=f"diff file {path}", diff_text=diff_text)


def load_changed_files_from_file(path: Path) -> DiffSource:
    if not path.exists():
        raise MergepackError(f"changed-files file does not exist: {path}")
    raw_text = path.read_text(encoding="utf-8")
    paths = parse_changed_file_list(raw_text)
    if not paths:
        raise MergepackError(f"changed-files file is empty: {path}")
    return DiffSource(
        label=f"changed files {path}",
        diff_text="",
        changed_paths=tuple(paths),
        limitations=(
            "Changed-files input limitation: diff preview and line-level additions/deletions "
            "are unavailable; inspect the PR diff before merging.",
        ),
    )


def load_diff_from_pr(pr: str) -> DiffSource:
    if shutil.which("gh") is None:
        raise MergepackError("--pr requires GitHub CLI (`gh`) on PATH")

    repo, number = parse_pr_spec(pr)
    view_raw = run_command(
        [
            "gh",
            "pr",
            "view",
            number,
            "--repo",
            repo,
            "--json",
            "title,body,url,baseRefName,headRefName",
        ]
    )
    try:
        view = json.loads(view_raw)
    except json.JSONDecodeError as exc:
        raise MergepackError("gh returned invalid PR metadata") from exc
    diff_text = run_command(["gh", "pr", "diff", number, "--repo", repo])
    return DiffSource(
        label=f"GitHub PR {repo}#{number}",
        diff_text=diff_text,
        base=view.get("baseRefName"),
        head=view.get("headRefName"),
        url=view.get("url"),
        title=view.get("title"),
        body=view.get("body"),
    )


def parse_pr_spec(spec: str) -> tuple[str, str]:
    url_match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", spec)
    if url_match:
        return url_match.group(1), url_match.group(2)
    shorthand = re.fullmatch(r"([^/\s]+/[^#\s]+)#(\d+)", spec)
    if shorthand:
        return shorthand.group(1), shorthand.group(2)
    raise MergepackError("PR must look like owner/repo#123 or a GitHub pull request URL")


def build_packet(
    repo: Path,
    diff_source: DiffSource,
    title: str | None = None,
    max_diff_lines: int = 220,
    repo_label: str | None = None,
) -> MergePacket:
    if diff_source.changed_paths:
        changed_files = changed_files_from_paths(diff_source.changed_paths)
    else:
        changed_files = parse_changed_files(diff_source.diff_text)
    if not changed_files:
        raise MergepackError("diff did not contain changed files")

    stats = summarize_stats(changed_files)
    commands = detect_commands(repo, changed_files)
    instructions = collect_instructions(repo)
    risk_areas = detect_risks(changed_files, diff_source.diff_text)
    for limitation in diff_source.limitations:
        if limitation not in risk_areas:
            risk_areas.append(limitation)
    checklist = build_checklist(changed_files, commands, risk_areas)
    diff_preview = build_diff_preview(diff_source, max_diff_lines)
    packet_title = title or diff_source.title or f"Merge packet for {diff_source.label}"
    prompt = build_agent_prompt(
        title=packet_title,
        changed_files=changed_files,
        commands=commands,
        risk_areas=risk_areas,
        instructions=instructions,
        diff_preview=diff_preview,
    )

    return MergePacket(
        title=packet_title,
        source=diff_source.label,
        repo=repo_label or str(repo),
        base=diff_source.base,
        head=diff_source.head,
        url=diff_source.url,
        changed_files=changed_files,
        commands=commands,
        risk_areas=risk_areas,
        instructions=instructions,
        checklist=checklist,
        agent_prompt=prompt,
        diff_preview=diff_preview,
        stats=stats,
    )


def parse_changed_file_list(text: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        path = raw_line.strip()
        if not path:
            continue
        if "\x00" in path:
            raise MergepackError("changed-files list contains a NUL byte")
        if path.startswith("./"):
            path = path[2:]
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def changed_files_from_paths(paths: tuple[str, ...]) -> list[ChangedFile]:
    return sorted(
        (
            ChangedFile(
                path=path,
                status="modified",
                role=classify_path(path),
                additions=0,
                deletions=0,
            )
            for path in paths
        ),
        key=lambda item: (role_sort_key(item.role), item.path),
    )


def parse_changed_files(diff_text: str) -> list[ChangedFile]:
    files: dict[str, dict[str, int | str]] = {}
    current: str | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = parse_diff_git_path(line)
            if current:
                files.setdefault(current, {"path": current, "status": "modified", "additions": 0, "deletions": 0})
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            files[current]["status"] = "added"
        elif line.startswith("deleted file mode"):
            files[current]["status"] = "deleted"
        elif line.startswith("rename from "):
            files[current]["status"] = "renamed"
        elif line.startswith("+") and not line.startswith("+++"):
            files[current]["additions"] = int(files[current]["additions"]) + 1
        elif line.startswith("-") and not line.startswith("---"):
            files[current]["deletions"] = int(files[current]["deletions"]) + 1

    changed = []
    for path, data in files.items():
        changed.append(
            ChangedFile(
                path=path,
                status=str(data["status"]),
                role=classify_path(path),
                additions=int(data["additions"]),
                deletions=int(data["deletions"]),
            )
        )
    return sorted(changed, key=lambda item: (role_sort_key(item.role), item.path))


def parse_diff_git_path(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    right = parts[3]
    if right.startswith("b/"):
        return right[2:]
    if parts[2].startswith("a/"):
        return parts[2][2:]
    return right


def classify_path(path: str) -> str:
    lowered = path.lower()
    parts = lowered.split("/")
    name = parts[-1]
    suffix = Path(path).suffix.lower()
    test_suffixes = (
        "_test.py",
        "_test.go",
        "_test.rs",
        ".test.js",
        ".test.jsx",
        ".test.ts",
        ".test.tsx",
        ".spec.js",
        ".spec.jsx",
        ".spec.ts",
        ".spec.tsx",
    )

    if lowered.startswith(".github/workflows/") or "workflow" in parts:
        return "ci"
    if (
        "test" in parts
        or "tests" in parts
        or name.startswith(("test_", "test-"))
        or name.endswith(test_suffixes)
    ):
        return "test"
    if name in {"pyproject.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.mod", "cargo.toml", "requirements.txt"}:
        return "package"
    if "migration" in parts or "migrations" in parts:
        return "migration"
    if suffix in {".md", ".rst", ".txt"} or lowered.startswith("docs/"):
        return "docs"
    if name in {"dockerfile", "makefile"} or suffix in {".yml", ".yaml", ".toml", ".ini", ".cfg", ".json"}:
        return "config"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}:
        return "asset"
    if suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs"}:
        return "source"
    return "other"


def role_sort_key(role: str) -> int:
    order = {
        "source": 0,
        "test": 1,
        "package": 2,
        "migration": 3,
        "ci": 4,
        "config": 5,
        "docs": 6,
        "asset": 7,
        "other": 8,
    }
    return order.get(role, 99)


def summarize_stats(files: list[ChangedFile]) -> dict[str, int]:
    stats: dict[str, int] = {
        "files": len(files),
        "additions": sum(file.additions for file in files),
        "deletions": sum(file.deletions for file in files),
    }
    for file in files:
        stats[file.role] = stats.get(file.role, 0) + 1
    return stats


def detect_commands(repo: Path, changed_files: list[ChangedFile]) -> list[str]:
    commands: list[str] = []

    def add(command: str) -> None:
        if command not in commands:
            commands.append(command)

    if (repo / "package.json").exists():
        scripts = read_package_scripts(repo / "package.json")
        if "test" in scripts:
            add("npm test")
        if "lint" in scripts:
            add("npm run lint")
        if "typecheck" in scripts:
            add("npm run typecheck")
        if "build" in scripts:
            add("npm run build")
    pyproject = repo / "pyproject.toml"
    if pyproject.exists() or (repo / "setup.py").exists():
        pyproject_text = read_text_safely(pyproject)
        if has_tox_config(repo, pyproject_text):
            if (repo / "uv.lock").exists():
                add("uv run --locked --no-default-groups --group dev tox run")
            else:
                add("tox run")
        elif has_pytest_config(repo, pyproject_text):
            add("python -m pytest")
        elif (repo / "tests").exists():
            add("python -m unittest discover -s tests")
        add("python -m compileall src tests")
    if (repo / "requirements.txt").exists() and (repo / "tests").exists():
        add("python -m unittest discover -s tests")
    if (repo / "go.mod").exists():
        add("go test ./...")
    if (repo / "Cargo.toml").exists():
        add("cargo test")
        add("cargo build")
    if has_make_target(repo / "Makefile", "test"):
        add("make test")
    if any(file.role == "ci" for file in changed_files):
        add("review changed GitHub Actions locally or with a disposable branch run")
    if not commands:
        add("run the repo's normal test command for the changed files")
    return commands


def read_package_scripts(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def read_text_safely(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def has_tox_config(repo: Path, pyproject_text: str) -> bool:
    return (
        (repo / "tox.ini").exists()
        or "[tool.tox]" in pyproject_text
        or "[tool.tox." in pyproject_text
        or "[tool.tox_" in pyproject_text
    )


def has_pytest_config(repo: Path, pyproject_text: str) -> bool:
    return (
        (repo / "pytest.ini").exists()
        or (repo / "conftest.py").exists()
        or "[tool.pytest" in pyproject_text
        or "pytest" in read_text_safely(repo / "requirements-dev.txt").lower()
    )


def has_make_target(path: Path, target: str) -> bool:
    if not path.exists():
        return False
    pattern = re.compile(rf"^{re.escape(target)}\s*:")
    try:
        return any(pattern.match(line) for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def collect_instructions(repo: Path) -> list[InstructionFile]:
    candidates = [
        "AGENTS.md",
        ".agents/AGENTS.md",
        ".github/copilot-instructions.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "README.md",
    ]
    instructions: list[InstructionFile] = []
    for relative in candidates:
        path = repo / relative
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        summary = summarize_text(text)
        if summary:
            instructions.append(InstructionFile(path=relative, summary=summary))
    return instructions[:4]


def summarize_text(text: str, limit: int = 420) -> str:
    lines = []
    in_fence = False
    saw_prose = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned = clean_instruction_line(line)
        if not cleaned:
            continue
        if line.startswith("#"):
            if saw_prose:
                break
            if not saw_prose:
                lines.append(cleaned.lstrip("#").strip())
        elif len(lines) < 4:
            lines.append(cleaned)
            saw_prose = True
        if sum(len(item) for item in lines) >= limit:
            break
    summary = " ".join(lines)
    return summary[:limit].rstrip()


def clean_instruction_line(line: str) -> str:
    if line.startswith(("![", "[!", "<img", "<div", "</div", "<p", "</p")):
        return ""
    if re.fullmatch(r"\[.*\]:\s+\S+", line):
        return ""
    line = re.sub(r"<[^>]+>", " ", line)
    line = re.sub(r"\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)", " ", line)
    line = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def detect_risks(changed_files: list[ChangedFile], diff_text: str) -> list[str]:
    risks: list[str] = []
    roles = {file.role for file in changed_files}
    paths = " ".join(file.path.lower() for file in changed_files)
    diff_lower = diff_text.lower()

    def add(risk: str) -> None:
        if risk not in risks:
            risks.append(risk)

    if "migration" in roles:
        add("Migration change: verify rollback, data shape, and deployment order.")
    if "package" in roles:
        add("Dependency/package change: verify lockfiles, install path, and supply-chain impact.")
    if "ci" in roles:
        add("CI workflow change: verify permissions, triggers, and artifact behavior.")
    if any(token in paths for token in ("auth", "login", "token", "secret", "password", "permission")):
        add("Auth/security-adjacent path touched: review access control and secret handling.")
    sensitive_patterns = (
        r"\bapi[_-]?key\s*[:=]",
        r"\bprivate[_-]?key\s*[:=]",
        r"\b(secret|password)\s*[:=]",
        r"(^|[/\s])\.env(\.|$|\s)",
    )
    if any(re.search(pattern, diff_lower, re.MULTILINE) for pattern in sensitive_patterns):
        add("Sensitive-looking text appears in diff: confirm no credentials are committed.")
    if "test" not in roles and any(file.role == "source" for file in changed_files):
        add("Source changed without nearby test changes: identify existing tests or add coverage.")
    if not risks:
        add("No high-risk pattern detected by v0.1 heuristics.")
    return risks


def build_checklist(
    changed_files: list[ChangedFile],
    commands: list[str],
    risk_areas: list[str],
) -> list[str]:
    checklist = [
        "Read the changed files before editing.",
        "Confirm the intended behavior from the PR description or issue.",
    ]
    checklist.extend(f"Run `{command}`." for command in commands[:4])
    if any(file.role == "test" for file in changed_files):
        checklist.append("Check whether changed tests cover the changed source paths.")
    if any("Source changed without" in risk for risk in risk_areas):
        checklist.append("Find or add a targeted test for the source change.")
    if any(file.role == "ci" for file in changed_files):
        checklist.append("Review workflow permissions and artifact paths.")
    checklist.append("Summarize residual risk before merge.")
    return checklist


def build_agent_prompt(
    title: str,
    changed_files: list[ChangedFile],
    commands: list[str],
    risk_areas: list[str],
    instructions: list[InstructionFile],
    diff_preview: str,
) -> str:
    file_lines = "\n".join(
        f"- {file.path} ({file.role}, {file.status}, +{file.additions}/-{file.deletions})"
        for file in changed_files
    )
    command_lines = "\n".join(f"- {command}" for command in commands)
    risk_lines = "\n".join(f"- {risk}" for risk in risk_areas)
    instruction_lines = "\n".join(f"- {item.path}: {item.summary}" for item in instructions)
    if not instruction_lines:
        instruction_lines = "- No repo instruction files found by mergepack."

    return (
        f"You are reviewing this pull request: {title}\n\n"
        "Use the repository instructions and changed-file map below. Focus on correctness, "
        "tests, regressions, and merge risk. Do not rewrite unrelated code.\n\n"
        "Changed files:\n"
        f"{file_lines}\n\n"
        "Repo instructions:\n"
        f"{instruction_lines}\n\n"
        "Verification commands to consider:\n"
        f"{command_lines}\n\n"
        "Risk areas:\n"
        f"{risk_lines}\n\n"
        "Diff preview:\n"
        "```diff\n"
        f"{diff_preview}\n"
        "```\n\n"
        "Return findings first, then suggested fixes, then exact commands to run."
    )


def trim_diff(diff_text: str, max_lines: int) -> str:
    lines = diff_text.splitlines()
    if max_lines <= 0 or len(lines) <= max_lines:
        return diff_text.rstrip()
    omitted = len(lines) - max_lines
    return "\n".join(lines[:max_lines]).rstrip() + f"\n... ({omitted} diff lines omitted)"


def build_diff_preview(diff_source: DiffSource, max_lines: int) -> str:
    if diff_source.diff_text.strip():
        return trim_diff(diff_source.diff_text, max_lines)
    if diff_source.changed_paths:
        listed_paths = "\n".join(f"- {path}" for path in diff_source.changed_paths)
        limitation = "\n".join(diff_source.limitations)
        return f"{limitation}\n\nChanged files:\n{listed_paths}".rstrip()
    return ""


def _inside_git_worktree(repo: Path) -> bool:
    try:
        output = run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo)
    except MergepackError:
        return False
    return output.strip() == "true"
