# spec — flyon

What each milestone must do, written as criteria a test can fail. The engineering contract (versions,
gates, docs, non-goals) is the vault note *Meeting transcriber — engineering standards*; this file is
the product half.

## Contents

- [Scope of the first release](#scope-of-the-first-release)
- [Decisions closed by this spec](#decisions-closed-by-this-spec)
- [M1 — transcript core](#m1--transcript-core)
- [M2 — live capture and local STT](#m2--live-capture-and-local-stt)
- [M3 — notes](#m3--notes)
- [Cross-cutting criteria](#cross-cutting-criteria)
- [Acceptance-criteria to test map](#acceptance-criteria-to-test-map)
- [Out of scope](#out-of-scope)
- [Open questions](#open-questions)

## Scope of the first release

`v0.1` is a working loop on one machine: start `flyon listen`, talk, stop it, read the transcript,
ask for notes. Nothing in v0.1 talks to a network unless a cloud engine is configured.

Three milestones, each shippable on its own:

| Milestone | Ships | Gate to move on |
|---|---|---|
| M1 | session store, segmenter, read commands, `doctor` | `make check` green, README example true |
| M2 | capture adapters, VAD, faster-whisper, blocking `listen` | a real 5-minute meeting transcribed end to end |
| M3 | notes provider, `summarize`, optional vault copy | one note written from a real transcript |

This document specifies M1 in full and M2/M3 as contracts, because their details belong to the slice
that builds them.

## Decisions closed by this spec

The three questions the engineering note left open, decided 2026-11-17:

1. **Default model on first run: `large-v3-turbo`.** One 1.6 GB download, good text from the first
   meeting, no "come back later and upgrade" step. `doctor` warns before the download, so nobody is
   surprised by it mid-meeting.
2. **`flyon listen` blocks.** Live output in the terminal; Ctrl-C stops and finalises the session.
   A detached mode is a later flag (`--detach`), not a second code path in v0.1.
3. **The segmenter cuts on silence *and* caps a monologue at 15 s.** A monologue becomes a sequence
   of timestamped segments rather than one unbounded chunk; the cap is `max_segment_ms`, so it is
   configurable without a code change.

## M1 — transcript core

### Domain

**AC-1 — a frame at or above the voice threshold counts as speech.**
`push(level >= voice_threshold)` opens or extends a segment; `level < voice_threshold` does not.

**AC-2 — silence shorter than `silence_ms` does not split a segment.**
Voice 200 ms, silence 400 ms, voice 200 ms, then 800 ms of silence yield exactly one 800 ms segment.

**AC-3 — `silence_ms` of quiet closes the segment at the last voiced frame.**
Trailing silence never appears in the segment's `end_ms`; a 1 s utterance followed by 800 ms of
silence is `Segment(start=0, end=1000)`, not `end=1800`.

**AC-4 — a segment shorter than `min_segment_ms` is dropped.**
100 ms of voice followed by silence yields no segment at all.

**AC-5 — a monologue is force-cut at `max_segment_ms` and continues.**
30 s of unbroken voice yields exactly two segments, `[0, 15000)` and `[15000, 30000)`, with no audio
lost between them.

**AC-6 — `flush()` closes an open segment at its last voiced frame.**
Stopping mid-speech must not discard the tail.

**AC-7 — segments carry their stream.**
`Segment.stream` is `mic` or `system`; a value outside that set is a `ValueError`.

**AC-8 — a line is ordered and typed.** `Line` rejects an unknown stream and an `end_ms` before its
`start_ms`.

**AC-9 — a transcript is append-only.** Appending a line from another session, or one that starts
before the previous line, raises `OutOfOrderLine`.

**AC-10 — timestamps render as `mm:ss`, and as `h:mm:ss` past an hour.**
`0 -> 00:00`, `59999 -> 00:59`, `60000 -> 01:00`, `3600000 -> 1:00:00`; a negative value raises.

### Store

**AC-11 — both adapters satisfy one port.** `tests/contract/test_store.py` is parametrized over
`sqlite` and `jsonl`; every criterion below runs against both.

**AC-12 — creating then reading a session returns the same record**, including its start time and
title.

**AC-13 — a session can be ended once.** After `end_session`, `Session.ended_at` is set and
`is_open` is false; ending an unknown session raises.

**AC-14 — appending lines returns them in start order**, and each carries a store-assigned id that
increases.

**AC-15 — `list_sessions` is newest first and respects `limit`.**

**AC-16 — data survives reopening.** A second store instance on the same path sees the same sessions
and lines — this is what makes the store a store and not a cache.

**AC-17 — an unknown session is a `None`, not an exception**; `lines()` of it is empty.

**AC-26 — the backend is configuration.** `store = "sqlite" | "jsonl"` in `config.toml` selects the
adapter, `sqlite` is the default, an unknown value is a configuration error, and both backends read
back through the same CLI command — the seam is tested end to end, not asserted in a comment.

### CLI

**AC-18 — `flyon --version` prints `flyon <version>` and exits 0.**

**AC-19 — `flyon` with no arguments answers, it does not dump a dashboard**: no sessions, the two
lines that say what to type next; with sessions, one summary line for the latest.

**AC-20 — `flyon sessions` prints a table newest-first, and `--json` prints only the payload.**
The JSON parses with `json.loads` and must not contain a human notice; exit code 0.

**AC-21 — `flyon show <prefix>` resolves a unique session-id prefix**, prints one line per
transcript line prefixed with `mm:ss` and the stream; `--json` prints `{session, lines}` only.

**AC-22 — `flyon show` with an unknown prefix exits non-zero and says so on stderr**; an ambiguous
prefix exits non-zero and lists the candidates.

**AC-23 — `flyon doctor` reports one row per check** (python, data dir, config, store, STT extra,
capture tools, model cache), exits 0 when nothing failed and 1 when something did. A missing STT
extra or capture tool is a **warn**, not a failure: the read commands work without them.

**AC-24 — `--data-dir` isolates everything.** Pointing it at a fresh directory yields an empty
`flyon sessions --json` and creates the directory, never touching the default path.

**AC-25 — a broken `config.toml` exits 2 with the file path in the message**, and no traceback. A
`--data-dir` that cannot hold a database is the same shape of error: exit 2, one line on stderr.

## M2 — live capture and local STT

**Built (capture half):** AC-27 … AC-31 below are tested; the transcriber half is the next slice.

- **AC-27 — `flyon doctor --probe` records for `--seconds` and reports frames per stream with the
  peak level**, warning when a stream delivers nothing (muted, suspended bluetooth) and failing when
  the capturer cannot start. Verified against real `parec` on this machine: 148 frames in 3.1 s,
  peak 0.261 for a 440 Hz tone at 0.366 full scale (RMS = amplitude/√2 = 0.259).
- **AC-28 — one frame is 20 ms of s16le mono at 16 kHz**, and the framer keeps a partial frame across
  chunk boundaries instead of dropping it, because a pipe hands over whatever sizes it likes.
- **AC-29 — a level is RMS normalised to 0…1**: silence 0.0, full-scale square 1.0, half amplitude
  ≈ 0.5, a stray odd byte ignored.
- **AC-30 — two streams, one capturer, one queue**; each frame carries its stream and its offset in
  that stream, and the offsets advance by exactly one frame.
- **AC-31 — the capture port is a tested seam**: `tests/contract/test_capturer.py` runs the same
  criteria against a scripted fake and the real `parec` adapter driven by a fake process; `stop()` is
  idempotent, a second `start()` raises, and a missing binary is a `CapturerError`, not a traceback.

**Still to build:** the transcriber port and `faster-whisper` adapter, then blocking `listen`.

- Both streams share a monotonic timeline, so a `mic` segment and a `system` segment can be ordered
  against each other.
- The transcriber consumes 16 kHz mono float32 slices; an adapter that needs another rate resamples
  inside itself, not in the pipeline.
- `flyon listen` writes each recognised line to the store as it arrives and renders it live; Ctrl-C
  finalises the session, and a second Ctrl-C during shutdown exits immediately.
- If the STT extra is missing, `listen` says so once, with the exact install command, and exits 2.
- An engine failure mid-meeting does not end the recording: the session stays open and the failure is
  written to stderr.

## M3 — notes

- `flyon summarize <session>` sends the transcript to the configured provider and writes a markdown
  note to the state dir; with `output.extra_copy` set, an identical copy is written there.
- The note has front-matter (`session`, `date`, `duration`, `streams`) and sections: summary,
  decisions, action items, open questions.
- Nothing is uploaded without an engine explicitly configured: the default configuration cannot make
  a network call.
- A failed provider call leaves no partial note behind.

## Cross-cutting criteria

- **AC-JSON — every read command has `--json`, and its stdout is pure JSON.** Notices go to stderr.
  One test per command asserts `json.loads(stdout)` succeeds and stderr carries the notice.
- **AC-LAYER — `domain/` imports nothing outside the standard library**; mypy strict passes on
  `domain/` and `ports/`.
- **AC-GATES — `make check` runs the identical commands CI runs**; a green local run and a red PR
  mean an environment difference, never a different command.
- **AC-STARTUP — startup is measured, not assumed.** `flyon --version` returns in under 300 ms and
  `flyon sessions --json` in under 500 ms on this machine (measured 2026-11-17: 185 ms and 404 ms).
  The criterion exists so a new import is a decision, not an accident: `pydantic` costs ~150 ms and is
  worth it for config validation, `rich` costs ~40 ms and is kept off the `--json` path entirely.
- **AC-STATE — no recording or transcript is ever written inside the repository**; the default paths
  come from `platformdirs`, and `--data-dir` is the only way they move.

## Acceptance-criteria to test map

| Criteria | Test file |
|---|---|
| AC-1 … AC-7 | `tests/unit/test_segment.py` |
| AC-8 … AC-10 | `tests/unit/test_transcript.py` |
| AC-11 … AC-17 | `tests/contract/test_store.py` |
| AC-18 … AC-25, AC-JSON | `tests/unit/test_cli.py` |
| AC-28 … AC-29 | `tests/unit/test_pcm.py` |
| AC-31 (parec side), AC-27 | `tests/unit/test_parec.py`, `tests/unit/test_cli.py` |
| AC-30 … AC-31 | `tests/contract/test_capturer.py` |
| config load + overrides | `tests/unit/test_config.py` |
| M2, M3 | written with their slice |

## Out of scope

Identical to the engineering note's non-goals: no TUI, no diarization, no torch, no async rewrite, no
GUI or web dashboard, no cloud sync, no recording of third parties in fixtures — synthetic audio only.

## Open questions

Nothing blocking M1. Deferred, with the slice that owns each:

1. Should `show` re-order interleaved `mic`/`system` lines, or keep each stream's blocks? (M2, once
   real interleaving exists.)
2. Retention: does the JSONL transcript get rotated, or is deleting a session an explicit command?
   (M3.)
3. Does `summarize` accept a partial range (`--from 12:30`)? (M3.)

---

[back to contents](#contents)
