from __future__ import annotations

from importlib.metadata import entry_points, version

from pytest_agent_behavior import AgentAssertions, Trace, __version__


def test_package_version_matches_distribution_metadata() -> None:
    assert version("pytest-agent-behavior") == __version__ == "0.1.0"


def test_pytest11_entry_point_is_installed() -> None:
    matches = [entry for entry in entry_points(group="pytest11") if entry.name == "agent_behavior"]
    assert matches
    assert matches[0].value == "pytest_agent_behavior.plugin"


def test_agent_assertions_type_annotation() -> None:
    from pytest_agent_behavior.plugin import agent_assertions

    fixture_function = getattr(agent_assertions, "__wrapped__", agent_assertions)
    assert fixture_function.__annotations__["return"] == "AgentAssertionsFactory"
    assert isinstance(
        AgentAssertions(Trace.from_dict({"schema_version": 1, "events": []})),
        AgentAssertions,
    )


def test_fixture_is_discovered_and_works_with_parametrization(pytester) -> None:
    pytester.makepyfile(
        """
        import pytest
        from pytest_agent_behavior import Trace

        @pytest.mark.parametrize("times", [1, 1])
        def test_fixture_and_parametrization(agent_assertions, times):
            trace = Trace.from_dict({
                "schema_version": 1,
                "events": [
                    {
                        "type": "tool_call",
                        "call_id": "c1",
                        "tool": "send_email",
                        "arguments": {"to": "fake@example.com"},
                    }
                ],
            })
            check = agent_assertions(trace)
            check.called("send_email", times=times)
            check.max_calls(1)
            check.max_repeated_calls(1)
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=2)
    assert result.ret == 0


def test_fixture_failure_has_clear_pytest_output(pytester) -> None:
    pytester.makepyfile(
        """
        from pytest_agent_behavior import Trace

        def test_missing_approval(agent_assertions):
            trace = Trace.from_dict({
                "schema_version": 1,
                "events": [
                    {
                        "type": "tool_call",
                        "call_id": "c2",
                        "tool": "send_email",
                        "arguments": {"body": "private body"},
                    }
                ],
            })
            agent_assertions(trace).requires_approval("send_email")
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(failed=1)
    assert result.ret == 1
    output = result.stdout.str()
    assert "Agent behavior assertion failed: requires_approval" in output
    assert "event index: 0" in output
    assert "call_id: c2" in output
    assert "observed: no matching preceding approval" in output
    assertion_message = output.split("Agent behavior assertion failed:", 1)[1]
    assert "private body" not in assertion_message
    assert "AgentAssertionError" in output


def test_fixture_rejects_unvalidated_mapping_as_programmer_error(pytester) -> None:
    pytester.makepyfile(
        """
        def test_bad_factory_input(agent_assertions):
            agent_assertions({"schema_version": 1, "events": []})
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(failed=1)
    assert "TypeError: trace must be a Trace instance" in result.stdout.str()


def test_malformed_trace_is_a_validation_error_not_assertion_failure(pytester) -> None:
    pytester.makepyfile(
        """
        from pytest_agent_behavior import Trace, TraceValidationError

        def test_malformed_trace():
            try:
                Trace.from_dict({"schema_version": 1, "events": [{"type": "unknown"}]})
            except TraceValidationError as exc:
                assert "events[0].type" in str(exc)
            else:
                raise AssertionError("expected TraceValidationError")
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)
