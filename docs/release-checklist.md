# Release checklist

This document describes the release process for `pytest-agent-behavior`.
Uploading, tagging, pushing, and publishing require authorization from the
repository owner.

## 1. Confirm the project name

The distribution name is `pytest-agent-behavior`.

- On 2026-10-29, `https://pypi.org/pypi/pytest-agent-behavior/json` returned
  HTTP 404, so no project was published under the exact name at that time. That
  did **not** reserve the name.
- Recheck immediately before creating credentials, environments, or uploads.
  Check both PyPI and TestPyPI, and search for confusingly similar names.
- Do not state that the name is available until the registry confirms it.

If the name is occupied, make these changes before release:

1. Choose a new distribution name in `[project].name` in `pyproject.toml`.
2. Update installation commands and prose in `README.md`,
   `docs/release-checklist.md`, and `CHANGELOG.md`.
3. Update expected artifact names in release notes and CI upload paths.
4. Decide whether to rename the import package `pytest_agent_behavior` and the
   pytest entry point `agent_behavior`. They can remain unchanged, but document
   any mismatch between distribution and import names.
5. Rebuild and repeat the clean-install verification.

## 2. Owner metadata

The project metadata now contains the supplied author and repository details:

- Author: Varun Talari `<varun.talari1@gmail.com>`
- Repository: `https://github.com/VarunTx/pytest-agent-behavior`
- Issues: `https://github.com/VarunTx/pytest-agent-behavior/issues`
- Documentation: `https://github.com/VarunTx/pytest-agent-behavior/blob/main/docs/api.md`
- Changelog: `https://github.com/VarunTx/pytest-agent-behavior/blob/main/CHANGELOG.md`
- License copyright holder: Varun Talari

No security contact or separate maintainer identity has been supplied. Add one
only if the owner provides it; do not invent it. If metadata changes, rebuild
and repeat the clean-install verification.

## 3. Run the complete local preflight

From a clean checkout:

```console
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pytest -q
ruff check .
ruff format --check .
mypy

rm -rf dist build
python -m build
python -m twine check dist/*
```

Also run the intentional failure demo and confirm exit status 1:

```console
pytest examples/failing_demo.py -q --tb=short
echo $?   # must print 1
```

## 4. Verify outside the source checkout

Do not rely on an editable install. Use a fresh virtual environment and a
directory outside the repository.

```console
rm -rf /tmp/agent-behavior-wheel-venv /tmp/agent-behavior-consumer
python -m venv /tmp/agent-behavior-wheel-venv
/tmp/agent-behavior-wheel-venv/bin/pip install --upgrade pip
/tmp/agent-behavior-wheel-venv/bin/pip install dist/pytest_agent_behavior-0.1.0-py3-none-any.whl

mkdir -p /tmp/agent-behavior-consumer
cd /tmp/agent-behavior-consumer
```

Create `test_consumer.py` with one passing and one deliberately failing test in
separate files, then run them separately so exit codes are unambiguous. The
passing test must use the automatically discovered `agent_assertions` fixture.
The failing test must exit 1 and show an `AgentAssertionError` message.

Also verify the sdist can build a wheel:

```console
python -m venv /tmp/agent-behavior-sdist-venv
/tmp/agent-behavior-sdist-venv/bin/pip install build
cd /tmp
/tmp/agent-behavior-sdist-venv/bin/python -m build --wheel \
  /path/to/pytest_agent_behavior-0.1.0.tar.gz
```

Confirm the wheel contains `pytest_agent_behavior/py.typed`,
`pytest_agent_behavior/schema/trace.schema.json`, and the plugin module.
Confirm importing from `/tmp/agent-behavior-consumer` resolves the installed
wheel, not a source tree.

## 5. Choose the version

- Update `[project].version` in `pyproject.toml`.
- Update `__version__` in `src/pytest_agent_behavior/__init__.py`.
- Add a dated `CHANGELOG.md` entry.
- Rebuild after every change; never publish stale artifacts.

## 6. Prepare the GitHub repository

The repository is `VarunTx/pytest-agent-behavior`, default branch `main`.

1. Keep the public repository metadata accurate: description, topics, and
   links. Do not add adoption, download, or performance claims.
2. Confirm Actions are enabled and run the CI workflow. The configured matrix
   is Ubuntu + CPython 3.10–3.14 with pytest 9.2.0, plus pytest 8.3.5 on
   CPython 3.11. Record the actual run.
3. Create GitHub environments named `testpypi` and `pypi` for the release
   workflow. Apply tag or branch policies supported by the repository plan.
4. If repository URLs or author metadata change, rebuild before tagging.
5. After CI passes for the exact release commit, create the release tag (for
   example `v0.1.0`) from that commit. Do not move an existing released tag.

## 7. Configure TestPyPI with Trusted Publishing

Preferred flow: OpenID Connect Trusted Publishing, no stored API token. The
release workflow is `.github/workflows/release.yml` and is triggered manually
for an explicit release tag.

1. Create/confirm the TestPyPI account, verify its email, and enable 2FA.
2. In TestPyPI, add a **pending Trusted Publisher** with these exact values:
   - Project name: `pytest-agent-behavior`
   - Owner: `VarunTx`
   - Repository: `pytest-agent-behavior`
   - Workflow: `release.yml`
   - Environment: `testpypi`
3. In GitHub, create/protect the matching `testpypi` environment.
4. The workflow grants `id-token: write` only to publishing jobs and uploads to
   `https://test.pypi.org/legacy/`.
5. Confirm the publisher and environment settings in the TestPyPI UI before the
   first upload. Do not embed a token in the repository.

A manual upload is possible with `twine upload --repository testpypi dist/*`
using a token supplied interactively, but Trusted Publishing is preferred.
Never commit credentials.

## 8. Verify TestPyPI

```console
python -m venv /tmp/agent-behavior-testpypi-venv
/tmp/agent-behavior-testpypi-venv/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  pytest-agent-behavior==0.1.0
```

Run the consumer passing/failing tests again. TestPyPI is not a production
index and may be slower or incomplete.

## 9. Publish to PyPI

1. Create/confirm the production PyPI account, verify its email, and enable 2FA.
2. Configure a pending Trusted Publisher with these exact values:
   - Project name: `pytest-agent-behavior`
   - Owner: `VarunTx`
   - Repository: `pytest-agent-behavior`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. Create/protect the matching GitHub `pypi` environment.
4. Confirm the final name and version one last time.
5. Build from the exact tagged commit and rerun `twine check`.
6. Obtain explicit authorization, then run the PyPI publish job or manual
   upload.
7. Verify the project page, metadata, license, README rendering, wheel, sdist,
   and installed fixture behavior.

Do not assume a failed upload is safe to retry blindly. PyPI files and versions
cannot always be replaced. If a bad release is published, yank it and publish a
new patch version.

## 10. After publication

- Install from PyPI in a clean environment and run both consumer tests.
- Create GitHub release notes for the verified tag and attach the same verified
  wheel and sdist.
- Record which Python/pytest versions the release was actually tested against.
- Keep the CI matrix results with the release record; prepared CI is not proof
  that it passed.

## Metadata changes if the name conflicts

Required: distribution name, README install commands, changelog, CI artifact
paths, TestPyPI/PyPI project configuration, release notes.

Optional: import package name, pytest entry point name, repository directory
name, schema title. Renaming these changes user code and should be a deliberate
breaking decision, not an automatic consequence.
