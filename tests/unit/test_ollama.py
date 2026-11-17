"""The Ollama adapter, driven by a stub transport: the request shape and the failure messages."""

from __future__ import annotations

import json
import urllib.error
from collections.abc import Mapping
from typing import Any

import pytest

from flyon.adapters.notes.ollama import OllamaNotes
from flyon.app.prompt import NOTE_SCHEMA
from flyon.domain.segment import MIC
from flyon.domain.transcript import Line, Transcript
from flyon.ports.notes import NotesError

ANSWER = {
    "summary": "We agreed to keep the schema change.",
    "decisions": ["keep the schema change"],
    "action_items": ["take the backfill"],
    "open_questions": [],
}


def transcript() -> Transcript:
    return Transcript(
        "6f4c",
        [
            Line(
                session_id="6f4c",
                stream=MIC,
                start_ms=0,
                end_ms=900,
                text="shall we start with the migration",
            )
        ],
    )


def reply(content: str | None) -> dict[str, Any]:
    message = (
        {"role": "assistant"} if content is None else {"role": "assistant", "content": content}
    )
    return {"model": "llama3.2", "message": message, "done": True}


class Recorder:
    """A transport that records the call and answers with whatever it was given."""

    def __init__(self, answer: Mapping[str, Any] | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[str, Mapping[str, Any], float]] = []

    def __call__(self, url: str, body: Mapping[str, Any], timeout_s: float) -> Mapping[str, Any]:
        self.calls.append((url, body, timeout_s))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_request_is_json_mode_with_the_schema_attached() -> None:
    # AC-44: structured output, one call, no streaming
    transport = Recorder(reply(json.dumps(ANSWER)))

    OllamaNotes("llama3.2", transport=transport).summarize(transcript())

    url, body, timeout_s = transport.calls[0]
    assert url == "http://localhost:11434/api/chat"
    assert body["model"] == "llama3.2"
    assert body["format"] == NOTE_SCHEMA
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0}
    assert isinstance(body["messages"], list)
    assert timeout_s == 180.0


def test_an_answer_becomes_a_note() -> None:
    # AC-44
    note = OllamaNotes(transport=Recorder(reply(json.dumps(ANSWER)))).summarize(transcript())

    assert note.summary.startswith("We agreed")
    assert note.actions == ("take the backfill",)
    assert note.questions == ()


def test_the_host_is_configuration() -> None:
    # AC-44
    transport = Recorder(reply(json.dumps(ANSWER)))

    OllamaNotes("m", host="http://box.local:11500/", transport=transport).summarize(transcript())

    assert transport.calls[0][0] == "http://box.local:11500/api/chat"


def test_an_unreachable_daemon_says_what_to_start() -> None:
    # AC-44: the commonest failure on a fresh machine, so the message names the fix
    transport = Recorder(urllib.error.URLError("connection refused"))

    with pytest.raises(NotesError, match="ollama serve"):
        OllamaNotes(transport=transport).summarize(transcript())


def test_text_that_is_not_json_becomes_a_provider_failure() -> None:
    # AC-44
    with pytest.raises(NotesError, match="not JSON"):
        OllamaNotes(transport=Recorder(reply("Sure! Here are the minutes:"))).summarize(
            transcript()
        )


def test_an_answer_without_a_message_is_a_failure() -> None:
    # AC-44
    with pytest.raises(NotesError, match="without a message"):
        OllamaNotes(transport=Recorder({"done": True})).summarize(transcript())
    with pytest.raises(NotesError, match="empty message"):
        OllamaNotes(transport=Recorder(reply(None))).summarize(transcript())


def test_an_empty_transcript_never_reaches_the_daemon() -> None:
    # AC-44: nothing to summarise is a local decision, not a round trip
    transport = Recorder(reply(json.dumps(ANSWER)))

    with pytest.raises(NotesError, match="no lines"):
        OllamaNotes(transport=transport).summarize(Transcript("6f4c"))

    assert transport.calls == []
