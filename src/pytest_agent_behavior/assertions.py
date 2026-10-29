"""Behavioral assertions over an observed trace."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from ._json import canonical_json
from .exceptions import AgentAssertionError
from .models import Approval, ToolCall, Trace

_MAX_EVENT_INDICES = 20
_MAX_VIOLATIONS = 10


class AgentAssertions:
    """Assertions over one immutable :class:`~pytest_agent_behavior.Trace`.

    Methods return ``None`` on success and raise
    :class:`~pytest_agent_behavior.AgentAssertionError` on behavioral failure.
    Invalid parameter types raise :class:`TypeError`; valid types with invalid
    values (such as a negative count or empty tool name) raise
    :class:`ValueError`.
    """

    def __init__(self, trace: Trace) -> None:
        if type(trace) is not Trace:
            raise TypeError("trace must be a Trace instance")
        self._trace = trace

    def called(self, tool: str, *, times: int | None = None) -> None:
        """Assert that *tool* was called at least once or exactly *times* times.

        Matching is exact and case-sensitive. Only ``tool_call`` events count.
        ``times=None`` means at least one; ``times=0`` means exactly zero.
        """
        tool = _validate_tool(tool, "tool")
        expected = _validate_times(times)
        indices = self._tool_call_indices(tool)

        if expected is None:
            if indices:
                return
            _fail(
                [
                    "Agent behavior assertion failed: called",
                    f"tool: {tool}",
                    "expected: at least 1 tool_call",
                    "observed: 0 tool_calls",
                ]
            )

        if len(indices) == expected:
            return
        _fail(
            [
                "Agent behavior assertion failed: called",
                f"tool: {tool}",
                f"expected: exactly {expected} tool_call(s)",
                f"observed: {len(indices)} tool_call(s) at event indices "
                f"{_format_indices(indices)}",
            ]
        )

    def not_called(self, tool: str) -> None:
        """Assert that *tool* has no matching ``tool_call`` events."""
        tool = _validate_tool(tool, "tool")
        indices = self._tool_call_indices(tool)
        if not indices:
            return
        _fail(
            [
                "Agent behavior assertion failed: not_called",
                f"tool: {tool}",
                "expected: no tool_call events",
                f"observed: {len(indices)} tool_call(s) at event indices "
                f"{_format_indices(indices)}",
            ]
        )

    def requires_approval(self, tool: str) -> None:
        """Assert every call to *tool* was preceded by a matching approval.

        For each matching call, the last preceding approval with the same
        ``call_id`` and tool must be ``"approved"``. A call with no such
        approval fails. If *tool* never appears, the assertion passes
        vacuously; combine it with :meth:`called` when existence matters.
        """
        tool = _validate_tool(tool, "tool")
        unauthorized: list[tuple[int, ToolCall, str]] = []
        latest_approvals: dict[tuple[str, str], str] = {}

        for index, event in enumerate(self._trace.events):
            if type(event) is Approval:
                latest_approvals[(event.call_id, event.tool)] = event.decision
                continue
            if type(event) is not ToolCall or event.tool != tool:
                continue

            decision = latest_approvals.get((event.call_id, event.tool))
            if decision is None:
                unauthorized.append(
                    (
                        index,
                        event,
                        "no matching preceding approval",
                    )
                )
            elif decision != "approved":
                unauthorized.append(
                    (
                        index,
                        event,
                        "last matching preceding approval was denied",
                    )
                )

        if not unauthorized:
            return

        shown = unauthorized[:_MAX_VIOLATIONS]
        lines = [
            "Agent behavior assertion failed: requires_approval",
            f"tool: {tool}",
            f"unauthorized calls: {len(unauthorized)} (showing {len(shown)})",
        ]
        for index, call, observed in shown:
            lines.extend(
                [
                    f"  event index: {index}",
                    f"  call_id: {call.call_id}",
                    "  expected: a preceding matching approval for the same "
                    "call_id and tool with decision approved",
                    f"  observed: {observed}",
                ]
            )
        if len(unauthorized) > len(shown):
            lines.append(
                f"  ... {len(unauthorized) - len(shown)} more unauthorized call(s) omitted"
            )
        _fail(lines)

    def max_calls(self, limit: int, *, tool: str | None = None) -> None:
        """Assert that tool-call events do not exceed *limit*.

        With ``tool=None`` every ``tool_call`` event counts. Approval events
        never count. A limit of zero is valid.
        """
        limit = _validate_limit(limit, "limit")
        if tool is not None:
            tool = _validate_tool(tool, "tool")
        indices = (
            [index for index, event in enumerate(self._trace.events) if type(event) is ToolCall]
            if tool is None
            else self._tool_call_indices(tool)
        )
        if len(indices) <= limit:
            return
        _fail(
            [
                "Agent behavior assertion failed: max_calls",
                f"tool: {tool if tool is not None else '(any)'}",
                f"expected: at most {limit} tool_call(s)",
                f"observed: {len(indices)} tool_call(s) at event indices "
                f"{_format_indices(indices)}",
            ]
        )

    def max_repeated_calls(self, limit: int, *, tool: str | None = None) -> None:
        """Assert no ``(tool, arguments)`` signature occurs more than *limit*.

        Occurrences are counted across the whole trace, not only consecutive
        runs. Object key order is ignored; array order and JSON value types
        are significant. This is a threshold check, not proof of a loop.
        """
        limit = _validate_limit(limit, "limit")
        if tool is not None:
            tool = _validate_tool(tool, "tool")

        groups: dict[tuple[Any, ...], list[int]] = {}
        for index, event in enumerate(self._trace.events):
            if type(event) is not ToolCall:
                continue
            if tool is not None and event.tool != tool:
                continue
            signature = (event.tool, canonical_json(event.arguments))
            groups.setdefault(signature, []).append(index)

        violations = [
            (signature[0], indices) for signature, indices in groups.items() if len(indices) > limit
        ]
        if not violations:
            return

        violations.sort(key=lambda item: item[1][0])
        shown = violations[:_MAX_VIOLATIONS]
        lines = [
            "Agent behavior assertion failed: max_repeated_calls",
            f"tool: {tool if tool is not None else '(any)'}",
            f"expected: at most {limit} call(s) per distinct (tool, arguments) signature",
            f"observed: {len(violations)} signature(s) exceed the limit (showing {len(shown)})",
        ]
        for violation_tool, indices in shown:
            lines.extend(
                [
                    f"  tool: {violation_tool}",
                    f"  count: {len(indices)}",
                    f"  event indices: {_format_indices(indices)}",
                ]
            )
        if len(violations) > len(shown):
            lines.append(
                f"  ... {len(violations) - len(shown)} more violating signature(s) omitted"
            )
        _fail(lines)

    def _tool_call_indices(self, tool: str) -> list[int]:
        return [
            index
            for index, event in enumerate(self._trace.events)
            if type(event) is ToolCall and event.tool == tool
        ]


AgentAssertionsFactory: TypeAlias = Callable[[Trace], AgentAssertions]
"""Public factory type returned by the ``agent_assertions`` fixture."""


def _validate_tool(value: object, name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _validate_limit(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _validate_times(value: object) -> int | None:
    if value is None:
        return None
    return _validate_limit(value, "times")


def _format_indices(indices: list[int]) -> str:
    if not indices:
        return "[]"
    shown = indices[:_MAX_EVENT_INDICES]
    rendered = ", ".join(str(index) for index in shown)
    if len(indices) > len(shown):
        rendered += f", ... {len(indices) - len(shown)} more"
    return f"[{rendered}]"


def _fail(lines: list[str]) -> None:
    raise AgentAssertionError("\n".join(lines))
