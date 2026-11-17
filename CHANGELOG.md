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

## [0.1.0] - 2026-11-17

### Added

- `flyon sessions`, `flyon show <id>` and `flyon doctor`, each with `--json` on the read commands.
- Two-stream segmenter: silence closes a segment, a monologue is cut at 15 s and continues.
- Session store with two interchangeable adapters, SQLite and append-only JSONL, selected with
  `store = "sqlite" | "jsonl"` in `config.toml`.
- Repository gates: ruff, mypy strict on `domain`+`ports`, pytest, a `--json` contract, CI on 3.14
  and 3.15, and a `make check` that runs exactly what CI runs.
