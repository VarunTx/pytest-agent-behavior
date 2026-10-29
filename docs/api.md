# API reference

## Public imports

```python
from pytest_agent_behavior import (
    AgentAssertionError,
    AgentAssertions,
    AgentAssertionsFactory,
    Approval,
    ToolCall,
    Trace,
    TraceValidationError,
    __version__,
)
```

## Models

All three model classes are immutable, slotted dataclasses.

### `ToolCall(call_id, tool, arguments, *, type="tool_call")`

- `type` must be `"tool_call"`; the public value is always `"tool_call"`.
- `call_id` and `tool` must be nonempty `str` values.
- `arguments` must be a JSON object (`dict` with string keys and strict JSON
  values).
- Arguments are deep-copied and validated at construction. The `arguments`
  property returns a fresh mutable copy each time, so callers cannot mutate the
  stored trace. The property is not included in `repr`.
- `to_dict()` returns fresh JSON-compatible containers.

Direct construction and JSON loading apply the same validation.

### `Approval(call_id, tool, decision, *, type="approval")`

- `type` must be `"approval"`.
- `call_id` and `tool` must be nonempty strings.
- `decision` must be exactly `"approved"` or `"denied"`.
- `to_dict()` returns a fresh JSON-compatible dictionary.

### `Trace(events, *, schema_version=1)`

- `schema_version` must be the Python integer `1`; `True` is rejected.
- `events` must be a list or tuple of actual `ToolCall`/`Approval` instances.
- `tool_call.call_id` values must be unique.
- The stored `events` value is a tuple, preserving order.
- Empty events are valid.

Loaders:

- `Trace.from_dict(data)` accepts a JSON-compatible dictionary. Unknown fields
  and invalid values raise `TraceValidationError`.
- `Trace.from_json(text)` accepts `str`. JSON decoding errors and invalid
  constants are wrapped in `TraceValidationError`.
- `Trace.from_path(path)` reads UTF-8 text. Filesystem failures remain their
  normal exception types; invalid UTF-8 is wrapped in
  `TraceValidationError`.
- `trace.to_dict()` returns a fresh JSON-compatible dictionary.
- `trace.to_json()` returns deterministic indented JSON text.

Event indices are zero-based.

## `AgentAssertions(trace)`

Accepts a validated `Trace`. Any other type raises `TypeError`. Assertion
objects hold a reference to the immutable trace and no mutable per-run state,
so independent objects do not affect each other.

Every assertion method returns `None` on success. Behavioral failures raise
`AgentAssertionError`, which subclasses `AssertionError`. Explicit `raise`
statements mean checks still execute under `python -O`.

Invalid parameters follow one contract:

- wrong parameter type -> `TypeError`
- correct type but invalid value or range -> `ValueError`

### `called(tool, *, times=None)`

- Exact, case-sensitive tool-name match.
- Counts `tool_call` events only.
- `times=None`: at least one.
- `times=N`: exactly N; `N=0` is valid.
- Tool must be a nonempty string; count must be a nonnegative integer and not
  a boolean.

### `not_called(tool)`

- Passes only when the exact tool has no `tool_call` events.
- Failure lists matching zero-based event indices, bounded for large traces.

### `requires_approval(tool)`

For each matching `tool_call` at index `i`:

1. Consider approvals at indices before `i`.
2. Keep those with the same `call_id` and same `tool`.
3. If none exist, the call is unauthorized.
4. Otherwise, the last remaining approval must have decision `"approved"`.

Consequences:

- An approval at or after the call is not considered.
- Another call's approval is not considered.
- The same call ID with a different tool is not considered.
- `approved`, then `denied`, then the call fails.
- `denied`, then `approved`, then the call passes.
- Multiple approvals are allowed.
- If the tool never appears, the method passes vacuously. Use `called(tool)`
  too when the tool must exist.

The failure reports every unauthorized matching call, with at most 10 detailed
entries. It includes event index, `call_id`, expected state, and observed state,
but never argument values.

Approvals are observed metadata, not proof of a human decision or of blocked
execution.

### `max_calls(limit, *, tool=None)`

- `tool=None`: count every `tool_call` event.
- Otherwise: count exact tool matches.
- Approvals never count.
- Passes when `count <= limit`; zero is valid.
- Failure lists bounded event indices.

### `max_repeated_calls(limit, *, tool=None)`

- Optionally filter to one exact tool first.
- Group every `tool_call` by a canonical `(tool, arguments)` signature.
- Count total occurrences across the whole trace, including nonconsecutive
  occurrences.
- Fail if any group exceeds `limit`; zero is valid.
- Object key order is normalized at every level.
- Array order is retained.
- Tool names are part of the signature.
- Call IDs are not part of the signature.
- Strict JSON types are part of the signature: `true`, `1`, and `1.0` differ.
- At most 10 violating signatures are detailed, with at most 20 indices each.
- Arguments are never printed.

## Pytest fixture

The package entry point registers:

```toml
[project.entry-points.pytest11]
agent_behavior = "pytest_agent_behavior.plugin"
```

The fixture is named `agent_assertions` and returns
`AgentAssertionsFactory`, i.e. `Callable[[Trace], AgentAssertions]`.

```python
def test_something(agent_assertions):
    trace = Trace.from_path("trace.json")
    agent_assertions(trace).called("search")
```

The fixture works in ordinary and parametrized tests. It does not add markers,
global state, or automatic trace capture.

## Errors and diagnostics

```python
class TraceValidationError(ValueError): ...


class AgentAssertionError(AssertionError): ...
```

Failure messages have a stable shape:

```text
Agent behavior assertion failed: requires_approval
tool: send_email
unauthorized calls: 1 (showing 1)
  event index: 3
  call_id: c2
  expected: a preceding matching approval for the same call_id and tool with decision approved
  observed: no matching preceding approval
```

Messages are deterministic: they preserve event order and do not include
object addresses or hash-randomized values. Very large failures report total
counts and a bounded set of representative indices.

The library omits argument values from its messages and model reprs. It cannot
control pytest's rendering of user source code or locals; see the privacy
section in the README.
