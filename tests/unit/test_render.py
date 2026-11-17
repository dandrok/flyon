"""The recording report: what the levels say, and what to do about them."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from flyon.cli.render import print_levels


def render(peaks: dict[str, float], *, threshold: float = 0.02, lines: int = 0) -> str:
    buffer = StringIO()
    target = Console(file=buffer, width=120, no_color=True, highlight=False)
    print_levels(target, peaks, threshold=threshold, lines=lines)
    return buffer.getvalue()


def test_the_loudest_frame_is_always_reported() -> None:
    # AC-50: "0 lines" alone is not a diagnosis
    output = render({"mic": 0.049, "system": 0.6}, lines=3)

    assert "loudest frame: mic 0.049 · system 0.600" in output


def test_a_stream_that_heard_nothing_says_so() -> None:
    # AC-50: the suspended-bluetooth case
    output = render({"mic": 0.062, "system": 0.0})

    assert "nothing arrived from system" in output
    assert "suspended bluetooth" in output


def test_a_stream_below_the_threshold_names_the_fix() -> None:
    # AC-50: the measured failure — audio arrives, voices never clear the gate
    output = render({"mic": 0.008, "system": 0.1})

    assert "mic stayed below voice_threshold" in output
    assert "lower voice_threshold" in output


def test_audio_that_cleared_the_gate_but_made_no_segment_blames_the_minimum() -> None:
    # AC-50: blips above the threshold, each shorter than min_segment_ms
    output = render({"mic": 0.05, "system": 0.2}, threshold=0.02, lines=0)

    assert "no segment formed" in output
    assert "min_segment_ms" in output


def test_a_good_recording_gets_no_warning() -> None:
    # AC-50: one dim line, no advice nobody needs
    output = render({"mic": 0.08, "system": 0.3}, lines=9)

    assert "loudest frame" in output
    assert "warning" not in output
    assert "nothing arrived" not in output
    assert "stayed below" not in output
