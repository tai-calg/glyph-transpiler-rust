from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Mapping

from .ui_ir import UiAction, UiApplication, UiNode


UI_MANIFEST_SCHEMA = "glyph.ui-manifest"
UI_MANIFEST_VERSION = 1

_ALLOWED_WIDGETS = {
    "number",
    "integer",
    "checkbox",
    "text",
    "select",
    "object",
    "metric",
    "status",
    "badge",
    "json",
    "tuple",
    "result",
    "option",
    "unit",
}
_ALLOWED_ROOT_KEYS = {"schema", "version", "title", "function", "locale", "nodes"}
_ALLOWED_NODE_KEYS = {
    "label",
    "description",
    "widget",
    "default",
    "minimum",
    "maximum",
    "choices",
}


class UiManifestError(ValueError):
    """Raised when a public UI manifest is malformed or unsafe."""


@dataclass(frozen=True)
class UiNodeOverride:
    label: str | None = None
    description: str | None = None
    widget: str | None = None
    default: Any = None
    has_default: bool = False
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class UiManifest:
    title: str | None = None
    function: str | None = None
    locale: str = "en"
    nodes: Mapping[str, UiNodeOverride] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.nodes is None:
            object.__setattr__(self, "nodes", {})

    def to_dict(self) -> dict[str, object]:
        node_data: dict[str, object] = {}
        for node_id, override in sorted(self.nodes.items()):
            data: dict[str, object] = {}
            if override.label is not None:
                data["label"] = override.label
            if override.description is not None:
                data["description"] = override.description
            if override.widget is not None:
                data["widget"] = override.widget
            if override.has_default:
                data["default"] = override.default
            if override.minimum is not None:
                data["minimum"] = override.minimum
            if override.maximum is not None:
                data["maximum"] = override.maximum
            if override.choices is not None:
                data["choices"] = list(override.choices)
            node_data[node_id] = data
        return {
            "schema": UI_MANIFEST_SCHEMA,
            "version": UI_MANIFEST_VERSION,
            "title": self.title,
            "function": self.function,
            "locale": self.locale,
            "nodes": node_data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _expect_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UiManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _expect_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UiManifestError(f"{field} must be a number")
    return value


def parse_ui_manifest(data: Mapping[str, Any]) -> UiManifest:
    unknown = sorted(set(data) - _ALLOWED_ROOT_KEYS)
    if unknown:
        raise UiManifestError("unknown manifest field(s): " + ", ".join(unknown))
    if data.get("schema") != UI_MANIFEST_SCHEMA:
        raise UiManifestError(f"schema must be '{UI_MANIFEST_SCHEMA}'")
    if data.get("version") != UI_MANIFEST_VERSION:
        raise UiManifestError(f"version must be {UI_MANIFEST_VERSION}")

    title = data.get("title")
    function = data.get("function")
    locale = data.get("locale", "en")
    if title is not None:
        title = _expect_text(title, "title")
    if function is not None:
        function = _expect_text(function, "function")
    locale = _expect_text(locale, "locale")

    raw_nodes = data.get("nodes", {})
    if not isinstance(raw_nodes, Mapping):
        raise UiManifestError("nodes must be an object keyed by semantic node ID")
    nodes: dict[str, UiNodeOverride] = {}
    for raw_id, raw_override in raw_nodes.items():
        node_id = _expect_text(raw_id, "node ID")
        if not isinstance(raw_override, Mapping):
            raise UiManifestError(f"nodes.{node_id} must be an object")
        unknown_node = sorted(set(raw_override) - _ALLOWED_NODE_KEYS)
        if unknown_node:
            raise UiManifestError(
                f"nodes.{node_id} has unknown field(s): " + ", ".join(unknown_node)
            )
        widget = raw_override.get("widget")
        if widget is not None:
            widget = _expect_text(widget, f"nodes.{node_id}.widget")
            if widget not in _ALLOWED_WIDGETS:
                raise UiManifestError(
                    f"nodes.{node_id}.widget must be one of {', '.join(sorted(_ALLOWED_WIDGETS))}"
                )
        choices = raw_override.get("choices")
        parsed_choices: tuple[str, ...] | None = None
        if choices is not None:
            if not isinstance(choices, list) or not choices:
                raise UiManifestError(f"nodes.{node_id}.choices must be a non-empty array")
            parsed_choices = tuple(
                _expect_text(item, f"nodes.{node_id}.choices") for item in choices
            )
        minimum = raw_override.get("minimum")
        maximum = raw_override.get("maximum")
        if minimum is not None:
            minimum = _expect_number(minimum, f"nodes.{node_id}.minimum")
        if maximum is not None:
            maximum = _expect_number(maximum, f"nodes.{node_id}.maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise UiManifestError(f"nodes.{node_id}: minimum exceeds maximum")
        nodes[node_id] = UiNodeOverride(
            label=(
                _expect_text(raw_override["label"], f"nodes.{node_id}.label")
                if "label" in raw_override
                else None
            ),
            description=(
                _expect_text(raw_override["description"], f"nodes.{node_id}.description")
                if "description" in raw_override
                else None
            ),
            widget=widget,
            default=raw_override.get("default"),
            has_default="default" in raw_override,
            minimum=minimum,
            maximum=maximum,
            choices=parsed_choices,
        )
    return UiManifest(title=title, function=function, locale=locale, nodes=nodes)


def load_ui_manifest(path: str | Path) -> UiManifest:
    manifest_path = Path(path)
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UiManifestError(f"invalid JSON in {manifest_path}: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise UiManifestError("manifest root must be a JSON object")
    return parse_ui_manifest(parsed)


def _apply_node(node: UiNode, overrides: Mapping[str, UiNodeOverride], seen: set[str]) -> UiNode:
    children = tuple(_apply_node(child, overrides, seen) for child in node.children)
    override = overrides.get(node.id)
    if override is None:
        return replace(node, children=children)
    seen.add(node.id)
    return replace(
        node,
        label=override.label if override.label is not None else node.label,
        description=(
            override.description if override.description is not None else node.description
        ),
        kind=override.widget if override.widget is not None else node.kind,
        default=override.default if override.has_default else node.default,
        minimum=override.minimum if override.minimum is not None else node.minimum,
        maximum=override.maximum if override.maximum is not None else node.maximum,
        choices=override.choices if override.choices is not None else node.choices,
        children=children,
    )


def apply_ui_manifest(app: UiApplication, manifest: UiManifest) -> UiApplication:
    seen: set[str] = set()
    inputs = tuple(_apply_node(node, manifest.nodes, seen) for node in app.action.inputs)
    output = _apply_node(app.action.output, manifest.nodes, seen)
    unknown = sorted(set(manifest.nodes) - seen)
    if unknown:
        raise UiManifestError(
            "manifest references unknown UI node ID(s): " + ", ".join(unknown)
        )
    action = UiAction(
        id=app.action.id,
        name=app.action.name,
        label=app.action.label,
        source_line=app.action.source_line,
        inputs=inputs,
        output=output,
    )
    return UiApplication(
        source_name=app.source_name,
        title=manifest.title or app.title,
        action=action,
        candidates=app.candidates,
    )
