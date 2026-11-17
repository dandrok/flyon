"""The release helper: version bumps and changelog closes, with no git in the way."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release.py"
spec = importlib.util.spec_from_file_location("flyon_release", SCRIPT)
assert spec is not None and spec.loader is not None
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

PYPROJECT = '[project]\nname = "flyon"\nversion = "0.1.0"\n'
CHANGELOG = """# Changelog

## [Unreleased]

### Added

- a thing that shipped

## [0.1.0] - 2026-11-17

### Added

- the first thing
"""


def test_the_current_version_is_read_from_pyproject() -> None:
    assert release.current_version(PYPROJECT) == "0.1.0"


def test_a_version_bump_replaces_exactly_one_line() -> None:
    bumped = release.set_version(PYPROJECT, "0.2.0")
    assert 'version = "0.2.0"' in bumped
    assert bumped.count('version = "') == 1


def test_a_nonsense_version_is_refused() -> None:
    with pytest.raises(release.ReleaseError, match="semver"):
        release.set_version(PYPROJECT, "0.2")
    with pytest.raises(release.ReleaseError, match="semver"):
        release.set_version(PYPROJECT, "v0.2.0")


def test_closing_the_changelog_dates_the_section_and_empties_unreleased() -> None:
    closed = release.close_changelog(CHANGELOG, "0.2.0", date(2026, 12, 1))
    assert "## [Unreleased]\n\n## [0.2.0] - 2026-12-01" in closed
    assert "- a thing that shipped" in closed
    assert closed.index("## [0.2.0]") < closed.index("## [0.1.0]")
    # the items moved down: Unreleased is now empty
    unreleased = closed.split("## [0.2.0]")[0]
    assert "- a thing that shipped" not in unreleased


def test_the_released_heading_keeps_its_blank_line_and_its_subsections() -> None:
    # a heading with no blank line under it reads as one paragraph in every markdown renderer
    closed = release.close_changelog(CHANGELOG, "0.2.0", date(2026, 12, 1))
    assert "## [0.2.0] - 2026-12-01\n\n### Added" in closed
    assert "\n## [0.2.0] - 2026-12-01\n### " not in closed


def test_an_empty_unreleased_section_is_a_release_with_no_notes() -> None:
    empty = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-11-17\n\n- old\n"
    with pytest.raises(release.ReleaseError, match="empty"):
        release.close_changelog(empty, "0.2.0", date(2026, 12, 1))


def test_a_changelog_without_an_unreleased_heading_is_refused() -> None:
    with pytest.raises(release.ReleaseError, match="Unreleased"):
        release.close_changelog("# Changelog\n", "0.2.0", date(2026, 12, 1))


def test_a_dirty_working_tree_blocks_the_release() -> None:
    assert release.working_tree_is_clean(run=lambda: "") is True
    assert release.working_tree_is_clean(run=lambda: " M README.md") is False


def test_the_script_refuses_the_version_it_already_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "working_tree_is_clean", lambda run=None: True)
    monkeypatch.setattr(release, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(release, "CHANGELOG", tmp_path / "CHANGELOG.md")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    assert release.main(["0.1.0"]) == 2
