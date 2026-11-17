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
the version number is never reusable. That is the whole reason not to publish a 0.0.1 today: nothing
here has transcribed a single real sentence yet.

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
