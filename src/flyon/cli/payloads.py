"""JSON payloads — pure functions, no `rich`, so the `--json` path stays cheap.

These key names are a public interface the moment another client reads them: keep them stable.
"""

from __future__ import annotations

from collections.abc import Sequence

from flyon.domain.transcript import Line, Session, format_timestamp

Row = tuple[Session, int]


def duration_text(ms: int | None) -> str:
    """A duration a human can read: `12:31`, or an em dash while the session is still open."""
    return "—" if ms is None else format_timestamp(ms)


def session_payload(session: Session, line_count: int) -> dict[str, object]:
    return {
        "id": session.session_id,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration_ms": session.duration_ms,
        "title": session.title,
        "lines": line_count,
    }


def sessions_payload(rows: Sequence[Row]) -> dict[str, object]:
    return {"sessions": [session_payload(session, count) for session, count in rows]}


def line_payload(line: Line) -> dict[str, object]:
    return {
        "id": line.line_id,
        "stream": line.stream,
        "start_ms": line.start_ms,
        "end_ms": line.end_ms,
        "text": line.text,
        "engine": line.engine,
        "model": line.model,
    }


def lines_payload(session: Session, lines: Sequence[Line]) -> dict[str, object]:
    return {
        "session": session_payload(session, len(lines)),
        "lines": [line_payload(line) for line in lines],
    }
