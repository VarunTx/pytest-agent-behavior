# Design notes

## Problem boundary

The package answers a narrow question: given an observed, ordered list of agent
tool-call attempts and approval decisions, did specified behavioral properties
hold? It is a deterministic pytest assertion library, not an execution engine
or policy enforcement point.

The intended workflow is:

1. The agent runs with manual or framework instrumentation.
2. Instrumentation emits a version-1 trace.
3. Tests load the trace and assert behavior.
4. A regression produces an `AgentAssertionError` with a bounded, stable
   diagnostic.

## Why supplied traces

Evaluating observed traces keeps tests local, fast, and deterministic. It also
makes the package's boundary explicit: it cannot intercept a call, block a
call, prove a call was safe, verify that an approval was genuinely human, or
guarantee exactly-once execution. Runtime policy belongs in the execution path.

Traces may be generated in the test process (as the examples do) or loaded from
files produced elsewhere. The package neither generates traces itself nor
imports agent frameworks.

## Data model

`ToolCall`, `Approval`, and `Trace` are frozen slotted dataclasses. `Trace.events`
is a tuple, and tool arguments are stored as a private validated deep copy.
The public `arguments` property returns another deep copy. This prevents both
the caller's original dictionary and previously returned copies from mutating
the stored trace or later assertion results.

JSON object key order is representation detail. Event array order is semantic.
There are no timestamps, so ordering cannot be inferred from them.

## Validation

The loader is deliberately stricter than permissive JSON handling:

- exact built-in types, not subclasses or coercions;
- `schema_version` must be Python integer `1`, not `True` or `1.0`;
- finite floats only;
- string object keys only;
- no unknown fields;
- no cycles;
- no unsupported objects.

Errors use zero-based paths such as `events[2].arguments.to`. Paths and type
names are included; offending values are not. This keeps a malformed trace
diagnosable without copying credentials or personal data into an exception.

`Trace.from_dict`, direct constructors, and JSON loading converge on the same
class constructors. There is no alternate unvalidated path.

Filesystem errors are allowed to propagate. Converting `FileNotFoundError` into
a validation error would hide a practical setup problem behind the wrong
exception category.

## Approval algorithm

For each matching call at index `i`, only approvals with index `< i` are
candidates. Candidates must match both `call_id` and `tool`. The last candidate
wins. This models the common policy interpretation that a later decision
overrides an earlier one, while a decision after the call cannot retroactively
authorize that call.

The implementation makes one left-to-right pass and keeps the latest approval
decision keyed by `(call_id, tool)`. A call consults that map at its position,
so earlier approvals are visible, later approvals are not yet visible, and
approvals for other call IDs or tools do not interfere. This preserves the
ordering rules without rescanning the prefix for each call.

The trace format permits late approvals and approval-only traces because they
are structurally valid observations. Rejecting them during loading would
prevent tests from diagnosing the ordering problem they exist to catch.

The method passes vacuously when no matching call exists. Existence is a
separate property, so callers who need it combine `called(tool)` with
`requires_approval(tool)`.

## Repeated-call signatures

A signature is `(tool, canonical_json(arguments))`. Canonicalization:

- tags each JSON type (`null`, `boolean`, `integer`, `number`, `string`,
  `array`, `object`);
- sorts object keys at every level;
- preserves array order;
- represents floats with `float.hex()` for exact, stable distinction;
- keeps tool name outside the argument value.

Tags are necessary because Python considers `True == 1` and `1 == 1.0`.
Without tags, distinct JSON inputs would incorrectly collapse. Sorting keys makes
the check independent of dictionary insertion order. Because call IDs are not
part of the signature, nonconsecutive retries with identical arguments are
counted together.

This check is a threshold, not a loop detector. Repeating an idempotent read
can be correct; repeating an email send can be harmful. The assertion only
reports counts and indices so a human can judge context.

## Diagnostics

Failures use a small, stable text format rather than dumping events or argument
values. For large traces:

- event-index lists show at most 20 entries plus the omitted count;
- repeated-call violations detail at most 10 signatures;
- unauthorized-call diagnostics detail at most 10 calls.

All ordering is event order, so output is stable across runs. No object
addresses, random hashes, or elapsed times appear. Counting is linear in the
number of events for each assertion; no assertion builds quadratic messages.

## pytest integration

The plugin contains one fixture and no global state. The pytest entry point
autoloads it from the installed distribution. Assertions raise explicitly, so
`python -O` does not remove checks. The package uses no pytest-private
assertion-rewriting APIs.

## Compatibility and format evolution

Version 1 fixes the event shapes and sequential ordering. Any incompatible
change requires a new `schema_version`; the loader rejects unsupported versions.
The JSON Schema is a structural aid, but the Python loader remains the
authority because JSON Schema cannot express unique `call_id` values, exact
Python scalar types, finite-float requirements, or cycle freedom.

## Known limitations

- No parallel, multi-agent, or cross-run semantics.
- No timestamps or causal ordering.
- No runtime enforcement or blocking.
- No proof of approval authenticity.
- No exactly-once guarantee.
- No semantic or answer-quality evaluation.
- No automatic instrumentation.
- Traces can contain sensitive arguments; storage and pytest output are the
  user's responsibility.
