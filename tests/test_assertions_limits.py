from __future__ import annotations

import pytest

from pytest_agent_behavior import AgentAssertionError, AgentAssertions, Trace


def make_trace(events: list[dict] | None = None) -> Trace:
    return Trace.from_dict({"schema_version": 1, "events": events or []})


def call(
    call_id: str,
    tool: str = "send_email",
    arguments: dict | None = None,
) -> dict:
    return {
        "type": "tool_call",
        "call_id": call_id,
        "tool": tool,
        "arguments": {} if arguments is None else arguments,
    }


def approval(call_id: str, tool: str = "send_email") -> dict:
    return {
        "type": "approval",
        "call_id": call_id,
        "tool": tool,
        "decision": "approved",
    }


def test_max_calls_all_tools_counts_calls_not_approvals() -> None:
    trace = make_trace([approval("c1"), call("c1"), approval("c2"), call("c2", tool="log")])
    check = AgentAssertions(trace)
    assert check.max_calls(2) is None
    with pytest.raises(AgentAssertionError) as caught:
        check.max_calls(1)
    message = str(caught.value)
    assert "Agent behavior assertion failed: max_calls" in message
    assert "tool: (any)" in message
    assert "observed: 2 tool_call(s) at event indices [1, 3]" in message


def test_max_calls_filtered_by_exact_tool_name() -> None:
    trace = make_trace([call("c1", tool="send_email"), call("c2", tool="Send_Email")])
    check = AgentAssertions(trace)
    assert check.max_calls(1, tool="send_email") is None
    with pytest.raises(AgentAssertionError, match="tool: send_email"):
        check.max_calls(0, tool="send_email")


def test_max_calls_zero_and_boundary() -> None:
    assert AgentAssertions(make_trace([])).max_calls(0) is None
    check = AgentAssertions(make_trace([call("c1")]))
    with pytest.raises(AgentAssertionError, match="at most 0"):
        check.max_calls(0)
    assert check.max_calls(1) is None


@pytest.mark.parametrize("value", [True, False, 1.0, "1", object()])
def test_max_calls_rejects_noninteger_limits(value: object) -> None:
    with pytest.raises(TypeError, match="limit must be an integer"):
        AgentAssertions(make_trace()).max_calls(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, -100])
def test_max_calls_rejects_negative_limits(value: int) -> None:
    with pytest.raises(ValueError, match="limit must be nonnegative"):
        AgentAssertions(make_trace()).max_calls(value)


def test_max_calls_rejects_invalid_tool_parameter() -> None:
    check = AgentAssertions(make_trace())
    with pytest.raises(TypeError, match="tool must be a string"):
        check.max_calls(1, tool=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tool must be a nonempty string"):
        check.max_calls(1, tool="")


def test_max_repeated_calls_counts_nonconsecutive_occurrences() -> None:
    trace = make_trace(
        [
            approval("c1"),
            call("c1", arguments={"action": "repeat"}),
            approval("c2"),
            call("c2", arguments={"action": "different"}),
            call("c3", arguments={"action": "repeat"}),
        ]
    )
    check = AgentAssertions(trace)
    assert check.max_repeated_calls(2) is None
    with pytest.raises(AgentAssertionError) as caught:
        check.max_repeated_calls(1)
    message = str(caught.value)
    assert "observed: 1 signature(s) exceed the limit" in message
    assert "count: 2" in message
    assert "event indices: [1, 4]" in message


def test_nested_object_key_order_does_not_affect_signature() -> None:
    first = {"outer": {"a": 1, "b": [{"x": 1, "y": 2}]}}
    second = {"outer": {"b": [{"y": 2, "x": 1}], "a": 1}}
    trace = make_trace([call("c1", arguments=first), call("c2", arguments=second)])
    with pytest.raises(AgentAssertionError, match="count: 2"):
        AgentAssertions(trace).max_repeated_calls(1)


def test_array_order_affects_signature() -> None:
    trace = make_trace(
        [call("c1", arguments={"items": [1, 2]}), call("c2", arguments={"items": [2, 1]})]
    )
    assert AgentAssertions(trace).max_repeated_calls(1) is None


def test_strict_boolean_integer_float_signatures() -> None:
    events: list[dict] = []
    counter = 1
    for value in (True, 1, 1.0):
        for _ in range(2):
            events.append(call(f"c{counter}", arguments={"value": value}))
            counter += 1

    check = AgentAssertions(make_trace(events))
    assert check.max_repeated_calls(2) is None
    with pytest.raises(AgentAssertionError) as caught:
        check.max_repeated_calls(1)
    assert "observed: 3 signature(s) exceed the limit" in str(caught.value)


def test_different_tools_with_identical_arguments_are_separate() -> None:
    trace = make_trace(
        [
            call("c1", tool="send_email", arguments={"value": 1}),
            call("c2", tool="send_email", arguments={"value": 1}),
            call("c3", tool="log", arguments={"value": 1}),
            call("c4", tool="log", arguments={"value": 1}),
        ]
    )
    check = AgentAssertions(trace)
    assert check.max_repeated_calls(2) is None
    with pytest.raises(AgentAssertionError) as caught:
        check.max_repeated_calls(1)
    assert "observed: 2 signature(s)" in str(caught.value)


def test_different_call_ids_do_not_make_calls_distinct() -> None:
    trace = make_trace(
        [
            call("c1", arguments={"same": True}),
            call("c2", arguments={"same": True}),
            call("c3", arguments={"same": True}),
        ]
    )
    with pytest.raises(AgentAssertionError, match="count: 3"):
        AgentAssertions(trace).max_repeated_calls(2)


def test_max_repeated_calls_filters_by_tool_before_grouping() -> None:
    trace = make_trace(
        [
            call("c1", tool="send_email", arguments={"value": 1}),
            call("c2", tool="send_email", arguments={"value": 1}),
            *[call(f"u{index}", tool="log", arguments={"value": 1}) for index in range(5)],
        ]
    )
    check = AgentAssertions(trace)
    assert check.max_repeated_calls(2, tool="send_email") is None
    with pytest.raises(AgentAssertionError, match="tool: log"):
        check.max_repeated_calls(2, tool="log")


def test_max_repeated_calls_zero_and_empty() -> None:
    assert AgentAssertions(make_trace([approval("c1")])).max_repeated_calls(0) is None
    with pytest.raises(AgentAssertionError, match="at most 0"):
        AgentAssertions(make_trace([call("c1")])).max_repeated_calls(0)


@pytest.mark.parametrize("value", [True, False, 2.0, "2", object()])
def test_max_repeated_calls_rejects_noninteger_limits(value: object) -> None:
    with pytest.raises(TypeError, match="limit must be an integer"):
        AgentAssertions(make_trace()).max_repeated_calls(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, -5])
def test_max_repeated_calls_rejects_negative_limits(value: int) -> None:
    with pytest.raises(ValueError, match="limit must be nonnegative"):
        AgentAssertions(make_trace()).max_repeated_calls(value)


def test_max_repeated_calls_rejects_invalid_tool() -> None:
    check = AgentAssertions(make_trace())
    with pytest.raises(TypeError, match="tool must be a string"):
        check.max_repeated_calls(1, tool=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonempty"):
        check.max_repeated_calls(1, tool="")


def test_repeated_call_failure_reports_indices_without_arguments() -> None:
    arguments = {"password": "sk-live-SECRET", "nested": {"token": "abc"}}
    trace = make_trace([call("c1", arguments=arguments), call("c2", arguments=arguments)])
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).max_repeated_calls(1)
    message = str(caught.value)
    assert "event indices: [0, 1]" in message
    assert "sk-live-SECRET" not in message
    assert "password" not in message
    assert "abc" not in message


def test_repeated_call_output_is_bounded_for_many_signatures() -> None:
    events = []
    counter = 1
    for signature in range(30):
        for _ in range(2):
            events.append(call(f"c{counter}", arguments={"signature": signature}))
            counter += 1
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(make_trace(events)).max_repeated_calls(1)
    message = str(caught.value)
    assert "observed: 30 signature(s) exceed the limit (showing 10)" in message
    assert "20 more violating signature(s) omitted" in message
    assert len(message) < 5000


def test_repeated_call_failure_output_is_stable() -> None:
    trace = make_trace([call("c1", arguments={"x": 1}), call("c2", arguments={"x": 1})])
    messages = []
    for _ in range(2):
        with pytest.raises(AgentAssertionError) as caught:
            AgentAssertions(trace).max_repeated_calls(1)
        messages.append(str(caught.value))
    assert messages[0] == messages[1]
    assert "0x" not in messages[0]
