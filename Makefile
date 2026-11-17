# Every target mirrors the CI job that runs the same command. Never a different
# invocation, or the local gate lies about the remote one.
UV ?= uv

.PHONY: help venv fmt lint types test cov check e2e build clean

help:
	@printf '%s\n' \
	  'make venv    create .venv on Python 3.14 and install dev deps' \
	  'make fmt     format + autofix (ruff)' \
	  'make lint    format check + lint (ruff)' \
	  'make types   mypy strict on domain+ports' \
	  'make test    pytest, slow tests excluded' \
	  'make cov     pytest with coverage gate' \
	  'make check   lint + types + test   <- what CI runs' \
	  'make e2e     slow tests' \
	  'make build   wheel + sdist into dist/' \\
	  'make release VERSION=x.y.z   bump the version and date the changelog'

venv:
	$(UV) sync --python 3.14

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint:
	$(UV) run ruff format --check .
	$(UV) run ruff check .

types:
	$(UV) run mypy

test:
	$(UV) run pytest -m "not slow"

cov:
	$(UV) run pytest --cov --cov-report=term-missing -m "not slow"

check: lint types test

e2e:
	$(UV) run pytest -m slow

release:
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=0.2.0"; exit 2; }
	$(UV) run python scripts/release.py $(VERSION)

dry-publish:
	$(UV) build
	$(UV) publish --publish-url https://test.pypi.org/legacy/ dist/*

build:
	$(UV) build

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache
