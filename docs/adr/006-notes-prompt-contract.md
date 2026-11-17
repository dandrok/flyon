# 006 — the notes prompt is a contract, and it lives in one module

Date: 2026-11-17
Status: accepted

## Context

`flyon summarize` asks a model to turn a transcript into minutes. Two things about that are easy to get
wrong in ways nobody notices until the notes are bad:

- **The prompt is the product.** Sections, tone, "don't invent names", "empty lists are fine" — every
  instruction shapes every note. If each provider carried its own copy, swapping providers would
  quietly change what the notes are, and a regression would look like a model getting worse.
- **The transcript is a two-stream thing, not a conversation.** `mic` and `system` are sides of the
  call, not named people. A model told to "summarise this chat" will invent speaker names, and a
  transcript with the timestamps stripped loses the only ordering signal we have.

## Decision

One module, `app/prompt.py`, owns:

- the instructions (`INSTRUCTIONS`) — including "answer in the language of the meeting", "never invent
  a name", "empty lists are correct answers", and "return JSON only";
- the JSON schema (`NOTE_SCHEMA`) the answer must match, in a form Ollama can enforce as structured
  output and a future provider can pass as a response schema;
- the transcript rendering (`[mm:ss] stream: text`, one line per utterance);
- the answer reader (`parse_note`), which is deliberately tolerant about key names (`actions` for
  `action_items`) and strict about shape and emptiness.

Adapters own transport only: request shape, timeouts, and turning their own errors into `NotesError`.

The note's shape is fixed by AC-43 … AC-49 in `spec.md`: summary, decisions, action items, open
questions; front-matter with session, date, duration, streams, lines.

## Consequences

- A second provider (Gemini, llama.cpp, a cloud model) cannot silently write different kinds of notes,
  because it is handed the same prompt and its answer goes through the same reader.
- Changing the prompt is a visible change to one file with an ADR beside it — and it changes every note
  ever written, so it is a `feat:` or `fix:` commit with a changelog line, not a tweak.
- The prompt is English while the notes are not: the instructions say "answer in the language of the
  meeting", which is one sentence a model can ignore. If notes come back in English from a Polish
  meeting, the fix belongs here, not in the adapter.
- Nothing in this module touches a network, so it is unit-tested without a provider — which is most of
  the reason the answering logic was allowed to get this opinionated.
