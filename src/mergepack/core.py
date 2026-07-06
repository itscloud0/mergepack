from __future__ import annotations

import fnmatch
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


@dataclass(frozen=True)
class PackageGroup:
    name: str
    path: str
    ecosystem: str
    changed_files: tuple[str, ...]
    commands: tuple[str, ...]


VALID_FILE_ROLES = (
    "source",
    "test",
    "package",
    "migration",
    "ci",
    "config",
    "docs",
    "asset",
    "other",
)
CONFIG_FILENAMES = (".mergepack.json", "mergepack.json")
PACKAGE_MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "Cargo.toml")
MANIFEST_SCAN_SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


@dataclass(frozen=True)
class PathRoleRule:
    pattern: str
    role: str


@dataclass(frozen=True)
class MergepackConfig:
    commands: tuple[str, ...] = ()
    path_roles: tuple[PathRoleRule, ...] = ()
    source: str | None = None

    def role_for_path(self, path: str) -> str | None:
        normalized = path.replace("\\", "/")
        for rule in self.path_roles:
            pattern = rule.pattern.replace("\\", "/")
            if fnmatch.fnmatchcase(normalized, pattern):
                return rule.role
        return None


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
    package_groups: list[PackageGroup]
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
            "package_groups": [group.__dict__ for group in self.package_groups],
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


def load_config(repo: Path, config_path: Path | None = None) -> MergepackConfig:
    path = resolve_config_path(repo, config_path)
    if path is None:
        return MergepackConfig()
    if not path.exists():
        raise MergepackError(f"config file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MergepackError(f"config file is not valid JSON: {path}") from exc
    except OSError as exc:
        raise MergepackError(f"could not read config file: {path}") from exc
    if not isinstance(data, dict):
        raise MergepackError("config file must contain a JSON object")

    commands = parse_config_commands(data.get("commands", []), "commands")
    path_roles = parse_config_path_roles(data.get("path_roles", []))
    return MergepackConfig(
        commands=tuple(commands),
        path_roles=tuple(path_roles),
        source=str(path),
    )


def resolve_config_path(repo: Path, config_path: Path | None) -> Path | None:
    if config_path is None:
        for name in CONFIG_FILENAMES:
            candidate = repo / name
            if candidate.exists():
                return candidate
        return None

    candidate = config_path.expanduser()
    if candidate.is_absolute():
        return candidate
    cwd_candidate = candidate.resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (repo / candidate).resolve()


def parse_config_commands(raw_commands: object, field_name: str) -> list[str]:
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise MergepackError(f"config field `{field_name}` must be a list of strings")
    commands: list[str] = []
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, str) or not raw_command.strip():
            raise MergepackError(f"config field `{field_name}[{index}]` must be a non-empty string")
        command = raw_command.strip()
        if command not in commands:
            commands.append(command)
    return commands


def parse_config_path_roles(raw_rules: object) -> list[PathRoleRule]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        raise MergepackError("config field `path_roles` must be a list of objects")
    rules: list[PathRoleRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise MergepackError(f"config field `path_roles[{index}]` must be an object")
        pattern = raw_rule.get("pattern")
        role = raw_rule.get("role")
        if not isinstance(pattern, str) or not pattern.strip():
            raise MergepackError(
                f"config field `path_roles[{index}].pattern` must be a non-empty string"
            )
        if role not in VALID_FILE_ROLES:
            valid = ", ".join(VALID_FILE_ROLES)
            raise MergepackError(f"config field `path_roles[{index}].role` must be one of: {valid}")
        rules.append(PathRoleRule(pattern=pattern.strip(), role=str(role)))
    return rules


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
    config: MergepackConfig | None = None,
) -> MergePacket:
    config = config or MergepackConfig()
    if diff_source.changed_paths:
        changed_files = changed_files_from_paths(diff_source.changed_paths, config)
    else:
        changed_files = parse_changed_files(diff_source.diff_text, config)
    if not changed_files:
        raise MergepackError("diff did not contain changed files")

    stats = summarize_stats(changed_files)
    package_groups = detect_package_groups(repo, changed_files)
    commands = detect_commands(repo, changed_files, config)
    append_package_group_commands(commands, package_groups)
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
        package_groups=package_groups,
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
        package_groups=package_groups,
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


def changed_files_from_paths(
    paths: tuple[str, ...],
    config: MergepackConfig | None = None,
) -> list[ChangedFile]:
    return sorted(
        (
            ChangedFile(
                path=path,
                status="modified",
                role=classify_path(path, config),
                additions=0,
                deletions=0,
            )
            for path in paths
        ),
        key=lambda item: (role_sort_key(item.role), item.path),
    )


def parse_changed_files(
    diff_text: str,
    config: MergepackConfig | None = None,
) -> list[ChangedFile]:
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
                role=classify_path(path, config),
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


def classify_path(path: str, config: MergepackConfig | None = None) -> str:
    if config:
        configured_role = config.role_for_path(path)
        if configured_role:
            return configured_role

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


def detect_commands(
    repo: Path,
    changed_files: list[ChangedFile],
    config: MergepackConfig | None = None,
) -> list[str]:
    commands: list[str] = []

    def add(command: str) -> None:
        if command not in commands:
            commands.append(command)

    if config:
        for command in config.commands:
            add(command)

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


def append_package_group_commands(commands: list[str], package_groups: list[PackageGroup]) -> None:
    for group in package_groups:
        for command in group.commands:
            if command not in commands:
                commands.append(command)


def detect_package_groups(repo: Path, changed_files: list[ChangedFile]) -> list[PackageGroup]:
    roots = discover_package_roots(repo)
    if not roots or not any(root.path != "." for root in roots):
        return []

    groups_by_path: dict[str, list[str]] = {}
    sorted_roots = sorted(roots, key=lambda root: (-len(root.path), root.path))
    for changed_file in changed_files:
        root = matching_package_root(changed_file.path, sorted_roots)
        if root is None:
            continue
        groups_by_path.setdefault(root.path, []).append(changed_file.path)

    groups: list[PackageGroup] = []
    for root in sorted(roots, key=lambda item: (item.ecosystem, item.path)):
        files = groups_by_path.get(root.path)
        if not files:
            continue
        groups.append(
            PackageGroup(
                name=root.name,
                path=root.path,
                ecosystem=root.ecosystem,
                changed_files=tuple(sorted(files)),
                commands=tuple(root.commands),
            )
        )
    return groups


@dataclass(frozen=True)
class PackageRoot:
    name: str
    path: str
    ecosystem: str
    commands: tuple[str, ...]


def discover_package_roots(repo: Path) -> list[PackageRoot]:
    workspace_paths = discover_npm_workspace_paths(repo)
    roots: dict[tuple[str, str], PackageRoot] = {}

    for manifest in iter_package_manifests(repo):
        package_dir = manifest.parent
        relative = relative_package_path(repo, package_dir)
        name = infer_package_name(package_dir, manifest)
        ecosystem = ecosystem_for_manifest(manifest.name)
        commands = package_commands(repo, package_dir, ecosystem, name, relative, workspace_paths)
        key = (ecosystem, relative)
        if commands and key not in roots:
            roots[key] = PackageRoot(
                name=name,
                path=relative,
                ecosystem=ecosystem,
                commands=tuple(commands),
            )

    return list(roots.values())


def iter_package_manifests(repo: Path) -> list[Path]:
    manifests: list[Path] = []
    for name in PACKAGE_MANIFESTS:
        for path in repo.rglob(name):
            try:
                relative_parts = path.relative_to(repo).parts
            except ValueError:
                continue
            if any(part in MANIFEST_SCAN_SKIP_DIRS for part in relative_parts):
                continue
            manifests.append(path)
    return sorted(manifests, key=lambda path: path.relative_to(repo).as_posix())


def ecosystem_for_manifest(name: str) -> str:
    if name == "package.json":
        return "npm"
    if name == "Cargo.toml":
        return "cargo"
    return "python"


def relative_package_path(repo: Path, package_dir: Path) -> str:
    try:
        relative = package_dir.relative_to(repo).as_posix()
    except ValueError:
        return str(package_dir)
    return relative or "."


def matching_package_root(path: str, roots: list[PackageRoot]) -> PackageRoot | None:
    normalized = path.replace("\\", "/")
    for root in roots:
        if root.path == "." or normalized == root.path or normalized.startswith(f"{root.path}/"):
            return root
    return None


def package_commands(
    repo: Path,
    package_dir: Path,
    ecosystem: str,
    name: str,
    relative: str,
    npm_workspace_paths: set[str],
) -> list[str]:
    raw_commands = detect_commands(package_dir, [])
    if raw_commands == ["run the repo's normal test command for the changed files"]:
        return []
    if relative == ".":
        return raw_commands
    if ecosystem == "npm" and relative in npm_workspace_paths:
        return [workspace_npm_command(command, relative) for command in raw_commands]
    if ecosystem == "cargo" and cargo_package_is_workspace_member(repo, package_dir):
        return [workspace_cargo_command(command, name, relative) for command in raw_commands]
    return [f"cd {relative} && {command}" for command in raw_commands]


def workspace_npm_command(command: str, workspace: str) -> str:
    if command == "npm test":
        return f"npm test --workspace {workspace}"
    if command.startswith("npm run "):
        return f"{command} --workspace {workspace}"
    return f"cd {workspace} && {command}"


def workspace_cargo_command(command: str, package_name: str, package_path: str) -> str:
    if package_name and command in {"cargo test", "cargo build"}:
        action = command.removeprefix("cargo ")
        return f"cargo {action} -p {package_name}"
    return f"cd {package_path} && {command}"


def cargo_package_is_workspace_member(repo: Path, package_dir: Path) -> bool:
    if package_dir == repo:
        return False
    return "[workspace]" in read_text_safely(repo / "Cargo.toml")


def discover_npm_workspace_paths(repo: Path) -> set[str]:
    package_json = repo / "package.json"
    data = read_json_object(package_json)
    raw_workspaces = data.get("workspaces")
    if isinstance(raw_workspaces, dict):
        raw_workspaces = raw_workspaces.get("packages")
    if not isinstance(raw_workspaces, list):
        return set()

    workspaces: set[str] = set()
    for raw_pattern in raw_workspaces:
        if not isinstance(raw_pattern, str) or raw_pattern.startswith("!"):
            continue
        pattern = raw_pattern.strip().rstrip("/")
        if not pattern:
            continue
        for package_json_path in repo.glob(f"{pattern}/package.json"):
            if package_json_path.is_file():
                workspaces.add(relative_package_path(repo, package_json_path.parent))
    return workspaces


def infer_package_name(package_dir: Path, manifest: Path) -> str:
    if manifest.name == "package.json":
        data = read_json_object(manifest)
        raw_name = data.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()
    if manifest.name in {"pyproject.toml", "Cargo.toml"}:
        found = parse_toml_string_value(read_text_safely(manifest), "name")
        if found:
            return found
    return package_dir.name or "."


def parse_toml_string_value(text: str, key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def read_json_object(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_package_scripts(path: Path) -> dict[str, str]:
    data = read_json_object(path)
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
    package_groups: list[PackageGroup],
    risk_areas: list[str],
    instructions: list[InstructionFile],
    diff_preview: str,
) -> str:
    file_lines = "\n".join(
        f"- {file.path} ({file.role}, {file.status}, +{file.additions}/-{file.deletions})"
        for file in changed_files
    )
    command_lines = "\n".join(f"- {command}" for command in commands)
    package_lines = format_package_groups_for_prompt(package_groups)
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
        "Package groups:\n"
        f"{package_lines}\n\n"
        "Risk areas:\n"
        f"{risk_lines}\n\n"
        "Diff preview:\n"
        "```diff\n"
        f"{diff_preview}\n"
        "```\n\n"
        "Return findings first, then suggested fixes, then exact commands to run."
    )


def format_package_groups_for_prompt(package_groups: list[PackageGroup]) -> str:
    if not package_groups:
        return "- No package/workspace groups detected by mergepack."
    lines: list[str] = []
    for group in package_groups:
        files = ", ".join(group.changed_files)
        commands = "; ".join(group.commands) if group.commands else "no package command detected"
        lines.append(
            f"- {group.name} ({group.ecosystem}, {group.path}): {files}; commands: {commands}"
        )
    return "\n".join(lines)


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
