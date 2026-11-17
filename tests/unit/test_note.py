"""The `Note` value: a summary is mandatory, padding is not allowed."""

from __future__ import annotations

import pytest

from flyon.domain.note import Note


def test_a_note_needs_a_summary() -> None:
    # AC-43: an empty answer is a failed call, not an empty note
    with pytest.raises(ValueError, match="needs a summary"):
        Note(summary="   ")


def test_the_summary_and_every_bullet_are_stripped() -> None:
    # AC-43
    with pytest.raises(ValueError, match="stripped"):
        Note(summary=" summary")
    with pytest.raises(ValueError, match="blank entry"):
        Note(summary="ok", actions=("  ",))
    with pytest.raises(ValueError, match="stripped"):
        Note(summary="ok", decisions=(" pay the invoice",))


def test_a_note_with_no_decisions_is_a_note() -> None:
    # AC-43: plenty of meetings decide nothing
    note = Note(summary="we talked about the migration", actions=("take the backfill",))

    assert note.decisions == ()
    assert note.item_count == 1


def test_item_count_counts_bullets_not_the_summary() -> None:
    # AC-43
    note = Note(
        summary="s",
        decisions=("a", "b"),
        actions=("c",),
        questions=("d", "e", "f"),
    )

    assert note.item_count == 6
