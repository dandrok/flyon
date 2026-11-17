# DESIGN — flyon

The shape of the thing, and the reasons. The rules that bind the repository (versions, gates, docs,
non-goals) live in the vault note *Meeting transcriber — engineering standards*; this file explains
the machinery those rules protect.

## Contents

- [The problem](#the-problem)
- [Two streams, and why](#two-streams-and-why)
- [The pipeline](#the-pipeline)
- [Layers and the import rule](#layers-and-the-import-rule)
- [Ports](#ports)
- [The segmenter](#the-segmenter)
- [The store](#the-store)
- [Startup, measured](#startup-measured)
- [Trade-offs we accepted](#trade-offs-we-accepted)

## The problem

A meeting has two sides: what the room says, and what comes out of the speakers. A single mixed
recording blurs both into one channel, and every downstream fix — diarization models, speaker
embeddings — is probabilistic work spent recovering information the operating system already had.

## Two streams, and why

`pipewire` (or `parec`) can hand us the microphone and the monitor of the default sink as two
separate captures. Keeping them apart means:

- speaker attribution is exact for the two-party case: `mic` vs `system`, no model;
- a quiet remote participant is not drowned by a loud room;
- each stream is transcribed on its own timeline, so a segment from one never swallows a segment
  from the other, and both keep millisecond offsets into the same recording.

The cost is bookkeeping: two clocks, two segmenters, one merged transcript ordered by start time.
That is arithmetic, and arithmetic is testable without a microphone. See
[ADR 001](docs/adr/001-two-streams.md).

## The pipeline

```
capture (2 streams)  ->  segmenter (per stream)  ->  transcriber  ->  transcript (append-only)
        |                      |                          |
     parec/pw-record    domain/segment.py         ports/transcriber.py
```

1. **capture** produces fixed frames (20 ms) per stream and pushes a level per frame;
2. **segment** turns levels into `Segment(stream, start_ms, end_ms)` — silence closes a segment, a
   long monologue is force-cut at 15 s and continues as the next segment;
3. **transcribe** takes a segment plus its audio slice and returns text (local Whisper by default);
4. **store** appends the resulting `Line` to the session: SQLite for querying, JSONL as the
   append-only artifact.

Every arrow is a `Protocol` in `src/flyon/ports/`. The domain package — segments, lines, sessions,
the transcript itself — touches nothing but the standard library, so the rules that decide where a
cut happens are testable in microseconds with no audio, no model and no database.

## Layers and the import rule

```
domain  <-  ports  <-  adapters  <-  app  <-  cli
```

- `domain/` imports nothing outside the standard library; mypy `strict` covers it.
- `ports/` imports `domain` only.
- `adapters/` implement ports; they may import `domain` and `ports`, never `cli`.
- `cli/` imports everything and is imported by nothing.

The rule is enforced by review plus an import-linter check in CI. Its purpose is narrow: adding a
Groq engine or a JSONL store must not require editing the module that computes segments.

## Ports

| Port | Contract | Adapters today |
|---|---|---|
| `capturer.Capturer` | start/stop two named streams, yield frames with levels | next slice |
| `transcriber.Transcriber` | `transcribe(frames, hint) -> text` | next slice |
| `store.Store` | sessions and append-only lines | `sqlite`, `jsonl` |

Which store is live is configuration (`store = "sqlite" | "jsonl"`), resolved in one place,
`app/wiring.py`. The CLI never imports an adapter, which is what makes the second backend a setting
rather than a fork.

`tests/contract/test_store.py` is parametrized over **both** store adapters, so the port is a
tested seam rather than a comment. A port with one adapter and no contract test is a claim.

## The segmenter

Pure, per stream, no clock of its own: the caller pushes `(level, frame_ms)` in order and gets back
closed segments.

- a frame at or above `voice_threshold` opens a segment or extends the open one;
- silence shorter than `silence_ms` is absorbed, so a breath does not split a sentence;
- `silence_ms` of consecutive quiet closes the segment at the last voiced frame — trailing silence
  never inflates a timestamp;
- a segment still open at `max_segment_ms` is force-cut there and the next voiced frame opens a new
  one, because Whisper's accuracy falls off a cliff on very long inputs and a 90-second monologue
  should still produce timestamped lines;
- a segment shorter than `min_segment_ms` is dropped: it is a door, not speech.

## The store

SQLite is the queryable store: one `session` table, one `line` table, an index on
`(session_id, start_ms)`, `PRAGMA journal_mode = WAL` set in the schema, and DDL gated on
`PRAGMA user_version` so it runs once per database rather than on every command. The JSONL adapter
keeps the same data as plain append-only files — the artifact you can read with `grep`, hand to
another tool, or diff, and the answer if a future SQLite change ever needs an escape hatch.

Both implement the same port so the CLI does not care which one is behind it.

## Startup, measured

Measured on 2026-11-17, this machine, Python 3.14.7, `.venv/bin/flyon` directly:

| Invocation | Wall clock | What it pays for |
|---|---|---|
| `flyon --version` | **185 ms** | interpreter (~29 ms) + typer (~66 ms) + `dataclasses` (~19 ms) |
| `flyon sessions --json` | **404 ms** | the above + `pydantic` (~150 ms) + sqlite + `platformdirs` |

Two decisions came out of that measurement, and one trade was refused:

- `rich` is imported only on the human-output path (`cli/render.py`), never for `--json`
  (`cli/payloads.py` is pure). That is the difference between 404 ms and ~450 ms, and it keeps the
  JSON contract independent of a terminal library.
- `--version` returns before the config, the store or `rich` are imported, because those imports live
  inside the command bodies.
- **Refused:** dropping `pydantic` to buy back 150 ms. A typo in `silence_ms` would become a strange
  transcript three meetings later instead of a field name on stderr. The number is under the threshold
  where a typed command feels slow, so nothing else needs fixing.

## Trade-offs we accepted

| Decision | Cost we accept |
|---|---|
| two streams instead of diarization | exact for two-party meetings, says nothing about a third voice in the room |
| local Whisper by default | a 1.6 GB model download on first run; cloud engines are opt-in extras |
| SQLite + JSONL, not one of them | two adapters to keep honest — paid for by one contract test file |
| blocking `flyon listen` | closing the terminal ends the recording; a detached mode is a later flag |
| a 15 s cap on monologues | a single sentence can be cut mid-clause — the transcript shows it as two lines |

---

[back to contents](#contents)
