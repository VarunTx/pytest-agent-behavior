"""Strict, path-aware JSON value validation and canonicalization."""

from __future__ import annotations

import math
from typing import Any, TypeAlias, cast

from .exceptions import TraceValidationError

JSONScalar: TypeAlias = bool | int | float | str | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def type_name(value: object) -> str:
    """Return a stable, non-revealing name for a Python value's type."""
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    return type(value).__name__


def validate_json_value(value: object, path: str) -> None:
    """Validate that *value* is an acyclic, strict JSON value.

    Only exact built-in JSON types are accepted. Subclasses and objects that
    merely look JSON-like are rejected instead of being coerced.
    """
    _validate(value, path, set())


def _validate(value: object, path: str, active: set[int]) -> None:
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise TraceValidationError(f"{path}: expected a finite JSON number")
        return
    if type(value) is str:
        return
    if type(value) is list:
        container_id = id(value)
        if container_id in active:
            raise TraceValidationError(f"{path}: cyclic JSON structure")
        active.add(container_id)
        try:
            for index, item in enumerate(value):
                _validate(item, f"{path}[{index}]", active)
        finally:
            active.remove(container_id)
        return
    if type(value) is dict:
        container_id = id(value)
        if container_id in active:
            raise TraceValidationError(f"{path}: cyclic JSON structure")
        active.add(container_id)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    raise TraceValidationError(f"{path}: JSON object keys must be strings")
                _validate(item, f"{path}.{key}", active)
        finally:
            active.remove(container_id)
        return
    raise TraceValidationError(f"{path}: expected a JSON value, got {type_name(value)}")


def copy_json_object(value: object, path: str) -> dict[str, Any]:
    """Validate and deep-copy a JSON object.

    The copy is made from primitives and containers, so mutating the original
    input later cannot change the returned object.
    """
    if type(value) is not dict:
        raise TraceValidationError(f"{path}: expected a JSON object, got {type_name(value)}")
    validate_json_value(value, path)
    return cast(dict[str, Any], _deep_copy(value))


def _deep_copy(value: JSONValue) -> Any:
    if type(value) is dict:
        return {key: _deep_copy(item) for key, item in value.items()}
    if type(value) is list:
        return [_deep_copy(item) for item in value]
    return value


def canonical_json(value: JSONValue) -> tuple[Any, ...]:
    """Return a hashable canonical form with strict JSON type semantics.

    Object key order is normalized by sorting. Array order is retained.
    ``True``, ``1``, and ``1.0`` produce distinct canonical values.
    """
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("boolean", value)
    if type(value) is int:
        return ("integer", value)
    if type(value) is float:
        # hex() is exact, stable, and distinguishes 1.0 from 1 and -0.0.
        return ("number", value.hex())
    if type(value) is str:
        return ("string", value)
    if type(value) is list:
        return ("array", tuple(canonical_json(item) for item in value))
    if type(value) is dict:
        return (
            "object",
            tuple((key, canonical_json(value[key])) for key in sorted(value)),
        )
    # Values reach this function only after validation.
    raise TypeError(f"unsupported JSON value type: {type_name(value)}")
