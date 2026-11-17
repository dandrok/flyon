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
- [Later — cloud engines](#later--cloud-engines-not-scheduled)
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

The three questions the engineering note left open, decided 2026-11-17 (the model, again, on the
evidence in `docs/VERIFICATION.md`):

1. **Default model on first run: `small`.** Live transcription is the point, and the engine costs one
   30 s encoder window per *segment*: `large-v3-turbo` spends ~7 s on a 5 s segment and falls behind a
   normal turn-taking pace on CPU, while `small` answers in ~1.7 s with exact text on the measured
   fixture. 464 MB once, `doctor` names the size before the download. `large-v3-turbo` stays one
   config line away for reading a transcript afterwards — `docs/adr/005`.
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

**Built (capture half):** AC-27 … AC-31 below are tested; the transcriber half is verified against a
real model by AC-41.

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

**Built (engine half, wired into `listen`):**

- **AC-32 — one transcriber contract, two engines.** `tests/contract/test_transcriber.py` runs a
  scripted engine and the `faster-whisper` adapter (driven by a stub model) through the same checks:
  text comes back stripped, every result names its engine and model, silence and empty audio produce
  an empty transcription rather than an exception.
- **AC-33 — the model loads once, lazily, and failures say which model.** The adapter builds a single
  `WhisperModel` on first use; a missing `flyon[stt]` extra raises one `TranscriberError` naming the
  install command; a download or CTranslate2 failure names the model that failed.
- **AC-34 — audio conversion is exact.** `s16le` becomes float32 in −1.0 … 1.0 (16384 → 0.5), an odd
  trailing byte is ignored, and empty bytes convert to an empty array.
- **AC-35 — numpy is a declared dependency, not an inherited one.** It is imported by the adapter, so
  it is listed in the `stt` extra and the dev group instead of arriving by accident through
  `ctranslate2`.

- **AC-36 — the session loop is the only place capture, segmentation, transcription and storage
  meet**, and it holds these rules: one segmenter per declared stream; the audio handed to the engine
  is cut to exactly the segment (`end_ms - start_ms` of audio, no trailing silence padded in); an
  empty transcription is counted, not stored; an engine failure is counted and reported while the
  recording continues; a frame from a stream the capturer never declared is ignored.
- **AC-37 — Ctrl-C finalises the session.** Interrupting mid-recording still ends the session row,
  flushes the open segment of every stream, and returns a summary — a meeting is never abandoned as
  an open row.
- **AC-38 — the audio buffer is bounded.** Only the last `max_segment_ms` plus one frame of audio per
  stream is kept, so memory does not grow with the length of the meeting.
- **AC-39 — `flyon listen` blocks and reports.** It prints a `mm:ss stream text` line as each segment
  lands (suppressed by `--quiet`), then one summary line with line count, segment counts and session
  id, and exits 0. `--source fake --engine fake` runs the whole loop with no microphone and no model.
- **AC-40 — a missing engine is one clean error.** `flyon listen` with the STT extra absent exits 2
  before recording starts, naming `uv tool install 'flyon[stt]'`; an unknown `--source` or `--engine`
  is the same shape of error with the accepted values.

- **AC-41 — a real model transcribes real speech.** `tests/e2e/test_real_whisper.py` is the one test
  that downloads a model and listens to it: a committed 2.3 s speech fixture goes through the real
  adapter, and the result must contain the words *start* and *migration*, and name the engine and the
  model. A 1.5 s clip of the same fixture — segment length, which is what this pipeline actually
  produces — must still return text, and two seconds of digital silence must return none, because a
  silent segment that invents a sentence poisons the transcript. Two seconds of noise loud enough to
  clear `voice_threshold` must return none as well: that is what `vad_filter` in the adapter is for,
  and this criterion is why it is on. The test is `slow` (never in `make check`), skips when the `stt`
  extra is absent, runs the shipped default model, and caches it in the same directory `listen` uses,
  so running the tests once means the first meeting downloads nothing. Measured cost (download, load,
  realtime factor) is recorded in `docs/VERIFICATION.md`.

- **AC-42 — the default model is `small`, and everything that names it agrees.** `DEFAULT_MODEL` in the
  `faster-whisper` adapter is the single source: the `Settings` default, the template that
  `write_default_config` writes, and `doctor`'s download warning all read it, so no file drifts to
  another model — a test writes the default config and loads it back to prove it. `doctor` prints the
  measured download size for the configured model (`small` → 464 MB) and says "size unknown until it
  downloads" for a model it has no measurement for, because a guessed size is worse than an admitted
  gap. Measured: `tiny` 75 MB, `base` 142 MB, `small` 464 MB, `large-v3-turbo` 1.6 GB.

- **AC-50 — a recording that produced nothing says why.** `flyon listen` reports the loudest frame it
  saw on every stream, and when a stream produced no lines it names the cause: nothing arrived (muted,
  suspended bluetooth, wrong device), audio arrived but stayed below `voice_threshold` (lower it or
  raise the gain), or audio cleared the threshold but every burst was shorter than `min_segment_ms`.
  "0 lines" on its own is not a diagnosis — it is the one output that leaves the user with nothing to
  act on.

- **AC-51 — a WAV file is a capture source, so the loop is testable without a device.** `flyon listen
  --source wav:<file>` replays a 16 kHz mono `s16le` WAV on the microphone stream and declares the
  system stream silent, because a fixture is one voice; a file in the wrong format is one
  `CapturerError` naming the exact `ffmpeg` command, and both streams still share the frame timeline.
  The point is diagnostic: with a real model this transcribes the committed fixture end to end
  through the CLI with no sound card anywhere, which is the only way to tell "the pipeline is broken"
  apart from "your microphone is not delivering audio".

- **AC-52 — the language is decided once per session, not per segment.** With `language` empty the
  adapter votes on what each call detected, weighting by audio length and confidence, and pins the
  winner once ~6 s has been heard; every later call is decoded as that language. An explicit
  `language = "pl"` in the config, or `flyon listen --language pl`, skips detection entirely. Whisper
  decodes one language per call and cannot switch inside one, so the honest claim is one language per
  session chosen from evidence — measured on a 19 s Polish clip, the transcript came back Polish, where
  guessing from 1.5 s fragments labelled Polish as Hungarian and transliterated it.

- **AC-53 — the three things the app trusts are the three things it validates.** A `Session.session_id`
  is a filename-safe token (`[A-Za-z0-9_-]{1,64}`), because that value names a file in both stores and in
  the notes directory — so a session id can never arrive at the filesystem as a path. The notes host must
  be an `http(s)` URL, so a config cannot aim `urlopen` at `file:` or a custom scheme. The prompt states
  that the transcript is data and not instructions, because anyone in the meeting can put a sentence in
  it. Workflows declare `permissions: contents: read` unless a job needs more, so the token CI holds is
  the smallest one it can do the work with.

**Still to build:** nothing for M2; M3 (notes) is untouched.

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

**Built** for a local provider; a cloud provider is the unscheduled slice below. Ollama is verified
against a stub transport, not yet against a daemon on the host — that is the one row missing from
`docs/VERIFICATION.md`.

- **AC-43 — a note has four parts and refuses half of one.** `Note(summary, decisions, actions,
  questions)` requires a stripped, non-empty summary and rejects a blank bullet; empty sections are
  allowed, because plenty of meetings decide nothing. A provider answer that is prose, or JSON with no
  summary, is a `NotesError` — not a note with an empty summary.
- **AC-44 — every provider satisfies one port.** `tests/contract/test_notes.py` runs a scripted
  provider and the Ollama adapter (driven by a stub transport) through the same criteria: it names
  itself, it answers with a `Note`, an empty transcript raises `NotesError` without a call, and every
  failure surfaces as `NotesError` so the CLI has one path to report. A second backend costs one line
  in that parametrization.
- **AC-45 — the prompt is the contract.** One set of instructions and one JSON schema
  (`app/prompt.py`) serve every provider; the transcript reaches the model one line per utterance with
  its `mm:ss` offset and its stream. Reading an answer tolerates the key names models reach for
  (`actions` for `action_items`), drops blank bullets, and turns anything unusable into `NotesError`.
- **AC-46 — `flyon summarize <prefix>` writes the minutes.** The note lands in `<data-dir>/notes/` as
  markdown with front-matter (`session`, `date`, `duration`, `streams`, `lines`) and four sections —
  summary, decisions, action items, open questions — with `- none` where a section is empty. An open
  (interrupted) session can be summarised too; its duration says `unknown`.
- **AC-47 — a failed provider call leaves no note behind.** The provider is called before anything is
  rendered or written, and the write goes through a temporary file in the target directory, so there
  is no state in which a half-written note looks finished.
- **AC-48 — the default install cannot send a transcript anywhere.** `[notes] provider` is empty by
  default; `summarize` then exits 2 naming the setting, without creating a notes directory. An unknown
  provider name is the same shape of error, an unreachable daemon is exit 1 with the `ollama serve`
  hint, and `--provider fake` proves the whole path offline.
- **AC-49 — `output.extra_copy` gets identical bytes.** With a copy directory configured, the vault
  copy is the same file content, written by the same call — not a second render that could differ.

## Later — cloud engines (not scheduled)

Decided 2026-11-17: v0.1 stays local. Live transcription is the goal, and a cloud engine is the
obvious escape hatch when local latency or accuracy is not enough — it is one more `Transcriber`
adapter, not a redesign, because the port is already a synchronous call per segment. Recorded here so
the pricing work is not thrown away. Nothing below is scheduled and none of it is verified by us.

| Engine | Call | Price | Limits that matter |
|---|---|---|---|
| DeepSeek ASR | `POST https://api.deepseek.com/v1/tools/asr`, multipart WAV/Ogg | $0.116/hr list, $0.058 promotional | ≤120 s and ≤8 MiB per request, no streaming, 21 languages auto-detected (Polish included), content checks can refuse a segment |
| Groq `whisper-large-v3-turbo` | the OpenAI-compatible `audio/transcriptions` endpoint | $0.04/hr | ~216x realtime, word error rate 12%; bills a 10 s minimum per request, so 5 s segments cost double |
| Groq `whisper-large-v3` | same endpoint | $0.111/hr | ~189x realtime, word error rate 10.3% |

Our segments are capped at 15 s, so DeepSeek's 120 s ceiling is not a constraint, and an hour of
meeting costs about 12 cents there. What has to exist before any of them lands: an ADR for "audio
leaves the machine" — what is sent, what is retained, what happens to a refused or failed segment —
the same contract-test line the other engines get, and a measured latency and accuracy row in
`docs/VERIFICATION.md` on the same fixtures. A closed model with no published weights cannot be
argued into the default; it has to be measured against a local one.

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
| AC-32, AC-35 | `tests/contract/test_transcriber.py` |
| AC-33 … AC-34 | `tests/unit/test_faster_whisper.py` |
| AC-36 … AC-38 | `tests/unit/test_session.py` |
| AC-39 … AC-40 | `tests/unit/test_listen.py` |
| AC-41 | `tests/e2e/test_real_whisper.py` |
| AC-42 | `tests/unit/test_config.py`, `tests/unit/test_cli.py` |
| AC-43 | `tests/unit/test_note.py` |
| AC-44 | `tests/contract/test_notes.py`, `tests/unit/test_ollama.py` |
| AC-45 | `tests/unit/test_prompt.py` |
| AC-46 … AC-49 | `tests/unit/test_notes_app.py`, `tests/unit/test_cli.py` |
| AC-50 | `tests/unit/test_render.py`, `tests/unit/test_session.py`, `tests/unit/test_listen.py` |
| AC-51 | `tests/unit/test_wav_capturer.py`, `tests/contract/test_capturer.py`, `tests/e2e/test_real_whisper.py` |
| AC-52 | `tests/unit/test_faster_whisper.py`, `tests/unit/test_wiring.py` |
| AC-53 | `tests/unit/test_transcript.py`, `tests/unit/test_ollama.py`, `tests/unit/test_prompt.py` |
| config load + overrides | `tests/unit/test_config.py` |

## Out of scope

Identical to the engineering note's non-goals: no TUI, no diarization, no torch, no async rewrite, no
GUI or web dashboard, no cloud sync, no recording of third parties in fixtures — synthetic audio only.
Cloud *engines* are the separate, unscheduled item above; cloud *sync* of transcripts stays out.

## Open questions

Nothing blocking M1. Deferred, with the slice that owns each:

1. Should `show` re-order interleaved `mic`/`system` lines, or keep each stream's blocks? (M2, once
   real interleaving exists.)
2. Retention: does the JSONL transcript get rotated, or is deleting a session an explicit command?
   (M3.)
3. Does `summarize` accept a partial range (`--from 12:30`)? (M3.)

---

[back to contents](#contents)
