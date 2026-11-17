"""Terminal rendering with `rich`.

The printer stays a printer: what to show is decided by the caller, how it looks is decided here.
Import this module only on the human-output path — `--json` uses `flyon.cli.payloads`, which has no
`rich` dependency and therefore no rendering cost.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from flyon.cli.payloads import Row, duration_text
from flyon.domain.transcript import Line, Session

if TYPE_CHECKING:
    from flyon.app.notes import NoteResult

__all__ = ["Row", "console", "print_line", "print_lines", "print_note", "print_sessions"]


def console() -> Console:
    """A console for this invocation; created lazily so importing this module is cheap."""
    return Console()


def print_sessions(target: Console, rows: Sequence[Row]) -> None:
    if not rows:
        target.print("no sessions yet — nothing has been recorded on this machine", style="dim")
        return
    table = Table(box=None, pad_edge=False, show_edge=False, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column("STARTED", no_wrap=True)
    table.add_column("DURATION", justify="right", no_wrap=True)
    table.add_column("LINES", justify="right", no_wrap=True)
    table.add_column("TITLE")
    for session, line_count in rows:
        table.add_row(
            session.session_id[:8],
            session.started_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            duration_text(session.duration_ms),
            str(line_count),
            escape(session.title) or "[dim]untitled[/dim]",
        )
    target.print(table)


def print_line(target: Console, line: Line) -> None:
    """One transcript line, as `listen` writes it while you talk."""
    target.print(
        f"[dim]{line.timestamp}[/dim] [bold cyan]{line.stream:<6}[/bold cyan] {escape(line.text)}"
    )


def print_lines(target: Console, session: Session, lines: Sequence[Line]) -> None:
    target.print(
        f"[bold]{escape(session.title or 'untitled')}[/bold] "
        f"[dim]{session.session_id[:8]} · "
        f"{session.started_at.astimezone().strftime('%Y-%m-%d %H:%M')} · "
        f"{len(lines)} lines[/dim]"
    )
    if not lines:
        target.print("this session has no transcript lines yet", style="dim")
        return
    for line in lines:
        print_line(target, line)


def print_note(target: Console, result: NoteResult) -> None:
    """Report what was written, where it went, and how much the note actually says.

    Paths are printed with `soft_wrap`: a path broken across two lines is a path you cannot paste.
    """
    target.print(
        f"[bold]{result.note.item_count} items[/bold] · "
        f"{result.provider}:{result.model} · note written"
    )
    target.print(f"  {result.path}", soft_wrap=True)
    if result.copy_path is not None:
        target.print(f"  {result.copy_path} [dim](copy)[/dim]", soft_wrap=True)
