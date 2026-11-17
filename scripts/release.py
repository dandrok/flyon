"""Prepare a release: bump the version, close the changelog section.

Deliberately does not commit, tag or push. A release is a human decision with three visible steps
(version, changelog, tag); a script that does all of them silently is a script that tags the wrong
commit at 1 a.m. This one edits two files and prints the commands that follow.

Usage: python scripts/release.py 0.2.0
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or "git"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PYPROJECT_VERSION = re.compile(r'(?m)^version = "(?P<version>\d+\.\d+\.\d+)"$')
UNRELEASED_HEADING = "## [Unreleased]"
NEXT_SECTION = re.compile(r"(?m)^## \[")


class ReleaseError(RuntimeError):
    """Raised when a release cannot be prepared safely."""


def current_version(pyproject_text: str) -> str:
    match = PYPROJECT_VERSION.search(pyproject_text)
    if match is None:
        raise ReleaseError('pyproject.toml has no `version = "x.y.z"` line')
    return match.group("version")


def set_version(pyproject_text: str, version: str) -> str:
    if not SEMVER.match(version):
        raise ReleaseError(f"{version!r} is not a semver version like 0.2.0")
    if PYPROJECT_VERSION.search(pyproject_text) is None:
        raise ReleaseError("pyproject.toml has no version line to replace")
    return PYPROJECT_VERSION.sub(f'version = "{version}"', pyproject_text, count=1)


def close_changelog(changelog_text: str, version: str, released_on: date) -> str:
    """Turn the `[Unreleased]` section into `[version] - date`, leaving an empty Unreleased above.

    A release with an empty Unreleased section is a release with no notes, which is a release nobody
    asked for. Refusing here is cheaper than explaining it in a changelog later.
    """
    if not SEMVER.match(version):
        raise ReleaseError(f"{version!r} is not a semver version like 0.2.0")
    if UNRELEASED_HEADING not in changelog_text:
        raise ReleaseError("CHANGELOG.md has no `## [Unreleased]` heading")

    start = changelog_text.index(UNRELEASED_HEADING)
    body_start = start + len(UNRELEASED_HEADING)
    following = NEXT_SECTION.search(changelog_text, body_start)
    body_end = following.start() if following else len(changelog_text)
    body = changelog_text[body_start:body_end]

    if not _has_items(body):
        raise ReleaseError("the Unreleased section is empty — nothing to release")

    released = f"\n\n## [{version}] - {released_on.isoformat()}\n\n{body.strip(chr(10))}\n\n"
    remainder = changelog_text[body_end:]
    return changelog_text[:start] + UNRELEASED_HEADING + released + remainder.lstrip("\n")


def _has_items(body: str) -> bool:
    return any(line.startswith(("- ", "* ")) for line in body.splitlines())


def working_tree_is_clean(run: object = None) -> bool:
    runner = run if callable(run) else _git_status
    return not runner()


def _git_status() -> str:
    result = subprocess.run(  # noqa: S603 - resolved git path, fixed arguments, no shell
        [GIT, "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a flyon release.")
    parser.add_argument("version", help="the version being released, e.g. 0.2.0")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="prepare the release even with uncommitted changes (not recommended)",
    )
    args = parser.parse_args(argv)

    if not args.allow_dirty and not working_tree_is_clean():
        print("flyon: working tree is dirty — commit or stash first", file=sys.stderr)
        return 2

    pyproject_text = PYPROJECT.read_text(encoding="utf-8")
    previous = current_version(pyproject_text)
    if previous == args.version:
        print(f"flyon: version is already {previous}", file=sys.stderr)
        return 2

    try:
        new_pyproject = set_version(pyproject_text, args.version)
        new_changelog = close_changelog(
            CHANGELOG.read_text(encoding="utf-8"), args.version, date.today()
        )
    except ReleaseError as exc:
        print(f"flyon: {exc}", file=sys.stderr)
        return 2

    PYPROJECT.write_text(new_pyproject, encoding="utf-8")
    CHANGELOG.write_text(new_changelog, encoding="utf-8")
    print(f"flyon: {previous} -> {args.version}; CHANGELOG closed")
    print()
    print("next:")
    print(f"  git checkout -b release/{args.version}")
    print("  git add -A")
    print(f"  git commit -m 'chore: release {args.version}'")
    print(f"  git push -u origin release/{args.version}    # open the PR, merge it")
    print(f"  git tag -a v{args.version} -m 'v{args.version}' && git push origin v{args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
