# 003 — No PyTorch, no LangChain, no async rewrite

Date: 2026-11-16
Status: accepted

## Context

Both are the obvious defaults in this space and both are tempting: `torch` because every Whisper
recipe uses it, an agent framework because "notes" sounds like an LLM chain, `asyncio` because audio
feels concurrent.

## Decision

None of the three. CTranslate2 for inference, `httpx` for cloud calls, one capture thread and one
worker queue for concurrency.

## Consequences

- An install is tens of megabytes, not gigabytes, and fits in a wheel a user will actually install.
- Concurrency is a `queue.Queue` with a stop sentinel: no event loop, no coloured functions, no
  `asyncio` leaking into the CLI.
- Notes generation is one prompt and one HTTP call. If it ever needs a chain, that is a new ADR with
  a job to do, not a framework to grow into.
