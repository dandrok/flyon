# AGENTS.md

How an agent should work in this repository. The product rules are in `spec.md`, the architecture in
`DESIGN.md`; this file is about not breaking either.

## Before you change anything

1. Read `spec.md` for the acceptance criteria of the slice you are on. If a change has no criterion,
   write the criterion first.
2. Read the ADR that covers the area (`docs/adr/`) before arguing with it. If you disagree, add a new
   numbered ADR that supersedes it — do not edit history into agreement.

## Layering, non-negotiable

- `domain/` — standard library only. No I/O, no clock, no network, no pydantic. mypy strict.
- `ports/` — `Protocol`s importing `domain` only.
- `adapters/` — implement a port. Never import `cli/`.
- `cli/` — imports anything, imported by nothing.

A change that makes `domain/` import an adapter is rejected regardless of how well it works.

## Every slice

1. Write the failing test for the acceptance criterion.
2. Make it pass with the smallest change that keeps the layering rule.
3. `make check` — raw, never piped through `head`/`grep`, so the exit code is the real one.
4. One `CHANGELOG.md` line, in user language ("`flyon show` accepts a session-id prefix").
5. Update the README/DESIGN statement the change makes untrue.

## Things that get rejected in review

- a new runtime dependency without a floor **and** a cap in `pyproject.toml`, and a reason in the PR;
- a `print()` on stdout in a `--json` path (it belongs on stderr);
- a port with adapters and no parametrized contract test;
- audio, transcripts or model files committed to git;
- `torch`, `openai-whisper`, or an async rewrite "for performance".

## Where things go

| You are adding | File |
|---|---|
| a rule about where a segment ends | `src/flyon/domain/segment.py` + `tests/unit/test_segment.py` |
| a new capture source | `src/flyon/adapters/capture/<name>.py` + `tests/contract/test_capturer.py` |
| a new engine | `src/flyon/adapters/stt/<name>.py` + one line in the contract test's parameters |
| a new store | `src/flyon/adapters/store/<name>.py` + `tests/contract/test_store.py` |
| a command | `src/flyon/cli/main.py`, rendering in `cli/render.py`, payload test in `tests/unit/test_cli.py` |
| a decision | `docs/adr/NNN-title.md`, numbered, immutable |
