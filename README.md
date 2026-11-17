# flyon

A fly on the wall: a local-first meeting transcriber. It records the microphone and the system
audio as two separate streams, transcribes each one live, keeps an append-only transcript, and
writes structured notes on demand. Audio stays on your machine unless you configure a cloud engine.

## Contents

- [Status](#status)
- [Install](#install)
- [The commands that exist today](#the-commands-that-exist-today)
- [One worked example](#one-worked-example)
- [Where files go](#where-files-go)
- [Configuration](#configuration)
- [Development](#development)
- [Docs](#docs)

## Status

`0.1.0` — the transcript core. Two-stream segmentation, the session store, and the read commands
work and are tested. Live capture and speech-to-text land in the next slice; see
[`spec.md`](spec.md) for the milestone map and the acceptance criteria behind every command.

## Install

```bash
# from a checkout, today
uv sync --python 3.14
uv run flyon --version

# once the capture slice ships
uv tool install flyon
```

## The commands that exist today

| Command | What it does |
|---|---|
| `flyon` | last session in four lines, or what to do first |
| `flyon sessions` | every session, newest first |
| `flyon show <id>` | one transcript, `mm:ss` per line, prefixed by stream |
| `flyon doctor` | environment check: python, data dir, config, store, STT extra, capture tools |

Every read command takes `--json` and prints nothing else in that mode, so a script can consume
it without stripping human chatter off the front.

## One worked example

```bash
$ flyon
no sessions yet — run `flyon listen` once capture lands, or `flyon doctor` to check the machine

$ flyon sessions --json
{}

$ flyon show 6f4c
flyon: no session matches '6f4c'
```

Once a session exists (the store tests create one), the same commands answer:

```bash
$ flyon sessions
ID        STARTED            DURATION  LINES  TITLE
6f4c1a2b  2026-11-17 10:04       12:31     84  weekly sync
```

## Where files go

Nothing assumes an Obsidian vault exists. The state directory is `platformdirs`' user data dir.

| Path | Contents | Override |
|---|---|---|
| `~/.local/share/flyon/` | SQLite database, JSONL transcripts | `--data-dir` |
| `~/.cache/flyon/` | downloaded Whisper models | `--cache-dir` |
| `~/.config/flyon/config.toml` | engine, model, thresholds | `--config` |

## Configuration

```toml
engine = "faster-whisper"
model = "large-v3-turbo"
language = ""            # empty = autodetect

[segmenter]
voice_threshold = 0.02   # RMS level that counts as speech
silence_ms = 800         # this much silence closes a segment
max_segment_ms = 15000   # a monologue is force-cut here and continues
min_segment_ms = 250     # shorter than this is dropped as noise

[output]
extra_copy = ""          # e.g. "~/Documents/obsidian-root/Meetings"
```

## Development

```bash
make venv     # .venv on 3.14
make check    # lint + types + tests, the same commands CI runs
make e2e      # slow tests
```

## Docs

- [`spec.md`](spec.md) — what each milestone must do, as testable criteria
- [`DESIGN.md`](DESIGN.md) — the pipeline, the ports, and the trade-offs behind them
- [`AGENTS.md`](AGENTS.md) — how an agent should work in this repo
- [`docs/adr/`](docs/adr/) — one decision per file

---

[back to contents](#contents)
