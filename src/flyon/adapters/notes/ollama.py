"""Local notes through Ollama: one JSON-mode chat call to a daemon on this machine.

Nothing leaves the machine, which is the point: the same promise the transcriber keeps. The
transport is a plain callable so the contract test can drive this adapter without a daemon running,
and so a future adapter can reuse the same shape against a different host.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from flyon.app.prompt import NOTE_SCHEMA, build_messages, parse_note
from flyon.domain.note import Note
from flyon.domain.transcript import Transcript
from flyon.ports.notes import NotesError

DEFAULT_MODEL = "llama3.2"
DEFAULT_HOST = "http://localhost:11434"
START_HINT = "is `ollama serve` running, and is the model pulled (`ollama pull llama3.2`)?"

Transport = Callable[[str, Mapping[str, Any], float], Mapping[str, Any]]


def urllib_transport(url: str, body: Mapping[str, Any], timeout_s: float) -> Mapping[str, Any]:
    """POST JSON and read JSON back. The only part of this adapter that touches the network."""
    request = urllib.request.Request(  # noqa: S310 - the host is configuration, not user input
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise NotesError("ollama answered with something that is not a JSON object")
    return payload


class OllamaNotes:
    """Satisfies `NotesProvider` against a local Ollama daemon."""

    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        host: str = DEFAULT_HOST,
        timeout_s: float = 180.0,
        transport: Transport | None = None,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport or urllib_transport

    @property
    def model(self) -> str:
        return self._model

    def summarize(self, transcript: Transcript) -> Note:
        if not transcript.lines:
            raise NotesError("nothing to summarise: the session has no lines")

        body: dict[str, Any] = {
            "model": self._model,
            "messages": build_messages(transcript),
            "format": NOTE_SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            reply = self._transport(f"{self._host}/api/chat", body, self._timeout_s)
        except urllib.error.URLError as exc:
            raise NotesError(
                f"cannot reach ollama at {self._host} — {START_HINT} ({exc.reason})"
            ) from exc
        except TimeoutError as exc:
            raise NotesError(f"ollama did not answer within {self._timeout_s:.0f}s") from exc
        except NotesError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise NotesError(f"ollama call failed: {exc}") from exc

        content = _content_of(reply)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise NotesError(f"ollama returned text that is not JSON: {content[:120]!r}") from exc
        return parse_note(parsed)


def _content_of(reply: Mapping[str, Any]) -> str:
    """The assistant's text out of Ollama's chat response, with a message that names the problem."""
    message = reply.get("message")
    if not isinstance(message, Mapping):
        raise NotesError("ollama answered without a message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise NotesError("ollama answered with an empty message")
    return content
