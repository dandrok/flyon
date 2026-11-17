"""One contract, every store adapter — AC-11 … AC-17 of spec.md.

Parametrized over both adapters on purpose: a port with a single implementation and no
shared test is a claim, not a design.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from flyon.adapters.store.jsonl import JsonlStore
from flyon.adapters.store.sqlite import SqliteStore
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Session
from flyon.ports.store import Store, StoreError

START = datetime(2026, 11, 17, 10, 4, tzinfo=UTC)


@pytest.fixture(params=["sqlite", "jsonl"])
def make_store(request: pytest.FixtureRequest, tmp_path: Path) -> Callable[[], Store]:
    path = tmp_path / ("flyon.db" if request.param == "sqlite" else "state")

    def factory() -> Store:
        store: Store = SqliteStore(path) if request.param == "sqlite" else JsonlStore(path)
        return store

    return factory


@pytest.fixture()
def store(make_store: Callable[[], Store]) -> Store:
    made = make_store()
    yield made
    made.close()


def session(session_id: str = "s1", *, minutes: int = 0, title: str = "weekly sync") -> Session:
    return Session(
        session_id=session_id, started_at=START + timedelta(minutes=minutes), title=title
    )


def line(start_ms: int, *, text: str = "hello", stream: str = MIC, session_id: str = "s1") -> Line:
    return Line(
        session_id=session_id,
        stream=stream,
        start_ms=start_ms,
        end_ms=start_ms + 400,
        text=text,
    )


def test_creating_then_reading_a_session_returns_the_same_record(store: Store) -> None:
    # AC-12
    store.create_session(session())
    stored = store.get_session("s1")
    assert stored is not None
    assert stored.session_id == "s1"
    assert stored.started_at == START
    assert stored.title == "weekly sync"
    assert stored.ended_at is None


def test_a_duplicate_session_id_is_refused(store: Store) -> None:
    store.create_session(session())
    with pytest.raises(StoreError):
        store.create_session(session())


def test_a_session_can_be_ended_and_ending_an_unknown_one_raises(store: Store) -> None:
    # AC-13
    store.create_session(session())
    store.end_session("s1", START + timedelta(minutes=12))
    stored = store.get_session("s1")
    assert stored is not None
    assert not stored.is_open
    assert stored.duration_ms == 12 * 60 * 1000
    with pytest.raises(StoreError):
        store.end_session("nope", START)


def test_lines_come_back_in_start_order_with_increasing_ids(store: Store) -> None:
    # AC-14
    store.create_session(session())
    first = store.append_line(line(0, text="first"))
    second = store.append_line(line(600, text="second"))
    assert first.line_id is not None
    assert second.line_id is not None
    assert second.line_id > first.line_id
    assert [stored.text for stored in store.lines("s1")] == ["first", "second"]


def test_lines_from_both_streams_are_kept_with_their_stream(store: Store) -> None:
    store.create_session(session())
    store.append_line(line(0, stream=MIC, text="local"))
    store.append_line(line(0, stream=SYSTEM, text="remote"))
    assert {stored.stream for stored in store.lines("s1")} == {MIC, SYSTEM}


def test_line_count_matches_the_lines(store: Store) -> None:
    store.create_session(session())
    assert store.line_count("s1") == 0
    store.append_line(line(0))
    store.append_line(line(1_000))
    assert store.line_count("s1") == 2


def test_appending_to_an_unknown_session_is_refused(store: Store) -> None:
    with pytest.raises(StoreError):
        store.append_line(line(0, session_id="ghost"))


def test_sessions_list_newest_first_and_respect_the_limit(store: Store) -> None:
    # AC-15
    store.create_session(session("old", minutes=0))
    store.create_session(session("new", minutes=30))
    store.create_session(session("middle", minutes=15))
    assert [s.session_id for s in store.list_sessions()] == ["new", "middle", "old"]
    assert [s.session_id for s in store.list_sessions(limit=2)] == ["new", "middle"]
    assert store.list_sessions(limit=0) == []


def test_an_unknown_session_is_a_none_and_its_lines_are_empty(store: Store) -> None:
    # AC-17
    assert store.get_session("ghost") is None
    assert store.lines("ghost") == []


def test_data_survives_reopening(make_store: Callable[[], Store]) -> None:
    # AC-16
    first = make_store()
    first.create_session(session())
    first.append_line(line(0, text="still here"))
    first.end_session("s1", START + timedelta(minutes=3))
    first.close()

    second = make_store()
    try:
        stored = second.get_session("s1")
        assert stored is not None
        assert stored.duration_ms == 3 * 60 * 1000
        assert [line.text for line in second.lines("s1")] == ["still here"]
        assert second.line_count("s1") == 1
    finally:
        second.close()
