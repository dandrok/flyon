"""The parec adapter: command shape, source discovery, and pumps driven by a fake process."""

from __future__ import annotations

import io
import struct

import pytest

from flyon.adapters.capture.parec import ParecCapturer, default_streams, monitor_name, parec_argv
from flyon.domain.segment import MIC, SYSTEM
from flyon.ports.capturer import CapturerError, Frame


def pcm(samples: int, amplitude: float = 0.0) -> bytes:
    value = int(amplitude * 32767)
    return struct.pack(f"<{samples}h", *([value] * samples))


class FakeProcess:
    """Quacks like the sliver of `Popen` a pump touches."""

    def __init__(self, data: bytes) -> None:
        self.stdout = io.BytesIO(data)
        self.terminated = False
        self.waited = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0


def test_the_command_asks_for_exactly_the_bytes_the_framer_expects() -> None:
    argv = parec_argv("@DEFAULT_SOURCE@")
    assert argv[0] == "parec"
    assert "--format=s16le" in argv
    assert "--rate=16000" in argv
    assert "--channels=1" in argv
    assert "--latency-msec=20" in argv
    assert "--device=@DEFAULT_SOURCE@" in argv


def test_a_monitor_name_is_added_once() -> None:
    assert monitor_name("alsa_output.x.analog-stereo") == "alsa_output.x.analog-stereo.monitor"
    assert monitor_name("alsa_output.x.analog-stereo.monitor") == (
        "alsa_output.x.analog-stereo.monitor"
    )
    with pytest.raises(ValueError, match="must not be empty"):
        monitor_name("")


def test_the_system_stream_is_the_monitor_of_the_default_sink() -> None:
    streams = default_streams(run=lambda cmd: "alsa_output.pci-0000_00.analog-stereo\n")
    assert streams[MIC] == "@DEFAULT_SOURCE@"
    assert streams[SYSTEM] == "alsa_output.pci-0000_00.analog-stereo.monitor"


def test_a_missing_pactl_falls_back_instead_of_exploding() -> None:
    def broken(cmd: list[str]) -> str:
        raise FileNotFoundError("pactl")

    streams = default_streams(run=broken)  # type: ignore[arg-type]
    assert streams[MIC] == "@DEFAULT_SOURCE@"
    assert streams[SYSTEM].endswith(".monitor")


def test_a_pump_turns_bytes_into_frames_on_the_shared_clock() -> None:
    # two frames of silence, then one at half scale
    data = pcm(320) + pcm(320) + pcm(320, 0.5)
    capturer = ParecCapturer({MIC: "@DEFAULT_SOURCE@"}, spawn=lambda argv: FakeProcess(data))
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()
    assert [frame.at_ms for frame in frames] == [0, 20, 40]
    assert [round(frame.level, 2) for frame in frames] == [0.0, 0.0, 0.5]
    assert all(frame.stream == MIC for frame in frames)


def test_two_streams_interleave_through_one_queue() -> None:
    def spawn(argv: list[str]) -> FakeProcess:
        amplitude = 0.0 if any("SOURCE" in arg for arg in argv) else 0.5
        return FakeProcess(pcm(320, amplitude))

    capturer = ParecCapturer({MIC: "@DEFAULT_SOURCE@", SYSTEM: "x.monitor"}, spawn=spawn)
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()
    assert {frame.stream for frame in frames} == {MIC, SYSTEM}
    system = [frame for frame in frames if frame.stream == SYSTEM]
    assert round(system[0].level, 2) == 0.5


def test_starting_twice_is_refused() -> None:
    capturer = ParecCapturer({MIC: "x"}, spawn=lambda argv: FakeProcess(b""))
    capturer.start()
    with pytest.raises(CapturerError, match="already started"):
        capturer.start()
    capturer.stop()


def test_frames_before_start_is_refused() -> None:
    capturer = ParecCapturer({MIC: "x"}, spawn=lambda argv: FakeProcess(b""))
    with pytest.raises(CapturerError, match="start"):
        list(capturer.frames())


def test_frames_cannot_be_consumed_twice() -> None:
    capturer = ParecCapturer({MIC: "x"}, spawn=lambda argv: FakeProcess(pcm(320)))
    capturer.start()
    list(capturer.frames())
    with pytest.raises(CapturerError, match="twice"):
        list(capturer.frames())
    capturer.stop()


def test_stop_is_idempotent_and_terminates_every_child() -> None:
    made: list[FakeProcess] = []

    def spawn(argv: list[str]) -> FakeProcess:
        process = FakeProcess(b"")
        made.append(process)
        return process

    capturer = ParecCapturer({MIC: "@DEFAULT_SOURCE@", SYSTEM: "x.monitor"}, spawn=spawn)
    capturer.start()
    capturer.stop()
    capturer.stop()
    assert len(made) == 2
    assert all(process.terminated for process in made)


def test_a_failing_binary_raises_a_capture_error() -> None:
    def spawn(argv: list[str]) -> FakeProcess:
        raise OSError("parec: not found")

    capturer = ParecCapturer({MIC: "@DEFAULT_SOURCE@"}, spawn=spawn)
    with pytest.raises(CapturerError, match="cannot start parec"):
        capturer.start()


def test_an_unknown_stream_is_refused_and_a_frame_carries_its_stream() -> None:
    with pytest.raises(ValueError, match="unknown stream"):
        ParecCapturer({"speaker_3": "x"})
    with pytest.raises(ValueError, match="unknown stream"):
        Frame(stream="speaker_3", level=0.0, frame_ms=20, at_ms=0)
