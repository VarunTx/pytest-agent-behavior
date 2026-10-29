from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pytest_agent_behavior import Approval, ToolCall, Trace
from pytest_agent_behavior._json import canonical_json
from pytest_agent_behavior.exceptions import TraceValidationError


def tool_call(
    call_id: str = "c1",
    tool: str = "send_email",
    arguments: dict | None = None,
) -> ToolCall:
    return ToolCall(call_id, tool, {"to": "fake@example.com"} if arguments is None else arguments)


def approval(call_id: str = "c1", tool: str = "send_email", decision: str = "approved") -> Approval:
    return Approval(call_id, tool, decision)


def test_public_constructors_and_frozen_types() -> None:
    call = tool_call(arguments={"nested": {"values": [1, True, None]}})
    decision = approval()

    assert call.type == "tool_call"
    assert decision.type == "approval"
    with pytest.raises(AttributeError):
        call.tool = "other"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        decision.decision = "denied"  # type: ignore[misc]


def test_direct_trace_construction_and_order() -> None:
    trace = Trace([approval(), tool_call()])
    assert [event.type for event in trace.events] == ["approval", "tool_call"]
    assert trace.schema_version == 1


def test_from_dict_round_trip_and_fresh_containers() -> None:
    data = {
        "schema_version": 1,
        "events": [
            {"type": "approval", "call_id": "c1", "tool": "send_email", "decision": "approved"},
            {
                "type": "tool_call",
                "call_id": "c1",
                "tool": "send_email",
                "arguments": {"to": "fake@example.com", "meta": {"tags": ["a", "b"]}},
            },
        ],
    }
    trace = Trace.from_dict(data)
    exported = trace.to_dict()

    assert exported == data
    assert exported is not data
    assert exported["events"][1]["arguments"] is not data["events"][1]["arguments"]

    exported["events"][1]["arguments"]["meta"]["tags"].append("changed")
    assert trace.to_dict() == data


def test_to_dict_returns_new_arguments_on_each_access() -> None:
    trace = Trace([tool_call(arguments={"items": [1, 2]})])
    first = trace.events[0]
    assert isinstance(first, ToolCall)
    first.arguments["items"].append(99)
    assert first.arguments == {"items": [1, 2]}


def test_source_mutation_cannot_change_trace() -> None:
    arguments = {"nested": {"items": [1, 2]}}
    data = {
        "schema_version": 1,
        "events": [{"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": arguments}],
    }
    trace = Trace.from_dict(data)
    arguments["nested"]["items"].append(3)
    data["events"].clear()
    assert trace.to_dict()["events"][0]["arguments"] == {"nested": {"items": [1, 2]}}


def test_empty_trace_and_empty_arguments_are_valid() -> None:
    assert Trace.from_dict({"schema_version": 1, "events": []}).events == ()
    assert tool_call(arguments={}).arguments == {}


def test_approval_only_and_approval_after_call_are_valid_input() -> None:
    approval_only = Trace.from_dict(
        {
            "schema_version": 1,
            "events": [{"type": "approval", "call_id": "c9", "tool": "t", "decision": "denied"}],
        }
    )
    assert len(approval_only.events) == 1

    after = Trace.from_dict(
        {
            "schema_version": 1,
            "events": [
                {"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": {}},
                {"type": "approval", "call_id": "c1", "tool": "t", "decision": "approved"},
            ],
        }
    )
    assert [event.type for event in after.events] == ["tool_call", "approval"]


@pytest.mark.parametrize("version", [True, False, 0, 2, "1", 1.0, None])
def test_invalid_schema_versions_rejected(version: object) -> None:
    with pytest.raises(TraceValidationError, match="schema_version"):
        Trace.from_dict({"schema_version": version, "events": []})


def test_schema_version_bool_is_not_integer() -> None:
    with pytest.raises(TraceValidationError, match="got boolean"):
        Trace.from_dict({"schema_version": True, "events": []})


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"schema_version": 1, "events": [], "extra": 1}, "unknown field"),
        ({"schema_version": 1}, "events: field is required"),
        ({"events": []}, "schema_version: field is required"),
        ({"schema_version": 1, "events": {}}, "expected a JSON array"),
        ({"schema_version": 1, "events": [1]}, "expected a JSON object"),
        (
            {"schema_version": 1, "events": [{"type": "other"}]},
            'expected "tool_call" or "approval"',
        ),
        (
            {
                "schema_version": 1,
                "events": [
                    {
                        "type": "approval",
                        "call_id": "c1",
                        "tool": "t",
                        "decision": "approved",
                        "extra": 1,
                    }
                ],
            },
            "unknown field",
        ),
        (
            {
                "schema_version": 1,
                "events": [
                    {"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": [], "x": 1}
                ],
            },
            "unknown field",
        ),
        (
            {
                "schema_version": 1,
                "events": [{"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": {}}],
                "unexpected": True,
            },
            "unknown field",
        ),
    ],
)
def test_structural_errors(data: object, fragment: str) -> None:
    with pytest.raises(TraceValidationError, match=fragment):
        Trace.from_dict(data)


@pytest.mark.parametrize("data", [None, True, [], "{}", 1])
def test_from_dict_requires_an_object(data: object) -> None:
    with pytest.raises(TraceValidationError, match="trace: expected a JSON object"):
        Trace.from_dict(data)


def test_direct_trace_accepts_an_ordered_tuple() -> None:
    trace = Trace((approval(), tool_call()))
    assert [event.type for event in trace.events] == ["approval", "tool_call"]


@pytest.mark.parametrize(
    "event, fragment",
    [
        ({"type": "tool_call", "call_id": "c1", "tool": "t"}, "arguments: field is required"),
        ({"type": "tool_call", "tool": "t", "arguments": {}}, "call_id: field is required"),
        ({"type": "tool_call", "call_id": "c1", "arguments": {}}, "tool: field is required"),
        (
            {"type": "approval", "call_id": "c1", "tool": "t"},
            "decision: field is required",
        ),
        (
            {"type": "tool_call", "call_id": "", "tool": "t", "arguments": {}},
            "call_id: expected a nonempty string",
        ),
        (
            {"type": "tool_call", "call_id": 1, "tool": "t", "arguments": {}},
            "call_id: expected a nonempty string, got integer",
        ),
        (
            {"type": "tool_call", "call_id": "c1", "tool": "", "arguments": {}},
            "tool: expected a nonempty string",
        ),
        (
            {"type": "tool_call", "call_id": "c1", "tool": "t", "arguments": []},
            "events\\[0\\]\\.arguments: expected a JSON object",
        ),
        (
            {"type": "approval", "call_id": "c1", "tool": "t", "decision": "maybe"},
            "decision: expected",
        ),
        (
            {"type": "approval", "call_id": "c1", "tool": "t", "decision": 1},
            "decision: expected",
        ),
    ],
)
def test_event_field_validation(event: object, fragment: str) -> None:
    with pytest.raises(TraceValidationError, match=fragment):
        Trace.from_dict({"schema_version": 1, "events": [event]})


def test_duplicate_call_ids_rejected() -> None:
    data = {
        "schema_version": 1,
        "events": [
            {"type": "tool_call", "call_id": "same", "tool": "t", "arguments": {}},
            {"type": "tool_call", "call_id": "same", "tool": "u", "arguments": {}},
        ],
    }
    with pytest.raises(TraceValidationError, match=r"events\[1\]\.call_id: duplicate"):
        Trace.from_dict(data)


def test_multiple_approvals_for_same_call_id_allowed() -> None:
    trace = Trace(
        [
            approval(decision="denied"),
            approval(decision="approved"),
            tool_call(),
        ]
    )
    assert len(trace.events) == 3


@pytest.mark.parametrize(
    "patch, fragment",
    [
        ({"arguments": {"value": math.nan}}, "finite JSON number"),
        ({"arguments": {"value": math.inf}}, "finite JSON number"),
        ({"arguments": {"value": -math.inf}}, "finite JSON number"),
        ({"arguments": {"value": (1, 2)}}, "expected a JSON value, got tuple"),
        ({"arguments": {"value": {1, 2}}}, "expected a JSON value, got set"),
        ({"arguments": {"value": object()}}, "expected a JSON value, got object"),
        ({"arguments": {1: "bad"}}, "JSON object keys must be strings"),
        ({"arguments": []}, "expected a JSON object"),
        ({"arguments": "secret-arguments"}, "expected a JSON object, got string"),
    ],
)
def test_direct_argument_validation_does_not_echo_values(
    patch: dict[str, object], fragment: str
) -> None:
    arguments = patch["arguments"]
    with pytest.raises(TraceValidationError) as caught:
        ToolCall("c1", "t", arguments)  # type: ignore[arg-type]
    assert fragment in str(caught.value)
    assert "secret-arguments" not in str(caught.value)


def test_cyclic_arguments_rejected() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(TraceValidationError, match="cyclic JSON structure"):
        ToolCall("c1", "t", {"cyclic": cyclic})

    cyclic_object: dict[str, object] = {}
    cyclic_object["self"] = cyclic_object
    with pytest.raises(TraceValidationError, match="cyclic JSON structure"):
        ToolCall("c1", "t", cyclic_object)


@pytest.mark.parametrize("decision", ["Approved", "denied ", "", True, None, 1])
def test_direct_approval_decision_validation(decision: object) -> None:
    with pytest.raises(TraceValidationError, match="decision"):
        Approval("c1", "t", decision)  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [True, 2, "1", None])
def test_direct_trace_version_validation(version: object) -> None:
    with pytest.raises(TraceValidationError, match="schema_version"):
        Trace([], schema_version=version)  # type: ignore[arg-type]


@pytest.mark.parametrize("events", [None, "events", {"a": 1}, 1])
def test_direct_trace_events_validation(events: object) -> None:
    with pytest.raises(TraceValidationError, match="events"):
        Trace(events)  # type: ignore[arg-type]


def test_direct_trace_rejects_non_event_values() -> None:
    with pytest.raises(TraceValidationError, match=r"events\[0\]"):
        Trace([{"type": "tool_call"}])  # type: ignore[list-item]


def test_direct_trace_rejects_duplicate_call_ids() -> None:
    with pytest.raises(TraceValidationError, match="duplicate tool_call call_id"):
        Trace([tool_call(), tool_call(tool="other")])


def test_json_round_trip_preserves_strict_values_and_order() -> None:
    trace = Trace(
        [
            tool_call(arguments={"a": True, "b": 1, "c": 1.0, "d": [None, False]}),
            approval(call_id="c2", decision="denied"),
        ]
    )
    restored = Trace.from_json(trace.to_json())
    assert restored == trace
    arguments = restored.events[0].arguments  # type: ignore[union-attr]
    assert arguments["a"] is True
    assert type(arguments["b"]) is int
    assert type(arguments["c"]) is float


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "[]",
        '{"schema_version": 1, "events": [],}',
        '{"schema_version": 1, "events": [NaN]}',
        '{"schema_version": 1, "events": [Infinity]}',
        '{"schema_version": 1, "events": [-Infinity]}',
        '{"schema_version": 1, "events": [], "extra": NaN}',
    ],
)
def test_from_json_errors_are_validation_errors(text: str) -> None:
    with pytest.raises(TraceValidationError):
        Trace.from_json(text)


def test_from_json_rejects_non_string_input() -> None:
    with pytest.raises(TypeError, match="text must be str"):
        Trace.from_json(b"{}")  # type: ignore[arg-type]


def test_from_json_overflow_becomes_finite_number_error() -> None:
    text = (
        '{"schema_version": 1, "events": ['
        '{"type": "tool_call", "call_id": "c1", "tool": "t", '
        '"arguments": {"value": 1e999}}]}'
    )
    with pytest.raises(TraceValidationError, match="finite JSON number"):
        Trace.from_json(text)


def test_from_path_round_trip(tmp_path: Path) -> None:
    trace = Trace([approval(), tool_call()])
    path = tmp_path / "trace.json"
    path.write_text(trace.to_json(), encoding="utf-8")
    assert Trace.from_path(path) == trace
    assert Trace.from_path(str(path)) == trace


def test_from_path_preserves_filesystem_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Trace.from_path(tmp_path / "missing.json")


def test_from_path_wraps_unicode_decoding_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(TraceValidationError, match="UTF-8"):
        Trace.from_path(path)


def test_to_json_is_parseable_and_does_not_allow_nan() -> None:
    trace = Trace([tool_call()])
    parsed = json.loads(trace.to_json())
    assert parsed == trace.to_dict()


def test_canonical_signature_semantics() -> None:
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})
    assert canonical_json({"a": [1, 2]}) != canonical_json({"a": [2, 1]})
    assert canonical_json({"a": True}) != canonical_json({"a": 1})
    assert canonical_json({"a": 1}) != canonical_json({"a": 1.0})
    assert canonical_json({"a": -0.0}) != canonical_json({"a": 0.0})
