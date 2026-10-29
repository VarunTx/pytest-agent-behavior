from __future__ import annotations

import pytest

from pytest_agent_behavior import AgentAssertionError, AgentAssertions, Trace


def make_trace(events: list[dict]) -> Trace:
    return Trace.from_dict({"schema_version": 1, "events": events})


def approval(call_id: str = "c1", tool: str = "send_email", decision: str = "approved") -> dict:
    return {
        "type": "approval",
        "call_id": call_id,
        "tool": tool,
        "decision": decision,
    }


def call(
    call_id: str = "c1",
    tool: str = "send_email",
    arguments: dict | None = None,
) -> dict:
    return {
        "type": "tool_call",
        "call_id": call_id,
        "tool": tool,
        "arguments": {"to": "fake@example.com"} if arguments is None else arguments,
    }


def test_preceding_matching_approval_passes() -> None:
    check = AgentAssertions(make_trace([approval(), call()]))
    assert check.requires_approval("send_email") is None


def test_no_approval_fails_with_location_and_state() -> None:
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(make_trace([call(call_id="c2")])).requires_approval("send_email")
    message = str(caught.value)
    assert "Agent behavior assertion failed: requires_approval" in message
    assert "tool: send_email" in message
    assert "event index: 0" in message
    assert "call_id: c2" in message
    assert "observed: no matching preceding approval" in message


def test_approval_after_call_does_not_authorize_it() -> None:
    trace = make_trace([call(), approval()])
    with pytest.raises(AgentAssertionError, match="no matching preceding approval"):
        AgentAssertions(trace).requires_approval("send_email")


def test_approval_for_another_call_id_does_not_authorize() -> None:
    trace = make_trace([approval(call_id="other"), call(call_id="c1")])
    with pytest.raises(AgentAssertionError, match="call_id: c1"):
        AgentAssertions(trace).requires_approval("send_email")


def test_approval_for_another_tool_does_not_authorize() -> None:
    trace = make_trace([approval(tool="other_tool"), call(tool="send_email")])
    with pytest.raises(AgentAssertionError, match="no matching preceding approval"):
        AgentAssertions(trace).requires_approval("send_email")


def test_latest_approval_is_tracked_per_call_id_and_tool() -> None:
    trace = make_trace(
        [
            approval(call_id="c1", tool="send_email", decision="approved"),
            approval(call_id="c1", tool="other_tool", decision="denied"),
            call(call_id="c1", tool="send_email"),
        ]
    )
    assert AgentAssertions(trace).requires_approval("send_email") is None


def test_approved_then_denied_before_call_fails() -> None:
    trace = make_trace([approval(decision="approved"), approval(decision="denied"), call()])
    with pytest.raises(
        AgentAssertionError,
        match="last matching preceding approval was denied",
    ):
        AgentAssertions(trace).requires_approval("send_email")


def test_denied_then_approved_before_call_passes() -> None:
    trace = make_trace([approval(decision="denied"), approval(decision="approved"), call()])
    assert AgentAssertions(trace).requires_approval("send_email") is None


def test_one_calls_approval_does_not_authorize_another() -> None:
    trace = make_trace(
        [
            approval(call_id="c1"),
            call(call_id="c1"),
            call(call_id="c2"),
        ]
    )
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).requires_approval("send_email")
    message = str(caught.value)
    assert "unauthorized calls: 1" in message
    assert "event index: 2" in message
    assert "call_id: c2" in message


def test_approval_and_call_tool_matching_is_case_sensitive() -> None:
    trace = make_trace([approval(tool="Send_Email"), call(tool="send_email")])
    with pytest.raises(AgentAssertionError):
        AgentAssertions(trace).requires_approval("send_email")


def test_approval_call_id_matching_is_case_sensitive() -> None:
    trace = make_trace([approval(call_id="C1"), call(call_id="c1")])
    with pytest.raises(AgentAssertionError):
        AgentAssertions(trace).requires_approval("send_email")


def test_approvals_only_and_missing_tool_pass_vacuously() -> None:
    approval_only = make_trace([approval(), approval(decision="denied")])
    assert AgentAssertions(approval_only).requires_approval("send_email") is None
    assert AgentAssertions(make_trace([])).requires_approval("send_email") is None


def test_approval_only_does_not_count_as_a_call() -> None:
    approval_only = make_trace([approval()])
    check = AgentAssertions(approval_only)
    check.requires_approval("send_email")
    with pytest.raises(AgentAssertionError):
        check.called("send_email")


def test_unrelated_tool_calls_are_ignored_by_filter() -> None:
    trace = make_trace([call(call_id="c1", tool="send_email"), call(call_id="c2", tool="log")])
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).requires_approval("send_email")
    message = str(caught.value)
    assert "unauthorized calls: 1" in message
    assert "event index: 0" in message
    assert "event index: 1" not in message


def test_all_unauthorized_calls_reported_with_bounded_output() -> None:
    events = [call(call_id=f"c{index}") for index in range(30)]
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(make_trace(events)).requires_approval("send_email")
    message = str(caught.value)
    assert "unauthorized calls: 30 (showing 10)" in message
    assert "20 more unauthorized call(s) omitted" in message
    assert "event index: 9" in message
    assert "event index: 10" not in message
    assert len(message) < 5000


def test_approval_failure_does_not_include_argument_values() -> None:
    trace = make_trace([call(arguments={"password": "sk-live-SECRET", "nested": {"token": "abc"}})])
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).requires_approval("send_email")
    message = str(caught.value)
    assert "sk-live-SECRET" not in message
    assert "abc" not in message
    assert "password" not in message


def test_requires_approval_rejects_invalid_tool_parameters() -> None:
    check = AgentAssertions(make_trace([]))
    with pytest.raises(TypeError, match="tool must be a string"):
        check.requires_approval(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tool must be a nonempty string"):
        check.requires_approval("")
