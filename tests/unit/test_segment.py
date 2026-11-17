"""Segmenter rules — acceptance criteria AC-1 … AC-7 of spec.md."""

from __future__ import annotations

import pytest

from flyon.domain.segment import MIC, SYSTEM, Segment, Segmenter, SegmenterConfig

VOICE = 0.5
QUIET = 0.0


def feed(
    segmenter: Segmenter, *, voice_frames: int = 0, quiet_frames: int = 0, frame_ms: int = 20
) -> list[Segment]:
    closed: list[Segment] = []
    for _ in range(voice_frames):
        closed.extend(segmenter.push(VOICE, frame_ms))
    for _ in range(quiet_frames):
        closed.extend(segmenter.push(QUIET, frame_ms))
    return closed


def test_a_voiced_frame_opens_a_segment_and_silence_short_of_the_gap_does_not_close_it() -> None:
    segmenter = Segmenter(MIC)
    assert feed(segmenter, voice_frames=10) == []
    assert segmenter.is_open
    assert feed(segmenter, quiet_frames=39) == []  # 780 ms, just under silence_ms


def test_silence_of_silence_ms_closes_the_segment_at_the_last_voiced_frame() -> None:
    segmenter = Segmenter(MIC)
    closed = feed(segmenter, voice_frames=20)  # 400 ms, above min_segment_ms
    closed += feed(segmenter, quiet_frames=40)
    assert closed == [Segment(MIC, 0, 400)]
    assert not segmenter.is_open


def test_trailing_silence_never_appears_in_the_end_timestamp() -> None:
    # AC-3: one second of speech, 800 ms of silence -> end at 1000, not 1800
    segmenter = Segmenter(MIC)
    closed = feed(segmenter, voice_frames=50)
    closed += feed(segmenter, quiet_frames=40)
    assert closed == [Segment(MIC, 0, 1000)]


def test_a_gap_shorter_than_silence_ms_does_not_split_a_sentence() -> None:
    # AC-2: 200 ms voice, 400 ms pause, 200 ms voice, 800 ms silence -> one segment
    segmenter = Segmenter(MIC)
    closed = feed(segmenter, voice_frames=10)
    closed += feed(segmenter, quiet_frames=20)
    closed += feed(segmenter, voice_frames=10)
    closed += feed(segmenter, quiet_frames=40)
    assert closed == [Segment(MIC, 0, 800)]


def test_a_blip_shorter_than_min_segment_ms_is_dropped() -> None:
    # AC-4: 100 ms of voice is a door, not speech
    segmenter = Segmenter(MIC)
    closed = feed(segmenter, voice_frames=5) + feed(segmenter, quiet_frames=40)
    assert closed == []


def test_a_monologue_is_cut_at_max_segment_ms_and_continues() -> None:
    # AC-5: 30 s of unbroken voice -> two 15 s segments, nothing lost
    segmenter = Segmenter(SYSTEM)
    closed = feed(segmenter, voice_frames=1500)
    assert closed == [Segment(SYSTEM, 0, 15_000), Segment(SYSTEM, 15_000, 30_000)]
    assert not segmenter.is_open  # the cut landed exactly on the last frame
    segmenter.push(VOICE)  # one more frame is a fresh segment, not a lost tail
    assert segmenter.is_open


def test_the_cap_is_configurable_without_touching_the_code() -> None:
    segmenter = Segmenter(MIC, SegmenterConfig(max_segment_ms=1_000))
    closed = feed(segmenter, voice_frames=100)
    assert closed == [Segment(MIC, 0, 1_000), Segment(MIC, 1_000, 2_000)]


def test_flush_closes_an_open_segment() -> None:
    # AC-6: stopping mid-sentence keeps the tail
    segmenter = Segmenter(MIC)
    feed(segmenter, voice_frames=20)
    assert segmenter.flush() == (Segment(MIC, 0, 400),)
    assert segmenter.flush() == ()


def test_flush_is_a_no_op_when_nothing_is_open() -> None:
    assert Segmenter(MIC).flush() == ()


def test_the_threshold_is_inclusive() -> None:
    # AC-1: level exactly at the threshold counts as speech
    config = SegmenterConfig(voice_threshold=0.02)
    segmenter = Segmenter(MIC, config)
    for _ in range(20):
        segmenter.push(config.voice_threshold)
    assert segmenter.flush() == (Segment(MIC, 0, 400),)


def test_a_segment_rejects_an_unknown_stream() -> None:
    # AC-7
    with pytest.raises(ValueError, match="unknown stream"):
        Segment("speaker_3", 0, 100)


def test_the_end_of_a_segment_cannot_precede_its_start() -> None:
    with pytest.raises(ValueError, match="before start_ms"):
        Segment(MIC, 500, 100)


def test_segmenters_carry_their_own_stream_and_do_not_share_state() -> None:
    mic, system = Segmenter(MIC), Segmenter(SYSTEM)
    feed(mic, voice_frames=20)
    feed(system, voice_frames=20)
    assert mic.flush() == (Segment(MIC, 0, 400),)
    assert system.flush() == (Segment(SYSTEM, 0, 400),)


def test_an_unknown_stream_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown stream"):
        Segmenter("speaker_3")
