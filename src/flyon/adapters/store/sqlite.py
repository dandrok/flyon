"""SQLite store: one file, two tables, WAL, and DDL gated on `user_version`."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from flyon.domain.transcript import Line, Session
from flyon.ports.store import StoreError

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1


class SqliteStore:
    """The queryable store. Satisfies `flyon.ports.store.Store`."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    @property
    def path(self) -> Path:
        return self._path

    def _migrate(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version < SCHEMA_VERSION:
            self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()

    def create_session(self, session: Session) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO session (session_id, started_at, ended_at, title)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        session.session_id,
                        session.started_at.isoformat(),
                        session.ended_at.isoformat() if session.ended_at else None,
                        session.title,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"session {session.session_id!r} already exists") from exc

    def end_session(self, session_id: str, ended_at: datetime) -> None:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE session SET ended_at = ? WHERE session_id = ?",
                (ended_at.isoformat(), session_id),
            )
        if cursor.rowcount == 0:
            raise StoreError(f"unknown session {session_id!r}")

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute(
            "SELECT session_id, started_at, ended_at, title FROM session WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else _session(row)

    def list_sessions(self, limit: int = 20) -> list[Session]:
        rows = self._conn.execute(
            "SELECT session_id, started_at, ended_at, title FROM session"
            " ORDER BY started_at DESC, session_id DESC LIMIT ?",
            (max(limit, 0),),
        ).fetchall()
        return [_session(row) for row in rows]

    def append_line(self, line: Line) -> Line:
        try:
            cursor = self._insert_line(line)
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"unknown session {line.session_id!r}") from exc
        if cursor.lastrowid is None:  # pragma: no cover - sqlite always reports it on INSERT
            raise StoreError("sqlite did not report a row id for the inserted line")
        return replace(line, line_id=cursor.lastrowid)

    def _insert_line(self, line: Line) -> sqlite3.Cursor:
        with self._conn:
            return self._conn.execute(
                "INSERT INTO line (session_id, stream, start_ms, end_ms, text, engine, model)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    line.session_id,
                    line.stream,
                    line.start_ms,
                    line.end_ms,
                    line.text,
                    line.engine,
                    line.model,
                ),
            )

    def lines(self, session_id: str) -> list[Line]:
        rows = self._conn.execute(
            "SELECT line_id, session_id, stream, start_ms, end_ms, text, engine, model"
            " FROM line WHERE session_id = ? ORDER BY start_ms, line_id",
            (session_id,),
        ).fetchall()
        return [_line(row) for row in rows]

    def line_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM line WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row[0])

    def close(self) -> None:
        self._conn.close()


def _session(row: sqlite3.Row) -> Session:
    ended_at = row["ended_at"]
    return Session(
        session_id=str(row["session_id"]),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        ended_at=datetime.fromisoformat(str(ended_at)) if ended_at else None,
        title=str(row["title"]),
    )


def _line(row: sqlite3.Row) -> Line:
    return Line(
        line_id=int(row["line_id"]),
        session_id=str(row["session_id"]),
        stream=str(row["stream"]),
        start_ms=int(row["start_ms"]),
        end_ms=int(row["end_ms"]),
        text=str(row["text"]),
        engine=str(row["engine"]),
        model=str(row["model"]),
    )
