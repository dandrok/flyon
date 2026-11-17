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
def doctor(ctx: typer.Context) -> None:
    """Check that this machine can record and transcribe."""
    from flyon.cli import doctor as doctor_module
    from flyon.cli.render import console

    context = _context(ctx)
    checks = doctor_module.run_checks(context.settings)
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
