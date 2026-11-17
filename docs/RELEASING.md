# Releasing

## Contents

- [When to release](#when-to-release)
- [The one-time setup only you can do](#the-one-time-setup-only-you-can-do)
- [Cutting a release](#cutting-a-release)
- [What the pipeline does](#what-the-pipeline-does)
- [If a release is wrong](#if-a-release-is-wrong)

## When to release

Publish when the version does something a stranger can use, not when the repo is tidy.

| Version | Bar |
|---|---|
| `0.1.0` | `listen` records and transcribes a real meeting, and `show` reads it back |
| `0.2.0` | notes on demand (`summarize`) and the optional vault copy |
| `1.0.0` | the CLI and the database schema are stable; a minor bump no longer breaks them |

The first upload **claims the PyPI name permanently** — a release can be yanked but never deleted, and
the version number is never reusable. That is why this took until 0.1.0 had transcribed a real call and
written a real note: a name is worth claiming once the thing under it works, not before.

## Rehearse on TestPyPI first

TestPyPI is a separate index with the same publishing machinery, and nothing there is permanent. Run
the rehearsal before the real thing, because the first real upload is the one that cannot be undone:

1. Create an account on <https://test.pypi.org> and a **pending publisher** for a project called
   `flyon`: owner `dandrok`, repository `flyon`, workflow `testpublish.yml`, environment `testpypi`.
2. GitHub → *Settings → Environments* → create an environment named `testpypi`. No secrets: trusted
   publishing mints the token per run.
3. Actions → **testpublish** → *Run workflow*. It runs the tests, the wheel smoke test and the upload.
4. Prove the artifact: `uv venv /tmp/tp && uv pip install --python /tmp/tp/bin/python
   --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ flyon` and run
   `flyon --version`. Dependencies come from PyPI, the package from TestPyPI — that is what the extra
   index is for.
5. Delete the version from TestPyPI if you want to re-hearse the same number, or rehearse with the
   next one; nothing downstream depends on it.

## The first release is 0.1.0, and it does not go through `make release`

`0.1.0` was never published, so it *is* the first release: the changelog section is already dated and
holds everything, and `scripts/release.py` refuses to "bump" to the version already in
`pyproject.toml`. Tag it from a clean `main` instead:

```bash
git switch main && git pull
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

Every later release goes through `make release VERSION=x.y.z`, which bumps the version and closes the
`[Unreleased]` section.

## The one-time setup only you can do

1. Create a PyPI account and enable 2FA.
2. PyPI → *Publishing* → add a **pending publisher** for a project that does not exist yet:
   - project name: `flyon`
   - owner: `dandrok`, repository: `flyon`
   - workflow: `release.yml`
   - environment: `pypi`
3. GitHub → the repo → *Settings → Environments* → create an environment named `pypi`. No secrets:
   trusted publishing uses OIDC, which is why nothing sensitive lives in this repository.

Until step 2 is done, the publish step fails with an authentication error and nothing is uploaded.

## Cutting a release

```bash
git switch main && git pull
uv sync --extra stt && make e2e    # the real model, real speech: docs/VERIFICATION.md
make release VERSION=0.1.0        # bumps pyproject, dates the CHANGELOG section, prints next steps
git switch -c release/0.1.0
git add -A && git commit -m "chore: release 0.1.0"
git push -u origin release/0.1.0  # open the PR, wait for CI, squash-merge
git switch main && git pull
git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0
```

The tag is the trigger; nothing else publishes.

## What the pipeline does

`.github/workflows/release.yml`, on a `v*` tag:

1. runs the test suite and lint — a red tree never reaches PyPI;
2. builds sdist + wheel, installs the wheel in a clean venv and runs `flyon --version`;
3. refuses to continue if the tag does not match `pyproject.toml`'s version;
4. publishes to PyPI through trusted publishing (OIDC, `environment: pypi`, no token anywhere);
5. creates the GitHub release with generated notes.

`main` is protected: the release commits arrive by PR like everything else.

## If a release is wrong

- A bad *file* is fixable: publish a patch version. You cannot overwrite a version.
- A bad *release* is hideable: `gh release delete vX.Y.Z` removes the GitHub release, and PyPI lets you
  yank a file (it stays downloadable by exact pin, nobody gets it by default).
- A wrong *name* is permanent. This is why the name was checked before the first upload.
