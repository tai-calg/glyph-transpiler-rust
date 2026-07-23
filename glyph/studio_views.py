from __future__ import annotations

from collections.abc import Mapping
from typing import Any


STUDIO_VIEWS_SCHEMA = "glyph.studio-views"
STUDIO_VIEWS_VERSION = 1
_VERIFICATION_ORDER = ("static", "model", "runtime", "trusted")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _line(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _applications_for(
    applications: list[Mapping[str, Any]],
    axis: str,
    name: str,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for application in applications:
        row = _mapping(application.get("row"))
        selected = row.get(axis)
        if axis == "laws":
            selected_names = selected if isinstance(selected, list) else []
            applies = name in selected_names
        else:
            applies = selected == name
        if not applies:
            continue
        matches.append(
            {
                "target": _text(application.get("target")),
                "target_kind": _text(application.get("target_kind")),
                "line": _line(application.get("line")),
            }
        )
    return matches


def _capability_view(design: Mapping[str, Any]) -> dict[str, object]:
    capabilities = _mapping(design.get("capabilities"))
    return {
        "resources": [dict(item) for item in _records(capabilities.get("resources"))],
        "functions": [dict(item) for item in _records(capabilities.get("functions"))],
        "aggregates": [dict(item) for item in _records(capabilities.get("aggregates"))],
        "operations": [dict(item) for item in _records(capabilities.get("operations"))],
    }


def _resource_view(design: Mapping[str, Any]) -> dict[str, object]:
    resource_flow = _mapping(design.get("resource_flow"))
    grouped: dict[str, dict[str, object]] = {}
    for transition in _records(resource_flow.get("transitions")):
        identity = _text(transition.get("identity"))
        target = _mapping(transition.get("target"))
        source = _mapping(transition.get("source"))
        if not identity or not target:
            continue
        group = grouped.setdefault(
            identity,
            {
                "identity": identity,
                "resource": _text(target.get("resource")),
                "states": [],
                "capabilities": [],
                "transitions": [],
                "line": _line(transition.get("line")),
            },
        )
        states = group["states"]
        capabilities = group["capabilities"]
        assert isinstance(states, list)
        assert isinstance(capabilities, list)
        for endpoint in (source, target):
            state = _text(endpoint.get("state"))
            capability = _text(endpoint.get("capability"))
            if state and state not in states:
                states.append(state)
            if capability and capability not in capabilities:
                capabilities.append(capability)
        transitions = group["transitions"]
        assert isinstance(transitions, list)
        transitions.append(
            {
                "function": _text(transition.get("function")),
                "kind": _text(transition.get("kind")),
                "line": _line(transition.get("line")),
                "source": None if not source else dict(source),
                "target": dict(target),
            }
        )
    identities = sorted(
        grouped.values(),
        key=lambda item: (item.get("line") or 10**9, str(item.get("identity"))),
    )
    return {"identities": identities}


def _world_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    worlds: list[dict[str, object]] = []
    for world in _records(runtime.get("worlds")):
        name = _text(world.get("name"))
        region = world.get("region") if isinstance(world.get("region"), list) else []
        worlds.append(
            {
                "name": name,
                "locus": _text(world.get("locus")),
                "region": [str(item) for item in region],
                "region_path": "/".join(str(item) for item in region),
                "line": _line(world.get("line")),
                "applications": _applications_for(applications, "world", name),
            }
        )
    return {"worlds": worlds}


def _protocol_events(root: Mapping[str, Any]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []

    def visit(
        node: Mapping[str, Any],
        path: tuple[int, ...],
        controls: tuple[str, ...],
    ) -> None:
        kind = _text(node.get("kind"))
        if kind in {"send", "receive"}:
            events.append(
                {
                    "index": len(events),
                    "path": "root" if not path else "root." + ".".join(map(str, path)),
                    "direction": kind,
                    "type": _text(node.get("type")),
                    "controls": list(controls),
                }
            )
            return
        nested = controls + ((kind,) if kind else ())
        children = _records(node.get("children"))
        for index, child in enumerate(children):
            visit(child, (*path, index), nested)

    visit(root, (), ())
    return events


def _protocol_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    protocols: list[dict[str, object]] = []
    for protocol in _records(runtime.get("protocols")):
        name = _text(protocol.get("name"))
        root = _mapping(protocol.get("root"))
        protocols.append(
            {
                "name": name,
                "line": _line(protocol.get("line")),
                "root": dict(root),
                "events": _protocol_events(root),
                "applications": _applications_for(applications, "protocol", name),
            }
        )
    return {"protocols": protocols}


def _handler_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    host = _mapping(design.get("host_requirements"))
    host_operations = _records(host.get("operations"))
    handlers: list[dict[str, object]] = []
    for handler in _records(runtime.get("handlers")):
        name = _text(handler.get("name"))
        steps = [dict(step) for step in _records(handler.get("steps"))]
        requirements = [
            dict(operation)
            for operation in host_operations
            if operation.get("contract") == name
            and _text(operation.get("kind")).startswith("handler_")
        ]
        nodes: list[dict[str, object]] = [
            {"id": "target", "kind": "target", "label": "Target exit", "line": None}
        ]
        edges: list[dict[str, str]] = []
        previous = "target"
        for index, step in enumerate(steps):
            node_id = f"step:{index}"
            operation = _text(step.get("operation"), "handler")
            nodes.append(
                {
                    "id": node_id,
                    "kind": "handler",
                    "label": operation,
                    "arguments": step.get("arguments", []),
                    "verification": _text(step.get("verification")),
                    "line": _line(step.get("line")),
                }
            )
            edges.append({"source": previous, "target": node_id, "label": "failure path"})
            previous = node_id
        nodes.append({"id": "exit", "kind": "exit", "label": "Declared exit", "line": None})
        edges.append({"source": previous, "target": "exit", "label": "complete"})
        handlers.append(
            {
                "name": name,
                "line": _line(handler.get("line")),
                "steps": steps,
                "nodes": nodes,
                "edges": edges,
                "requirements": requirements,
                "applications": _applications_for(applications, "handler", name),
            }
        )
    return {"handlers": handlers}


def _law_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    host = _mapping(design.get("host_requirements"))
    host_operations = _records(host.get("operations"))
    laws: list[dict[str, object]] = []
    for law in _records(runtime.get("laws")):
        name = _text(law.get("name"))
        requirements = [
            dict(operation)
            for operation in host_operations
            if operation.get("contract") == name and operation.get("kind") == "law_observe"
        ]
        laws.append(
            {
                "name": name,
                "formula": law.get("formula", {}),
                "verification": _text(law.get("verification")),
                "line": _line(law.get("line")),
                "requirements": requirements,
                "applications": _applications_for(applications, "laws", name),
            }
        )
    return {"laws": laws}


def _verification_view(design: Mapping[str, Any]) -> dict[str, object]:
    report = _mapping(design.get("verification"))
    items = [dict(item) for item in _records(report.get("items"))]
    class_rows: list[dict[str, object]] = []
    for name in _VERIFICATION_ORDER:
        selected = [
            item
            for item in items
            if name in (item.get("classes") if isinstance(item.get("classes"), list) else [])
        ]
        class_rows.append({"name": name, "count": len(selected), "items": selected})

    axes = sorted({_text(item.get("axis")) for item in items if _text(item.get("axis"))})
    matrix = []
    for axis in axes:
        row: dict[str, object] = {"axis": axis}
        axis_items = [item for item in items if item.get("axis") == axis]
        for verification_class in _VERIFICATION_ORDER:
            row[verification_class] = sum(
                verification_class
                in (item.get("classes") if isinstance(item.get("classes"), list) else [])
                for item in axis_items
            )
        matrix.append(row)
    return {
        "summary": dict(_mapping(report.get("summary"))),
        "classes": class_rows,
        "axes": axes,
        "matrix": matrix,
        "items": items,
    }


def build_studio_views(design: Mapping[str, Any]) -> dict[str, object]:
    """Project one canonical typed design into orthogonal Studio views.

    This function does not parse Glyph source and does not rebuild semantic models. It only
    reshapes the already-validated typed design emitted by the compilation pipeline.
    """

    runtime = _mapping(design.get("runtime_contracts"))
    applications = _records(runtime.get("applications"))
    capability = _capability_view(design)
    resource = _resource_view(design)
    world_region = _world_view(design, applications)
    protocol = _protocol_view(design, applications)
    handler = _handler_view(design, applications)
    law = _law_view(design, applications)
    verification_strength = _verification_view(design)

    views = {
        "capability": capability,
        "resource": resource,
        "world_region": world_region,
        "protocol": protocol,
        "handler": handler,
        "law": law,
        "verification_strength": verification_strength,
    }
    enabled = any(
        (
            capability["resources"],
            capability["functions"],
            capability["aggregates"],
            capability["operations"],
            resource["identities"],
            world_region["worlds"],
            protocol["protocols"],
            handler["handlers"],
            law["laws"],
            verification_strength["items"],
        )
    )
    return {
        "schema": STUDIO_VIEWS_SCHEMA,
        "version": STUDIO_VIEWS_VERSION,
        "enabled": enabled,
        "summary": {
            "resources": len(capability["resources"]),
            "capability_functions": len(capability["functions"]),
            "resource_identities": len(resource["identities"]),
            "worlds": len(world_region["worlds"]),
            "protocols": len(protocol["protocols"]),
            "handlers": len(handler["handlers"]),
            "laws": len(law["laws"]),
            "verification_items": len(verification_strength["items"]),
        },
        "views": views,
    }
