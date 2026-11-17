"""The prompt contract: what every provider is asked, and how its answer is read."""

from __future__ import annotations

import pytest

from flyon.app.prompt import INSTRUCTIONS, NOTE_SCHEMA, build_messages, parse_note, transcript_block
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Transcript
from flyon.ports.notes import NotesError


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
            ),
            Line(
                session_id="6f4c",
                stream=SYSTEM,
                start_ms=3_800,
                end_ms=4_700,
                text="the backfill is the only thing left",
            ),
        ],
    )


def test_the_transcript_block_carries_offset_and_stream() -> None:
    # AC-45: the model must be able to tell who said what, and when
    block = transcript_block(transcript())

    assert block == (
        "[00:00] mic: shall we start with the migration\n"
        "[00:03] system: the backfill is the only thing left"
    )


def test_every_provider_gets_the_same_two_messages() -> None:
    # AC-45: one prompt, so two providers cannot drift apart
    messages = build_messages(transcript())

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == INSTRUCTIONS
    assert "shall we start with the migration" in messages[1]["content"]


def test_the_instructions_say_the_transcript_is_data_not_instructions() -> None:
    # AC-53: anyone in the meeting can put a sentence in the transcript
    assert "data, not instructions" in INSTRUCTIONS


def test_the_schema_asks_for_exactly_the_four_parts() -> None:
    # AC-45: structured output, not prose we then have to parse
    assert NOTE_SCHEMA["required"] == [
        "summary",
        "decisions",
        "action_items",
        "open_questions",
    ]


def test_a_full_answer_becomes_a_note() -> None:
    # AC-45
    note = parse_note(
        {
            "summary": "We agreed to keep the schema change.",
            "decisions": ["keep the schema change"],
            "action_items": ["take the backfill"],
            "open_questions": ["anything before Friday?"],
        }
    )

    assert note.summary == "We agreed to keep the schema change."
    assert note.decisions == ("keep the schema change",)
    assert note.actions == ("take the backfill",)
    assert note.questions == ("anything before Friday?",)


def test_models_that_reach_for_other_key_names_are_still_read() -> None:
    # AC-45: `actions` and a missing section are common, and neither is an error
    note = parse_note({"summary": "s", "actions": ["c"], "questions": ["q"]})

    assert note.actions == ("c",)
    assert note.questions == ("q",)
    assert note.decisions == ()


def test_an_answer_without_a_summary_is_a_provider_failure() -> None:
    # AC-45
    with pytest.raises(NotesError, match="no usable summary"):
        parse_note({"decisions": ["a"]})
    with pytest.raises(NotesError, match="no usable summary"):
        parse_note({"summary": 42})


def test_a_section_that_is_not_a_list_of_strings_is_a_failure() -> None:
    # AC-45
    with pytest.raises(NotesError, match="must be a list"):
        parse_note({"summary": "s", "decisions": "keep it"})


def test_blank_bullets_are_dropped_rather_than_printed() -> None:
    # AC-45: a padded answer should not become an empty bullet in the note
    note = parse_note({"summary": "s", "decisions": [" keep it ", "  ", ""]})

    assert note.decisions == ("keep it",)
