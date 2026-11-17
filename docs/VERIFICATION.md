# Verification — what has actually been measured

`spec.md` states criteria; this file records the measurements behind the ones that cost real audio or
a real model. Numbers here are observations with a date and a machine, not promises — re-measure
before quoting them.

## Contents

- [The machine](#the-machine)
- [Capture — AC-27](#capture-ac-27)
- [Transcription — AC-41](#transcription-ac-41)
- [Cost is per segment, not per minute](#cost-is-per-segment-not-per-minute)
- [What this decided](#what-this-decided)
- [Hallucination on non-speech — and the fix](#hallucination-on-non-speech--and-the-fix)
- [Still not verified](#still-not-verified)
- [How to reproduce](#how-to-reproduce)

## The machine

| Thing | Value |
|---|---|
| CPU | AMD Ryzen 7 8845HS, 16 hardware threads (8 cores), no GPU |
| OS / Python | Linux 7.2.15, Python 3.14, `faster-whisper` 1.2.1, `ctranslate2` 4.9.0 |
| Compute type | `int8` (the adapter default), `device=cpu`, `beam_size=5` |
| Date | 2026-11-17 |
| Scope | capture row from an earlier session on the same machine; every transcription row measured here, 16 threads |

Fixtures, all mono `s16le` at 16 kHz — exactly what `parec` hands the pipeline:

| Fixture | Length | Source |
|---|---|---|
| `tests/fixtures/speech/start-with-the-migration.16k.wav` | 2.3 s | `espeak-ng 1.52`, committed |
| one spoken paragraph, 22 s | 21.8 s | same text, generated for this measurement |
| the same paragraph cut to 5 s | 5.0 s | derived |

Everything below is synthetic speech. It is a good enough judge of *wiring* and of *relative speed*;
it is not a real meeting.

## Capture — AC-27

Recorded on this machine with `flyon doctor --probe` against real `parec`:

| Stream | Frames | Window | Peak level | Expected |
|---|---|---|---|---|
| 440 Hz tone at 0.366 full scale | 148 | 3.1 s | 0.261 | 0.366 / √2 = 0.259 |

Both streams (microphone and the default sink's monitor) delivered at 20 ms per frame with no gaps.
Idle Bluetooth devices report `SUSPENDED` and show ~30 frames in 2 s at peak 0.000 — idle hardware,
not a defect.

## Transcription — AC-41

`tests/e2e/test_real_whisper.py`. Models cached, so `load` is a warm load; a cold first load also
downloads, and `large-v3-turbo` needs ~38 s for download plus int8 conversion. The 5 s column is the
median of five consecutive runs (the spread in brackets), the 22 s column a single run.

| Model | Download | Warm load | 5 s clip | 22 s clip | Realtime factor at 22 s |
|---|---|---|---|---|---|
| `tiny` | 75 MB | 1.17 s | 0.39 s (0.34–0.48) | 1.02 s | 0.047x (21x faster than realtime) |
| `base` | 142 MB | 0.56 s | 0.59 s (0.57–0.61) | 1.08 s | 0.049x |
| `small` | 464 MB | 0.54 s | 1.70 s (1.61–1.72) | 2.65 s | 0.121x |
| `large-v3-turbo` | 1.6 GB | 1.49 s | 6.71 s (6.46–8.02) | 7.76 s | 0.353x (2.8x faster than realtime) |

Wording on the same 22 s paragraph, verbatim:

| Model | Errors | Transcription |
|---|---|---|
| `tiny` | 4 | "…the **Mac feel** is the only thing left. I can take **Matt**… before **an animal** on Friday. **And the thing** else on the agenda…" |
| `base` | 1 | "…the **Mac fill** is the only thing left…" — everything else right |
| `small` | 0 | exact |
| `large-v3-turbo` | 0 | exact |

The 1.5 s cut of the fixture ("shall we start with the migration") returns text on every model —
`tiny`: "shall we start with my brain", `small`: "shall we start with the migra-", `large-v3-turbo`:
"shall we start with the mig-" — and finished words on none of them, because a clipped word is a
different word. That is why AC-41 asserts *text arrives* at segment length rather than which text.

## Cost is per segment, not per minute

The number that matters for a live meeting is the cost of **one `transcribe()` call**, because the
session loop calls the engine once per segment. Compare the 5 s and 22 s columns above: for
`large-v3-turbo` the cost barely moves (6.7 s → 7.8 s for 4.4x the audio), because Whisper runs a
30 s encoder window whatever you hand it and that window is the bill. The small models do grow with
length (`tiny` 0.39 → 1.02 s), but from a floor that is already cheap.

So the segmenter's shape sets the cost. A meeting where someone speaks every 5 s produces ~12
segments a minute, and the CPU time needed to keep up with one minute of it is:

| Model | CPU per meeting-minute | Verdict |
|---|---|---|
| `tiny` | ~5 s | 12x headroom |
| `base` | ~7 s | 8x headroom |
| `small` | ~20 s | 3x headroom |
| `large-v3-turbo` | ~81 s | **falls behind by ~1.3x** |

`large-v3-turbo` stays ahead only while segments average longer than ~7 s. Long monologues are
cheap; a fast back-and-forth with the 15 s cap never reached is expensive. On a single core it is
worse than that: one 22 s clip took 120 s there (5.5x *slower* than realtime).

Beam size is not the lever: `beam_size=1` saved 10–20% across the models, because the encoder window
dominates, not the decoder.

## What this decided

`spec.md` and `ADR 002` shipped `large-v3-turbo` by default, on the reasoning that accuracy is what
matters. The measurement says that reasoning misses the shape of the pipeline: the engine is called
once per segment, so a model that spends 7 s per call cannot keep up live — and live is the use case.

Decided (ADR 005): **`small` is the default**, `large-v3-turbo` stays one config line away for reading
a transcript afterwards or for a GPU. `small` transcribes the measured paragraph exactly at ~1.7 s per
segment, 464 MB, ~3x realtime headroom at a turn-taking pace.

Two things this deliberately does not claim:

- **The evidence is one synthetic paragraph.** Clean espeak speech, one voice, 22 s. A real
  two-speaker call over a Bluetooth microphone will be worse for every model here; the *relative*
  speeds will hold, the absolute word accuracy will not.
- **Cloud engines are not ruled out.** DeepSeek ASR (`$0.058–0.116/hr`, ≤120 s per request, no
  streaming) and Groq (`$0.04/hr` for `whisper-large-v3-turbo`, measures a 10 s minimum per request)
  are recorded in `spec.md` as a later slice. Neither is measured here, so neither is a
  recommendation: a closed model with no published weights has to be measured against a local one
  before it can become a default.

## Hallucination on non-speech — and the fix

Whisper invents a word when it has nothing to hear, and whether it does is model-specific: `tiny`
returned `""` for two seconds of digital silence, `small` returned `"You"`. That is exactly why the
silence check is a test and not an assumption — it failed on the first run with the new default.

Fix: `vad_filter=True` in the adapter (Silero VAD ships inside faster-whisper). Non-speech is dropped
before the decoder runs:

| input, 2 s | `small`, `vad_filter=False` | `small`, `vad_filter=True` |
|---|---|---|
| digital silence | `"You"` | `""` |
| noise at 5% amplitude (clears `voice_threshold`) | not measured | `""` |
| the 2.3 s speech fixture | exact | exact |

Skipping silence is also cheaper than decoding it: 77 s versus 36 s for the same 2 s of zeros on the
1-vCPU box.

Why it matters even though the segmenter already gates on level: the gate only catches *quiet*
non-speech. A keyboard, a door, a cough loud enough to clear `voice_threshold` used to reach the
decoder and could come back as a line. Now it reaches the VAD first.

## Still not verified

- A real meeting: microphone plus system audio, 5 minutes, two speakers, `large-v3-turbo`. That is
  M2's stated exit gate, and it needs a call in progress — `flyon listen` on a real machine.
- `Ctrl-C` behaviour inside a real terminal with a real recording in flight (tested with fakes only).
- The first-run download inside `listen` (doctor warns first; the download itself is verified here).
- Bluetooth microphone and sink in a live call. Both report `SUSPENDED` when idle, so the probe that
  proves them has to run during the call.

## How to reproduce

```sh
uv sync --extra stt            # faster-whisper, ctranslate2, numpy
make e2e                       # the slow tests, tiny by default (75 MB, cached under ~/.cache/flyon)
FLYON_TEST_WHISPER_MODEL=large-v3-turbo uv run pytest tests/e2e/test_real_whisper.py -m slow -s
```

`-s` shows the printed line: audio length, first-call time (load included), warm time, realtime
factor. The cost and word-accuracy tables above came from throwaway scripts against the same adapter
— two clip lengths, four models, five repetitions of the short one — which is why they are numbers in
this file and not assertions in a test.

---

[back to contents](#contents)
