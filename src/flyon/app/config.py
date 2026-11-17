"""Configuration: defaults from `platformdirs`, overrides from `config.toml` and the CLI.

TOML is read with `tomllib` and validated by pydantic models, so a typo in a threshold fails with a
field name instead of surfacing as strange segments three meetings later.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_cache_dir, user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from flyon.domain.segment import SegmenterConfig

APP_NAME = "flyon"


class SettingsError(RuntimeError):
    """Raised when configuration cannot be read or validated."""


class SegmenterSettings(BaseModel):
    """Thresholds for `flyon.domain.segment.Segmenter`, overridable per install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    voice_threshold: float = Field(default=0.02, gt=0.0, le=1.0)
    silence_ms: int = Field(default=800, gt=0)
    max_segment_ms: int = Field(default=15_000, ge=1_000)
    min_segment_ms: int = Field(default=250, ge=0)
    frame_ms: int = Field(default=20, gt=0)

    def to_domain(self) -> SegmenterConfig:
        return SegmenterConfig(
            voice_threshold=self.voice_threshold,
            silence_ms=self.silence_ms,
            max_segment_ms=self.max_segment_ms,
            min_segment_ms=self.min_segment_ms,
            frame_ms=self.frame_ms,
        )


class OutputSettings(BaseModel):
    """Where notes may be copied in addition to the state directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    extra_copy: str = ""

    def extra_copy_path(self) -> Path | None:
        return Path(self.extra_copy).expanduser() if self.extra_copy else None


class Settings(BaseModel):
    """Everything a command needs to know about this install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: Literal["sqlite", "jsonl"] = "sqlite"
    engine: str = "faster-whisper"
    model: str = "large-v3-turbo"
    language: str = ""
    data_dir: Path
    cache_dir: Path
    config_path: Path
    config_found: bool = False
    output: OutputSettings = OutputSettings()
    segmenter: SegmenterSettings = SegmenterSettings()

    def database_path(self) -> Path:
        return self.data_dir / "flyon.db"


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False))


def default_cache_dir() -> Path:
    return Path(user_cache_dir(APP_NAME, appauthor=False))


def default_config_path() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False)) / "config.toml"


def load_settings(
    *,
    config: Path | None = None,
    data_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> Settings:
    """Read the TOML config (if any) and apply CLI overrides on top.

    Precedence: CLI flag, then `config.toml`, then the `platformdirs` default.
    """
    path = (config or default_config_path()).expanduser()
    raw: dict[str, object] = {}
    if path.is_file():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise SettingsError(f"cannot read {path}: {exc}") from exc
    elif config is not None:
        raise SettingsError(f"no such config file: {path}")

    resolved_data = _resolve_dir(data_dir, raw.get("data_dir"), default_data_dir)
    resolved_cache = _resolve_dir(cache_dir, raw.get("cache_dir"), default_cache_dir)

    try:
        return Settings(
            store=str(raw.get("store", "sqlite")),  # type: ignore[arg-type]
            engine=str(raw.get("engine", "faster-whisper")),
            model=str(raw.get("model", "large-v3-turbo")),
            language=str(raw.get("language", "")),
            data_dir=resolved_data,
            cache_dir=resolved_cache,
            config_path=path,
            config_found=path.is_file(),
            output=OutputSettings.model_validate(raw.get("output") or {}),
            segmenter=SegmenterSettings.model_validate(raw.get("segmenter") or {}),
        )
    except ValidationError as exc:
        raise SettingsError(f"invalid configuration in {path}: {exc}") from exc


def write_default_config(settings: Settings, *, force: bool = False) -> Path:
    """Write a commented default `config.toml`; refuse to overwrite unless `force`."""
    if settings.config_path.exists() and not force:
        raise SettingsError(f"{settings.config_path} already exists")
    settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    return settings.config_path


DEFAULT_CONFIG_TEXT = """\
# flyon configuration. Every key below is optional; these are the defaults.
store = "sqlite"           # sqlite (queryable) or jsonl (plain append-only files)
engine = "faster-whisper"
model = "large-v3-turbo"
language = ""              # empty = autodetect

[segmenter]
voice_threshold = 0.02     # RMS level that counts as speech
silence_ms = 800           # this much silence closes a segment
max_segment_ms = 15000     # a monologue is cut here and continues as the next segment
min_segment_ms = 250       # shorter than this is noise, not speech

[output]
extra_copy = ""            # e.g. "~/Documents/obsidian-root/Meetings"
"""


def _resolve_dir(explicit: Path | None, from_config: object, fallback: object) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    if isinstance(from_config, str) and from_config:
        return Path(from_config).expanduser()
    if not callable(fallback):  # pragma: no cover - internal misuse
        raise SettingsError("internal: fallback must be callable")
    return fallback()


def is_writable(directory: Path) -> bool:
    """Create the directory and prove a file can be written there."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".flyon-probe-{os.getpid()}"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True
