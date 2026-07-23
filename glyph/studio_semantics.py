from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2s
import json
from typing import Any


SEMANTIC_INDEX_SCHEMA = "glyph.studio-semantic-index"
SEMANTIC_INDEX_VERSION = 1

RELATION_KINDS = (
    "declares",
    "accepts",
    "returns",
    "stores",
    "owns",
    "shares",
    "links",
    "borrows",
    "mutably-borrows",
    "converts",
    "moves",
    "creates",
    "preserves",
    "transitions",
    "instance-of",
    "applies",
    "executes-in",
    "uses-protocol",
    "handled-by",
    "constrained-by",
    "contains",
    "sends",
    "receives",
    "next",
    "requires-host",
    "verified-by",
)

_FUNCTION_TARGET_KINDS = {
    "function",
    "effect",
    "opaque",
    "pure-function",
    "effect-function",
}
_AGGREGATE_TARGET_KINDS = {"product", "sum", "aggregate"}
_TYPE_TARGET_KINDS = {"type", "alias"}
_PLACE_TARGET_KINDS = {"field", "place"}


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


def semantic_id(kind: str, key: str) -> str:
    normalized_kind = kind.strip().lower().replace("_", "-")
    normalized_key = key.strip()
    if not normalized_kind or not normalized_key:
        raise ValueError("semantic entity ID requires non-empty kind and key")
    return f"{normalized_kind}:{normalized_key}"


def resource_entity_id(name: str) -> str:
    return semantic_id("resource", name)


def function_entity_id(name: str) -> str:
    return semantic_id("function", name)


def aggregate_entity_id(name: str) -> str:
    return semantic_id("aggregate", name)


def type_entity_id(name: str) -> str:
    return semantic_id("type", name)


def place_entity_id(function: str, place: str) -> str:
    return semantic_id("place", f"{function}:{place}")


def identity_entity_id(identity: str) -> str:
    return semantic_id("identity", identity)


def world_entity_id(name: str) -> str:
    return semantic_id("world", name)


def protocol_entity_id(name: str) -> str:
    return semantic_id("protocol", name)


def protocol_event_entity_id(protocol: str, path: str) -> str:
    return semantic_id("protocol-event", f"{protocol}:{path}")


def handler_entity_id(name: str) -> str:
    return semantic_id("handler", name)


def handler_node_entity_id(handler: str, node: str) -> str:
    return semantic_id("handler-node", f"{handler}:{node}")


def law_entity_id(name: str) -> str:
    return semantic_id("law", name)


def host_requirement_entity_id(requirement_id: str) -> str:
    return semantic_id("host-requirement", requirement_id)


def _normalized_target_kind(target_kind: str) -> str:
    return target_kind.strip().lower().replace("_", "-")


def application_target_entity_id(target_kind: str, target: str) -> str:
    normalized = _normalized_target_kind(target_kind)
    if normalized in _FUNCTION_TARGET_KINDS:
        return function_entity_id(target)
    if normalized == "resource":
        return resource_entity_id(target)
    if normalized in _AGGREGATE_TARGET_KINDS:
        return aggregate_entity_id(target)
    if normalized in _TYPE_TARGET_KINDS:
        return type_entity_id(target)
    if normalized in _PLACE_TARGET_KINDS:
        return semantic_id("place", target)
    return semantic_id(normalized or "target", target)


def application_target_entity_kind(target_kind: str) -> str:
    normalized = _normalized_target_kind(target_kind)
    if normalized in _FUNCTION_TARGET_KINDS:
        return "function"
    if normalized == "resource":
        return "resource"
    if normalized in _AGGREGATE_TARGET_KINDS:
        return "aggregate"
    if normalized in _TYPE_TARGET_KINDS:
        return "type"
    if normalized in _PLACE_TARGET_KINDS:
        return "place"
    return normalized or "target"


def contract_entity_id(axis: str, name: str) -> str:
    if axis == "world":
        return world_entity_id(name)
    if axis == "protocol":
        return protocol_entity_id(name)
    if axis == "handler":
        return handler_entity_id(name)
    if axis in {"law", "laws"}:
        return law_entity_id(name)
    return semantic_id("contract", name)


def capability_operation_entity_id(operation: Mapping[str, Any]) -> str:
    parts = (
        _text(operation.get("function")),
        str(_line(operation.get("line")) or 0),
        _text(operation.get("kind")),
        _text(operation.get("source"), "-"),
        _text(operation.get("target"), "-"),
    )
    return semantic_id("capability-operation", ":".join(parts))


def resource_transition_entity_id(transition: Mapping[str, Any]) -> str:
    parts = (
        _text(transition.get("identity")),
        _text(transition.get("function")),
        str(_line(transition.get("line")) or 0),
        _text(transition.get("kind")),
    )
    return semantic_id("resource-transition", ":".join(parts))


def verification_entity_id(item: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {
            "subject": _text(item.get("subject")),
            "axis": _text(item.get("axis")),
            "classes": item.get("classes")
            if isinstance(item.get("classes"), list)
            else [],
            "statement": _text(item.get("statement")),
            "line": _line(item.get("line")),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = blake2s(canonical.encode("utf-8"), digest_size=6).hexdigest()
    return semantic_id(
        "verification",
        f"{_text(item.get('axis'), 'unknown')}:{_text(item.get('subject'), 'subject')}:{digest}",
    )


def _capability_relation(capability: str) -> str:
    return {
        "own": "owns",
        "share": "shares",
        "link": "links",
        "borrow": "borrows",
        "borrow_mut": "mutably-borrows",
    }.get(capability, "declares")


class _IndexBuilder:
    def __init__(self) -> None:
        self._entities: dict[str, dict[str, object]] = {}
        self._relations: dict[
            tuple[str, str, str, int | None], dict[str, object]
        ] = {}

    def entity(
        self,
        entity_id: str,
        kind: str,
        label: str,
        *,
        line: int | None = None,
        views: tuple[str, ...] = (),
        aliases: tuple[str, ...] = (),
        details: Mapping[str, object] | None = None,
    ) -> str:
        current = self._entities.get(entity_id)
        if current is None:
            current = {
                "id": entity_id,
                "kind": kind,
                "label": label,
                "line": line,
                "views": [],
                "aliases": [],
                "details": {},
            }
            self._entities[entity_id] = current
        elif current["kind"] != kind:
            raise ValueError(f"semantic entity kind conflict for {entity_id}")

        if current.get("line") is None and line is not None:
            current["line"] = line
        view_list = current.get("views")
        alias_list = current.get("aliases")
        detail_map = current.get("details")
        if not isinstance(view_list, list):
            raise TypeError(f"semantic entity views are not a list: {entity_id}")
        if not isinstance(alias_list, list):
            raise TypeError(f"semantic entity aliases are not a list: {entity_id}")
        if not isinstance(detail_map, dict):
            raise TypeError(f"semantic entity details are not a mapping: {entity_id}")
        for view in views:
            if view and view not in view_list:
                view_list.append(view)
        for alias in aliases:
            if alias and alias != label and alias not in alias_list:
                alias_list.append(alias)
        if details:
            for key, value in details.items():
                if value not in (None, "", [], {}):
                    detail_map[key] = value
        return entity_id

    def relation(
        self,
        source: str,
        kind: str,
        target: str,
        *,
        line: int | None = None,
        views: tuple[str, ...] = (),
        details: Mapping[str, object] | None = None,
    ) -> None:
        if source not in self._entities or target not in self._entities:
            raise ValueError(
                f"semantic relation endpoint is undefined: {source} {kind} {target}"
            )
        if kind not in RELATION_KINDS:
            raise ValueError(f"unknown semantic relation kind: {kind}")
        key = (source, kind, target, line)
        current = self._relations.get(key)
        if current is None:
            current = {
                "source": source,
                "kind": kind,
                "target": target,
                "line": line,
                "views": [],
                "details": {},
            }
            self._relations[key] = current
        view_list = current.get("views")
        detail_map = current.get("details")
        if not isinstance(view_list, list):
            raise TypeError("semantic relation views are not a list")
        if not isinstance(detail_map, dict):
            raise TypeError("semantic relation details are not a mapping")
        for view in views:
            if view and view not in view_list:
                view_list.append(view)
        if details:
            for key_name, value in details.items():
                if value not in (None, "", [], {}):
                    detail_map[key_name] = value

    def build(self) -> dict[str, object]:
        entities = sorted(
            self._entities.values(),
            key=lambda item: (
                item.get("line") if isinstance(item.get("line"), int) else 10**9,
                str(item.get("kind")),
                str(item.get("label")),
                str(item.get("id")),
            ),
        )
        relations = sorted(
            self._relations.values(),
            key=lambda item: (
                str(item.get("source")),
                str(item.get("kind")),
                str(item.get("target")),
                item.get("line")
                if isinstance(item.get("line"), int)
                else 10**9,
            ),
        )
        return {
            "schema": SEMANTIC_INDEX_SCHEMA,
            "version": SEMANTIC_INDEX_VERSION,
            "relation_kinds": list(RELATION_KINDS),
            "entities": entities,
            "relations": relations,
        }


def _canonical_type_entity(
    builder: _IndexBuilder,
    type_value: Mapping[str, Any],
    *,
    view: str,
) -> str:
    explicit_id = _text(type_value.get("type_entity_id"))
    name = _text(type_value.get("name"), "unknown")
    state = type_value.get("state")
    if explicit_id:
        prefix, separator, label = explicit_id.partition(":")
        if not separator or prefix not in {"resource", "type"} or not label:
            raise ValueError(f"invalid canonical type entity ID: {explicit_id}")
        entity_id = explicit_id
        entity_kind = prefix
        entity_label = label
    else:
        is_resource = state is not None
        entity_id = resource_entity_id(name) if is_resource else type_entity_id(name)
        entity_kind = "resource" if is_resource else "type"
        entity_label = name
    builder.entity(
        entity_id,
        entity_kind,
        entity_label,
        views=(view,),
        aliases=(_text(type_value.get("raw")),),
        details={
            "capability": _text(type_value.get("capability")),
            "state": state,
        },
    )
    for argument in _records(type_value.get("args")):
        _canonical_type_entity(builder, argument, view=view)
    return entity_id


def _subject_entity(
    builder: _IndexBuilder,
    axis: str,
    subject: str,
    line: int | None,
    known: Mapping[str, str],
) -> str:
    direct = known.get(f"{axis}:{subject}") or known.get(subject)
    if direct:
        return direct
    if axis == "handler" and "." in subject:
        handler_name, operation = subject.split(".", 1)
        direct = known.get(
            f"handler-step:{handler_name}:{operation}:{line or 0}"
        ) or known.get(f"handler-step:{handler_name}:{operation}")
        if direct:
            return direct
    entity_id = semantic_id("subject", f"{axis}:{subject}")
    builder.entity(
        entity_id,
        "subject",
        subject,
        line=line,
        views=("Verification",),
        details={"axis": axis},
    )
    return entity_id


def _register_capabilities(
    builder: _IndexBuilder,
    views: Mapping[str, Any],
    known: dict[str, str],
) -> None:
    capability = _mapping(views.get("capability"))
    for resource in _records(capability.get("resources")):
        name = _text(resource.get("name"))
        entity_id = _text(resource.get("entity_id"), resource_entity_id(name))
        builder.entity(
            entity_id,
            "resource",
            name,
            line=_line(resource.get("line")),
            views=("Capability", "Resource"),
            details={"states": resource.get("states", [])},
        )
        known[name] = entity_id
        known[f"resource:{name}"] = entity_id

    for aggregate in _records(capability.get("aggregates")):
        name = _text(aggregate.get("name"))
        entity_id = _text(aggregate.get("entity_id"), aggregate_entity_id(name))
        builder.entity(
            entity_id,
            "aggregate",
            name,
            line=_line(aggregate.get("line")),
            views=("Capability",),
        )
        known[name] = entity_id
        known[f"aggregate:{name}"] = entity_id
        for index, member in enumerate(_records(aggregate.get("members"))):
            target = _canonical_type_entity(builder, member, view="Capability")
            builder.relation(
                entity_id,
                "stores",
                target,
                line=_line(member.get("line")) or _line(aggregate.get("line")),
                views=("Capability",),
                details={"member": index},
            )

    for function in _records(capability.get("functions")):
        name = _text(function.get("name"))
        function_id = _text(function.get("entity_id"), function_entity_id(name))
        builder.entity(
            function_id,
            "function",
            name,
            line=_line(function.get("line")),
            views=("Capability", "Logic", "Flow"),
            details={"marker": _text(function.get("marker"))},
        )
        known[name] = function_id
        known[f"capability:{name}"] = function_id
        known[f"function:{name}"] = function_id

        for parameter in _records(function.get("params")):
            parameter_name = _text(parameter.get("name"))
            place_id = _text(
                parameter.get("entity_id"),
                place_entity_id(name, f"param:{parameter_name}"),
            )
            type_value = _mapping(parameter.get("type"))
            builder.entity(
                place_id,
                "place",
                f"{name}.{parameter_name}",
                line=_line(parameter.get("line")) or _line(function.get("line")),
                views=("Capability", "Resource"),
                details={
                    "role": "parameter",
                    "type": type_value.get("raw") or type_value.get("name"),
                },
            )
            type_id = _canonical_type_entity(builder, type_value, view="Capability")
            builder.relation(
                function_id,
                "accepts",
                place_id,
                line=_line(parameter.get("line")),
                views=("Capability",),
            )
            builder.relation(
                place_id,
                _capability_relation(_text(type_value.get("capability"))),
                type_id,
                line=_line(parameter.get("line")),
                views=("Capability", "Resource"),
                details={"state": type_value.get("state")},
            )
            known[f"place:{name}:{parameter_name}"] = place_id

        result = _mapping(function.get("result"))
        result_place = _text(
            function.get("result_entity_id"), place_entity_id(name, "result")
        )
        builder.entity(
            result_place,
            "place",
            f"{name}.result",
            line=_line(function.get("line")),
            views=("Capability", "Resource"),
            details={
                "role": "result",
                "type": result.get("raw") or result.get("name"),
            },
        )
        result_type = _canonical_type_entity(builder, result, view="Capability")
        builder.relation(
            function_id,
            "returns",
            result_place,
            line=_line(function.get("line")),
            views=("Capability",),
        )
        builder.relation(
            result_place,
            _capability_relation(_text(result.get("capability"))),
            result_type,
            line=_line(function.get("line")),
            views=("Capability", "Resource"),
            details={"state": result.get("state")},
        )

    for operation in _records(capability.get("operations")):
        operation_id = _text(
            operation.get("entity_id"), capability_operation_entity_id(operation)
        )
        function_name = _text(operation.get("function"))
        function_id = known.get(function_name)
        if function_id is None:
            function_id = function_entity_id(function_name)
            builder.entity(
                function_id,
                "function",
                function_name,
                line=_line(operation.get("line")),
                views=("Capability",),
            )
            known[function_name] = function_id
        builder.entity(
            operation_id,
            "capability-operation",
            _text(operation.get("kind"), "operation"),
            line=_line(operation.get("line")),
            views=("Capability",),
            details=dict(operation),
        )
        operation_kind = _text(operation.get("kind"))
        if "move" in operation_kind:
            relation_kind = "moves"
        elif "borrow_mut" in operation_kind:
            relation_kind = "mutably-borrows"
        elif "borrow" in operation_kind:
            relation_kind = "borrows"
        else:
            relation_kind = "converts"
        builder.relation(
            function_id,
            relation_kind,
            operation_id,
            line=_line(operation.get("line")),
            views=("Capability",),
        )


def _register_resources(
    builder: _IndexBuilder,
    views: Mapping[str, Any],
    known: dict[str, str],
) -> None:
    for identity in _records(_mapping(views.get("resource")).get("identities")):
        raw_identity = _text(identity.get("identity"))
        identity_id = _text(
            identity.get("entity_id"), identity_entity_id(raw_identity)
        )
        resource_name = _text(identity.get("resource"))
        resource_id = known.get(resource_name, resource_entity_id(resource_name))
        builder.entity(
            resource_id,
            "resource",
            resource_name,
            views=("Capability", "Resource"),
        )
        builder.entity(
            identity_id,
            "resource-identity",
            resource_name or raw_identity,
            line=_line(identity.get("line")),
            views=("Resource", "Capability", "Handler", "Verification"),
            aliases=(raw_identity,),
            details={
                "identity": raw_identity,
                "states": identity.get("states", []),
                "capabilities": identity.get("capabilities", []),
            },
        )
        builder.relation(
            identity_id,
            "instance-of",
            resource_id,
            line=_line(identity.get("line")),
            views=("Resource",),
        )
        known[raw_identity] = identity_id

        for transition in _records(identity.get("transitions")):
            transition_id = _text(
                transition.get("entity_id"),
                resource_transition_entity_id(
                    {**transition, "identity": raw_identity}
                ),
            )
            function_name = _text(transition.get("function"))
            function_id = known.get(function_name, function_entity_id(function_name))
            builder.entity(
                function_id,
                "function",
                function_name,
                line=_line(transition.get("line")),
                views=("Resource", "Capability"),
            )
            builder.entity(
                transition_id,
                "resource-transition",
                f"{function_name}: {_text(transition.get('kind'))}",
                line=_line(transition.get("line")),
                views=("Resource",),
                details={
                    "source": transition.get("source"),
                    "target": transition.get("target"),
                    "kind": transition.get("kind"),
                },
            )
            relation_kind = {
                "create": "creates",
                "preserve": "preserves",
                "transition": "transitions",
            }.get(_text(transition.get("kind")), "transitions")
            builder.relation(
                function_id,
                relation_kind,
                identity_id,
                line=_line(transition.get("line")),
                views=("Resource", "Capability"),
                details={"transition": transition_id},
            )
            builder.relation(
                transition_id,
                "instance-of",
                identity_id,
                line=_line(transition.get("line")),
                views=("Resource",),
            )


def _register_contracts(
    builder: _IndexBuilder,
    design: Mapping[str, Any],
    views: Mapping[str, Any],
    known: dict[str, str],
) -> None:
    for world in _records(_mapping(views.get("world_region")).get("worlds")):
        name = _text(world.get("name"))
        entity_id = _text(world.get("entity_id"), world_entity_id(name))
        builder.entity(
            entity_id,
            "world",
            name,
            line=_line(world.get("line")),
            views=("World/Region", "Verification"),
            details={"locus": world.get("locus"), "region": world.get("region", [])},
        )
        known[f"world:{name}"] = entity_id
        known.setdefault(name, entity_id)

    for protocol in _records(_mapping(views.get("protocol")).get("protocols")):
        name = _text(protocol.get("name"))
        protocol_id = _text(protocol.get("entity_id"), protocol_entity_id(name))
        builder.entity(
            protocol_id,
            "protocol",
            name,
            line=_line(protocol.get("line")),
            views=("Protocol", "Verification"),
        )
        known[f"protocol:{name}"] = protocol_id
        known.setdefault(name, protocol_id)
        for event in _records(protocol.get("events")):
            path = _text(event.get("path"), "root")
            event_id = _text(
                event.get("entity_id"), protocol_event_entity_id(name, path)
            )
            direction = _text(event.get("direction"))
            message_type = _text(event.get("type"), "unknown")
            builder.entity(
                event_id,
                "protocol-event",
                f"{direction} {message_type}",
                line=_line(protocol.get("line")),
                views=("Protocol",),
                details={"path": path, "controls": event.get("controls", [])},
            )
            builder.relation(
                protocol_id,
                "contains",
                event_id,
                line=_line(protocol.get("line")),
                views=("Protocol",),
            )
            type_id = type_entity_id(message_type)
            builder.entity(
                type_id,
                "type",
                message_type,
                views=("Protocol", "Capability"),
            )
            builder.relation(
                event_id,
                "sends" if direction == "send" else "receives",
                type_id,
                line=_line(protocol.get("line")),
                views=("Protocol",),
            )

    for handler in _records(_mapping(views.get("handler")).get("handlers")):
        name = _text(handler.get("name"))
        handler_id = _text(handler.get("entity_id"), handler_entity_id(name))
        builder.entity(
            handler_id,
            "handler",
            name,
            line=_line(handler.get("line")),
            views=("Handler", "Verification"),
        )
        known[f"handler:{name}"] = handler_id
        known.setdefault(name, handler_id)
        previous_node: str | None = None
        for node in _records(handler.get("nodes")):
            node_id = _text(
                node.get("entity_id"),
                handler_node_entity_id(name, _text(node.get("id"))),
            )
            builder.entity(
                node_id,
                "handler-node",
                _text(node.get("label")),
                line=_line(node.get("line")),
                views=("Handler",),
                details={
                    "node_kind": node.get("kind"),
                    "arguments": node.get("arguments", []),
                    "verification": node.get("verification"),
                },
            )
            builder.relation(
                handler_id,
                "contains",
                node_id,
                line=_line(node.get("line")) or _line(handler.get("line")),
                views=("Handler",),
            )
            if previous_node is not None:
                builder.relation(
                    previous_node,
                    "next",
                    node_id,
                    line=_line(node.get("line")),
                    views=("Handler",),
                )
            previous_node = node_id
            operation = _text(node.get("label"))
            if operation:
                known.setdefault(f"handler-step:{name}:{operation}", node_id)
                known[
                    f"handler-step:{name}:{operation}:{_line(node.get('line')) or 0}"
                ] = node_id

    for law in _records(_mapping(views.get("law")).get("laws")):
        name = _text(law.get("name"))
        law_id = _text(law.get("entity_id"), law_entity_id(name))
        builder.entity(
            law_id,
            "law",
            name,
            line=_line(law.get("line")),
            views=("Law/Monitor", "Verification"),
            details={
                "formula": law.get("formula", {}),
                "verification": law.get("verification"),
            },
        )
        known[f"law:{name}"] = law_id
        known.setdefault(name, law_id)

    runtime = _mapping(design.get("runtime_contracts"))
    for application in _records(runtime.get("applications")):
        target = _text(application.get("target"))
        target_kind = _text(application.get("target_kind"))
        target_id = application_target_entity_id(target_kind, target)
        builder.entity(
            target_id,
            application_target_entity_kind(target_kind),
            target,
            line=_line(application.get("line")),
            views=(
                "Capability",
                "World/Region",
                "Protocol",
                "Handler",
                "Law/Monitor",
            ),
        )
        row = _mapping(application.get("row"))
        selections = (
            ("world", row.get("world"), "executes-in"),
            ("protocol", row.get("protocol"), "uses-protocol"),
            ("handler", row.get("handler"), "handled-by"),
        )
        for axis, selected, relation_kind in selections:
            if not isinstance(selected, str) or not selected:
                continue
            contract_id = contract_entity_id(axis, selected)
            view = {
                "world": "World/Region",
                "protocol": "Protocol",
                "handler": "Handler",
            }[axis]
            builder.entity(contract_id, axis, selected, views=(view,))
            builder.relation(
                contract_id,
                "applies",
                target_id,
                line=_line(application.get("line")),
                views=(view,),
            )
            builder.relation(
                target_id,
                relation_kind,
                contract_id,
                line=_line(application.get("line")),
                views=(view,),
            )
        laws = row.get("laws") if isinstance(row.get("laws"), list) else []
        for law_name in (
            item for item in laws if isinstance(item, str) and item
        ):
            law_id = law_entity_id(law_name)
            builder.entity(law_id, "law", law_name, views=("Law/Monitor",))
            builder.relation(
                law_id,
                "applies",
                target_id,
                line=_line(application.get("line")),
                views=("Law/Monitor",),
            )
            builder.relation(
                target_id,
                "constrained-by",
                law_id,
                line=_line(application.get("line")),
                views=("Law/Monitor",),
            )


def _register_host_requirements(
    builder: _IndexBuilder,
    design: Mapping[str, Any],
    known: Mapping[str, str],
) -> None:
    host = _mapping(design.get("host_requirements"))
    for requirement in _records(host.get("operations")):
        requirement_id = host_requirement_entity_id(
            _text(requirement.get("id"), "unknown")
        )
        builder.entity(
            requirement_id,
            "host-requirement",
            _text(requirement.get("kind"), "Host requirement"),
            line=_line(requirement.get("line")),
            views=("Handler", "Law/Monitor", "Verification"),
            aliases=(_text(requirement.get("subject")),),
            details=dict(requirement),
        )
        contract = _text(requirement.get("contract"))
        if not contract:
            continue
        candidates = (
            known.get(f"handler:{contract}"),
            known.get(f"law:{contract}"),
            known.get(f"protocol:{contract}"),
            known.get(f"world:{contract}"),
        )
        owner = next((candidate for candidate in candidates if candidate), None)
        if owner:
            builder.relation(
                owner,
                "requires-host",
                requirement_id,
                line=_line(requirement.get("line")),
                views=("Handler", "Law/Monitor", "Verification"),
            )


def _register_verification(
    builder: _IndexBuilder,
    views: Mapping[str, Any],
    known: Mapping[str, str],
) -> None:
    verification = _mapping(views.get("verification_strength"))
    for item in _records(verification.get("items")):
        verification_id = _text(
            item.get("entity_id"), verification_entity_id(item)
        )
        axis = _text(item.get("axis"), "unknown")
        subject = _text(item.get("subject"), "subject")
        builder.entity(
            verification_id,
            "verification",
            subject,
            line=_line(item.get("line")),
            views=("Verification",),
            details={
                "axis": axis,
                "classes": item.get("classes", []),
                "statement": item.get("statement"),
            },
        )
        subject_id = _subject_entity(
            builder, axis, subject, _line(item.get("line")), known
        )
        builder.relation(
            subject_id,
            "verified-by",
            verification_id,
            line=_line(item.get("line")),
            views=("Verification",),
        )


def build_semantic_index(
    design: Mapping[str, Any],
    views: Mapping[str, Any],
) -> dict[str, object]:
    """Build a closed Studio-only semantic graph from validated compiler output.

    IDs and relation kinds are independent of presentation order. This function does
    not parse Glyph source, change Public IR, or infer concrete runtime mechanisms.
    """

    builder = _IndexBuilder()
    known: dict[str, str] = {}
    _register_capabilities(builder, views, known)
    _register_resources(builder, views, known)
    _register_contracts(builder, design, views, known)
    _register_host_requirements(builder, design, known)
    _register_verification(builder, views, known)
    return builder.build()
