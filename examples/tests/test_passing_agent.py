from __future__ import annotations

from demo_agents import run_passing_agent


def test_passing_demo_agent(agent_assertions) -> None:
    trace = run_passing_agent()
    check = agent_assertions(trace)

    check.called("lookup_order", times=1)
    check.called("send_email", times=1)
    check.not_called("issue_refund")
    check.requires_approval("send_email")
    check.max_calls(2)
    check.max_repeated_calls(1)
