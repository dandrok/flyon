# flyon

![ci](https://github.com/dandrok/flyon/actions/workflows/ci.yml/badge.svg)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.14%2B-blue)

A fly on the wall: a local-first meeting transcriber for Linux. It records your microphone and your
computer's audio as **two separate streams**, transcribes each one as you talk, keeps an
append-only transcript, and writes the minutes on demand. Nothing leaves the machine unless you
configure a provider.

**Why two streams.** The microphone is you; the default sink's monitor is everyone else. Speaker
attribution then costs nothing and needs no diarization model — the stream a line came from *is* the
speaker. It is exact for the two-party case, which is the case a call actually is.

**Why live.** The transcript is the point while the call is happening, so the default model is chosen
to keep up rather than to win a benchmark: see [Models and speed](#models-and-speed).

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Models and speed](#models-and-speed)
- [Notes](#notes)
- [What it does not do](#what-it-does-not-do)
- [Where files go](#where-files-go)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Docs](#docs)
- [License](#license)

## Requirements

| | |
|---|---|
| OS | Linux with PipeWire or PulseAudio (`parec` or `pw-record` on `PATH`) |
| Python | 3.14 or newer — `uv` installs one if you have none |
| Disk | ~500 MB for the default model; 1.6 GB if you take `large-v3-turbo` |
| For notes | a local [Ollama](https://ollama.com) daemon, or any OpenAI-compatible chat server you point it at |

## Install

```bash
uv tool install --python 3.14 'flyon[stt] @ git+https://github.com/dandrok/flyon'
flyon doctor
```

`flyon doctor` is the first command to run: it checks Python, the data and cache directories, the
config, the store, the `stt` extra, the capture tools and the cached models, and it exits non-zero
only when something is actually broken. `--probe` also records a few seconds and reports frames and
peak level per stream — talk while it runs.

Once `0.1.0` is on PyPI the line becomes `uv tool install 'flyon[stt]'`. Until then, install from git.

From a checkout, if you want to work on it: `uv tool install --python 3.14 --editable "$PWD[stt]"`.

## Quick start

Start recording **during** a call, not before it — a Bluetooth headset only delivers audio while the
call is up:

```bash
flyon listen --title "weekly sync"     # talk; Ctrl-C stops and finalises
flyon show 6f4c                        # read the transcript back
flyon summarize 6f4c                   # write the minutes, once a provider is configured
```

Each segment prints as it is recognised:

```console
$ flyon listen --title "weekly sync"
recording mic, system · faster-whisper:small · Ctrl-C stops
00:00 mic    shall we start with the migration
00:01 system yes, I pushed the schema change last night
00:03 mic    then the backfill is the only thing left
00:06 system I can take that, it is maybe two days
^C4 lines · 4 segments (0 silent, 0 failed) · 00:07 · saved as 6f4c1a2b9d8e
loudest frame: mic 0.208 · system 0.188 · voice_threshold 0.02
```

That last line is the diagnostic: it says what the recording actually heard, and when a stream
produced nothing it names the reason — muted, suspended, below `voice_threshold`, or bursts shorter
than `min_segment_ms`.

## Commands

| Command | What it does |
|---|---|
| `flyon` | the last session in four lines, or what to do first |
| `flyon listen` | record both streams, transcribe live, save the session; Ctrl-C stops |
| `flyon sessions` | every session, newest first |
| `flyon show <id>` | one transcript, `mm:ss` per line, prefixed by stream |
| `flyon summarize <id>` | write the minutes: summary, decisions, action items, open questions |
| `flyon doctor` | environment check; `--probe [--seconds N]` records briefly and reports levels |
| `flyon config` | where `config.toml` lives; `--init` writes a commented file with the defaults |

Useful flags:

| Flag | On | Meaning |
|---|---|---|
| `--title "weekly sync"` | `listen` | name the session |
| `--language pl` | `listen` | pin the language for this meeting (otherwise decided once per session) |
| `--quiet` | `listen` | record without printing each line |
| `--source fake \| wav:<file>` | `listen` | replay a script, or a WAV, instead of the microphone |
| `--engine fake` | `listen` | scripted text instead of a model — the whole loop with no download |
| `--provider ollama \| fake` | `summarize` | override the configured notes provider |
| `--json` | `sessions`, `show` | print only the payload, so a script can consume it |

## Configuration

Every key is optional; the file is `~/.config/flyon/config.toml`. `flyon config` says where that is,
and `flyon config --init` writes a commented file holding these defaults.

```toml
store = "sqlite"         # sqlite (queryable) or jsonl (plain append-only files)
engine = "faster-whisper"
model = "small"          # 464 MB, ~1.7 s per segment: keeps up live on CPU
language = ""            # empty = decide once per session, then stick to it
                         # "pl" or "en" pins every segment, which is more accurate when a
                         # meeting is mostly one language with borrowed words

[segmenter]
voice_threshold = 0.02   # RMS level that counts as speech — lower it for quiet headsets
silence_ms = 800         # this much silence closes a segment
max_segment_ms = 15000   # a monologue is cut here and continues as the next segment
min_segment_ms = 250     # shorter than this is dropped as noise

[output]
extra_copy = ""          # e.g. "~/Documents/obsidian-root/Meetings" — the note, copied

[notes]
provider = ""            # "ollama" writes the minutes locally; empty = no note, no network call
model = "llama3.2"
host = "http://localhost:11434"
```

## Models and speed

Every `transcribe()` call pays a full 30 s encoder window, and the pipeline makes one call per
segment — so the cost is per segment, not per minute of meeting. Measured on a Ryzen 7 8845HS (16
threads, `int8`), median of five runs on a 5 s clip:

| Model | Download | Per 5 s segment | Keeps up live? |
|---|---|---|---|
| `tiny` | 75 MB | 0.39 s | yes, with word errors |
| `base` | 142 MB | 0.59 s | yes, some errors |
| **`small`** (default) | 464 MB | 1.70 s | yes, exact on clean speech |
| `large-v3-turbo` | 1.6 GB | 6.71 s | no — it falls behind turn-taking on CPU |

`large-v3-turbo` is the better model and stays one config line away for reading a transcript after the
call. The full tables, the per-model word accuracy and the reasoning are in
[`docs/VERIFICATION.md`](docs/VERIFICATION.md) and [`docs/adr/005`](docs/adr/005-small-model-on-cpu.md).

## Notes

`flyon summarize` sends the transcript to the configured provider and writes markdown into
`~/.local/share/flyon/notes/<session>.md`: front-matter (session, date, duration, streams) plus
summary, decisions, action items and open questions. With `[output] extra_copy` set you get an
identical copy there too — that is how a note reaches an Obsidian vault.

An unconfigured install cannot make a network call: `provider` is empty by default and `summarize`
exits 2 naming the setting. `--provider fake` proves the whole path offline. A failed provider call
leaves no note behind — the provider is asked before anything is written, and the write goes through
a temporary file.

## What it does not do

- **No diarization.** Two parties by stream; a third voice in the room is attributed to whichever
  device heard it.
- **One language per session.** Whisper decodes one language per call, so a sentence that is half
  Polish and half English comes back in the session's language, English words included.
- **Not a meeting bot.** It records this machine's audio: to capture the other side you have to be in
  the call on this machine.
- **No cloud sync, no GUI, no summarising service.** Transcripts are files; notes need a local
  provider.
- **Linux for capture** — the capture adapters are PipeWire/PulseAudio. The store, the notes and the
  model run anywhere Python does.

## Where files go

| Path | Contents | Override |
|---|---|---|
| `~/.local/share/flyon/` | SQLite database or JSONL transcripts, and `notes/` | `--data-dir` |
| `~/.cache/flyon/` | downloaded Whisper models | `--cache-dir` |
| `~/.config/flyon/config.toml` | engine, model, thresholds, providers | `--config` |

Nothing is written inside a repository, ever.

## Troubleshooting

**Zero lines, and it saved a session.** Read the `loudest frame:` line. `0.000` means nothing arrived
— a suspended Bluetooth device, a muted microphone, or the wrong default source. A value under
`voice_threshold` means the level; lower the threshold or raise the input gain. The
[Bluetooth notes](docs/VERIFICATION.md#a-real-call--2026-11-17) are worth reading before a call.

**Microphone works in `doctor --probe` but not in `listen`.** Start `listen` during the call: a
headset's microphone only comes up while the call holds it.

**The pipeline itself.** Prove it without a device:

```bash
flyon listen --source fake --engine fake                    # scripted, no model
flyon listen --source wav:$HOME/git/flyon/tests/fixtures/speech/start-with-the-migration.16k.wav
```

The second one runs a real 16 kHz mono WAV through capture, segmentation, the model and the store. If
that transcribes and a live recording does not, the pipeline is fine and the device is the problem.

## Development

```bash
make venv     # .venv on 3.14
make check    # lint + types + tests
make ci       # the whole GitHub job, in a venv without the extras
make e2e      # slow tests; the real-model one needs `uv sync --extra stt`
```

## Docs

- [`spec.md`](spec.md) — what each milestone must do, as testable criteria
- [`DESIGN.md`](DESIGN.md) — the pipeline, the ports, and the trade-offs behind them
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — what has actually been measured on real hardware
- [`docs/adr/`](docs/adr/) — one decision per file
- [`docs/RELEASING.md`](docs/RELEASING.md) — when a version is worth publishing, and how
- [`AGENTS.md`](AGENTS.md) / [`CONTRIBUTING.md`](CONTRIBUTING.md) — how work reaches `main`

## License

MIT. See [`LICENSE`](LICENSE).

---

[back to contents](#contents)
