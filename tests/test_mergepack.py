from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mergepack import __version__
from mergepack.core import (
    DiffSource,
    ReviewComment,
    build_packet,
    classify_path,
    collect_instructions,
    detect_commands,
    load_changed_files_from_file,
    load_config,
    load_diff_from_file,
    load_diff_from_git,
    load_diff_from_pr,
    parse_changed_files,
    parse_changed_file_list,
    parse_pr_spec,
)
from mergepack.render import render_html, render_markdown, render_sarif


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "language-fixtures"
CONFIG_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "config-fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
index 7f3a111..89abcde 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,4 +1,7 @@
 def login(user):
-    return True
+    if not user.active:
+        return False
+    return True
diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,3 @@
+def test_inactive_user_cannot_login():
+    assert True
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 1111111..2222222 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1,3 +1,4 @@
 name: CI
+permissions: read-all
"""


class MergepackTests(unittest.TestCase):
    def test_runtime_version_matches_project_metadata(self) -> None:
        project_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"$', project_text, re.MULTILINE)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(__version__, match.group(1))

    def test_external_action_refs_are_immutable(self) -> None:
        action_files = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*"))
        action_files.append(PROJECT_ROOT / "action.yml")
        mutable_refs = []

        for path in action_files:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = re.search(r"\buses:\s*([^\s#]+)", line)
                if not match or match.group(1).startswith(("./", "../")):
                    continue
                ref = match.group(1).rsplit("@", 1)[-1]
                if re.fullmatch(r"[0-9a-f]{40}", ref) is None:
                    mutable_refs.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number} {ref}")

        self.assertEqual(mutable_refs, [], "mutable external action refs: " + ", ".join(mutable_refs))

    def test_classifies_common_paths(self) -> None:
        self.assertEqual(classify_path("src/app.py"), "source")
        self.assertEqual(classify_path("tests/test_app.py"), "test")
        self.assertEqual(classify_path("internal/http/health_test.go"), "test")
        self.assertEqual(classify_path("src/cart.test.ts"), "test")
        self.assertEqual(classify_path("src/cart.spec.tsx"), "test")
        self.assertEqual(classify_path(".github/workflows/ci.yml"), "ci")
        self.assertEqual(classify_path("pyproject.toml"), "package")
        self.assertEqual(classify_path("docs/usage.md"), "docs")

    def test_parse_changed_files_counts_delta(self) -> None:
        files = parse_changed_files(SAMPLE_DIFF)
        by_path = {file.path: file for file in files}

        self.assertEqual(by_path["src/auth.py"].role, "source")
        self.assertEqual(by_path["src/auth.py"].additions, 3)
        self.assertEqual(by_path["src/auth.py"].deletions, 1)
        self.assertEqual(by_path["tests/test_auth.py"].status, "added")
        self.assertEqual(by_path[".github/workflows/ci.yml"].role, "ci")

    def test_build_packet_detects_commands_instructions_and_risk(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
            (repo / "AGENTS.md").write_text("# Rules\nRun tests before final review.\n", encoding="utf-8")

            packet = build_packet(repo, DiffSource(label="sample diff", diff_text=SAMPLE_DIFF), "Test packet")

        self.assertEqual(packet.stats["files"], 3)
        self.assertIn("python -m unittest discover -s tests", packet.commands)
        self.assertTrue(any(item.path == "AGENTS.md" for item in packet.instructions))
        self.assertTrue(any("CI workflow" in risk for risk in packet.risk_areas))
        self.assertIn("Agent-Ready Prompt", render_markdown(packet))
        self.assertIn("<table>", render_html(packet))

    def test_pr_description_is_preserved_in_packet_outputs(self) -> None:
        description = (
            "Why:\n\nFixes the checkout path.\n\n"
            "<script>alert(1)</script> & keep this context\n"
            "```text\nkeep this context\n```"
        )
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            packet = build_packet(
                repo,
                DiffSource(
                    label="GitHub PR owner/repo#12",
                    diff_text=SAMPLE_DIFF,
                    title="Fix checkout path",
                    body=description,
                    url="https://github.com/owner/repo/pull/12",
                ),
            )
            markdown = render_markdown(packet)
            html = render_html(packet)
            payload = packet.to_json()

        self.assertEqual(packet.pull_request_body, description)
        self.assertIn("## Pull Request Description", markdown)
        self.assertIn("> Fixes the checkout path.", markdown)
        self.assertIn("keep this context", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("pull_request_body", payload)
        self.assertEqual(payload["pull_request_body"], description)
        self.assertIn("Pull request description:", packet.agent_prompt)
        self.assertIn("> Fixes the checkout path.", packet.agent_prompt)

    def test_empty_pr_description_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            packet = build_packet(
                Path(raw_tmp),
                DiffSource(label="GitHub PR owner/repo#12", diff_text=SAMPLE_DIFF, body="  \n"),
            )

        self.assertIsNone(packet.pull_request_body)
        self.assertNotIn("## Pull Request Description", render_markdown(packet))
        self.assertNotIn("<h2>Pull Request Description</h2>", render_html(packet))

    def test_review_comments_are_preserved_in_packet_outputs(self) -> None:
        comment = ReviewComment(
            author="octocat",
            body="Please add a regression test.",
            path="src/auth.py",
            line=4,
            side="RIGHT",
            url="https://github.com/owner/repo/pull/12#discussion_r1",
            diff_hunk="@@ -1,2 +1,3 @@\n+return False",
        )
        with tempfile.TemporaryDirectory() as raw_tmp:
            packet = build_packet(
                Path(raw_tmp),
                DiffSource(
                    label="GitHub PR owner/repo#12",
                    diff_text=SAMPLE_DIFF,
                    review_comments=(comment,),
                ),
            )
            markdown = render_markdown(packet)
            html = render_html(packet)
            payload = packet.to_json()

        self.assertIn("## Inline Review Comments", markdown)
        self.assertIn("src/auth.py:4 (RIGHT)", markdown)
        self.assertIn("> Please add a regression test.", markdown)
        self.assertIn("Inline Review Comments", html)
        self.assertIn("Please add a regression test.", html)
        self.assertIn("review_comments", payload)
        self.assertEqual(payload["review_comments"][0]["author"], "octocat")
        self.assertIn("Inline review comments:", packet.agent_prompt)
        self.assertIn("Please add a regression test.", packet.agent_prompt)

    def test_load_diff_from_pr_fetches_paginated_review_comments(self) -> None:
        metadata = json.dumps(
            {
                "title": "Fix auth",
                "body": "Please review",
                "url": "https://github.com/owner/repo/pull/12",
                "baseRefName": "main",
                "headRefName": "fix-auth",
            }
        )
        comments = json.dumps(
            [
                [
                    {
                        "body": "Please add a test.",
                        "path": "src/auth.py",
                        "line": 4,
                        "side": "RIGHT",
                        "html_url": "https://github.com/owner/repo/pull/12#discussion_r1",
                        "user": {"login": "octocat"},
                    }
                ],
                [],
            ]
        )
        with (
            patch("mergepack.core.shutil.which", return_value="/usr/bin/gh"),
            patch(
                "mergepack.core.run_command",
                side_effect=[metadata, SAMPLE_DIFF, comments],
            ) as run_command,
        ):
            source = load_diff_from_pr("owner/repo#12")

        self.assertEqual(len(source.review_comments), 1)
        self.assertEqual(source.review_comments[0].author, "octocat")
        self.assertEqual(source.review_comments[0].path, "src/auth.py")
        self.assertIn(
            "repos/owner/repo/pulls/12/comments?per_page=100",
            run_command.call_args_list[2].args[0],
        )

    def test_json_shape_is_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            packet = build_packet(repo, DiffSource(label="sample diff", diff_text=SAMPLE_DIFF), "JSON packet")
            encoded = json.dumps(packet.to_json())
        self.assertIn("changed_files", encoded)
        self.assertIn("high_risk", encoded)

    def test_sarif_shape_maps_risk_to_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            packet = build_packet(
                repo,
                DiffSource(label="sample diff", diff_text=SAMPLE_DIFF),
                "SARIF packet",
            )
            payload = json.loads(render_sarif(packet))

        run = payload["runs"][0]
        results = run["results"]
        rule_ids = {item["ruleId"] for item in results}
        result_paths = {
            item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for item in results
        }

        self.assertEqual(payload["version"], "2.1.0")
        self.assertIn("mergepack.ci", rule_ids)
        self.assertIn("mergepack.security-path", rule_ids)
        self.assertIn(".github/workflows/ci.yml", result_paths)
        self.assertIn("src/auth.py", result_paths)
        self.assertTrue(run["tool"]["driver"]["rules"])

    def test_tox_env_section_does_not_trigger_secret_risk(self) -> None:
        diff = """diff --git a/pyproject.toml b/pyproject.toml
index 1111111..2222222 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,2 +1,3 @@
+[tool.tox.env.stress]
+commands = ["pytest"]
"""
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            packet = build_packet(repo, DiffSource(label="tox diff", diff_text=diff), "tox")

        self.assertFalse(any("Sensitive-looking" in risk for risk in packet.risk_areas))

    def test_detect_commands_prefers_uv_tox_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            (repo / "tests").mkdir()
            (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text(
                "[tool.tox]\nrequires = []\n[tool.tox.env.style]\ncommands = []\n",
                encoding="utf-8",
            )

            commands = detect_commands(repo, [])

        self.assertIn("uv run --locked --no-default-groups --group dev tox run", commands)
        self.assertNotIn("python -m unittest discover -s tests", commands)

    def test_detect_commands_prefers_pytest_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            (repo / "tests").mkdir()
            (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

            commands = detect_commands(repo, [])

        self.assertIn("python -m pytest", commands)
        self.assertNotIn("python -m unittest discover -s tests", commands)

    def test_python_config_fixture_adds_commands_and_path_roles(self) -> None:
        repo = CONFIG_FIXTURE_ROOT / "python-repo"
        config = load_config(repo)
        diff = """diff --git a/checks/sample_case.py b/checks/sample_case.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/checks/sample_case.py
@@ -0,0 +1,2 @@
+def test_fixture():
+    assert True
"""

        packet = build_packet(
            repo,
            DiffSource(label="python config diff", diff_text=diff),
            config=config,
        )

        self.assertEqual(packet.commands[:2], ["nox -s tests", "python -m ruff check src tests"])
        self.assertEqual(packet.changed_files[0].role, "test")
        self.assertIn("python -m compileall src tests", packet.commands)

    def test_node_config_fixture_adds_commands_and_path_roles(self) -> None:
        repo = CONFIG_FIXTURE_ROOT / "node-repo"
        config = load_config(repo)
        diff = """diff --git a/apps/web/e2e/login.ts b/apps/web/e2e/login.ts
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/apps/web/e2e/login.ts
@@ -0,0 +1,2 @@
+test("login", async () => {})
+export {}
"""

        packet = build_packet(
            repo,
            DiffSource(label="node config diff", diff_text=diff),
            config=config,
        )

        self.assertEqual(packet.commands[:2], ["pnpm test -- --runInBand", "pnpm lint"])
        self.assertEqual(packet.changed_files[0].role, "test")
        self.assertIn("npm test", packet.commands)

    def test_detects_package_groups_for_monorepo_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            (repo / "packages" / "web" / "src").mkdir(parents=True)
            (repo / "services" / "api" / "src").mkdir(parents=True)
            (repo / "crates" / "core" / "src").mkdir(parents=True)
            (repo / "package.json").write_text(
                json.dumps({"workspaces": ["packages/*"]}),
                encoding="utf-8",
            )
            (repo / "packages" / "web" / "package.json").write_text(
                json.dumps(
                    {"name": "@acme/web", "scripts": {"test": "vitest", "lint": "eslint ."}}
                ),
                encoding="utf-8",
            )
            (repo / "services" / "api" / "pyproject.toml").write_text(
                "[project]\nname = 'api-service'\n[tool.pytest.ini_options]\n",
                encoding="utf-8",
            )
            (repo / "Cargo.toml").write_text(
                '[workspace]\nmembers = ["crates/*"]\n',
                encoding="utf-8",
            )
            (repo / "crates" / "core" / "Cargo.toml").write_text(
                "[package]\nname = 'mergepack-core'\nversion = '0.1.0'\n",
                encoding="utf-8",
            )
            diff = """diff --git a/packages/web/src/cart.ts b/packages/web/src/cart.ts
index 1111111..2222222 100644
--- a/packages/web/src/cart.ts
+++ b/packages/web/src/cart.ts
@@ -1 +1,2 @@
 export const cart = []
+export const checkout = []
diff --git a/services/api/src/app.py b/services/api/src/app.py
index 1111111..2222222 100644
--- a/services/api/src/app.py
+++ b/services/api/src/app.py
@@ -1 +1,2 @@
 def app(): pass
+def health(): return True
diff --git a/crates/core/src/lib.rs b/crates/core/src/lib.rs
index 1111111..2222222 100644
--- a/crates/core/src/lib.rs
+++ b/crates/core/src/lib.rs
@@ -1 +1,2 @@
 pub fn run() {}
+pub fn check() {}
"""

            packet = build_packet(repo, DiffSource(label="monorepo diff", diff_text=diff))
            groups = {group.path: group for group in packet.package_groups}
            payload = packet.to_json()

        self.assertEqual(set(groups), {"crates/core", "packages/web", "services/api"})
        self.assertEqual(groups["packages/web"].name, "@acme/web")
        self.assertIn("npm test --workspace packages/web", groups["packages/web"].commands)
        self.assertIn("npm run lint --workspace packages/web", packet.commands)
        self.assertIn("cd services/api && python -m pytest", groups["services/api"].commands)
        self.assertIn("cargo test -p mergepack-core", groups["crates/core"].commands)
        self.assertIn("packages/web/src/cart.ts", groups["packages/web"].changed_files)
        self.assertEqual(len(payload["package_groups"]), 3)
        self.assertIn("Package Groups", render_markdown(packet))
        self.assertIn("mergepack-core", render_html(packet))

    def test_detects_nested_go_module_package_group(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            module = repo / "services" / "worker"
            module.mkdir(parents=True)
            (module / "go.mod").write_text(
                "module example.com/worker\n\ngo 1.22\n",
                encoding="utf-8",
            )
            diff = """diff --git a/services/worker/main.go b/services/worker/main.go
index 1111111..2222222 100644
--- a/services/worker/main.go
+++ b/services/worker/main.go
@@ -1 +1,2 @@
 package main
+func main() {}
"""

            packet = build_packet(repo, DiffSource(label="go monorepo diff", diff_text=diff))

        self.assertEqual(len(packet.package_groups), 1)
        group = packet.package_groups[0]
        self.assertEqual(group.name, "example.com/worker")
        self.assertEqual(group.path, "services/worker")
        self.assertEqual(group.ecosystem, "go")
        self.assertEqual(group.commands, ("cd services/worker && go test ./...",))
        self.assertIn("cd services/worker && go test ./...", packet.commands)

    def test_language_fixtures_match_expected_packets(self) -> None:
        expected = json.loads((FIXTURE_ROOT / "expected-packets.json").read_text(encoding="utf-8"))

        for name, fixture in expected.items():
            with self.subTest(language=name):
                repo = FIXTURE_ROOT / fixture["repo"]
                diff_path = FIXTURE_ROOT / fixture["diff"]
                packet = build_packet(
                    repo,
                    load_diff_from_file(diff_path),
                    f"{name} fixture packet",
                )
                changed = {
                    item.path: {"role": item.role, "status": item.status}
                    for item in packet.changed_files
                }

                self.assertEqual(packet.commands, fixture["commands"])
                self.assertEqual(changed, fixture["changed_files"])
                self.assertIn(fixture["commands"][0], render_markdown(packet))
                self.assertIn("Dependency/package change", "\n".join(packet.risk_areas))
                self.assertIn("Check whether changed tests cover", "\n".join(packet.checklist))

    def test_instruction_summary_strips_html_hero(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            (repo / "README.md").write_text(
                '<div align="center"><img src="logo.svg"></div>\n'
                "# Click\n\n"
                "Click is a Python package for creating command line interfaces.\n\n"
                "## Donate\n\n"
                "Funding links are not repo instructions.\n",
                encoding="utf-8",
            )

            instructions = collect_instructions(repo)

        self.assertEqual(instructions[0].path, "README.md")
        self.assertEqual(
            instructions[0].summary,
            "Click Click is a Python package for creating command line interfaces.",
        )

    def test_load_diff_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            path = Path(raw_tmp) / "sample.diff"
            path.write_text(SAMPLE_DIFF, encoding="utf-8")
            source = load_diff_from_file(path)
        self.assertEqual(source.diff_text, SAMPLE_DIFF)
        self.assertIn("diff file", source.label)

    def test_changed_files_input_marks_missing_diff_preview(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            changed_path = repo / "changed-files.txt"
            changed_path.write_text(
                "./src/app.py\n\n" "tests/test_app.py\nsrc/app.py\n",
                encoding="utf-8",
            )
            source = load_changed_files_from_file(changed_path)
            packet = build_packet(repo, source, "Changed files packet")

        self.assertEqual(parse_changed_file_list("./src/app.py\nsrc/app.py\n"), ["src/app.py"])
        self.assertEqual(packet.stats["files"], 2)
        self.assertEqual(packet.stats["additions"], 0)
        self.assertEqual(packet.stats["deletions"], 0)
        self.assertIn("diff preview", packet.diff_preview)
        self.assertTrue(any("Changed-files input limitation" in risk for risk in packet.risk_areas))
        self.assertIn("src/app.py", packet.agent_prompt)

    def test_load_diff_from_git_range(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
            (repo / "app.py").write_text("print('one')\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)
            subprocess.run(["git", "branch", "base"], cwd=repo, check=True)
            (repo / "app.py").write_text("print('two')\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-qam", "change"], cwd=repo, check=True)

            source = load_diff_from_git(repo, "base", "HEAD")

        self.assertIn("app.py", source.diff_text)

    def test_parse_pr_spec_accepts_url_and_shorthand(self) -> None:
        self.assertEqual(parse_pr_spec("owner/repo#12"), ("owner/repo", "12"))
        self.assertEqual(
            parse_pr_spec("https://github.com/owner/repo/pull/34"),
            ("owner/repo", "34"),
        )


class CliTests(unittest.TestCase):
    def test_cli_writes_json_from_diff_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            diff_path = tmp / "sample.diff"
            out_path = tmp / "packet.json"
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mergepack",
                    "--repo",
                    str(tmp),
                    "--diff-file",
                    str(diff_path),
                    "--format",
                    "json",
                    "--output",
                    str(out_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["files"], 3)

    def test_cli_writes_json_from_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            changed_path = tmp / "changed-files.txt"
            out_path = tmp / "packet.json"
            changed_path.write_text("src/app.py\ntests/test_app.py\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mergepack",
                    "--repo",
                    str(tmp),
                    "--changed-files",
                    str(changed_path),
                    "--format",
                    "json",
                    "--output",
                    str(out_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["files"], 2)
            self.assertEqual(payload["stats"]["additions"], 0)
            self.assertIn("Changed-files input limitation", payload["diff_preview"])

    def test_cli_writes_sarif_from_diff_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            diff_path = tmp / "sample.diff"
            out_path = tmp / "mergepack.sarif"
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mergepack",
                    "--repo",
                    str(tmp),
                    "--diff-file",
                    str(diff_path),
                    "--format",
                    "sarif",
                    "--output",
                    str(out_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(payload["runs"][0]["tool"]["driver"]["name"], "mergepack")
            self.assertTrue(payload["runs"][0]["results"])

    def test_cli_reads_config_for_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            changed_path = tmp / "changed-files.txt"
            config_path = tmp / "mergepack.json"
            out_path = tmp / "packet.json"
            changed_path.write_text("custom/check.fixture\nsrc/app.py\n", encoding="utf-8")
            config_path.write_text(
                json.dumps(
                    {
                        "commands": ["make verify"],
                        "path_roles": [{"pattern": "custom/*.fixture", "role": "test"}],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mergepack",
                    "--repo",
                    str(tmp),
                    "--changed-files",
                    str(changed_path),
                    "--config",
                    str(config_path),
                    "--format",
                    "json",
                    "--output",
                    str(out_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            roles = {item["path"]: item["role"] for item in payload["changed_files"]}
            self.assertEqual(payload["commands"][0], "make verify")
            self.assertEqual(roles["custom/check.fixture"], "test")


class ActionMetadataTests(unittest.TestCase):
    def test_readme_documents_exact_release_artifact_urls(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "https://github.com/itscloud0/mergepack/releases/download/"
            "v0.7.1/mergepack-0.7.1-py3-none-any.whl",
            readme,
        )
        self.assertIn(
            "https://github.com/itscloud0/mergepack/releases/download/"
            "v0.7.1/mergepack-0.7.1.tar.gz",
            readme,
        )

    def test_pr_comment_mode_is_explicit_opt_in(self) -> None:
        action = (PROJECT_ROOT / "action.yml").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("pr-comment:", action)
        self.assertIn('default: "false"', action)
        self.assertIn("inputs.pr-comment == 'true'", action)
        self.assertIn("github.event_name == 'pull_request'", action)
        self.assertIn("mergepack-pr-comment", action)
        self.assertIn("pull-requests: write", readme)


if __name__ == "__main__":
    unittest.main()
