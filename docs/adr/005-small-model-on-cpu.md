# 005 — `small` is the default transcription model on CPU

Date: 2026-11-17
Status: accepted
Supersedes: the model choice in ADR 002 (the engine choice there stands)

## Context

ADR 002 picked `faster-whisper` with `large-v3-turbo`: one download, best text from the first meeting.
That reasoning assumed accuracy is the scarce resource. `docs/VERIFICATION.md` measured what the shape
of this pipeline actually charges for: the session loop calls the engine **once per segment**, and
every call pays a whole 30 s encoder window, so cost is per segment rather than per minute.

On this machine (Ryzen 7 8845HS, 16 threads, `int8`):

| model | download | per 5 s segment | errors on the fixture |
|---|---|---|---|
| `tiny` | 75 MB | 0.39 s | 4 |
| `base` | 142 MB | 0.59 s | 1 |
| `small` | 464 MB | 1.70 s | 0 |
| `large-v3-turbo` | 1.6 GB | 6.71 s | 0 |

A meeting where someone speaks every 5 s produces ~12 segments a minute. `large-v3-turbo` therefore
needs ~81 s of CPU per meeting-minute: it falls behind in exactly the case the product exists for.
`small` needs ~20 s, which leaves 3x headroom, and it transcribed the measured paragraph exactly.
Beam size is not a lever — the encoder window dominates, and `beam_size=1` saves 10–20%.

Live transcription is the decided use case; reading a transcript afterwards is "extra".

## Decision

`small` is `DEFAULT_MODEL`. `large-v3-turbo` stays one config line away — `model = "large-v3-turbo"` —
for the read-it-afterwards case, a GPU, or a machine with CPU to spare.

`DEFAULT_MODEL` in the adapter is the single source of truth: the `Settings` default, the generated
config template and `doctor`'s download warning all read it, and `doctor` names the measured size
(464 MB) or admits it does not know one.

## Consequences

- First run downloads 464 MB instead of 1.6 GB, on a CPU that has to keep up live.
- Word accuracy on hard audio is slightly below `large-v3-turbo`. Accepted: a line that arrives 1.7 s
  late beats a better line that arrives after the meeting.
- The evidence is **one synthetic 22 s paragraph** of clean espeak speech. A real two-speaker call,
  with a Bluetooth microphone, will move these numbers; if the real meeting says `small` is not good
  enough, the answer is measured in `docs/VERIFICATION.md` and this ADR is revised, not quietly
  overwritten.
- A cloud engine (DeepSeek ASR, Groq — recorded in `spec.md` as a later, unscheduled slice) is the
  escape hatch if local accuracy or latency stops being acceptable. It is a second adapter behind the
  same port, and it costs an ADR of its own, because it sends meeting audio off the machine.
- `small` invents a word on silence where `tiny` did not (`"You"`, measured), which the AC-41 test
  caught on the first run with the new default. `vad_filter` is now on in the adapter and that is the
  rule for any engine that has a VAD to offer: non-speech is removed before the decoder sees it.
