# Contributing

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]' black ruff
pytest
```

The suite is hermetic: no network, no model, no database. A judge in a test is
a stub whose `complete()` returns canned text.

## Rules

- **No network and no framework in the library.** A model call is
  `client.complete(prompt)` on an object the caller passes in; a storage write
  is a path the caller passes in. Nothing here imports an HTTP client, an SDK,
  or Django.
- **No domain in the defaults.** The default rubric and report wording know
  nothing about any product or industry. A product supplies its own templates
  through `Rubric(...)`; the validation stays here.
- **Every behaviour that protects a measurement has a test that names the
  failure it prevents** — a position-biased judge scoring a tie, a bool read
  as a 1, a backend returning too few vectors.
- Format with `black` and `ruff check` before pushing. `scripts/deorg_scan.py`
  runs in CI and refuses machine paths, credential-shaped strings and the
  maintainer's private tokens; keep examples and fixtures on public sources.

## Releasing

1. Bump `version` in `pyproject.toml` and `judgeswap/__init__.py`, add the
   changelog entry.
2. Push the tag `vX.Y.Z` (the workflow refuses a tag that does not equal the
   committed version), or run **Release** from the Actions tab on the branch
   to release: the run tags that commit itself.
3. `release.yml` tests, builds, publishes to PyPI through trusted publishing
   (configured on PyPI for this repository, workflow `release.yml`,
   environment `pypi`) and creates the GitHub release.

Security reports: see `SECURITY.md`.
