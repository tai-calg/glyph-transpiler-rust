from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .studio_semantics import (
    aggregate_entity_id,
    application_target_entity_id,
    build_semantic_index,
    capability_operation_entity_id,
    contract_entity_id,
    function_entity_id,
    handler_entity_id,
    handler_node_entity_id,
    host_requirement_entity_id,
    identity_entity_id,
    law_entity_id,
    place_entity_id,
    protocol_entity_id,
    protocol_event_entity_id,
    resource_entity_id,
    resource_transition_entity_id,
    type_entity_id,
    verification_entity_id,
    world_entity_id,
)


STUDIO_VIEWS_SCHEMA = "glyph.studio-views"
STUDIO_VIEWS_VERSION = 2
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


def _capability_type(value: object) -> dict[str, object]:
    result = dict(_mapping(value))
    name = _text(result.get("name"), "unknown")
    result["type_entity_id"] = (
        resource_entity_id(name) if result.get("state") else type_entity_id(name)
    )
    result["args"] = [_capability_type(item) for item in _records(result.get("args"))]
    return result


def _application_target(target_kind: str, target: str) -> str:
    return application_target_entity_id(target_kind, target)


def _applications_for(
    applications: list[Mapping[str, Any]],
    axis: str,
    name: str,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    contract_id = contract_entity_id(axis, name)
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
        target = _text(application.get("target"))
        target_kind = _text(application.get("target_kind"))
        matches.append(
            {
                "target": target,
                "target_kind": target_kind,
                "line": _line(application.get("line")),
                "entity_id": _application_target(target_kind, target),
                "contract_entity_id": contract_id,
            }
        )
    return matches


def _capability_view(design: Mapping[str, Any]) -> dict[str, object]:
    capabilities = _mapping(design.get("capabilities"))

    resources: list[dict[str, object]] = []
    for source in _records(capabilities.get("resources")):
        item = dict(source)
        item["entity_id"] = resource_entity_id(_text(item.get("name")))
        resources.append(item)

    functions: list[dict[str, object]] = []
    for source in _records(capabilities.get("functions")):
        item = dict(source)
        name = _text(item.get("name"))
        item["entity_id"] = function_entity_id(name)
        parameters: list[dict[str, object]] = []
        for parameter_source in _records(item.get("params")):
            parameter = dict(parameter_source)
            parameter_name = _text(parameter.get("name"))
            parameter["entity_id"] = place_entity_id(name, f"param:{parameter_name}")
            parameter["type"] = _capability_type(parameter.get("type"))
            parameters.append(parameter)
        item["params"] = parameters
        item["result"] = _capability_type(item.get("result"))
        item["result_entity_id"] = place_entity_id(name, "result")
        functions.append(item)

    aggregates: list[dict[str, object]] = []
    for source in _records(capabilities.get("aggregates")):
        item = dict(source)
        name = _text(item.get("name"))
        item["entity_id"] = aggregate_entity_id(name)
        members: list[dict[str, object]] = []
        for index, member_source in enumerate(_records(item.get("members"))):
            member = _capability_type(member_source)
            member["name"] = _text(member.get("field_name"), str(index))
            member["entity_id"] = place_entity_id(name, f"member:{index}")
            members.append(member)
        item["members"] = members
        aggregates.append(item)

    operations: list[dict[str, object]] = []
    for source in _records(capabilities.get("operations")):
        item = dict(source)
        function_name = _text(item.get("function"))
        item["entity_id"] = capability_operation_entity_id(item)
        item["function_entity_id"] = function_entity_id(function_name)
        source_place = _text(item.get("source"))
        target_place = _text(item.get("target"))
        item["source_entity_id"] = (
            place_entity_id(function_name, source_place) if source_place else None
        )
        item["target_entity_id"] = (
            place_entity_id(function_name, target_place) if target_place else None
        )
        operations.append(item)

    return {
        "resources": resources,
        "functions": functions,
        "aggregates": aggregates,
        "operations": operations,
    }


def _resource_view(design: Mapping[str, Any]) -> dict[str, object]:
    resource_flow = _mapping(design.get("resource_flow"))
    grouped: dict[str, dict[str, object]] = {}
    for source_transition in _records(resource_flow.get("transitions")):
        transition = dict(source_transition)
        identity = _text(transition.get("identity"))
        target = _mapping(transition.get("target"))
        source = _mapping(transition.get("source"))
        if not identity or not target:
            continue
        identity_id = identity_entity_id(identity)
        group = grouped.setdefault(
            identity,
            {
                "identity": identity,
                "entity_id": identity_id,
                "resource": _text(target.get("resource")),
                "resource_entity_id": resource_entity_id(_text(target.get("resource"))),
                "states": [],
                "capabilities": [],
                "transitions": [],
                "line": _line(transition.get("line")),
            },
        )
        states = group["states"]
        capabilities = group["capabilities"]
        if not isinstance(states, list) or not isinstance(capabilities, list):
            raise ValueError(f"invalid Studio resource group for {identity}")
        for endpoint in (source, target):
            state = _text(endpoint.get("state"))
            capability = _text(endpoint.get("capability"))
            if state and state not in states:
                states.append(state)
            if capability and capability not in capabilities:
                capabilities.append(capability)
        transitions = group["transitions"]
        if not isinstance(transitions, list):
            raise ValueError(f"invalid Studio transition group for {identity}")
        transition["entity_id"] = resource_transition_entity_id(transition)
        transition["identity_entity_id"] = identity_id
        transition["function_entity_id"] = function_entity_id(
            _text(transition.get("function"))
        )
        transition["source"] = None if not source else dict(source)
        transition["target"] = dict(target)
        transitions.append(transition)
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
    for source in _records(runtime.get("worlds")):
        world = dict(source)
        name = _text(world.get("name"))
        region = world.get("region") if isinstance(world.get("region"), list) else []
        world.update(
            {
                "entity_id": world_entity_id(name),
                "region": [str(item) for item in region],
                "region_path": "/".join(str(item) for item in region),
                "applications": _applications_for(applications, "world", name),
            }
        )
        worlds.append(world)
    return {"worlds": worlds}


def _protocol_events(protocol_name: str, root: Mapping[str, Any]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []

    def visit(
        node: Mapping[str, Any],
        path: tuple[int, ...],
        controls: tuple[str, ...],
    ) -> None:
        kind = _text(node.get("kind"))
        if kind in {"send", "receive"}:
            path_text = "root" if not path else "root." + ".".join(map(str, path))
            events.append(
                {
                    "index": len(events),
                    "path": path_text,
                    "entity_id": protocol_event_entity_id(protocol_name, path_text),
                    "protocol_entity_id": protocol_entity_id(protocol_name),
                    "direction": kind,
                    "type": _text(node.get("type")),
                    "type_entity_id": type_entity_id(_text(node.get("type"), "unknown")),
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
    for source in _records(runtime.get("protocols")):
        protocol = dict(source)
        name = _text(protocol.get("name"))
        root = _mapping(protocol.get("root"))
        protocol.update(
            {
                "entity_id": protocol_entity_id(name),
                "root": dict(root),
                "events": _protocol_events(name, root),
                "applications": _applications_for(applications, "protocol", name),
            }
        )
        protocols.append(protocol)
    return {"protocols": protocols}


def _handler_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    host = _mapping(design.get("host_requirements"))
    host_operations = _records(host.get("operations"))
    handlers: list[dict[str, object]] = []
    for source in _records(runtime.get("handlers")):
        handler = dict(source)
        name = _text(handler.get("name"))
        steps = [dict(step) for step in _records(handler.get("steps"))]
        requirements = []
        for source_requirement in host_operations:
            if source_requirement.get("contract") != name or not _text(
                source_requirement.get("kind")
            ).startswith("handler_"):
                continue
            requirement = dict(source_requirement)
            requirement["entity_id"] = host_requirement_entity_id(
                _text(requirement.get("id"), "unknown")
            )
            requirements.append(requirement)
        nodes: list[dict[str, object]] = [
            {
                "id": "target",
                "entity_id": handler_node_entity_id(name, "target"),
                "kind": "target",
                "label": "Target exit",
                "line": None,
            }
        ]
        edges: list[dict[str, object]] = []
        previous = "target"
        for index, step in enumerate(steps):
            node_id = f"step:{index}"
            operation = _text(step.get("operation"), "handler")
            node = {
                "id": node_id,
                "entity_id": handler_node_entity_id(name, node_id),
                "kind": "handler",
                "label": operation,
                "arguments": step.get("arguments", []),
                "verification": _text(step.get("verification")),
                "line": _line(step.get("line")),
            }
            nodes.append(node)
            edges.append(
                {
                    "source": previous,
                    "target": node_id,
                    "label": "failure path",
                }
            )
            previous = node_id
        nodes.append(
            {
                "id": "exit",
                "entity_id": handler_node_entity_id(name, "exit"),
                "kind": "exit",
                "label": "Declared exit",
                "line": None,
            }
        )
        edges.append({"source": previous, "target": "exit", "label": "complete"})
        handler.update(
            {
                "entity_id": handler_entity_id(name),
                "steps": steps,
                "nodes": nodes,
                "edges": edges,
                "requirements": requirements,
                "applications": _applications_for(applications, "handler", name),
            }
        )
        handlers.append(handler)
    return {"handlers": handlers}


def _law_view(
    design: Mapping[str, Any],
    applications: list[Mapping[str, Any]],
) -> dict[str, object]:
    runtime = _mapping(design.get("runtime_contracts"))
    host = _mapping(design.get("host_requirements"))
    host_operations = _records(host.get("operations"))
    laws: list[dict[str, object]] = []
    for source in _records(runtime.get("laws")):
        law = dict(source)
        name = _text(law.get("name"))
        requirements = []
        for source_requirement in host_operations:
            if source_requirement.get("contract") != name or source_requirement.get(
                "kind"
            ) != "law_observe":
                continue
            requirement = dict(source_requirement)
            requirement["entity_id"] = host_requirement_entity_id(
                _text(requirement.get("id"), "unknown")
            )
            requirements.append(requirement)
        law.update(
            {
                "entity_id": law_entity_id(name),
                "requirements": requirements,
                "applications": _applications_for(applications, "laws", name),
            }
        )
        laws.append(law)
    return {"laws": laws}


def _verification_view(design: Mapping[str, Any]) -> dict[str, object]:
    report = _mapping(design.get("verification"))
    items: list[dict[str, object]] = []
    for source in _records(report.get("items")):
        item = dict(source)
        item["entity_id"] = verification_entity_id(item)
        items.append(item)
    class_rows: list[dict[str, object]] = []
    for name in _VERIFICATION_ORDER:
        selected = [
            item
            for item in items
            if name
            in (item.get("classes") if isinstance(item.get("classes"), list) else [])
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
                in (
                    item.get("classes")
                    if isinstance(item.get("classes"), list)
                    else []
                )
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
    """Project one validated typed design into orthogonal Studio views.

    This function does not parse Glyph source and does not rebuild semantic models.
    It enriches the presentation projection with stable semantic IDs, then creates a
    Studio-only semantic index for navigation. The compiler Public IR is unchanged.
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
    semantic_index = build_semantic_index(design, views)
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
            "semantic_entities": len(semantic_index["entities"]),
            "semantic_relations": len(semantic_index["relations"]),
        },
        "views": views,
        "semantic_index": semantic_index,
    }
