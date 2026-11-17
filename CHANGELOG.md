# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Below `1.0.0` a **minor** bump means an
existing database or CLI invocation may stop working; a patch bump never does.

## [Unreleased]

## [0.1.0] - 2026-11-17

### Added

- `flyon sessions`, `flyon show <id>` and `flyon doctor`, each with `--json` on the read commands.
- Two-stream segmenter: silence closes a segment, a monologue is cut at 15 s and continues.
- Session store with two interchangeable adapters, SQLite and append-only JSONL, selected with
  `store = "sqlite" | "jsonl"` in `config.toml`.
- Repository gates: ruff, mypy strict on `domain`+`ports`, pytest, a `--json` contract, CI on 3.14
  and 3.15, and a `make check` that runs exactly what CI runs.
