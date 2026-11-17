"""Wiring: turn configuration into adapters.

The only module that knows which concrete class sits behind a port. Everything else asks for a
`Store`; this decides whether that is SQLite or the append-only JSONL files.
"""

from __future__ import annotations

from pathlib import Path

from flyon.adapters.store.jsonl import JsonlStore
from flyon.adapters.store.sqlite import SqliteStore
from flyon.app.config import Settings
from flyon.ports.store import Store

__all__ = ["open_store", "store_location"]


def open_store(settings: Settings) -> Store:
    if settings.store == "jsonl":
        return JsonlStore(settings.data_dir)
    return SqliteStore(settings.database_path())


def store_location(settings: Settings) -> Path:
    """Where this install keeps its sessions, for `doctor` and error messages."""
    if settings.store == "jsonl":
        return settings.data_dir
    return settings.database_path()
