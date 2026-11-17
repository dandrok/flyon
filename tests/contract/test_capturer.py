"""One capture contract, two implementations — the port as a tested seam.

A scripted fake and the real `parec` adapter (driven by a fake process) are held to the same rules.
If a third source — `pw-record` directly, a WAV file, a test fixture — ever arrives, it joins this
parametrization and inherits the whole check list.
"""

from __future__ import annotations

import struct

import pytest

from flyon.adapters.capture.fake import FakeCapturer
from flyon.adapters.capture.parec import ParecCapturer
from flyon.domain.pcm import FRAME_MS
from flyon.domain.segment import MIC, STREAMS, SYSTEM
from flyon.ports.capturer import Capturer, CapturerError

SCRIPT: tuple[tuple[str, float], ...] = (
    (MIC, 0.0),
    (MIC, 0.5),
    (SYSTEM, 0.0),
    (SYSTEM, 0.4),
    (MIC, 0.0),
)


class FakeProcess:
    def __init__(self, data: bytes = b"") -> None:
        import io

        self.stdout = io.BytesIO(data)
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def silence_frames(count: int) -> bytes:
    return struct.pack(f"<{320 * count}h", *([0] * 320 * count))


@pytest.fixture(params=["fake", "parec"])
def capturer(request: pytest.FixtureRequest) -> Capturer:
    if request.param == "fake":
        return FakeCapturer(SCRIPT)
    return ParecCapturer(
        {MIC: "@DEFAULT_SOURCE@", SYSTEM: "sink.monitor"},
        spawn=lambda argv: FakeProcess(silence_frames(3)),
    )


def test_every_frame_names_a_real_stream_with_a_level_in_range(capturer: Capturer) -> None:
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()
    assert frames, "a capturer that yields nothing is not a capturer"
    for frame in frames:
        assert frame.stream in STREAMS
        assert 0.0 <= frame.level <= 1.0
        assert frame.frame_ms == FRAME_MS


def test_offsets_advance_by_one_frame_per_stream(capturer: Capturer) -> None:
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()
    by_stream: dict[str, list[int]] = {}
    for frame in frames:
        by_stream.setdefault(frame.stream, []).append(frame.at_ms)
    for stream, offsets in by_stream.items():
        assert offsets == [index * FRAME_MS for index in range(len(offsets))], stream


def test_iteration_ends_when_capture_ends(capturer: Capturer) -> None:
    # no islice here on purpose: a capturer that never finishes would hang the suite, and that is
    # exactly the failure worth catching.
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()
    assert len(frames) < 1_000


def test_starting_twice_is_refused(capturer: Capturer) -> None:
    capturer.start()
    with pytest.raises(CapturerError):
        capturer.start()
    capturer.stop()


def test_stop_is_safe_to_call_twice(capturer: Capturer) -> None:
    capturer.start()
    list(capturer.frames())
    capturer.stop()
    capturer.stop()


def test_frames_before_start_is_refused(capturer: Capturer) -> None:
    with pytest.raises(CapturerError):
        list(capturer.frames())


def test_one_capturer_reaches_both_streams(capturer: Capturer) -> None:
    capturer.start()
    streams = {frame.stream for frame in capturer.frames()}
    capturer.stop()
    assert streams == {MIC, SYSTEM}
