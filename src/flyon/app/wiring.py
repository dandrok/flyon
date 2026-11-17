"""Wiring: turn configuration into adapters.

The only module that knows which concrete class sits behind a port. Everything else asks for a
`Store`; this decides whether that is SQLite or the append-only JSONL files.
"""

from __future__ import annotations

from pathlib import Path

from flyon.adapters.capture.fake import FakeCapturer
from flyon.adapters.capture.parec import ParecCapturer, default_streams
from flyon.adapters.notes.fake import FakeNotes
from flyon.adapters.notes.ollama import OllamaNotes
from flyon.adapters.store.jsonl import JsonlStore
from flyon.adapters.store.sqlite import SqliteStore
from flyon.adapters.stt.fake import FakeTranscriber
from flyon.adapters.stt.faster_whisper import (
    FasterWhisperTranscriber,
    _import_faster_whisper,
)
from flyon.app.config import Settings
from flyon.ports.capturer import Capturer
from flyon.ports.notes import NotesProvider
from flyon.ports.store import Store
from flyon.ports.transcriber import Transcriber

__all__ = [
    "open_capturer",
    "open_notes_provider",
    "open_store",
    "open_transcriber",
    "store_location",
]


def open_store(settings: Settings) -> Store:
    if settings.store == "jsonl":
        return JsonlStore(settings.data_dir)
    return SqliteStore(settings.database_path())


def open_capturer(source: str = "parec") -> Capturer:
    """`parec` records the machine, `fake` replays a script, `wav:<file>` replays a fixture."""
    if source == "fake":
        return FakeCapturer()
    if source == "parec":
        return ParecCapturer(default_streams())
    if source.startswith("wav:"):
        path = source[len("wav:") :].strip()
        if not path:
            raise ValueError("wav: needs a file, e.g. --source wav:speech.wav")
        from flyon.adapters.capture.wav import WavCapturer

        return WavCapturer(Path(path))
    raise ValueError(f"unknown capture source {source!r}; expected 'parec', 'fake' or 'wav:<file>'")


def open_transcriber(settings: Settings, engine: str | None = None) -> Transcriber:
    """`faster-whisper` is the default; `fake` proves the pipeline without a download."""
    name = (engine or settings.engine).strip()
    if name == "fake":
        return FakeTranscriber()
    if name in {"faster-whisper", "faster_whisper", "whisper"}:
        # import now, so a missing extra is one clear error before the meeting starts rather than
        # one failed segment per sentence once it has
        _import_faster_whisper()
        return FasterWhisperTranscriber(
            settings.model,
            cache_dir=settings.cache_dir,
            language=settings.language,
        )
    raise ValueError(f"unknown engine {name!r}; expected 'faster-whisper' or 'fake'")


def open_notes_provider(settings: Settings, provider: str | None = None) -> NotesProvider:
    """`ollama` writes the minutes on this machine; `fake` proves the path without a model.

    An empty provider is a configuration choice, not a bug: the default install cannot send a
    transcript anywhere, and this error says how to opt in.
    """
    name = (provider or settings.notes.provider).strip().lower()
    if not name:
        raise ValueError(
            'no notes provider configured — set [notes] provider = "ollama" in config.toml, '
            "or pass --provider fake to see the path without a model"
        )
    if name == "fake":
        return FakeNotes()
    if name == "ollama":
        return OllamaNotes(
            settings.notes.model,
            host=settings.notes.host,
            timeout_s=settings.notes.timeout_s,
        )
    raise ValueError(f"unknown notes provider {name!r}; expected 'ollama' or 'fake'")


def store_location(settings: Settings) -> Path:
    """Where this install keeps its sessions, for `doctor` and error messages."""
    if settings.store == "jsonl":
        return settings.data_dir
    return settings.database_path()
