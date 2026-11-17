# 002 — faster-whisper is the default transcription engine

Date: 2026-11-16
Status: accepted

## Context

The two credible local paths are `openai-whisper` (reference implementation, PyTorch) and
`faster-whisper` (CTranslate2 backend). PyTorch is a ~2 GB dependency, slow on CPU, and drags its own
CUDA matrix into a tool that is supposed to install in one command.

## Decision

`faster-whisper` with the `large-v3-turbo` model is the default. Other engines — `whisper.cpp`, Groq,
a local Ollama-backed notes model — are adapters behind the `Transcriber` port.

## Consequences

- CTranslate2 wheels decide the Python floor; 3.14 is the target and 3.15 runs in CI so we notice
  early.
- First run downloads ~1.6 GB once, into `platformdirs`' cache dir, never into the repository.
- `flyon` inherits faster-whisper's quantisation options rather than writing its own kernels.
- No `torch`, anywhere, in any dependency of this project.
