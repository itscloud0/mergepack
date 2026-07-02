from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import (
    MergepackError,
    build_packet,
    load_changed_files_from_file,
    load_diff_from_file,
    load_diff_from_git,
    load_diff_from_pr,
)
from .render import render_html, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mergepack",
        description="Turn a pull request diff into an agent-ready merge packet.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository path for git diff, command detection, and repo instructions. Default: .",
    )
    parser.add_argument("--base", default="main", help="Base ref for local git diff. Default: main")
    parser.add_argument("--head", default="HEAD", help="Head ref for local git diff. Default: HEAD")
    parser.add_argument(
        "--diff-file",
        help="Read a pasted unified diff from a file instead of running git diff.",
    )
    parser.add_argument(
        "--changed-files",
        help="Read a newline-delimited changed-file list when a full diff is unavailable.",
    )
    parser.add_argument(
        "--pr",
        help=(
            "GitHub PR spec such as owner/repo#123 or a PR URL. Requires gh. "
            "Uses gh pr diff and gh pr view."
        ),
    )
    parser.add_argument(
        "--title",
        help="Packet title. Defaults to PR title, diff source, or base..head.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format. Default: markdown",
    )
    parser.add_argument("--output", "-o", help="Write output to this file instead of stdout.")
    parser.add_argument(
        "--max-diff-lines",
        type=int,
        default=220,
        help="Max diff lines to include in the agent prompt preview. Default: 220",
    )
    parser.add_argument(
        "--fail-on-risk",
        choices=["never", "high"],
        default="never",
        help="Exit 2 when high-risk changes are found. Default: never",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_arg = Path(args.repo).expanduser()
    repo = repo_arg.resolve()

    try:
        input_modes = sum(bool(value) for value in (args.pr, args.diff_file, args.changed_files))
        if input_modes > 1:
            parser.error("choose only one of --pr, --diff-file, or --changed-files")

        if args.pr:
            diff_source = load_diff_from_pr(args.pr)
        elif args.diff_file:
            diff_source = load_diff_from_file(Path(args.diff_file))
        elif args.changed_files:
            diff_source = load_changed_files_from_file(Path(args.changed_files))
        else:
            diff_source = load_diff_from_git(repo, args.base, args.head)

        packet = build_packet(
            repo=repo,
            diff_source=diff_source,
            title=args.title,
            max_diff_lines=args.max_diff_lines,
            repo_label=args.repo,
        )
    except MergepackError as exc:
        print(f"mergepack: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        rendered = json.dumps(packet.to_json(), indent=2, sort_keys=True) + "\n"
    elif args.format == "html":
        rendered = render_html(packet)
    else:
        rendered = render_markdown(packet)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    if args.fail_on_risk == "high" and packet.high_risk:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
