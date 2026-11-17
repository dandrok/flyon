"""JSONL store: append-only files you can read with `grep` and diff with git.

One log holds the session records (creation and end events); each transcript is its own file under
``transcripts/<session_id>.jsonl``. No index, no schema migration — this is the artifact format, and
the escape hatch if a future SQLite change ever needs one.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from flyon.domain.transcript import Line, Session
from flyon.ports.store import StoreError


class JsonlStore:
    """The readable store. Satisfies `flyon.ports.store.Store`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._transcripts = root / "transcripts"
        self._transcripts.mkdir(parents=True, exist_ok=True)
        self._log = root / "sessions.jsonl"
        self._log.touch(exist_ok=True)
        self._sessions: dict[str, Session] = self._load_sessions()
        self._counts: dict[str, int] = {}

    @property
    def root(self) -> Path:
        return self._root

    def create_session(self, session: Session) -> None:
        if session.session_id in self._sessions:
            raise StoreError(f"session {session.session_id!r} already exists")
        self._append_record(
            {
                "type": "session",
                "session_id": session.session_id,
                "started_at": session.started_at.isoformat(),
                "title": session.title,
            }
        )
        self._sessions[session.session_id] = session

    def end_session(self, session_id: str, ended_at: datetime) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise StoreError(f"unknown session {session_id!r}")
        self._append_record(
            {"type": "end", "session_id": session_id, "ended_at": ended_at.isoformat()}
        )
        self._sessions[session_id] = replace(session, ended_at=ended_at)

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 20) -> list[Session]:
        ordered = sorted(
            self._sessions.values(),
            key=lambda session: (session.started_at, session.session_id),
            reverse=True,
        )
        return ordered[: max(limit, 0)]

    def append_line(self, line: Line) -> Line:
        if line.session_id not in self._sessions:
            raise StoreError(f"unknown session {line.session_id!r}")
        line_id = self.line_count(line.session_id) + 1
        stored = replace(line, line_id=line_id)
        with self._path_for(line.session_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_line_record(stored), ensure_ascii=False) + "\n")
        self._counts[line.session_id] = line_id
        return stored

    def lines(self, session_id: str) -> list[Line]:
        path = self._path_for(session_id)
        if not path.exists():
            return []
        lines: list[Line] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                lines.append(_line_from_record(json.loads(raw), session_id))
        return sorted(lines, key=lambda line: (line.start_ms, line.line_id or 0))

    def line_count(self, session_id: str) -> int:
        if session_id in self._counts:
            return self._counts[session_id]
        count = len(self.lines(session_id))
        self._counts[session_id] = count
        return count

    def close(self) -> None:
        self._sessions.clear()
        self._counts.clear()

    def _path_for(self, session_id: str) -> Path:
        return self._transcripts / f"{session_id}.jsonl"

    def _append_record(self, record: dict[str, Any]) -> None:
        with self._log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _load_sessions(self) -> dict[str, Session]:
        sessions: dict[str, Session] = {}
        for raw in self._log.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            record: dict[str, Any] = json.loads(raw)
            session_id = str(record["session_id"])
            if record["type"] == "session":
                sessions[session_id] = Session(
                    session_id=session_id,
                    started_at=datetime.fromisoformat(str(record["started_at"])),
                    title=str(record.get("title", "")),
                )
            elif record["type"] == "end" and session_id in sessions:
                sessions[session_id] = replace(
                    sessions[session_id],
                    ended_at=datetime.fromisoformat(str(record["ended_at"])),
                )
        return sessions


def _line_record(line: Line) -> dict[str, Any]:
    return {
        "line_id": line.line_id,
        "stream": line.stream,
        "start_ms": line.start_ms,
        "end_ms": line.end_ms,
        "text": line.text,
        "engine": line.engine,
        "model": line.model,
    }


def _line_from_record(record: dict[str, Any], session_id: str = "") -> Line:
    return Line(
        session_id=session_id,
        line_id=record.get("line_id"),
        stream=str(record["stream"]),
        start_ms=int(record["start_ms"]),
        end_ms=int(record["end_ms"]),
        text=str(record["text"]),
        engine=str(record.get("engine", "unknown")),
        model=str(record.get("model", "unknown")),
    )
