from __future__ import annotations

import json
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator

from pytest_agent_behavior import Trace
from pytest_agent_behavior.exceptions import TraceValidationError

SCHEMA = json.loads(
    files("pytest_agent_behavior").joinpath("schema/trace.schema.json").read_text(encoding="utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA)


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": 1, "events": []},
        {
            "schema_version": 1,
            "events": [
                {"type": "approval", "call_id": "c1", "tool": "t", "decision": "denied"},
                {
                    "type": "tool_call",
                    "call_id": "c1",
                    "tool": "t",
                    "arguments": {"a": [1, True, None, {"b": 1.5}]},
                },
            ],
        },
    ],
)
def test_schema_accepts_representative_valid_traces(data: dict) -> None:
    VALIDATOR.validate(data)
    Trace.from_dict(data)


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": 2, "events": []},
        {"schema_version": 1, "events": [], "extra": True},
        {"schema_version": 1, "events": [{"type": "unknown"}]},
        {
            "schema_version": 1,
            "events": [{"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": []}],
        },
        {
            "schema_version": 1,
            "events": [
                {
                    "type": "approval",
                    "call_id": "c1",
                    "tool": "t",
                    "decision": "maybe",
                }
            ],
        },
    ],
)
def test_schema_rejects_representative_invalid_traces(data: dict) -> None:
    assert list(VALIDATOR.iter_errors(data))
    with pytest.raises(TraceValidationError):
        Trace.from_dict(data)


def test_loader_only_constraints_are_documented() -> None:
    data = {
        "schema_version": 1,
        "events": [
            {"type": "tool_call", "call_id": "same", "tool": "a", "arguments": {}},
            {"type": "tool_call", "call_id": "same", "tool": "b", "arguments": {}},
        ],
    }
    VALIDATOR.validate(data)
    with pytest.raises(TraceValidationError, match="duplicate tool_call call_id"):
        Trace.from_dict(data)
