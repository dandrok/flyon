"""The WAV capturer: a fixture replayed as the microphone, so the loop needs no sound card."""

from __future__ import annotations

import wave
from itertools import pairwise
from pathlib import Path

import pytest

from flyon.adapters.capture.wav import WavCapturer
from flyon.domain.pcm import FRAME_MS
from flyon.domain.segment import MIC, SYSTEM
from flyon.ports.capturer import CapturerError

FIXTURE = Path(__file__).parent.parent / "fixtures" / "speech" / "start-with-the-migration.16k.wav"


def write_wav(path: Path, *, rate: int = 16_000, channels: int = 1, frames: int = 3_200) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x10" * frames * channels)
    return path


def test_a_fixture_becomes_frames_with_real_levels() -> None:
    # AC-51: the point of the adapter — known audio, measurable levels, no device
    capturer = WavCapturer(FIXTURE)
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()

    assert frames, "a 2.3 s fixture must produce frames"
    assert max(frame.level for frame in frames) > 0.02
    assert {frame.stream for frame in frames} == {MIC, SYSTEM}


def test_the_system_stream_is_silence() -> None:
    # AC-51: a fixture is one voice; inventing the other side would make the test a lie
    capturer = WavCapturer(FIXTURE)
    capturer.start()
    system = [frame for frame in capturer.frames() if frame.stream == SYSTEM]
    capturer.stop()

    assert system and all(frame.level == 0.0 for frame in system)


def test_both_streams_share_the_timeline() -> None:
    # AC-30 applies to every capturer: offsets advance by exactly one frame
    capturer = WavCapturer(FIXTURE)
    capturer.start()
    frames = list(capturer.frames())
    capturer.stop()

    for stream in (MIC, SYSTEM):
        offsets = [frame.at_ms for frame in frames if frame.stream == stream]
        assert offsets[:3] == [0, FRAME_MS, 2 * FRAME_MS]
        assert all(later - earlier == FRAME_MS for earlier, later in pairwise(offsets))


def test_a_partial_last_frame_is_padded_not_dropped() -> None:
    # AC-51: 10 ms of audio is not a reason to raise
    path = write_wav(Path("/workspace/flyon/.tmp-short.wav"), frames=160)
    capturer = WavCapturer(path)
    capturer.start()
    frames = [frame for frame in capturer.frames() if frame.stream == MIC]
    capturer.stop()
    path.unlink()

    assert len(frames) == 1
    assert len(frames[0].pcm) == 640


def test_the_wrong_format_names_the_ffmpeg_command(tmp_path: Path) -> None:
    # AC-51: a wrong WAV is a one-line conversion, not a mystery
    path = write_wav(tmp_path / "48k.wav", rate=48_000)
    capturer = WavCapturer(path)

    with pytest.raises(CapturerError, match="ffmpeg"):
        capturer.start()


def test_a_missing_file_fails_at_start_rather_than_mid_meeting(tmp_path: Path) -> None:
    # AC-51
    with pytest.raises(CapturerError, match="cannot read"):
        WavCapturer(tmp_path / "ghost.wav").start()


def test_starting_twice_is_an_error_and_stop_is_not(tmp_path: Path) -> None:
    # AC-31 applies to every capturer
    capturer = WavCapturer(write_wav(tmp_path / "ok.wav", frames=320))
    capturer.start()
    with pytest.raises(CapturerError, match="already started"):
        capturer.start()
    capturer.stop()
    capturer.stop()
