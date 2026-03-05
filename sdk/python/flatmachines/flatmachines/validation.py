"""
Schema validation for flatmachine configurations.

Uses JSON Schema validation against the bundled schema.
Validation errors are warnings by default to avoid breaking user configs.
"""

import copy
import json
import warnings
from importlib.resources import files
from typing import Any, Dict, List, Optional

_ASSETS = files("flatmachines.assets")


class ValidationWarning(UserWarning):
    """Warning for schema validation issues."""



def _load_schema(filename: str) -> Optional[Dict[str, Any]]:
    try:
        content = (_ASSETS / filename).read_text()
        return json.loads(content)
    except FileNotFoundError:
        return None


def _coerce_templated_tool_loop_guardrails_for_validation(
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a copy of config with casted Jinja guardrails coerced to numbers.

    Runtime supports templated guardrails via `_render_guardrail`, e.g.:
      max_turns: "{{ context.max_iters | int }}"
      max_cost: "{{ context.budget | float }}"

    Keep schema strict (`number`) while avoiding false-positive warnings by
    replacing only clearly-casted Jinja expressions with numeric sentinels.
    Uncasted strings remain strings and still fail schema validation.
    """
    cloned = copy.deepcopy(config)

    states = (((cloned.get("data") or {}).get("states")) or {})
    if not isinstance(states, dict):
        return cloned

    numeric_fields = {
        "max_tool_calls": 0,
        "max_turns": 0,
        "tool_timeout": 0.0,
        "total_timeout": 0.0,
        "max_cost": 0.0,
    }

    for state in states.values():
        if not isinstance(state, dict):
            continue
        tool_loop = state.get("tool_loop")
        if not isinstance(tool_loop, dict):
            continue

        for field, sentinel in numeric_fields.items():
            value = tool_loop.get(field)
            if not isinstance(value, str):
                continue

            compact = "".join(value.split())  # remove whitespace
            if not (compact.startswith("{{") and compact.endswith("}}")):
                continue

            if "|int" in compact and isinstance(sentinel, int):
                tool_loop[field] = sentinel
            elif "|float" in compact and isinstance(sentinel, float):
                tool_loop[field] = sentinel

    return cloned


def _validate_with_jsonschema(config: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    try:
        import jsonschema
    except ImportError:
        return []

    validation_config = _coerce_templated_tool_loop_guardrails_for_validation(config)

    errors: List[str] = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(validation_config):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")
    return errors


def validate_flatmachine_config(
    config: Dict[str, Any],
    warn: bool = True,
    strict: bool = False,
) -> List[str]:
    """Validate a flatmachine configuration against the schema."""
    schema = _load_schema("flatmachine.schema.json")
    if schema is None:
        return []

    errors = _validate_with_jsonschema(config, schema)

    if errors:
        if strict:
            raise ValueError(
                "Flatmachine config validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
        if warn:
            warnings.warn(
                "Flatmachine config has validation issues:\n"
                + "\n".join(f"  - {e}" for e in errors),
                ValidationWarning,
                stacklevel=3,
            )

    return errors


def get_flatmachine_schema() -> Optional[Dict[str, Any]]:
    """Get the bundled flatmachine JSON schema."""
    return _load_schema("flatmachine.schema.json")


def get_asset(filename: str) -> str:
    """Get the contents of a bundled asset file."""
    return (_ASSETS / filename).read_text()
