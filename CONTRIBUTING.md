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

## Branching and PRs

`main` is only ever updated by a squash-merged pull request. Never commit to it directly, not even
for a one-line docs fix — the branch protection rules below are there to make that a rule and not a
habit.

| Branch prefix | For |
|---|---|
| `feat/` | a new command, port, or adapter |
| `fix/` | a bug, with the test that reproduces it |
| `chore/` | gates, CI, dependencies, repo hygiene |
| `docs/` | README, DESIGN, ADRs, the spec |
| `test/` | tests only, including real-audio and real-model verification |

Rules:

1. Branch from `main`, one slice per branch, conventional-commit title (`feat: ...`).
2. The PR body uses the template: what changed, how it was verified, which gate proves it.
3. Squash merge only; the PR title becomes the commit subject, so it must read as a changelog line.
4. A branch that changes behaviour without touching `spec.md` or `CHANGELOG.md` is incomplete.

`gh pr create --fill` after the first push, or open the compare link GitHub prints.

## Commit style

Conventional commits, one slice per PR: `feat:`, `fix:`, `chore:`, `docs:`, `test:`. Squash merge,
linear history. The PR body answers three questions: what changed, how it was verified, which gate
proves it.
