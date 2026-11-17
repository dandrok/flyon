"""Speech-to-text adapters."""

from flyon.adapters.stt.fake import FakeTranscriber
from flyon.adapters.stt.faster_whisper import FasterWhisperTranscriber

__all__ = ["FakeTranscriber", "FasterWhisperTranscriber"]
