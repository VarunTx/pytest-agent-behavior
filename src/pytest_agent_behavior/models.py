"""Immutable trace models and strict JSON loaders."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeAlias

from ._json import JSONValue, copy_json_object, type_name
from .exceptions import TraceValidationError

_MISSING = object()
_TOOL_CALL_FIELDS = frozenset({"type", "call_id", "tool", "arguments"})
_APPROVAL_FIELDS = frozenset({"type", "call_id", "tool", "decision"})
_TRACE_FIELDS = frozenset({"schema_version", "events"})


def _nonempty_string(value: object, path: str) -> str:
    if type(value) is not str:
        raise TraceValidationError(f"{path}: expected a nonempty string, got {type_name(value)}")
    if not value:
        raise TraceValidationError(f"{path}: expected a nonempty string")
    return value


@dataclass(frozen=True, slots=True, init=False)
class ToolCall:
    """One observed attempt to invoke a tool.

    ``arguments`` is stored as a validated deep copy. Reading the property
    returns another fresh copy, so callers cannot mutate the stored trace.
    The public ``type`` is always ``"tool_call"``.
    """

    type: Literal["tool_call"]
    call_id: str
    tool: str
    _arguments: dict[str, JSONValue] = field(repr=False)

    def __init__(
        self,
        call_id: str,
        tool: str,
        arguments: dict[str, JSONValue],
        *,
        type: str = "tool_call",
    ) -> None:
        if type != "tool_call":
            raise TraceValidationError('type: expected "tool_call"')
        object.__setattr__(self, "type", "tool_call")
        object.__setattr__(self, "call_id", _nonempty_string(call_id, "call_id"))
        object.__setattr__(self, "tool", _nonempty_string(tool, "tool"))
        object.__setattr__(self, "_arguments", copy_json_object(arguments, "arguments"))

    @property
    def arguments(self) -> dict[str, JSONValue]:
        """Return a fresh, mutable copy of the call's JSON arguments."""
        return copy_json_object(self._arguments, "arguments")

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible dictionary for this event."""
        return {
            "type": self.type,
            "call_id": self.call_id,
            "tool": self.tool,
            "arguments": self.arguments,
        }


@dataclass(frozen=True, slots=True, init=False)
class Approval:
    """One observed approval decision associated with a call.

    Approvals are metadata in the trace. The package cannot verify who made a
    decision or whether tool execution was actually blocked.
    """

    type: Literal["approval"]
    call_id: str
    tool: str
    decision: Literal["approved", "denied"]

    def __init__(
        self,
        call_id: str,
        tool: str,
        decision: str,
        *,
        type: str = "approval",
    ) -> None:
        if type != "approval":
            raise TraceValidationError('type: expected "approval"')
        if decision not in ("approved", "denied"):
            raise TraceValidationError(
                f'decision: expected "approved" or "denied", got {type_name(decision)}'
            )
        object.__setattr__(self, "type", "approval")
        object.__setattr__(self, "call_id", _nonempty_string(call_id, "call_id"))
        object.__setattr__(self, "tool", _nonempty_string(tool, "tool"))
        object.__setattr__(self, "decision", decision)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible dictionary for this event."""
        return {
            "type": self.type,
            "call_id": self.call_id,
            "tool": self.tool,
            "decision": self.decision,
        }


Event: TypeAlias = ToolCall | Approval


@dataclass(frozen=True, slots=True, init=False)
class Trace:
    """An ordered, immutable sequence of tool calls and approvals.

    List (or tuple) position is the only ordering information. Traces are
    single-run and sequential; timestamps are not part of this format.
    """

    schema_version: int
    events: tuple[Event, ...]

    def __init__(self, events: list[Event] | tuple[Event, ...], *, schema_version: int = 1) -> None:
        if type(schema_version) is not int:
            raise TraceValidationError(
                f"schema_version: expected integer 1, got {type_name(schema_version)}"
            )
        if schema_version != 1:
            raise TraceValidationError(
                f"schema_version: unsupported version {schema_version}; expected 1"
            )
        if type(events) is not list and type(events) is not tuple:
            raise TraceValidationError(
                f"events: expected an ordered sequence, got {type_name(events)}"
            )

        validated: list[Event] = []
        seen_call_ids: dict[str, int] = {}
        for index, event in enumerate(events):
            if type(event) is ToolCall:
                if event.call_id in seen_call_ids:
                    first = seen_call_ids[event.call_id]
                    raise TraceValidationError(
                        f"events[{index}].call_id: duplicate tool_call call_id "
                        f"(first used at events[{first}])"
                    )
                seen_call_ids[event.call_id] = index
            elif type(event) is not Approval:
                raise TraceValidationError(
                    f"events[{index}]: expected ToolCall or Approval, got {type_name(event)}"
                )
            validated.append(event)

        object.__setattr__(self, "schema_version", 1)
        object.__setattr__(self, "events", tuple(validated))

    def __repr__(self) -> str:
        """Return a short summary without dumping the event list."""
        return f"Trace(schema_version={self.schema_version}, events={len(self.events)})"

    @classmethod
    def from_dict(cls, data: object) -> Trace:
        """Load and validate a trace from a JSON-compatible dictionary."""
        if type(data) is not dict:
            raise TraceValidationError(f"trace: expected a JSON object, got {type_name(data)}")
        _reject_non_string_keys(data, "trace")
        unknown = sorted(set(data) - _TRACE_FIELDS)
        if unknown:
            raise TraceValidationError(f"trace: unknown field(s): {', '.join(unknown)}")

        schema_version = _required_field(data, "schema_version", "trace")
        raw_events = _required_field(data, "events", "trace")
        if type(raw_events) is not list:
            raise TraceValidationError(
                f"events: expected a JSON array, got {type_name(raw_events)}"
            )

        events = [_event_from_dict(raw_event, index) for index, raw_event in enumerate(raw_events)]
        return cls(events, schema_version=schema_version)

    @classmethod
    def from_json(cls, text: str) -> Trace:
        """Load and validate a trace from JSON text."""
        if type(text) is not str:
            raise TypeError(f"text must be str, got {type_name(text)}")
        try:
            data = json.loads(text, parse_constant=_reject_json_constant)
        except _InvalidJSONConstant as exc:
            raise TraceValidationError(
                f"JSON decode error: invalid JSON constant {exc.token}"
            ) from None
        except json.JSONDecodeError as exc:
            raise TraceValidationError(
                f"JSON decode error at line {exc.lineno} column {exc.colno}: {exc.msg}"
            ) from None
        return cls.from_dict(data)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str]) -> Trace:
        """Read UTF-8 JSON from *path* and validate it.

        Missing files and permission errors propagate as their normal
        filesystem exception types.
        """
        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise TraceValidationError(f"{file_path}: expected UTF-8 encoded JSON text") from exc
        return cls.from_json(text)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible dictionary in event order."""
        return {
            "schema_version": self.schema_version,
            "events": [event.to_dict() for event in self.events],
        }

    def to_json(self) -> str:
        """Serialize to deterministic, human-readable JSON text."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def _event_from_dict(raw_event: object, index: int) -> Event:
    path = f"events[{index}]"
    if type(raw_event) is not dict:
        raise TraceValidationError(f"{path}: expected a JSON object, got {type_name(raw_event)}")
    _reject_non_string_keys(raw_event, path)

    event_type = _required_field(raw_event, "type", path)
    if type(event_type) is not str or event_type not in ("tool_call", "approval"):
        raise TraceValidationError(
            f'{path}.type: expected "tool_call" or "approval", got {type_name(event_type)}'
        )

    allowed = _TOOL_CALL_FIELDS if event_type == "tool_call" else _APPROVAL_FIELDS
    unknown = sorted(set(raw_event) - allowed)
    if unknown:
        raise TraceValidationError(f"{path}: unknown field(s): {', '.join(unknown)}")

    call_id = _required_field(raw_event, "call_id", path)
    tool = _required_field(raw_event, "tool", path)
    try:
        if event_type == "tool_call":
            arguments = _required_field(raw_event, "arguments", path)
            return ToolCall(
                call_id=call_id,
                tool=tool,
                arguments=arguments,
            )
        decision = _required_field(raw_event, "decision", path)
        return Approval(
            call_id=call_id,
            tool=tool,
            decision=decision,
        )
    except TraceValidationError as exc:
        raise TraceValidationError(f"{path}.{exc}") from None


def _required_field(data: dict[str, Any], name: str, path: str) -> Any:
    if name not in data:
        raise TraceValidationError(f"{path}.{name}: field is required")
    return data[name]


def _reject_non_string_keys(data: dict[Any, Any], path: str) -> None:
    for key in data:
        if type(key) is not str:
            raise TraceValidationError(f"{path}: JSON object keys must be strings")


class _InvalidJSONConstant(ValueError):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


def _reject_json_constant(token: str) -> Any:
    raise _InvalidJSONConstant(token)
