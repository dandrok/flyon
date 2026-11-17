"""The note a meeting becomes: one summary and three lists, and nothing invented in between."""

from __future__ import annotations

from dataclasses import dataclass

SECTIONS = ("decisions", "actions", "questions")


@dataclass(frozen=True, slots=True)
class Note:
    """What a notes provider must return.

    A note with no summary is a failed call, not an empty note: something was asked and nothing came
    back. Empty *sections* are fine — plenty of meetings decide nothing — but a blank bullet is a
    model padding its answer, so it is rejected here rather than printed.
    """

    summary: str
    decisions: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a note needs a summary; an empty note is a failed call")
        if self.summary != self.summary.strip():
            raise ValueError("summary must be stripped")
        for name in SECTIONS:
            items: tuple[str, ...] = getattr(self, name)
            for item in items:
                if not item.strip():
                    raise ValueError(f"{name} contains a blank entry")
                if item != item.strip():
                    raise ValueError(f"{name} entries must be stripped")

    @property
    def item_count(self) -> int:
        """How many bullets the note carries, summary excluded."""
        return sum(len(getattr(self, name)) for name in SECTIONS)
