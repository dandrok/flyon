# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Below `1.0.0` a **minor** bump means an
existing database or CLI invocation may stop working; a patch bump never does.

## [Unreleased]

### Added

- Real audio capture: one `parec` process per stream (microphone and the default sink's monitor),
  raw `s16le` turned into 20 ms frames with an RMS level, fed to a single queue.
- `flyon doctor --probe [--seconds N]` records briefly and reports frames and peak level per stream,
  so "will this work in the meeting" has an answer that is not a PATH lookup.
- A scripted `fake` capturer, so the pipeline and the contract test run without a sound card.
- A transcription port with a `faster-whisper` adapter (lazy model load, one instance, engine and
  model written into every line) and a scripted `fake` engine for machines without a 1.6 GB model.
- `flyon listen`: records the microphone and the system audio, segments each stream, transcribes every
  segment as it closes, and saves the session. Ctrl-C finalises instead of discarding.
- `--source fake` and `--engine fake` run the whole loop with no microphone and no model download, so
  the pipeline is testable anywhere.
- The session loop cuts engine input to the exact segment boundaries and keeps only a bounded window
  of audio per stream, so a long meeting does not grow in memory.
- Verified against a real model: a `slow` test transcribes a committed speech clip with
  `faster-whisper` itself and asserts the words, the engine and the model it was attributed to.
  `docs/VERIFICATION.md` records what a download, a load and a segment actually cost on this machine.

### Changed

- The default model is now `small` (464 MB) instead of `large-v3-turbo`. Live transcription is the
  point and every call costs a full 30 s encoder window, so the big model spent ~7 s on a 5 s segment
  and fell behind a normal turn-taking pace on CPU; `small` answers in ~1.7 s and transcribed the
  measured fixture exactly. `model = "large-v3-turbo"` stays one config line away for reading a
  transcript afterwards. Measurements in `docs/VERIFICATION.md`, decision in `docs/adr/005`, and
  `doctor` now names the real download size for whichever model is configured.
- Voice activity detection is on in the `faster-whisper` adapter, so non-speech never reaches the
  decoder. Without it the default model answered `"You"` to two seconds of silence; with it, silence
  and loud noise both return nothing, and quiet segments are cheaper to skip than to decode.

### Infrastructure

- A tag-driven release pipeline: `make release VERSION=x.y.z` bumps the version and dates the
  changelog, and a `v*` tag runs the tests, verifies the wheel and publishes through PyPI trusted
  publishing (OIDC, no stored token). `docs/RELEASING.md` records when a version is worth shipping.

## [0.1.0] - 2026-11-17

### Added

- `flyon sessions`, `flyon show <id>` and `flyon doctor`, each with `--json` on the read commands.
- Two-stream segmenter: silence closes a segment, a monologue is cut at 15 s and continues.
- Session store with two interchangeable adapters, SQLite and append-only JSONL, selected with
  `store = "sqlite" | "jsonl"` in `config.toml`.
- Repository gates: ruff, mypy strict on `domain`+`ports`, pytest, a `--json` contract, CI on 3.14
  and 3.15, and a `make check` that runs exactly what CI runs.
