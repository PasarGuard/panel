"""Small JSON Schema subset for plugin settings (``jsonschema`` is not a dependency).

Supported keywords: ``type`` (string, number, integer, boolean, object, array, null, or a list of them),
``properties``, ``required``, ``additionalProperties: false``, ``enum``, ``default``, ``minimum``,
``maximum``, ``items``. Everything else (``format``, ``pattern``, ...) is ignored.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def apply_defaults(schema: dict[str, Any] | None, value: Any) -> Any:
    """Return ``value`` with missing object properties filled from ``default`` (recursively)."""
    if not isinstance(schema, dict):
        return deepcopy(value)
    if value is None and "default" in schema:
        return deepcopy(schema["default"])
    properties = schema.get("properties")
    if isinstance(value, dict) and isinstance(properties, dict):
        result = deepcopy(value)
        for name, sub_schema in properties.items():
            if not isinstance(sub_schema, dict):
                continue
            if name in result:
                result[name] = apply_defaults(sub_schema, result[name])
            elif "default" in sub_schema:
                result[name] = deepcopy(sub_schema["default"])
            elif sub_schema.get("type") == "object" and isinstance(sub_schema.get("properties"), dict):
                nested = apply_defaults(sub_schema, {})
                if nested:
                    result[name] = nested
        return result
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [apply_defaults(schema["items"], item) for item in value]
    return deepcopy(value)


def validate(schema: dict[str, Any] | None, value: Any, path: str = "") -> list[str]:
    """Return a list of ``"<path>: <problem>"`` strings; empty means valid."""
    if not isinstance(schema, dict):
        return []
    where = path or "$"
    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        known = [t for t in types if t in _TYPE_CHECKS]
        if known and not any(_TYPE_CHECKS[t](value) for t in known):
            return [f"{where}: expected {' or '.join(known)}"]

    if "enum" in schema and isinstance(schema["enum"], list) and value not in schema["enum"]:
        errors.append(f"{where}: must be one of {schema['enum']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{where}: must be >= {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{where}: must be <= {maximum}")

    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for name in schema.get("required") or []:
            if name not in value:
                errors.append(f"{_join(path, name)}: is required")
        for name, item in value.items():
            if name in properties:
                errors.extend(validate(properties[name], item, _join(path, name)))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{_join(path, name)}: unknown property")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(validate(schema["additionalProperties"], item, _join(path, name)))

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(validate(schema["items"], item, f"{where}[{index}]"))

    return errors


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else str(name)
