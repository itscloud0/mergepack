from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mergepack.core import (
    DiffSource,
    build_packet,
    classify_path,
    collect_instructions,
    detect_commands,
    load_changed_files_from_file,
    load_config,
    load_diff_from_file,
    load_diff_from_git,
    parse_changed_files,
    parse_changed_file_list,
    parse_pr_spec,
)
from mergepack.render import render_html, render_markdown


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "language-fixtures"
CONFIG_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "config-fixtures"

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

    def test_json_shape_is_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            repo = Path(raw_tmp)
            packet = build_packet(repo, DiffSource(label="sample diff", diff_text=SAMPLE_DIFF), "JSON packet")
            encoded = json.dumps(packet.to_json())
        self.assertIn("changed_files", encoded)
        self.assertIn("high_risk", encoded)

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


if __name__ == "__main__":
    unittest.main()
