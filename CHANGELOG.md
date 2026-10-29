# Changelog

All notable changes to this project are documented here. The project follows
semantic versioning for its public API.

## [0.1.0] - 2026-10-29

### Added

- Immutable `ToolCall`, `Approval`, and `Trace` models with a version-1 JSON
  format.
- Strict validation for unknown fields and event types, schema versions,
  scalar types, finite numbers, object keys, cycles, and unique tool-call IDs.
- Load/export APIs: `Trace.from_dict`, `Trace.from_json`, `Trace.from_path`,
  `Trace.to_dict`, and `Trace.to_json`.
- `AgentAssertions` with `called`, `not_called`, `requires_approval`,
  `max_calls`, and `max_repeated_calls`.
- Deterministic, bounded failure diagnostics that omit argument values.
- The `agent_assertions` pytest fixture, registered through the `pytest11`
  entry point.
- JSON Schema for the trace format.
- Unit, pytest plugin, privacy, schema, and optimized-mode tests.
- Two deterministic local demo agents, including an intentional failure demo.
- Packaging, GitHub Actions CI, documentation, and release checklist.

### Changed

- `requires_approval` now tracks the latest approval per `(call_id, tool)` in
  one left-to-right pass instead of rescanning all earlier events for each
  call. Ordering, vacuous-pass, and failure semantics are unchanged.

### Notes

- Initial public release of `pytest-agent-behavior` 0.1.0.
