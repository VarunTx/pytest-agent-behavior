# Trace format (version 1)

This document is normative for the external JSON format accepted by
`pytest_agent_behavior` 0.1.x. The JSON Schema at
[`src/pytest_agent_behavior/schema/trace.schema.json`](../src/pytest_agent_behavior/schema/trace.schema.json)
describes the structural rules. The Python loader enforces additional
cross-event and Python-type rules described below.

## Top level

```json
{
  "schema_version": 1,
  "events": []
}
```

| Field | Requirement |
| --- | --- |
| `schema_version` | Required. Must be exactly the integer `1`. Python `True` is rejected. Floats such as `1.0`, strings, and other versions are rejected. |
| `events` | Required JSON array. May be empty. Order is meaningful. |
| Other fields | Rejected as unknown. |

Unknown bottom-level fields are also rejected. This is intentional: a typo
such as `"argument"` should fail loudly rather than silently weakening a test.

## Events

### `tool_call`

```json
{
  "type": "tool_call",
  "call_id": "c1",
  "tool": "send_email",
  "arguments": {"to": "fake@example.com"}
}
```

- `type` is exactly the string `"tool_call"`.
- `call_id` and `tool` are nonempty strings. There is no pattern restriction;
  any nonempty identifier is accepted.
- `arguments` is required and must be a JSON object. It may be empty.
- Each `tool_call.call_id` must be unique within the trace.
- The event represents an observed invocation attempt. Whether the operation
  succeeded is outside the format.

### `approval`

```json
{
  "type": "approval",
  "call_id": "c1",
  "tool": "send_email",
  "decision": "approved"
}
```

- `type` is exactly the string `"approval"`.
- `call_id` and `tool` are nonempty strings.
- `decision` is exactly `"approved"` or `"denied"`.
- Multiple approvals for one `call_id` are allowed, in any order.
- An approval may appear before or after its associated call. Loading does not
  reject a late approval; `requires_approval` will treat it as insufficient
  authorization for the earlier call.
- Approval-only traces are valid. Approvals whose `call_id` never appears in a
  `tool_call` are valid input but do not authorize anything.

## JSON values

`arguments` may contain only strict JSON values:

- `null`, booleans, strings, finite numbers;
- arrays of JSON values;
- objects with string keys and JSON values.

The loader rejects:

- `NaN`, positive or negative infinity, including numbers that overflow to
  infinity during parsing;
- non-string mapping keys;
- tuples, sets, arbitrary Python objects, and type subclasses when constructing
  directly;
- cyclic lists or dictionaries;
- values that cannot be represented in JSON.

`Trace.from_dict` and direct constructors require actual Python built-in
containers (`dict` and `list`) and actual scalar types. They do not coerce
strings, booleans, or arbitrary objects into the desired types.

Consistent with strict JSON semantics, `true`, integer `1`, and float `1.0` are
different argument values for repeated-call signatures.

## Ordering and positions

Array position is the only ordering information. There are no timestamps and
no inference from timestamps. V1 traces are single-run and sequential; they
cannot faithfully represent interleaved parallel or multi-agent execution.

All event indices in API results and failure messages are **zero-based**. For
example, `events[0]` is the first event.

## Cross-event constraints not expressed by JSON Schema

The Python loader additionally enforces:

1. `tool_call.call_id` values are unique.
2. `schema_version` has Python integer type, not boolean or float.
3. Argument values use exact Python JSON types, not subclasses or coercible
   objects.
4. Argument floats are finite.
5. Argument containers are acyclic.

The schema also treats a JSON number such as `1.0` as mathematically integral;
the Python loader does not accept `1.0` for `schema_version`. These differences
are intentional: schema validation is a useful structural check, while the
loader is the authority for accepted Python input.

## Loading and export

```python
from pytest_agent_behavior import Trace

trace = Trace.from_dict(data)  # dict -> validated Trace
trace = Trace.from_json(text)  # JSON text -> validated Trace
trace = Trace.from_path("trace.json")  # UTF-8 file -> validated Trace

data = trace.to_dict()  # fresh JSON-compatible dict
text = trace.to_json()  # JSON text
```

- `to_dict()` returns fresh ordinary `dict` and `list` containers. Mutating
  it cannot change the trace.
- `to_json()` uses `allow_nan=False`; invalid values cannot reach it because
  construction already rejected them.
- Round trips preserve represented data and event order.
- Structural and JSON decoding problems are wrapped in
  `TraceValidationError`. Missing files, permission failures, and other
  filesystem errors remain their normal exception types.

## Versioning

`0.1.0` supports `schema_version` 1 only. A future incompatible change to event
shape or meanings must use a new schema version. Additive documentation or
loader strictness that rejects previously invalid input does not require a new
schema version, but release notes must call it out.
