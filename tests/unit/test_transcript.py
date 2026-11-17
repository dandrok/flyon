"""Line, Session, Transcript and timestamp rules — AC-8 … AC-10 of spec.md."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import (
    Line,
    OutOfOrderLine,
    Session,
    Transcript,
    format_timestamp,
    sort_lines,
)


def line(start_ms: int, text: str = "hello", stream: str = MIC, end_ms: int | None = None) -> Line:
    return Line(
        session_id="s1",
        stream=stream,
        start_ms=start_ms,
        end_ms=start_ms + 500 if end_ms is None else end_ms,
        text=text,
    )


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "00:00"),
        (999, "00:00"),
        (1_000, "00:01"),
        (59_999, "00:59"),
        (60_000, "01:00"),
        (3_599_999, "59:59"),
        (3_600_000, "1:00:00"),
        (3_723_000, "1:02:03"),
    ],
)
def test_timestamps_render_as_minutes_and_seconds(ms: int, expected: str) -> None:
    # AC-10
    assert format_timestamp(ms) == expected


def test_a_negative_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        format_timestamp(-1)


def test_a_line_rejects_an_unknown_stream_and_backwards_time() -> None:
    # AC-8
    with pytest.raises(ValueError, match="unknown stream"):
        line(0, stream="speaker_3")
    with pytest.raises(ValueError, match="before start_ms"):
        line(500, end_ms=100)


def test_a_line_exposes_its_duration_and_timestamp() -> None:
    assert line(61_000).timestamp == "01:01"
    assert line(0).duration_ms == 500


def test_a_transcript_is_append_only_and_ordered() -> None:
    # AC-9
    transcript = Transcript("s1")
    transcript.append(line(0))
    transcript.append(line(500))
    with pytest.raises(OutOfOrderLine):
        transcript.append(line(400))
    assert len(transcript) == 2


def test_a_transcript_refuses_a_line_from_another_session() -> None:
    transcript = Transcript("s1")
    stranger = Line(session_id="s2", stream=MIC, start_ms=0, end_ms=100, text="hi")
    with pytest.raises(ValueError, match="belongs to session"):
        transcript.append(stranger)


def test_a_transcript_can_be_seeded_and_rendered_as_text() -> None:
    transcript = Transcript("s1", [line(0, "first"), line(500, "second")])
    assert transcript.text() == "first\nsecond"
    assert transcript.session_id == "s1"
    assert len(transcript.lines) == 2


def test_two_streams_sort_by_start_time_with_the_microphone_first() -> None:
    system = line(0, "remote", stream=SYSTEM)
    mic = line(0, "local", stream=MIC)
    later = line(100, "later", stream=SYSTEM)
    assert sort_lines([later, system, mic]) == (mic, system, later)


def test_a_session_reports_its_duration_only_once_it_is_closed() -> None:
    started = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    open_session = Session(session_id="s1", started_at=started)
    assert open_session.is_open
    assert open_session.duration_ms is None
    closed = Session(session_id="s1", started_at=started, ended_at=started + timedelta(minutes=12))
    assert not closed.is_open
    assert closed.duration_ms == 12 * 60 * 1000
