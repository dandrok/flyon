# Contributing

## Setup, three commands

```bash
uv sync --python 3.14
uv run pre-commit install --install-hooks
make check
```

## Gates

| Ring | Command | Target |
|---|---|---|
| format + lint | `make lint` | instant |
| types (strict, domain+ports) | `make types` | < 5 s |
| tests | `make test` | < 10 s |
| all of it | `make check` | the same commands CI runs |

`make check` is not a suggestion: CI runs the identical invocations, so a green local run and a red
PR mean the environment differs, not the commands.

## Commit style

Conventional commits, one slice per PR: `feat:`, `fix:`, `chore:`, `docs:`, `test:`. Squash merge,
linear history. The PR body answers three questions: what changed, how it was verified, which gate
proves it.
