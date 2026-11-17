# 004 — Releases are tag-driven, not bot-driven

Date: 2026-11-17
Status: accepted

## Context

Two credible shapes: a release bot (`release-please`) that keeps a "chore: release" PR open, bumps the
version from conventional commits and tags automatically on merge; or a tag that a human pushes after
merging a prepared release commit.

The bot is less typing and its changelog is generated. It is also a second actor in a repository whose
changelog is written in user language on purpose, and whose releases are rare (one per milestone, not
one per week).

## Decision

Tag-driven. `make release VERSION=x.y.z` edits exactly two files (version in `pyproject.toml`, the
dated section in `CHANGELOG.md`), prints the commands that follow, and stops. A human commits, opens
the PR, and pushes the tag. The pipeline then tests, builds, verifies the wheel and publishes through
OIDC.

## Consequences

- The changelog stays hand-written: five lines that say what changed for a user, not every commit
  subject with a scope prefix.
- Three visible steps instead of one merge: version, changelog, tag. Slower, and the reason the wrong
  commit is much harder to tag.
- No bot token, no bot commits, no "release PR" to keep rebasing.
- Migrating to `release-please` later is a workflow file and a config file; nothing in the code
  depends on how the version got its number.
