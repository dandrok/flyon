"""The store contract: sessions and an append-only transcript per session."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from flyon.domain.transcript import Line, Session


class StoreError(RuntimeError):
    """Raised when a store cannot satisfy a request, e.g. an unknown session."""


@runtime_checkable
class Store(Protocol):
    """Everything the CLI needs from a storage backend.

    Implementations must be interchangeable: `tests/contract/test_store.py` runs the same
    criteria against every adapter, so a new backend either satisfies all of them or fails loudly.
    """

    def create_session(self, session: Session) -> None:
        """Persist a new session. A duplicate id raises `StoreError`."""
        ...

    def end_session(self, session_id: str, ended_at: datetime) -> None:
        """Close an open session. An unknown session raises `StoreError`."""
        ...

    def get_session(self, session_id: str) -> Session | None:
        """Return the session, or `None` when it does not exist."""
        ...

    def list_sessions(self, limit: int = 20) -> list[Session]:
        """Sessions newest first, at most `limit` of them."""
        ...

    def append_line(self, line: Line) -> Line:
        """Append one line and return it with the store-assigned `line_id`."""
        ...

    def lines(self, session_id: str) -> list[Line]:
        """Every line of a session in start order; empty for an unknown session."""
        ...

    def line_count(self, session_id: str) -> int:
        """How many lines a session has."""
        ...

    def close(self) -> None:
        """Release resources. Idempotent."""
        ...
