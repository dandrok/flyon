"""The command line: three read commands, a doctor, and an answer for the bare invocation.

Imports are deferred into the command bodies on purpose: `flyon --version` and `flyon sessions
--json` never need `rich`, pydantic or the store, and paying for them on every invocation is the
difference between a command that feels instant and one that does not.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from flyon import __version__
from flyon.cli.payloads import duration_text, lines_payload, sessions_payload
from flyon.domain.segment import STREAMS

if TYPE_CHECKING:
    from flyon.app.config import Settings
    from flyon.domain.transcript import Session
    from flyon.ports.store import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="A fly on the wall: transcribe meetings locally, keep the transcript on your machine.",
)


@dataclass(slots=True)
class Context:
    settings: Settings
    store: Store


def main() -> None:
    """Console-script entry point."""
    app()


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"flyon {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            is_eager=True,
            callback=_print_version,
            help="Print the version and exit.",
        ),
    ] = False,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Where sessions and transcripts live.", show_default=False),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Where Whisper models are cached.", show_default=False),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config.toml.", show_default=False),
    ] = None,
) -> None:
    """A fly on the wall: transcribe meetings locally."""
    from flyon.app.config import SettingsError, load_settings
    from flyon.app.wiring import open_store

    try:
        settings = load_settings(config=config, data_dir=data_dir, cache_dir=cache_dir)
    except SettingsError as exc:
        typer.echo(f"flyon: {exc}", err=True)
        raise typer.Exit(2) from exc
    try:
        store = open_store(settings)
    except (OSError, sqlite3.Error) as exc:
        typer.echo(f"flyon: cannot open the store: {exc}", err=True)
        raise typer.Exit(2) from exc
    ctx.obj = Context(settings=settings, store=store)
    if ctx.invoked_subcommand is None:
        _status(ctx.obj)


@app.command()
def sessions(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", help="How many sessions.")] = 20,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON and nothing else.")] = False,
) -> None:
    """List sessions, newest first."""
    context = _context(ctx)
    rows = [
        (session, context.store.line_count(session.session_id))
        for session in context.store.list_sessions(limit=limit)
    ]
    if as_json:
        typer.echo(json.dumps(sessions_payload(rows), ensure_ascii=False))
        return
    from flyon.cli import render

    render.print_sessions(render.console(), rows)


@app.command()
def show(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session id, or any unique prefix of one.")],
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON and nothing else.")] = False,
) -> None:
    """Print one transcript."""
    context = _context(ctx)
    session = _resolve_session(context.store, session_id)
    lines = context.store.lines(session.session_id)
    if as_json:
        typer.echo(json.dumps(lines_payload(session, lines), ensure_ascii=False))
        return
    from flyon.cli import render

    render.print_lines(render.console(), session, lines)


@app.command()
def listen(
    ctx: typer.Context,
    title: Annotated[str, typer.Option("--title", help="Name this session.")] = "",
    engine: Annotated[
        str,
        typer.Option("--engine", help="faster-whisper (default) or fake.", show_default=False),
    ] = "",
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help="parec (real audio), fake (scripted), or wav:<file> (16 kHz mono WAV as the mic).",
        ),
    ] = "parec",
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Record without printing each line.")
    ] = False,
) -> None:
    """Record, transcribe as you talk, and save the session. Ctrl-C stops."""
    from flyon.app.session import SessionRecorder
    from flyon.app.wiring import open_capturer, open_transcriber
    from flyon.cli import render
    from flyon.ports.capturer import CapturerError
    from flyon.ports.transcriber import TranscriberError

    context = _context(ctx)
    settings = context.settings
    try:
        capturer = open_capturer(source)
        transcriber = open_transcriber(settings, engine or settings.engine)
    except (ValueError, CapturerError, TranscriberError) as exc:
        typer.echo(f"flyon: {exc}", err=True)
        raise typer.Exit(2) from exc

    target = render.console()
    recorder = SessionRecorder(
        capturer=capturer,
        transcriber=transcriber,
        store=context.store,
        title=title,
        segmenter_config=settings.segmenter.to_domain(),
        on_line=None if quiet else lambda line: render.print_line(target, line),
        on_error=lambda message: typer.echo(f"flyon: {message}", err=True),
    )
    target.print(
        f"[dim]recording {', '.join(capturer.streams)} · "
        f"{transcriber.name}:{transcriber.model} · Ctrl-C stops[/dim]"
    )
    summary = recorder.run()
    duration = summary.session.duration_ms or 0
    target.print(
        f"[bold]{len(summary.lines)} lines[/bold] · "
        f"{summary.segments} segments ({summary.empty_segments} silent, "
        f"{summary.failed_segments} failed) · {render.duration_text(duration)} · "
        f"saved as {summary.session.session_id}"
    )
    declared = capturer.streams
    peaks = {
        stream: level
        for stream, level in summary.peak_level.items()
        if declared.get(stream) != "silence"
    }
    render.print_levels(
        target, peaks, threshold=settings.segmenter.voice_threshold, lines=len(summary.lines)
    )
    target.print(f"[dim]flyon show {summary.session.session_id[:8]}[/dim]")


@app.command()
def summarize(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session id, or any unique prefix of one.")],
    provider: Annotated[
        str,
        typer.Option(
            "--provider",
            help="ollama (the configured default) or fake.",
            show_default=False,
        ),
    ] = "",
) -> None:
    """Write the minutes of a session: summary, decisions, actions, open questions."""
    from flyon.app.notes import summarize_session
    from flyon.app.wiring import open_notes_provider
    from flyon.cli import render
    from flyon.ports.notes import NotesError

    context = _context(ctx)
    session = _resolve_session(context.store, session_id)
    try:
        notes = open_notes_provider(context.settings, provider or None)
    except ValueError as exc:
        typer.echo(f"flyon: {exc}", err=True)
        raise typer.Exit(2) from exc

    target = render.console()
    target.print(f"[dim]{notes.name}:{notes.model} is reading the transcript…[/dim]")
    try:
        result = summarize_session(
            store=context.store,
            provider=notes,
            session=session,
            data_dir=context.settings.data_dir,
            extra_copy=context.settings.output.extra_copy_path(),
        )
    except NotesError as exc:
        typer.echo(f"flyon: {exc}", err=True)
        raise typer.Exit(1) from exc
    render.print_note(target, result)


@app.command()
def doctor(
    ctx: typer.Context,
    probe: Annotated[
        bool,
        typer.Option("--probe", help="Also record a couple of seconds and report what arrives."),
    ] = False,
    seconds: Annotated[
        float,
        typer.Option("--seconds", help="How long the probe records.", show_default=True),
    ] = 2.0,
) -> None:
    """Check that this machine can record and transcribe."""
    from flyon.cli import doctor as doctor_module
    from flyon.cli.render import console

    context = _context(ctx)
    checks = doctor_module.run_checks(context.settings)
    if probe:
        checks += doctor_module.probe_capture(seconds=seconds)
    target = console()
    doctor_module.print_checks(target, checks)
    target.print(
        f"[dim]streams: {', '.join(STREAMS)} · "
        f"engine: {context.settings.engine} · model: {context.settings.model}[/dim]"
    )
    if doctor_module.worst_status(checks) == "fail":
        raise typer.Exit(1)


def _context(ctx: typer.Context) -> Context:
    if not isinstance(ctx.obj, Context):
        typer.echo("flyon: internal error — command ran without a context", err=True)
        raise typer.Exit(3)
    return ctx.obj


def _resolve_session(store: Store, prefix: str) -> Session:
    matches = [s for s in store.list_sessions(limit=1000) if s.session_id.startswith(prefix)]
    if not matches:
        typer.echo(f"flyon: no session matches {prefix!r}", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo(f"flyon: {len(matches)} sessions match {prefix!r}:", err=True)
        for session in matches:
            typer.echo(f"  {session.session_id}", err=True)
        raise typer.Exit(1)
    stored = store.get_session(matches[0].session_id)
    return matches[0] if stored is None else stored


def _status(context: Context) -> None:
    """The bare command answers; it does not report."""
    from flyon.cli.render import console

    target = console()
    latest = context.store.list_sessions(limit=1)
    if not latest:
        target.print("no sessions yet on this machine")
        target.print("[dim]flyon doctor   check the microphone, the model and the store[/dim]")
        return
    session = latest[0]
    line_count = context.store.line_count(session.session_id)
    state = "recording" if session.is_open else "finished"
    target.print(
        f"last session [bold]{session.session_id[:8]}[/bold] · {state} · "
        f"{line_count} lines · {duration_text(session.duration_ms)}"
    )
    target.print(
        f"[dim]flyon show {session.session_id[:8]}   read it · "
        f"flyon sessions   list everything[/dim]"
    )
