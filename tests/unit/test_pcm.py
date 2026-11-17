"""PCM arithmetic: levels and frame boundaries, with synthetic samples only."""

from __future__ import annotations

import struct

import pytest

from flyon.domain.pcm import PcmFramer, bytes_per_frame, rms_level

FRAME_BYTES = 640  # 20 ms of 16 kHz mono s16le


def pcm(samples: int, amplitude: float = 1.0, count: int | None = None) -> bytes:
    """`samples` frames of one constant value — a square wave at `amplitude` of full scale."""
    value = max(-32768, min(32767, int(amplitude * 32767)))
    n = samples if count is None else count
    return struct.pack(f"<{n}h", *([value] * n))


def test_a_frame_is_twenty_milliseconds_of_sixteen_kilohertz_mono() -> None:
    assert bytes_per_frame() == FRAME_BYTES
    assert bytes_per_frame(frame_ms=10) == 320
    assert bytes_per_frame(sample_rate=8_000) == 320


def test_nonsense_frame_arguments_are_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        bytes_per_frame(frame_ms=0)


def test_silence_is_zero_and_full_scale_is_one() -> None:
    assert rms_level(b"\x00" * FRAME_BYTES) == 0.0
    assert rms_level(pcm(320, 1.0)) == pytest.approx(1.0, abs=0.01)


def test_half_amplitude_is_about_half() -> None:
    assert rms_level(pcm(320, 0.5)) == pytest.approx(0.5, abs=0.01)


def test_an_empty_chunk_or_a_stray_byte_is_zero_not_a_crash() -> None:
    assert rms_level(b"") == 0.0
    assert rms_level(b"\x01") == 0.0
    assert rms_level(pcm(320, 0.5) + b"\x01") == pytest.approx(0.5, abs=0.01)


def test_the_framer_holds_a_partial_frame_instead_of_dropping_it() -> None:
    # audio arrives in whatever sizes the pipe feels like
    framer = PcmFramer()
    assert framer.feed(pcm(160, 0.5)) == []  # 320 bytes, half a frame
    assert framer.pending_bytes == 320
    levels = framer.feed(pcm(160, 0.5))
    assert levels == pytest.approx([0.5], abs=0.01)
    assert framer.pending_bytes == 0


def test_three_frames_in_one_read_produce_three_levels() -> None:
    framer = PcmFramer()
    assert len(framer.feed(pcm(320 * 3, 0.25))) == 3


def test_flush_emits_the_short_tail_and_then_nothing() -> None:
    framer = PcmFramer()
    framer.feed(pcm(100, 0.5))
    assert framer.flush() == pytest.approx([0.5], abs=0.01)
    assert framer.flush() == []


def test_the_framer_ignores_an_empty_chunk() -> None:
    assert PcmFramer().feed(b"") == []
