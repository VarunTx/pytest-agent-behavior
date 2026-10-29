from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pytest_agent_behavior import AgentAssertionError, AgentAssertions, Trace


def make_trace(*, calls: list[str] | None = None) -> Trace:
    events = []
    for index, tool in enumerate(calls or [], start=1):
        events.append(
            {
                "type": "tool_call",
                "call_id": f"c{index}",
                "tool": tool,
                "arguments": {"index": index},
            }
        )
    return Trace.from_dict({"schema_version": 1, "events": events})


def test_called_passes_at_least_once_and_returns_none() -> None:
    check = AgentAssertions(make_trace(calls=["send_email"]))
    assert check.called("send_email") is None
    assert check.called("send_email", times=1) is None


def test_called_at_least_once_fails_for_empty_trace() -> None:
    with pytest.raises(AgentAssertionError) as caught:
        AgentAssertions(make_trace()).called("send_email")
    message = str(caught.value)
    assert "Agent behavior assertion failed: called" in message
    assert "expected: at least 1 tool_call" in message
    assert "observed: 0 tool_calls" in message


def test_called_exact_count_passes_and_reports_indices() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": 1,
            "events": [
                {"type": "tool_call", "call_id": "c1", "tool": "send_email", "arguments": {}},
                {"type": "approval", "call_id": "c2", "tool": "send_email", "decision": "approved"},
                {"type": "tool_call", "call_id": "c2", "tool": "send_email", "arguments": {}},
            ],
        }
    )
    check = AgentAssertions(trace)
    check.called("send_email", times=2)
    with pytest.raises(AgentAssertionError) as caught:
        check.called("send_email", times=1)
    message = str(caught.value)
    assert "expected: exactly 1 tool_call(s)" in message
    assert "observed: 2 tool_call(s) at event indices [0, 2]" in message


def test_called_zero_is_exact_zero() -> None:
    check = AgentAssertions(make_trace(calls=["other"]))
    assert check.called("send_email", times=0) is None
    with pytest.raises(AgentAssertionError, match="expected: exactly 0"):
        check.called("other", times=0)


def test_called_matching_is_exact_and_case_sensitive() -> None:
    check = AgentAssertions(make_trace(calls=["Send_Email", "send_email_2"]))
    with pytest.raises(AgentAssertionError):
        check.called("send_email")
    with pytest.raises(AgentAssertionError):
        check.called("SEND_EMAIL")
    check.called("Send_Email")


def test_not_called_passes_and_fails_with_indices() -> None:
    check = AgentAssertions(make_trace(calls=["send_email", "other"]))
    assert check.not_called("missing") is None
    with pytest.raises(AgentAssertionError) as caught:
        check.not_called("send_email")
    message = str(caught.value)
    assert "Agent behavior assertion failed: not_called" in message
    assert "observed: 1 tool_call(s) at event indices [0]" in message


def test_called_and_not_called_are_independent() -> None:
    trace = make_trace(calls=["send_email"])
    first = AgentAssertions(trace)
    second = AgentAssertions(trace)
    with pytest.raises(AgentAssertionError):
        first.not_called("send_email")
    assert second.called("send_email") is None


@pytest.mark.parametrize("value", [True, False, 1.0, "1", object()])
def test_called_rejects_noninteger_counts(value: object) -> None:
    with pytest.raises(TypeError, match="times must be an integer"):
        AgentAssertions(make_trace()).called("t", times=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, -10])
def test_called_rejects_negative_counts(value: int) -> None:
    with pytest.raises(ValueError, match="times must be nonnegative"):
        AgentAssertions(make_trace()).called("t", times=value)


def test_empty_tool_name_is_invalid() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        AgentAssertions(make_trace()).called("")


def test_whitespace_tool_name_is_nonempty_and_allowed() -> None:
    check = AgentAssertions(make_trace())
    assert check.called(" ", times=0) is None
    assert check.not_called(" ") is None


@pytest.mark.parametrize("value", [None, 1, True, object()])
def test_called_rejects_nonstring_tool(value: object) -> None:
    with pytest.raises(TypeError, match="tool must be a string"):
        AgentAssertions(make_trace()).called(value)  # type: ignore[arg-type]


def test_not_called_rejects_invalid_tool() -> None:
    check = AgentAssertions(make_trace())
    with pytest.raises(TypeError, match="tool must be a string"):
        check.not_called(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tool must be a nonempty string"):
        check.not_called("")


def test_agent_assertions_rejects_unvalidated_input() -> None:
    with pytest.raises(TypeError, match="trace must be a Trace"):
        AgentAssertions({"schema_version": 1, "events": []})  # type: ignore[arg-type]


def test_assertions_raise_explicitly_under_python_optimized_mode(tmp_path: Path) -> None:
    script = tmp_path / "optimized_check.py"
    script.write_text(
        "\n".join(
            [
                "from pytest_agent_behavior import AgentAssertionError, AgentAssertions, Trace",
                "trace = Trace.from_dict({'schema_version': 1, 'events': [",
                "    {'type': 'tool_call', 'call_id': 'c1', 'tool': 'send_email', 'arguments': {}}",
                "]})",
                "check = AgentAssertions(trace)",
                "checks = [",
                "    lambda: check.called('send_email', times=2),",
                "    lambda: check.not_called('send_email'),",
                "    lambda: check.requires_approval('send_email'),",
                "    lambda: check.max_calls(0),",
                "    lambda: check.max_repeated_calls(0),",
                "]",
                "for assertion in checks:",
                "    try:",
                "        assertion()",
                "    except AgentAssertionError:",
                "        continue",
                "    raise SystemExit(4)",
                "raise SystemExit(0)",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-O", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
