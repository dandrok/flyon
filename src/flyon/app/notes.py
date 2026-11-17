"""Writing a note: markdown out of a `Note`, and a file that either exists whole or not at all.

The order matters and is deliberate: the provider is called first, rendering second, writing third.
A provider that fails therefore leaves nothing on disk to delete, and the write itself goes through
a temporary file, so a half-written note can never be mistaken for a finished one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from flyon.domain.note import Note
from flyon.domain.transcript import Session, Transcript, format_timestamp
from flyon.ports.notes import NotesProvider
from flyon.ports.store import Store

NOTES_DIRNAME = "notes"
EMPTY = "- none"


@dataclass(frozen=True, slots=True)
class NoteResult:
    """What `summarize` did, so the CLI can report rather than guess."""

    note: Note
    path: Path
    copy_path: Path | None
    provider: str
    model: str


def note_path(data_dir: Path, session_id: str) -> Path:
    return data_dir / NOTES_DIRNAME / f"{session_id}.md"


def render_note(note: Note, session: Session, transcript: Transcript) -> str:
    """The note as markdown: front-matter a tool can read, then sections a person can."""
    title = session.title.strip() or "Meeting"
    streams = ", ".join(dict.fromkeys(line.stream for line in transcript.lines))
    duration = session.duration_ms
    front_matter = [
        "---",
        f"session: {session.session_id}",
        f"date: {session.started_at.astimezone().strftime('%Y-%m-%d %H:%M')}",
        f"duration: {'unknown' if duration is None else format_timestamp(duration)}",
        f"streams: {streams or 'none'}",
        f"lines: {len(transcript.lines)}",
        "---",
    ]
    body = [f"# {title}", "", "## Summary", note.summary.strip(), ""]
    for heading, items in (
        ("Decisions", note.decisions),
        ("Action items", note.actions),
        ("Open questions", note.questions),
    ):
        body.append(f"## {heading}")
        if items:
            body.extend(f"- {item}" for item in items)
        else:
            body.append(EMPTY)
        body.append("")
    return "\n".join(front_matter) + "\n" + "\n".join(body).rstrip() + "\n"


def write_note(text: str, path: Path) -> Path:
    """Write through a temporary file in the same directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(text, encoding="utf-8")
        staging.replace(path)
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return path


def summarize_session(
    *,
    store: Store,
    provider: NotesProvider,
    session: Session,
    data_dir: Path,
    extra_copy: Path | None = None,
) -> NoteResult:
    """Read the transcript, ask the provider, write the note (and its copy) — in that order."""
    transcript = Transcript(session.session_id, store.lines(session.session_id))
    note = provider.summarize(transcript)
    text = render_note(note, session, transcript)

    path = write_note(text, note_path(data_dir, session.session_id))
    copy_path = None
    if extra_copy is not None:
        copy_path = write_note(text, extra_copy / path.name)
    return NoteResult(
        note=note, path=path, copy_path=copy_path, provider=provider.name, model=provider.model
    )
