# 001 — Record microphone and system audio as two streams

Date: 2026-11-16
Status: accepted

## Context

A meeting has two acoustic sources: the room (microphone) and the call (system output). One mixed
capture loses the boundary; recovering it afterwards needs a diarization model, which is
probabilistic, downloads hundreds of megabytes, and is wrong exactly when someone talks over someone
else.

## Decision

Capture both sources independently, segment and transcribe each on its own timeline, and merge the
resulting lines by start time.

## Consequences

- Speaker attribution is exact for the two-party case, with no model and no training data.
- Two clocks, two segmenters and a merge rule are ours to maintain, and the merge must be tested.
- A meeting with three people in one room still cannot be separated — that is what diarization would
  buy, and it is a non-goal for v1.
