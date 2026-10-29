"""Minimal pytest plugin exposing the ``agent_assertions`` fixture."""

from __future__ import annotations

import pytest

from .assertions import AgentAssertions, AgentAssertionsFactory
from .models import Trace


@pytest.fixture
def agent_assertions() -> AgentAssertionsFactory:
    """Return a factory that builds assertions for a validated Trace."""

    def factory(trace: Trace) -> AgentAssertions:
        return AgentAssertions(trace)

    return factory
