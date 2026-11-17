"""`flyon doctor`: prove the machine can transcribe, or say exactly what is missing.

One row per check. A missing optional piece (the STT extra, a capture tool, a downloaded model) is a
warning: the read commands work without it. A failure is something no command can work around.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from flyon.adapters.stt.faster_whisper import MODEL_DOWNLOAD_SIZES
from flyon.app.config import Settings, is_writable
from flyon.domain.segment import STREAMS
from flyon.ports.capturer import Capturer, CapturerError
from flyon.ports.store import StoreError

Status = Literal["ok", "warn", "fail"]
STYLE: dict[Status, str] = {"ok": "green", "warn": "yellow", "fail": "red"}
MARK: dict[Status, str] = {"ok": "ok", "warn": "warn", "fail": "FAIL"}
MIN_PYTHON: tuple[int, int] = (3, 14)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: Status
    detail: str


def run_checks(settings: Settings) -> list[Check]:
    checks = [
        _check_python(),
        _check_dir("data dir", settings.data_dir),
        _check_dir("cache dir", settings.cache_dir),
        _check_config(settings),
        _check_store(settings),
        _check_module("stt extra", "faster_whisper", "uv tool install 'flyon[stt]'"),
        _check_capture(),
        _check_models(settings),
    ]
    return checks


def probe_capture(
    *,
    seconds: float = 2.0,
    capturer: Capturer | None = None,
    make_capturer: Callable[[], Capturer] | None = None,
) -> list[Check]:
    """Record for `seconds` and report what each stream actually delivered.

    `flyon doctor --probe` is the only honest answer to "will this work in the meeting", so it is a
    real capture rather than a PATH lookup: frames per stream, and the peak level seen.
    """
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    machine = capturer if capturer is not None else (make_capturer or _real_capturer)()
    frames: dict[str, int] = {}
    peaks: dict[str, float] = {}

    def drain() -> None:
        try:
            for frame in machine.frames():
                frames[frame.stream] = frames.get(frame.stream, 0) + 1
                peaks[frame.stream] = max(peaks.get(frame.stream, 0.0), frame.level)
        except CapturerError:  # a dying child is reported as a short count
            return

    try:
        machine.start()
    except CapturerError as exc:
        return [Check("probe", "fail", str(exc))]
    worker = threading.Thread(target=drain, name="flyon-probe", daemon=True)
    worker.start()
    try:
        time.sleep(seconds)
    finally:
        machine.stop()
        worker.join(timeout=5.0)

    checks: list[Check] = []
    for stream in sorted(STREAMS):
        count = frames.get(stream, 0)
        peak = peaks.get(stream, 0.0)
        if count == 0:
            checks.append(
                Check(f"probe {stream}", "warn", "no frames — is that source muted or suspended?")
            )
        else:
            expected = int(seconds * 1000 / 20)
            health = "ok" if count >= expected * 0.5 else "warn"
            checks.append(
                Check(
                    f"probe {stream}",
                    health,
                    f"{count} frames in {seconds:g}s (expect ~{expected}), peak {peak:.3f}",
                )
            )
    if not frames:
        checks.append(Check("probe", "fail", "the capturer produced nothing at all"))
    return checks


def _real_capturer() -> Capturer:
    from flyon.adapters.capture.parec import ParecCapturer, default_streams

    return ParecCapturer(default_streams())


def worst_status(checks: list[Check]) -> Status:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warn" for check in checks):
        return "warn"
    return "ok"


def print_checks(console: Console, checks: list[Check]) -> None:
    table = Table(box=None, pad_edge=False, show_edge=False, header_style="bold")
    table.add_column("", no_wrap=True)
    table.add_column("CHECK", no_wrap=True)
    table.add_column("DETAIL")
    for check in checks:
        style = STYLE[check.status]
        table.add_row(f"[{style}]{MARK[check.status]}[/{style}]", check.name, escape(check.detail))
    console.print(table)


def _check_python() -> Check:
    current = sys.version_info[:2]
    ok = current >= MIN_PYTHON
    return Check(
        "python",
        "ok" if ok else "fail",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        + ("" if ok else f" — flyon needs {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"),
    )


def _check_dir(name: str, directory: Path) -> Check:
    path = str(directory)
    writable = is_writable(directory)
    return Check(
        name, "ok" if writable else "fail", path if writable else f"{path} is not writable"
    )


def _check_config(settings: Settings) -> Check:
    if not settings.config_found:
        return Check("config", "ok", f"{settings.config_path} (absent — built-in defaults)")
    return Check("config", "ok", str(settings.config_path))


def _check_store(settings: Settings) -> Check:
    from flyon.app.wiring import open_store, store_location

    path = store_location(settings)
    try:
        store = open_store(settings)
        try:
            sessions = len(store.list_sessions(limit=1))
        finally:
            store.close()
    except (OSError, sqlite3.Error, StoreError) as exc:
        return Check("store", "fail", f"{path}: {exc}")
    return Check("store", "ok", f"{settings.store} · {path} · {sessions} session(s) seen")


def _check_module(name: str, module: str, hint: str) -> Check:
    if importlib.util.find_spec(module) is not None:
        return Check(name, "ok", f"{module} importable")
    return Check(name, "warn", f"{module} missing — {hint}")


def _check_capture() -> Check:
    found = [tool for tool in ("pw-record", "parec") if shutil.which(tool)]
    if found:
        return Check("capture", "ok", f"{found[0]} on PATH")
    return Check(
        "capture",
        "warn",
        "neither pw-record nor parec on PATH — live capture needs pipewire or pulseaudio",
    )


def _check_models(settings: Settings) -> Check:
    size = MODEL_DOWNLOAD_SIZES.get(settings.model)
    download = f"~{size}" if size else "size unknown until it downloads"
    hint = f"no model cached yet — first run downloads {settings.model} ({download})"
    cached = settings.cache_dir.is_dir() and any(settings.cache_dir.iterdir())
    if cached:
        return Check("models", "ok", f"{settings.cache_dir} has cached models")
    return Check("models", "warn", hint)


STREAMS_TEXT = ", ".join(STREAMS)
