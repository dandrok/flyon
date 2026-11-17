"""Real audio via `parec`: the microphone and the monitor of the default sink, as two streams.

One process per stream, one pump thread per process. The thread reads raw `s16le`, the framer turns
bytes into levels, and frames go onto a queue the session loop drains. Nothing here touches the
transcript — capture and transcription are separate paces.
"""

from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import suppress
from types import TracebackType
from typing import Protocol

from flyon.domain.pcm import FRAME_MS, SAMPLE_RATE, PcmFramer, bytes_per_frame
from flyon.domain.segment import MIC, SYSTEM
from flyon.ports.capturer import CapturerError, Frame

SENTINEL = None
DEFAULT_MIC = "@DEFAULT_SOURCE@"
DEFAULT_SINK_QUERY = ["pactl", "get-default-sink"]


class SpawnedProcess(Protocol):
    """The sliver of `subprocess.Popen` a pump needs, so a test can fake it."""

    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


Spawn = Callable[[Sequence[str]], SpawnedProcess]


def parec_argv(
    device: str, *, frame_ms: int = FRAME_MS, sample_rate: int = SAMPLE_RATE, sample_width: int = 2
) -> list[str]:
    """The command that produces exactly the bytes the framer expects."""
    return [
        "parec",
        "--format=s16le",
        f"--rate={sample_rate}",
        f"--channels={sample_width // 2}",
        f"--latency-msec={frame_ms}",
        f"--device={device}",
    ]


def monitor_name(sink: str) -> str:
    """`alsa_output.pci-0000_00_1f.3.analog-stereo` -> `...analog-stereo.monitor`."""
    if not sink:
        raise ValueError("sink name must not be empty")
    return sink if sink.endswith(".monitor") else f"{sink}.monitor"


def default_streams(run: Callable[[Sequence[str]], str] | None = None) -> dict[str, str]:
    """Resolve a device per stream: the default source, and the default sink's monitor.

    A failed `pactl` call is not fatal — pipewire without pulseaudio compatibility answers nothing,
    and the caller's `doctor` already warned about that.
    """
    if run is None:

        def run(cmd: Sequence[str]) -> str:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)  # noqa: S603
            return result.stdout

    try:
        sink = run(DEFAULT_SINK_QUERY).strip().splitlines()[0]
    except OSError, subprocess.SubprocessError, IndexError:
        sink = ""
    system_device = monitor_name(sink) if sink else f"{MIC}.monitor"
    return {MIC: DEFAULT_MIC, SYSTEM: system_device}


def _default_spawn(argv: Sequence[str]) -> SpawnedProcess:
    process = subprocess.Popen(  # noqa: S603
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    return process


class ParecCapturer:
    """Two `parec` processes, two pumps, one frame queue. Satisfies `Capturer`."""

    def __init__(
        self,
        streams: Mapping[str, str],
        *,
        frame_ms: int = FRAME_MS,
        sample_rate: int = SAMPLE_RATE,
        spawn: Spawn | None = None,
        read_size: int | None = None,
    ) -> None:
        if not streams:
            raise ValueError("at least one stream is required")
        unknown = set(streams) - {MIC, SYSTEM}
        if unknown:
            raise ValueError(f"unknown stream(s): {sorted(unknown)}")
        self._streams = dict(streams)
        self._frame_ms = frame_ms
        self._sample_rate = sample_rate
        self._spawn: Spawn = spawn or _default_spawn
        self._read_size = read_size or bytes_per_frame(frame_ms, sample_rate) * 2
        self._queue: queue.Queue[Frame] = queue.Queue()
        self._processes: dict[str, SpawnedProcess] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop = threading.Event()
        self._started = False
        self._iterating = False

    @property
    def streams(self) -> dict[str, str]:
        return dict(self._streams)

    def start(self) -> None:
        if self._started:
            raise CapturerError("already started")
        self._started = True
        for stream, device in self._streams.items():
            argv = parec_argv(device, frame_ms=self._frame_ms, sample_rate=self._sample_rate)
            try:
                process = self._spawn(argv)
            except OSError as exc:
                self.stop()
                raise CapturerError(f"cannot start parec for {stream}: {exc}") from exc
            self._processes[stream] = process
            thread = threading.Thread(
                target=self._pump, args=(stream, process), name=f"flyon-{stream}", daemon=True
            )
            self._threads[stream] = thread
            thread.start()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        for process in self._processes.values():
            with suppress(OSError):  # the child may already be gone
                process.terminate()
        for thread in self._threads.values():
            thread.join(timeout=2.0)
        for process in self._processes.values():
            with suppress(OSError, subprocess.TimeoutExpired):  # shutdown is best effort
                process.wait(timeout=2.0)

    def frames(self) -> Iterator[Frame]:
        if not self._started:
            raise CapturerError("start() before frames()")
        if self._iterating:
            raise CapturerError("frames() consumed twice")
        self._iterating = True
        while True:
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._pumps_finished():
                    return
                continue
            yield frame

    def __enter__(self) -> ParecCapturer:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _pumps_finished(self) -> bool:
        return all(not thread.is_alive() for thread in self._threads.values())

    def _pump(self, stream: str, process: SpawnedProcess) -> None:
        framer = PcmFramer(frame_ms=self._frame_ms, sample_rate=self._sample_rate)
        at_ms = 0
        stdout = getattr(process, "stdout", None)
        try:
            if stdout is None:  # pragma: no cover - a spawn that gives no pipe is a bug
                return
            while not self._stop.is_set():
                chunk = stdout.read(self._read_size)
                if not chunk:
                    break
                for level, raw in framer.feed(chunk):
                    self._queue.put(
                        Frame(
                            stream=stream,
                            level=level,
                            frame_ms=self._frame_ms,
                            at_ms=at_ms,
                            pcm=raw,
                        )
                    )
                    at_ms += self._frame_ms
        except (
            OSError,
            ValueError,
        ):  # pragma: no cover - a dying child is a failed stream, not a crash
            return
