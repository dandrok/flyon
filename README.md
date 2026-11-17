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

`0.1.0` — transcript core and capture. Two-stream segmentation, the session store, the read
commands, and real audio capture from the microphone plus the default sink's monitor all work and are
tested. Speech-to-text and `flyon listen` are the next slice; see [`spec.md`](spec.md) for the
milestone map and the acceptance criteria behind every command.

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
| `flyon doctor --probe` | records two seconds and reports frames + peak level per stream |

Every read command takes `--json` and prints nothing else in that mode, so a script can consume
it without stripping human chatter off the front.

## One worked example

A machine that has recorded nothing answers like this — two lines, and the next thing to type:

```console
$ flyon
no sessions yet on this machine
flyon doctor   check the microphone, the model and the store
```

With one 12½-minute meeting in the store (the same shape `flyon listen` will write once capture
lands):

```console
$ flyon sessions
ID        STARTED           DURATION  LINES  TITLE
6f4c1a2b  2026-11-17 10:04     12:31      4  weekly sync

$ flyon show 6f4c
weekly sync 6f4c1a2b · 2026-11-17 10:04 · 4 lines
00:00 mic    morning — shall we start with the migration?
00:01 system yes, I pushed the schema change last night
00:03 mic    then the backfill is the only thing left
00:06 system I can take that, it is maybe two days

$ flyon sessions --json
{"sessions": [{"id": "6f4c1a2b9d8e", "started_at": "2026-11-17T10:04:00+00:00", "ended_at": "2026-11-17T10:16:31+00:00", "duration_ms": 751000, "title": "weekly sync", "lines": 4}]}
```

The `mic` / `system` prefix is the whole point: the speakers are separated by which stream the words
came from, with no diarization model involved.

## Where files go

Nothing assumes an Obsidian vault exists. The state directory is `platformdirs`' user data dir.

| Path | Contents | Override |
|---|---|---|
| `~/.local/share/flyon/` | SQLite database, JSONL transcripts | `--data-dir` |
| `~/.cache/flyon/` | downloaded Whisper models | `--cache-dir` |
| `~/.config/flyon/config.toml` | engine, model, thresholds | `--config` |

## Configuration

```toml
store = "sqlite"         # sqlite (queryable) or jsonl (plain append-only files)
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
