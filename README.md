# pytest-agent-behavior

Deterministic pytest assertions for AI agent tool calls, approval ordering, and repeated-call limits.

`pytest-agent-behavior` evaluates a trace that your agent code already produced.
It makes no LLM calls and needs no API key, service, dashboard, or framework
plugin. Write ordinary pytest tests that catch behavioral regressions in tool
selection, approval order, call counts, and repeated identical calls.

**Version:** 0.1.0

## Install

From PyPI:

```console
python -m pip install pytest-agent-behavior
```

From a local checkout, for development:

```console
python -m pip install .
```

For development, including tests, linters, and build tools:

```console
python -m pip install -e ".[dev]"
```

The package registers the pytest plugin entry point `agent_behavior`
automatically. No `-p` flag or `pytest_plugins` entry is needed.

## Quickstart

```python
from pytest_agent_behavior import Trace


def test_email_requires_approval(agent_assertions):
    trace = Trace.from_dict(
        {
            "schema_version": 1,
            "events": [
                {
                    "type": "approval",
                    "call_id": "c1",
                    "tool": "send_email",
                    "decision": "approved",
                },
                {
                    "type": "tool_call",
                    "call_id": "c1",
                    "tool": "send_email",
                    "arguments": {"to": "fake@example.com", "body": "Hello"},
                },
            ],
        }
    )

    check = agent_assertions(trace)
    check.called("send_email", times=1)
    check.requires_approval("send_email")
```

Run it with `pytest`. This quickstart is a passing example. The
`agent_assertions` fixture returns a factory that accepts a validated `Trace`.
It deliberately does not accept dictionaries or paths: call `Trace.from_dict`,
`Trace.from_json`, or `Trace.from_path` explicitly so conversion is visible in
the test.

All assertion methods return `None` on success and raise `AgentAssertionError`
(a subclass of `AssertionError`) on a behavioral failure. Invalid parameter
types raise `TypeError`; valid types with invalid values, such as a negative
count or empty tool name, raise `ValueError`.

## Trace format

```json
{
  "schema_version": 1,
  "events": [
    {
      "type": "approval",
      "call_id": "c1",
      "tool": "send_email",
      "decision": "approved"
    },
    {
      "type": "tool_call",
      "call_id": "c1",
      "tool": "send_email",
      "arguments": {
        "to": "example@example.com",
        "body": "Hello"
      }
    }
  ]
}
```

- `schema_version` must be the integer `1`. Python `True` is rejected even
  though it compares equal to `1`.
- `events` is an ordered JSON array. Position is the only ordering signal;
  timestamps are not inferred or supported. Public event indices are
  **zero-based**.
- A `tool_call` has exact `type` `"tool_call"`, nonempty string `call_id` and
  `tool`, and a required JSON object `arguments`.
- An `approval` has exact `type` `"approval"`, nonempty string `call_id` and
  `tool`, and `decision` exactly `"approved"` or `"denied"`.
- Every `tool_call.call_id` must be unique in a trace. Multiple approvals for
  one `call_id` are allowed. Approval-only traces and approvals without a
  subsequent call are valid.
- Unknown fields, unknown event types, unsupported versions, non-JSON values,
  non-finite numbers, non-string object keys, and cyclic values raise
  `TraceValidationError` with a path such as
  `events[2].arguments: expected a JSON object`.
- Empty traces and empty `arguments` objects are valid.
- A tool call records an observed invocation **attempt**. It does not imply the
  external operation succeeded.

The published JSON Schema is at
[`src/pytest_agent_behavior/schema/trace.schema.json`](src/pytest_agent_behavior/schema/trace.schema.json).
The schema cannot express unique `tool_call.call_id` values or Python's exact
type distinctions; those are enforced by the Python loader. See
[docs/trace-format.md](docs/trace-format.md) for the full format and
cross-event constraints.

## Assertions

### `called(tool, *, times=None)`

Matches tool names exactly and case-sensitively and counts only `tool_call`
events. `times=None` requires at least one matching call. `times=N` requires
exactly `N`; `times=0` is valid.

### `not_called(tool)`

Passes only when no matching `tool_call` event exists. Behaviorally equivalent
to `called(tool, times=0)`. Failure messages include matching event indices.

### `requires_approval(tool)`

For every `tool_call` matching `tool`, finds approvals **before** that call
with the same `call_id` and the same `tool`. The last such preceding approval
must be `"approved"`.

- No matching preceding approval: failure.
- Approval after the call: does not authorize the earlier call.
- Approval for another `call_id` or another tool: does not authorize.
- `approved` then `denied` before the call: failure.
- `denied` then `approved` before the call: success.
- One call's approval never authorizes another call.
- If the selected tool never appears, the assertion passes **vacuously**.
  Combine it with `called(tool)` when existence is also required.

Approvals are observed authorization metadata. The package cannot prove who
supplied an approval or that an approval actually blocked execution.

### `max_calls(limit, *, tool=None)`

Counts all `tool_call` events when `tool` is `None`, otherwise only exact
matches. Passes when the count is at most `limit`. Approval events never count.
`limit=0` is valid.

### `max_repeated_calls(limit, *, tool=None)`

Counts total occurrences of each distinct `(tool, arguments)` signature across
the entire trace, not just consecutive repetitions. The assertion fails if any
signature count exceeds `limit`.

- Object key order is ignored, at every nesting level.
- Array order matters.
- Different tool names create different signatures.
- Different `call_id` values do not distinguish otherwise identical calls.
- JSON types are strict: `true`, `1`, and `1.0` are different argument values.
- Failure messages identify tools, counts, and event indices but never print
  argument values.

This is a repeated-call **threshold check**. It does not prove an agent is
stuck in a loop or that a retry was inappropriate.

See [docs/api.md](docs/api.md) for constructor details, exception contracts, and
privacy notes.

## Documentation

- [Trace format, version 1](docs/trace-format.md)
- [API reference](docs/api.md)
- [Design notes and tradeoffs](docs/design.md)
- [Release checklist](docs/release-checklist.md)
- [Contributing](CONTRIBUTING.md)

## A passing test

[`examples/demo_agents.py`](examples/demo_agents.py) contains two deterministic
demo agents. They call ordinary local Python functions through a small manual
recorder; there are no network requests, LLM calls, or real side effects. The
passing agent produces its trace through execution:

```python
from demo_agents import run_passing_agent


def test_passing_demo_agent(agent_assertions):
    trace = run_passing_agent()
    check = agent_assertions(trace)

    check.called("lookup_order", times=1)
    check.called("send_email", times=1)
    check.not_called("issue_refund")
    check.requires_approval("send_email")
    check.max_calls(2)
    check.max_repeated_calls(1)
```

Run the passing demo:

```console
pytest examples/tests/test_passing_agent.py -q
```

## A deliberately failing test

The faulty demo agent sends four identical emails without approvals. Its
intentionally failing checks live in `examples/failing_demo.py`, which is not
named `test_*.py` and therefore stays out of normal collection.

```console
pytest examples/failing_demo.py -q --tb=short
```

This command exits with status **1**. Actual output from this tree (CPython
3.11.0, pytest 9.2.0):

```text
FF                                                                       [100%]
=================================== FAILURES ===================================
________________ test_faulty_agent_exceeds_repeated_call_limit _________________
examples/failing_demo.py:18: in test_faulty_agent_exceeds_repeated_call_limit
    check.max_repeated_calls(2)
...
E   pytest_agent_behavior.exceptions.AgentAssertionError: Agent behavior assertion failed: max_repeated_calls
E   tool: (any)
E   expected: at most 2 call(s) per distinct (tool, arguments) signature
E   observed: 1 signature(s) exceed the limit (showing 1)
E     tool: send_email
E     count: 4
E     event indices: [0, 1, 2, 3]
______________________ test_faulty_agent_has_no_approval _______________________
...
E   pytest_agent_behavior.exceptions.AgentAssertionError: Agent behavior assertion failed: requires_approval
E   tool: send_email
E   unauthorized calls: 4 (showing 4)
E     event index: 0
E     call_id: c1
E     expected: a preceding matching approval for the same call_id and tool with decision approved
E     observed: no matching preceding approval
...
2 failed in 0.01s
```

The package's own failure text does not include argument values. Pytest itself
may display source lines or locals, which can contain test literals; see
[Privacy](#privacy).

## Manual instrumentation

Record the attempt immediately before you invoke a tool. Use fake arguments in
tests and examples. Approval events must be recorded before the call they are
meant to authorize.

```python
from pytest_agent_behavior import Approval, ToolCall, Trace


def run_agent(send_email):
    events = []

    call_id = "c1"
    events.append(Approval(call_id, "send_email", "approved"))
    events.append(
        ToolCall(
            call_id,
            "send_email",
            {"to": "fake@example.com", "body": "Synthetic message"},
        )
    )
    send_email("fake@example.com", "Synthetic message")  # the observed attempt

    events.append(ToolCall("c2", "lookup_order", {"order_id": "order-42"}))
    return Trace(events)
```

The tool call is recorded regardless of whether the external call later
succeeds or raises. This library does not wrap, intercept, or prevent that
call.

## What this package does and does not do

It **does**:

- validate and load supplied sequential traces;
- evaluate deterministic assertions in ordinary pytest tests;
- report bounded, index-based diagnostics without argument values.

It **does not**:

- make live LLM calls, require API keys, send telemetry, or contact a service;
- instrument or monkey-patch an agent framework;
- intercept or prevent tool execution;
- prove an agent is safe, correct, or compliant;
- assess answer quality or perform semantic similarity/LLM-as-judge scoring;
- provide exactly-once execution guarantees;
- model parallel or multi-agent execution.

Traces are **single-run and sequential**. Event order is exactly array order.
The format has no timestamps, concurrency, causal graph, or cross-run
semantics. Interleaved calls from parallel workers cannot be represented
faithfully in this release.

## Privacy

- Library-generated assertion failures identify assertion, tool, counts,
  event indices, and `call_id` where useful. They do not include argument
  values or full events.
- `ToolCall.__repr__` omits argument values; `Trace.__repr__` is a short
  summary rather than a dump of events.
- Validation errors identify paths and value types, not the offending values.
- `to_dict()` and `to_json()` intentionally contain arguments because they
  serialize the trace. Treat trace files and test literals as potentially
  sensitive.
- Pytest can display user source code, assertion expressions, or locals
  depending on traceback options and plugins. The library cannot promise
  complete redaction of pytest's output.

There is no telemetry, networking, or background work.

## Comparison with alternatives

- **Handwritten assertions** are often enough for one simple count. They give
  total control but tend to duplicate trace validation, approval-order logic,
  strict JSON signature handling, and diagnostic formatting. This package is a
  small local helper for those recurring checks.
- **Broader experiment/evaluation platforms** commonly manage datasets,
  hosted tracing, scoring, and LLM-judge workflows. This package is not an
  evaluation platform, has no hosted component, and performs no semantic
  scoring.
- **Runtime policy or approval gateways** can block execution. This package
  only evaluates an already-observed trace and cannot provide that guarantee.

## Compatibility and development

The package requires Python 3.10+ and declares `pytest>=8.3,<10` as its only
runtime dependency.

Locally tested for 0.1.0, on macOS arm64 against the checked-out source:

- CPython 3.10.18, 3.11.0, 3.12.11, 3.13.6, and 3.14.0rc1 with pytest 9.2.0:
  178 passed;
- CPython 3.11.0 with pytest 8.3.5: 178 passed;
- CPython 3.15.0 with pytest 9.2.0: 178 passed.

The configured GitHub Actions matrix covers Ubuntu with CPython 3.10–3.14
(stable setup-python builds), pytest 9.2.0, plus pytest 8.3.5 on CPython 3.11.
That CI matrix has **not been run** for this tree. The local 3.14 result used a
release candidate, not the stable 3.14 build used by CI; see
[CONTRIBUTING.md](CONTRIBUTING.md) for the distinction. Prepared CI does not
mean it passed.

Local verification commands:

```console
python -m pip install -e ".[dev]"
pytest -q
ruff check .
ruff format --check .
mypy
python -m build
python -m twine check dist/*
```

The release process, including TestPyPI/PyPI and Trusted Publishing guidance,
is in [docs/release-checklist.md](docs/release-checklist.md).

## Project links

- Distribution: `pytest-agent-behavior`
- Import package: `pytest_agent_behavior`
- pytest entry point: `agent_behavior`
- [Source repository](https://github.com/VarunTx/pytest-agent-behavior)
- [Issue tracker](https://github.com/VarunTx/pytest-agent-behavior/issues)
- [API documentation](https://github.com/VarunTx/pytest-agent-behavior/blob/main/docs/api.md)
- [Changelog](https://github.com/VarunTx/pytest-agent-behavior/blob/main/CHANGELOG.md)

Maintained by Varun Talari.

## License

MIT. See [LICENSE](LICENSE).
