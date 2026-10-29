"""Two tiny, deterministic demo agents that emit observed traces.

The tools below are local fakes. They perform no network requests and write
nothing to disk. Instrumentation is deliberately manual: the recorder records
an invocation attempt immediately before it calls the fake tool. No agent
framework is imported or monkey-patched.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pytest_agent_behavior import Approval, ToolCall, Trace


def _lookup_order(order_id: str) -> dict[str, str]:
    return {"order_id": order_id, "status": "ready"}


def _send_email(to: str, body: str) -> dict[str, object]:
    # Fake delivery: the body is returned for inspection, never sent.
    return {"to": to, "body": body, "delivered": False}


def _issue_refund(order_id: str, amount_cents: int) -> dict[str, object]:
    return {"order_id": order_id, "amount_cents": amount_cents, "issued": False}


_TOOLS: dict[str, Callable[..., Any]] = {
    "lookup_order": _lookup_order,
    "send_email": _send_email,
    "issue_refund": _issue_refund,
}


class TraceRecorder:
    """Record invocation attempts and execute local fake tools."""

    def __init__(self) -> None:
        self._events: list[Approval | ToolCall] = []
        self._next_call = 1

    def invoke(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        approval: str | None = None,
    ) -> Any:
        if tool not in _TOOLS:
            raise KeyError(f"unknown demo tool: {tool}")
        call_id = f"c{self._next_call}"
        self._next_call += 1
        if approval is not None:
            self._events.append(Approval(call_id, tool, approval))
        self._events.append(ToolCall(call_id, tool, arguments))
        return _TOOLS[tool](**arguments)

    def trace(self) -> Trace:
        return Trace(self._events)


def run_passing_agent(recorder: TraceRecorder | None = None) -> Trace:
    """Run the correct demo agent and return its observed trace."""
    rec = recorder or TraceRecorder()
    order = rec.invoke("lookup_order", {"order_id": "order-42"})
    if order["status"] == "ready":
        rec.invoke(
            "send_email",
            {
                "to": "fake-customer@example.com",
                "body": "Your fake order order-42 is ready.",
            },
            approval="approved",
        )
    return rec.trace()


def run_faulty_agent(recorder: TraceRecorder | None = None) -> Trace:
    """Run the deliberately faulty agent and return its observed trace.

    It sends four identical emails without any approval events.
    """
    rec = recorder or TraceRecorder()
    for _ in range(4):
        rec.invoke(
            "send_email",
            {
                "to": "fake-customer@example.com",
                "body": "Your fake order order-42 is ready.",
            },
        )
    return rec.trace()
