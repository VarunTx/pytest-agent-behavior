"""Exception types raised by :mod:`pytest_agent_behavior`."""

from __future__ import annotations


class TraceValidationError(ValueError):
    """A trace is structurally invalid or cannot be decoded as JSON.

    The message identifies the failing path (for example
    ``events[2].arguments``) and the expected kind of value. Argument values
    are not echoed.
    """


class AgentAssertionError(AssertionError):
    """An observed trace does not satisfy a behavioral assertion.

    This is a normal :class:`AssertionError` subclass, so it fails pytest
    tests and is raised explicitly (and therefore is not removed by
    ``python -O``).
    """
