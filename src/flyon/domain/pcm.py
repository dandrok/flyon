"""PCM arithmetic: how loud is this frame, and where do frames end.

Pure functions over raw `s16le` bytes. The operating system hands us a byte stream; the segmenter
wants one level per 20 ms frame. Everything in between is arithmetic, so it is tested without a
microphone: `tests/unit/test_pcm.py` feeds synthetic samples.
"""

from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass, field

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # s16le, mono: what `parec` and the transcriber both want
FRAME_MS = 20
FULL_SCALE = 32_768.0


def bytes_per_frame(
    frame_ms: int = FRAME_MS, sample_rate: int = SAMPLE_RATE, sample_width: int = SAMPLE_WIDTH
) -> int:
    """How many bytes one frame of this shape occupies."""
    if frame_ms <= 0 or sample_rate <= 0 or sample_width <= 0:
        raise ValueError("frame_ms, sample_rate and sample_width must be positive")
    return sample_rate * frame_ms // 1000 * sample_width


def rms_level(pcm: bytes) -> float:
    """Root-mean-square level of a chunk, normalised to 0.0 … 1.0.

    Silence is 0.0 and a full-scale square wave is 1.0. An odd trailing byte is ignored rather than
    crashing: the reader splits chunks arbitrarily and a frame boundary mid-sample is normal.
    """
    usable = len(pcm) - len(pcm) % SAMPLE_WIDTH
    if usable <= 0:
        return 0.0
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0.0
    total = 0
    for sample in samples:
        total += sample * sample
    level = math.sqrt(total / len(samples)) / FULL_SCALE
    return min(level, 1.0)


@dataclass
class PcmFramer:
    """Accumulates arbitrary byte chunks and emits one level per complete frame.

    A partial frame is kept, not dropped: audio arrives in whatever sizes the pipe feels like, and a
    300-byte read is half a frame, not a reason to lose it. The tail shorter than one frame is never
    emitted — under 20 ms of audio is not worth a transcription call.
    """

    frame_ms: int = FRAME_MS
    sample_rate: int = SAMPLE_RATE
    sample_width: int = SAMPLE_WIDTH
    _buffer: bytearray = field(default_factory=bytearray, repr=False)

    @property
    def frame_bytes(self) -> int:
        return bytes_per_frame(self.frame_ms, self.sample_rate, self.sample_width)

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[tuple[float, bytes]]:
        """Add bytes; return `(level, frame bytes)` for every frame this chunk completed.

        The bytes come back with the level because a segment cannot be transcribed from a number:
        the caller needs the audio that the number described, cut on exactly the same boundary.
        """
        if not chunk:
            return []
        self._buffer.extend(chunk)
        size = self.frame_bytes
        frames: list[tuple[float, bytes]] = []
        while len(self._buffer) >= size:
            raw = bytes(self._buffer[:size])
            frames.append((rms_level(raw), raw))
            del self._buffer[:size]
        return frames
