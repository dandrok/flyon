"""Capture adapters: where audio actually comes from."""

from flyon.adapters.capture.fake import FakeCapturer, synthesize_pcm
from flyon.adapters.capture.parec import ParecCapturer, default_streams, parec_argv

__all__ = ["FakeCapturer", "ParecCapturer", "default_streams", "parec_argv", "synthesize_pcm"]
