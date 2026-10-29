"""Intentionally failing demonstrations.

This file is not named ``test_*.py``, so normal collection skips it. Run it
explicitly to see two assertion failures and a nonzero exit status:

    pytest examples/failing_demo.py -q
"""

from __future__ import annotations

from demo_agents import run_faulty_agent


def test_faulty_agent_exceeds_repeated_call_limit(agent_assertions) -> None:
    trace = run_faulty_agent()
    check = agent_assertions(trace)
    check.called("send_email", times=4)
    check.max_repeated_calls(2)


def test_faulty_agent_has_no_approval(agent_assertions) -> None:
    trace = run_faulty_agent()
    agent_assertions(trace).requires_approval("send_email")
