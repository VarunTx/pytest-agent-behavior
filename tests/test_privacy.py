from __future__ import annotations

import pytest

from pytest_agent_behavior import AgentAssertionError, AgentAssertions, ToolCall, Trace
from pytest_agent_behavior.exceptions import TraceValidationError

SECRET = "sk-live-SECRET-123"
SECOND_SECRET = "personal-token-456"


def sensitive_trace() -> Trace:
    return Trace.from_dict(
        {
            "schema_version": 1,
            "events": [
                {
                    "type": "tool_call",
                    "call_id": "c1",
                    "tool": "send_email",
                    "arguments": {
                        "password": SECRET,
                        "nested": {"token": SECOND_SECRET},
                    },
                }
            ],
        }
    )


def test_reprs_do_not_include_argument_values() -> None:
    trace = sensitive_trace()
    call = trace.events[0]
    assert isinstance(call, ToolCall)
    assert repr(trace) == "Trace(schema_version=1, events=1)"
    for rendered in (repr(trace), repr(call)):
        assert SECRET not in rendered
        assert SECOND_SECRET not in rendered
        assert "password" not in rendered


def test_assertion_failures_do_not_include_argument_values() -> None:
    trace = sensitive_trace()
    checks = [
        lambda: AgentAssertions(trace).called("send_email", times=2),
        lambda: AgentAssertions(trace).not_called("send_email"),
        lambda: AgentAssertions(trace).requires_approval("send_email"),
        lambda: AgentAssertions(trace).max_calls(0),
        lambda: AgentAssertions(trace).max_repeated_calls(0),
    ]
    for check in checks:
        with pytest.raises(AgentAssertionError) as caught:
            check()
        message = str(caught.value)
        assert SECRET not in message
        assert SECOND_SECRET not in message
        assert "password" not in message


def test_validation_errors_do_not_echo_unsupported_values() -> None:
    class SensitiveObject:
        def __repr__(self) -> str:
            return SECRET

    with pytest.raises(TraceValidationError) as caught:
        ToolCall("c1", "send_email", {"payload": SensitiveObject()})
    message = str(caught.value)
    assert "events" not in message
    assert SECRET not in message
    assert "SensitiveObject" in message


def test_json_decode_errors_do_not_echo_document_text() -> None:
    with pytest.raises(TraceValidationError) as caught:
        Trace.from_json('{"password": "' + SECRET + '",')
    message = str(caught.value)
    assert SECRET not in message
    assert "line 1" in message
    assert "column" in message


def test_invalid_constant_errors_do_not_echo_other_document_text() -> None:
    text = '{"schema_version": 1, "events": [], "password": "' + SECRET + '", "bad": NaN}'
    with pytest.raises(TraceValidationError) as caught:
        Trace.from_json(text)
    message = str(caught.value)
    assert SECRET not in message
    assert "NaN" in message


def test_called_failure_output_is_bounded_for_large_trace() -> None:
    events = [
        {
            "type": "tool_call",
            "call_id": f"c{index}",
            "tool": "send_email",
            "arguments": {"index": index},
        }
        for index in range(1000)
    ]
    trace = Trace.from_dict({"schema_version": 1, "events": events})
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).called("send_email", times=1)
    message = str(caught.value)
    assert "observed: 1000 tool_call(s)" in message
    assert "... 980 more" in message
    assert message.count("event index") <= 1
    assert len(message) < 5000


def test_messages_contain_no_object_addresses() -> None:
    trace = sensitive_trace()
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(trace).requires_approval("send_email")
    assert "0x" not in str(caught.value)
    assert "0x" not in repr(trace)
