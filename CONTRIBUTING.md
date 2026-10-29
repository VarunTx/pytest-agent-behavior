# Contributing

## Development setup

```console
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The project targets Python 3.10+ and declares `pytest>=8.3,<10`.

## Verification status

For the 0.1.0 tree, the full test suite was run locally on macOS arm64 against
the checked-out source:

- CPython 3.10.18 with pytest 9.2.0 (178 passed);
- CPython 3.11.0 with pytest 8.3.5 (178 passed);
- CPython 3.11.0 with pytest 9.2.0 (178 passed);
- CPython 3.12.11 with pytest 9.2.0 (178 passed);
- CPython 3.13.6 with pytest 9.2.0 (178 passed);
- CPython 3.14.0rc1 with pytest 9.2.0 (178 passed);
- CPython 3.15.0 with pytest 9.2.0 (178 passed).

The configured GitHub Actions matrix uses Ubuntu and stable CPython 3.10–3.14
through `actions/setup-python`, with pytest 9.2.0 plus a pytest 8.3.5 job on
CPython 3.11. That workflow has **not run** for this tree, and no Linux or
stable-3.14 result is claimed. Do not describe a CI matrix as passing until its
workflow run exists.

## Checks

Run all local checks before proposing a change:

```console
pytest -q
ruff check .
ruff format --check .
mypy
python -m build
python -m twine check dist/*
```

`mypy` is configured to check the public library code under `src/`.

Run the intentional failure demo separately. It must exit nonzero:

```console
pytest examples/failing_demo.py -q --tb=short
```

Do not include that file in normal success criteria; its filename is
deliberately outside the `test_*.py` pattern.

## Test expectations

- Tests must be deterministic and must not use network access, real LLM calls,
  sleeps, paid services, or real side effects.
- Prefer behavioral tests over assertions that restate implementation details.
- Cover both success and failure paths, including invalid parameters and
  bounded diagnostics.
- When changing failure text, update the documented examples only with output
  actually produced by a command.
- Privacy tests should use clearly fake sensitive-looking values and verify
  they do not appear in library-generated message bodies or reprs.

## Code style

- Use Python 3.10-compatible syntax.
- Keep the public API small. Do not add assertion methods outside the documented
  five without a scope decision.
- Do not add runtime dependencies unless the standard library is insufficient;
  pytest is intended to remain the only runtime dependency.
- Keep the pytest plugin module minimal. Avoid global state and unrelated pytest
  behavior changes.
- Prefer explicit exceptions over `assert` statements in library code so checks
  survive `python -O`.
- Preserve strict validation and the TypeError/ValueError parameter contract.

## Documentation and release changes

- Update `CHANGELOG.md` for user-visible changes.
- Update the trace format document and schema together for format changes.
- Add a schema-version bump for incompatible format changes.
- Do not invent repository URLs, author identities, adoption, performance, or
  security claims.
- Publishing is a separate, authorized maintainer action. See
  `docs/release-checklist.md`.

## License

By contributing, you agree that your contribution is licensed under the MIT
license in `LICENSE`.
