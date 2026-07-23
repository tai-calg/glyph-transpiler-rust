from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

from .ui_ir import UI_IR_SCHEMA, UI_IR_VERSION, UiAction, UiApplication, UiNode


UI_SCHEMA_API_VERSION = 1


class UiSchemaError(ValueError):
    """Raised when serialized glyph.ui-ir does not satisfy the public schema contract."""


_NODE_KINDS = {
    "badge",
    "checkbox",
    "integer",
    "json",
    "metric",
    "number",
    "object",
    "option",
    "result",
    "select",
    "status",
    "text",
    "tuple",
    "unit",
}
_ROLES = {"input", "output"}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UiSchemaError(f"{path} must be an object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise UiSchemaError(f"{path} must be a non-empty string")
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiSchemaError(f"{path} must be an integer")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise UiSchemaError(f"{path} must be a boolean")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise UiSchemaError(f"{path} must be an array")
    return value


def _optional_number(value: Any, path: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UiSchemaError(f"{path} must be a number or null")
    return value


def _node_from_dict(value: Any, path: str) -> UiNode:
    data = _mapping(value, path)
    raw_path = _sequence(data.get("path"), f"{path}.path")
    node_path = tuple(_string(item, f"{path}.path[]") for item in raw_path)
    if not node_path:
        raise UiSchemaError(f"{path}.path must not be empty")

    kind = _string(data.get("kind"), f"{path}.kind")
    if kind not in _NODE_KINDS:
        raise UiSchemaError(f"{path}.kind '{kind}' is not supported by UI IR v1")
    role = _string(data.get("role"), f"{path}.role")
    if role not in _ROLES:
        raise UiSchemaError(f"{path}.role must be input or output")

    raw_choices = data.get("choices", [])
    choices = tuple(
        _string(item, f"{path}.choices[]")
        for item in _sequence(raw_choices, f"{path}.choices")
    )
    raw_children = data.get("children", [])
    children = tuple(
        _node_from_dict(item, f"{path}.children[{index}]")
        for index, item in enumerate(_sequence(raw_children, f"{path}.children"))
    )
    description = data.get("description", "")
    if not isinstance(description, str):
        raise UiSchemaError(f"{path}.description must be a string")

    return UiNode(
        id=_string(data.get("id"), f"{path}.id"),
        path=node_path,
        label=_string(data.get("label"), f"{path}.label"),
        type_name=_string(data.get("type"), f"{path}.type"),
        kind=kind,
        role=role,
        required=_boolean(data.get("required", True), f"{path}.required"),
        default=data.get("default"),
        minimum=_optional_number(data.get("minimum"), f"{path}.minimum"),
        maximum=_optional_number(data.get("maximum"), f"{path}.maximum"),
        choices=choices,
        children=children,
        description=description,
    )


def _action_from_dict(value: Any) -> UiAction:
    data = _mapping(value, "action")
    inputs = tuple(
        _node_from_dict(item, f"action.inputs[{index}]")
        for index, item in enumerate(_sequence(data.get("inputs"), "action.inputs"))
    )
    return UiAction(
        id=_string(data.get("id"), "action.id"),
        name=_string(data.get("name"), "action.name"),
        label=_string(data.get("label"), "action.label"),
        source_line=_integer(data.get("source_line"), "action.source_line"),
        inputs=inputs,
        output=_node_from_dict(data.get("output"), "action.output"),
    )


def load_ui_application(value: Mapping[str, Any]) -> UiApplication:
    """Load and validate one glyph.ui-ir version 1 document."""

    data = _mapping(value, "document")
    schema = _string(data.get("schema"), "schema")
    if schema != UI_IR_SCHEMA:
        raise UiSchemaError(f"schema must be '{UI_IR_SCHEMA}', received '{schema}'")
    version = _integer(data.get("version"), "version")
    if version != UI_IR_VERSION:
        raise UiSchemaError(
            f"unsupported {UI_IR_SCHEMA} version {version}; this SDK supports {UI_IR_VERSION}"
        )
    raw_candidates = _sequence(data.get("candidates", []), "candidates")
    application = UiApplication(
        source_name=_string(data.get("source"), "source"),
        title=_string(data.get("title"), "title"),
        action=_action_from_dict(data.get("action")),
        candidates=tuple(_string(item, "candidates[]") for item in raw_candidates),
    )
    validate_ui_application(application)
    return application


def loads_ui_application(text: str) -> UiApplication:
    """Decode a JSON string into a validated public UI application."""

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UiSchemaError(f"invalid UI IR JSON: {exc}") from exc
    return load_ui_application(_mapping(value, "document"))


def dump_ui_application(application: UiApplication) -> dict[str, object]:
    validate_ui_application(application)
    return application.to_dict()


def dumps_ui_application(application: UiApplication) -> str:
    validate_ui_application(application)
    return application.to_json()


def fingerprint_ui_application(application: UiApplication) -> str:
    """Return a deterministic component-graph compatibility fingerprint.

    Source locations are deliberately excluded. Moving a declaration or changing only a
    function body must not force a browser component rebuild when the typed UI contract is
    unchanged.
    """

    validate_ui_application(application)
    action = application.action.to_dict()
    action.pop("source_line", None)
    payload = json.dumps(
        action,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_ui_application(application: UiApplication) -> None:
    """Validate semantic invariants that are not expressible by the JSON shape alone."""

    if application.action.output.role != "output":
        raise UiSchemaError("action.output must have role=output")
    if any(node.role != "input" for node in application.action.inputs):
        raise UiSchemaError("every action input must have role=input")

    seen_ids: set[str] = set()
    seen_paths: set[tuple[str, tuple[str, ...]]] = set()

    def visit(node: UiNode, expected_role: str) -> None:
        if node.role != expected_role:
            raise UiSchemaError(
                f"node '{node.id}' has role={node.role}, expected {expected_role}"
            )
        if node.id in seen_ids:
            raise UiSchemaError(f"duplicate UI node id '{node.id}'")
        seen_ids.add(node.id)
        path_key = (node.role, node.path)
        if path_key in seen_paths:
            raise UiSchemaError(
                f"duplicate UI node path '{node.role}:{'.'.join(node.path)}'"
            )
        seen_paths.add(path_key)
        if node.minimum is not None and node.maximum is not None:
            if node.minimum > node.maximum:
                raise UiSchemaError(f"node '{node.id}' has minimum greater than maximum")
        if node.kind in {"select", "badge"} and not node.choices:
            raise UiSchemaError(f"node '{node.id}' requires at least one choice")
        if node.kind == "object" and not node.children:
            raise UiSchemaError(f"object node '{node.id}' must contain children")
        for child in node.children:
            if child.path[: len(node.path)] != node.path:
                raise UiSchemaError(
                    f"child '{child.id}' path is not nested under '{node.id}'"
                )
            visit(child, expected_role)

    for node in application.action.inputs:
        visit(node, "input")
    visit(application.action.output, "output")
