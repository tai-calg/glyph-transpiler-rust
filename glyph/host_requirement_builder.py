from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterator

from .capabilities import CapabilityKind, CapabilityModel, CapabilityType
from .contract_semantics import ContractSemanticModel, ProtocolNode
from .host_requirements import (
    HostInvariant,
    HostOperationRequirement,
    HostPort,
    HostRequirementModel,
    HostTypeRef,
    RepresentationSlot,
)
from .resource_flow import ResourceFlowModel
from .verification_classes import split_verification_classes


def _pascal(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    rendered = "".join(part[:1].upper() + part[1:] for part in parts)
    return rendered or "Value"


@dataclass(frozen=True)
class ProtocolTraceEvent:
    node: ProtocolNode
    path: tuple[int, ...]
    controls: tuple[str, ...]

    @property
    def path_text(self) -> str:
        return "root" if not self.path else "root." + ".".join(map(str, self.path))


def iter_protocol_events(
    node: ProtocolNode,
    path: tuple[int, ...] = (),
    controls: tuple[str, ...] = (),
) -> Iterator[ProtocolTraceEvent]:
    """Walk Protocol events without flattening away choice or parallel structure."""

    if node.kind in {"send", "receive"}:
        if node.type_name is None:
            raise ValueError(f"Protocol {node.kind} node has no type at {path!r}")
        yield ProtocolTraceEvent(node, path, controls)
        return

    nested_controls = controls + (node.kind,)
    for index, child in enumerate(node.children):
        yield from iter_protocol_events(
            child,
            (*path, index),
            nested_controls,
        )


class _Builder:
    def __init__(
        self,
        capabilities: CapabilityModel,
        runtime: ContractSemanticModel,
        resource_flow: ResourceFlowModel,
    ):
        self.capabilities = capabilities
        self.runtime = runtime
        self.resource_flow = resource_flow
        self._slots: dict[str, RepresentationSlot] = {}
        self.operations: list[HostOperationRequirement] = []
        self._applications = {item.target: item for item in runtime.applications}
        self._worlds = {item.name: item for item in runtime.worlds}
        self._protocols = {item.name: item for item in runtime.protocols}
        self._handlers = {item.name: item for item in runtime.handlers}
        self._laws = {item.name: item for item in runtime.laws}

    def _slot(
        self,
        ty: HostTypeRef,
        world: str | None,
        origin: str,
        line: int | None,
        *,
        include_plain: bool = False,
    ) -> str | None:
        if ty.capability not in {"own", "share", "link"} and not include_plain:
            return None

        key = f"{ty.canonical_key()}@{world or '_'}"
        slot_id = "repr:" + key
        current = self._slots.get(slot_id)
        if current is not None:
            if origin not in current.origins:
                self._slots[slot_id] = RepresentationSlot(
                    current.id,
                    current.associated_type,
                    current.type,
                    current.world,
                    tuple(sorted((*current.origins, origin))),
                    current.line if current.line is not None else line,
                )
            return slot_id

        digest = hashlib.sha1(slot_id.encode("utf-8")).hexdigest()[:8]
        associated_type = (
            "Repr"
            + _pascal(ty.capability)
            + _pascal(ty.name)
            + ("" if ty.state is None else _pascal(ty.state))
            + ("" if world is None else _pascal(world))
            + digest.upper()
        )
        self._slots[slot_id] = RepresentationSlot(
            slot_id,
            associated_type,
            ty,
            world,
            (origin,),
            line,
        )
        return slot_id

    def _port(
        self,
        name: str,
        ty: HostTypeRef,
        world: str | None,
        origin: str,
        line: int | None,
        *,
        include_plain: bool = False,
    ) -> HostPort:
        representation = self._slot(
            ty,
            world,
            origin,
            line,
            include_plain=include_plain,
        )
        if representation is None:
            raise ValueError(
                f"Host port '{name}' has no representation slot for {ty.canonical_key()}"
            )
        return HostPort(name, ty, representation)

    def collect_boundary_representations(self) -> None:
        """Register only values that actually cross a Host-facing boundary."""

        for function in self.capabilities.functions:
            application = self._applications.get(function.name)
            world = None if application is None else application.row.world
            for parameter in function.params:
                self._slot(
                    HostTypeRef.from_capability(parameter.type),
                    world,
                    f"function:{function.name}:param:{parameter.name}",
                    parameter.line,
                )
            self._slot(
                HostTypeRef.from_capability(function.result),
                world,
                f"function:{function.name}:result",
                function.line,
            )

    def capability_operations(self) -> None:
        by_function: dict[str, dict[str, CapabilityType]] = {
            function.name: {
                parameter.name: parameter.type for parameter in function.params
            }
            for function in self.capabilities.functions
        }
        counts: dict[tuple[str, str], int] = {}

        for operation in self.capabilities.operations:
            environment = by_function.setdefault(operation.function, {})
            source_name = operation.source
            if operation.kind == "move":
                if source_name is not None and operation.target is not None:
                    source_type = environment.get(source_name)
                    if source_type is not None:
                        environment[operation.target] = source_type
                continue
            if operation.kind != "capability_cast" or source_name is None:
                continue

            source_type = environment.get(source_name)
            if source_type is None:
                source_type = environment.get(source_name.split(".", 1)[0])
            if source_type is None or operation.capability is None:
                continue

            target_kind = CapabilityKind(operation.capability)
            target_type = CapabilityType(
                target_kind,
                source_type.name,
                source_type.args,
                source_type.state,
                source_type.raw,
            )
            if operation.target is not None:
                environment[operation.target] = target_type

            operation_kind = _CAPABILITY_OPERATIONS.get(
                (source_type.capability, target_kind)
            )
            if operation_kind is None:
                continue

            application = self._applications.get(operation.function)
            world = None if application is None else application.row.world
            count_key = (operation.function, operation_kind)
            index = counts.get(count_key, 0)
            counts[count_key] = index + 1
            input_port = self._port(
                "value",
                HostTypeRef.from_capability(source_type),
                world,
                f"operation:{operation.function}:{operation_kind}:input",
                operation.line,
            )
            output_port = self._port(
                "value",
                HostTypeRef.from_capability(target_type),
                world,
                f"operation:{operation.function}:{operation_kind}:output",
                operation.line,
            )
            preconditions, postconditions, may_fail = _capability_contract(
                operation_kind
            )
            self.operations.append(
                HostOperationRequirement(
                    f"cap:{operation.function}:{operation_kind}:{index}",
                    operation_kind,
                    operation.function,
                    None,
                    (input_port,),
                    (output_port,),
                    (),
                    preconditions,
                    postconditions,
                    may_fail,
                    ("static", "trusted"),
                    operation.line,
                )
            )

    def resource_operations(self) -> None:
        counts: dict[tuple[str, str], int] = {}
        for transition in self.resource_flow.transitions:
            application = self._applications.get(transition.function)
            world = None if application is None else application.row.world
            count_key = (transition.function, transition.kind)
            index = counts.get(count_key, 0)
            counts[count_key] = index + 1

            inputs: tuple[HostPort, ...] = ()
            if transition.source is not None:
                inputs = (
                    self._port(
                        "source",
                        HostTypeRef.from_endpoint(transition.source),
                        world,
                        f"resource:{transition.function}:{transition.identity}:source",
                        transition.line,
                    ),
                )
            outputs = (
                self._port(
                    "target",
                    HostTypeRef.from_endpoint(transition.target),
                    world,
                    f"resource:{transition.function}:{transition.identity}:target",
                    transition.line,
                ),
            )
            preconditions = (
                f"the input represents symbolic resource identity {transition.identity}",
            )
            if transition.source is not None:
                preconditions += (
                    f"the input state is {transition.source.state}",
                    f"the input capability is {transition.source.capability}",
                )
            postconditions = (
                f"the output represents the same symbolic identity {transition.identity}",
                f"the output state is {transition.target.state}",
                f"the output capability is {transition.target.capability}",
            )
            self.operations.append(
                HostOperationRequirement(
                    f"resource:{transition.function}:{transition.kind}:{index}",
                    f"resource_{transition.kind}",
                    transition.function,
                    None,
                    inputs,
                    outputs,
                    (("identity", transition.identity),),
                    preconditions,
                    postconditions,
                    False,
                    ("static", "trusted"),
                    transition.line,
                )
            )

    def runtime_operations(self) -> None:
        for application in self.runtime.applications:
            row = application.row
            if row.world is not None:
                self._world_operation(application, row.world)
            if row.protocol is not None:
                self._protocol_operations(application, row.protocol, row.world)
            if row.handler is not None:
                self._handler_operations(application, row.handler)
            for law_name in row.laws:
                self._law_operation(application, law_name)

    def _world_operation(self, application, world_name: str) -> None:
        world = self._worlds[world_name]
        region = "/".join(world.region)
        self.operations.append(
            HostOperationRequirement(
                f"world:{application.target}:{world_name}",
                "world_scope",
                application.target,
                world_name,
                (),
                (),
                (
                    ("locus", world.locus),
                    ("region", region),
                    ("target_kind", application.target_kind),
                ),
                (
                    f"execution begins in locus {world.locus}",
                    f"Region {region} is entered before the target runs",
                ),
                (
                    "the target executes only in the declared locus",
                    "the entered Region is closed exactly once on every exit",
                ),
                True,
                ("static", "trusted"),
                application.line,
            )
        )

    def _protocol_operations(
        self,
        application,
        protocol_name: str,
        world_name: str | None,
    ) -> None:
        protocol = self._protocols[protocol_name]
        for event in iter_protocol_events(protocol.root):
            type_name = event.node.type_name
            if type_name is None:
                raise ValueError(
                    f"Protocol event {protocol_name}:{event.path_text} has no type"
                )
            type_ref = HostTypeRef(type_name)
            origin = (
                f"protocol:{application.target}:{protocol_name}:{event.path_text}"
            )
            port = self._port(
                "value",
                type_ref,
                world_name,
                origin,
                application.line,
                include_plain=True,
            )
            inputs = (port,) if event.node.kind == "send" else ()
            outputs = (port,) if event.node.kind == "receive" else ()
            controls = "/".join(event.controls) or "event"
            preconditions = (
                f"the declared Protocol control state enables node {event.path_text}",
            )
            if "sequence" in event.controls:
                preconditions += (
                    "sequence predecessors in the same active branch have completed",
                )
            self.operations.append(
                HostOperationRequirement(
                    f"protocol:{application.target}:{protocol_name}:{event.path_text}",
                    f"protocol_{event.node.kind}",
                    application.target,
                    protocol_name,
                    inputs,
                    outputs,
                    (
                        ("path", event.path_text),
                        ("controls", controls),
                        ("type", type_name),
                    ),
                    preconditions,
                    (
                        f"the {event.node.kind} event advances the declared {controls} control state without selecting a transport",
                    ),
                    True,
                    ("static", "trusted"),
                    application.line,
                )
            )

    def _handler_operations(self, application, handler_name: str) -> None:
        handler = self._handlers[handler_name]
        for index, step in enumerate(handler.steps):
            preconditions, postconditions = _handler_contract(step.operation)
            classes = split_verification_classes(
                step.verification,
                default=("trusted",),
            )
            self.operations.append(
                HostOperationRequirement(
                    f"handler:{application.target}:{handler_name}:{index}",
                    f"handler_{step.operation}",
                    application.target,
                    handler_name,
                    (),
                    (),
                    tuple(
                        (f"arg{argument_index}", argument)
                        for argument_index, argument in enumerate(step.arguments)
                    ),
                    preconditions,
                    postconditions,
                    True,
                    classes,
                    step.line,
                )
            )

    def _law_operation(self, application, law_name: str) -> None:
        law = self._laws[law_name]
        classes = split_verification_classes(
            law.verification,
            default=("runtime",),
        )
        self.operations.append(
            HostOperationRequirement(
                f"law:{application.target}:{law_name}",
                "law_observe",
                application.target,
                law_name,
                (),
                (),
                (
                    (
                        "formula",
                        json.dumps(
                            law.formula,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                ),
                (
                    "runtime events use the canonical Contract identity and target identity",
                ),
                (
                    "events reach the monitor in execution order without being fabricated or dropped",
                ),
                False,
                classes,
                application.line,
            )
        )

    def finish(self) -> HostRequirementModel:
        slots = tuple(sorted(self._slots.values(), key=lambda item: item.id))
        associated_types = [slot.associated_type for slot in slots]
        if len(associated_types) != len(set(associated_types)):
            raise ValueError("Host representation associated type collision")
        return HostRequirementModel(slots, tuple(self.operations), _INVARIANTS)


_CAPABILITY_OPERATIONS = {
    (CapabilityKind.OWN, CapabilityKind.SHARE): "publish",
    (CapabilityKind.SHARE, CapabilityKind.SHARE): "clone_share",
    (CapabilityKind.SHARE, CapabilityKind.LINK): "downgrade",
    (CapabilityKind.LINK, CapabilityKind.LINK): "clone_link",
    (CapabilityKind.LINK, CapabilityKind.SHARE): "resolve_link",
}


def _capability_contract(
    kind: str,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    contracts = {
        "publish": (
            ("the input carries unique strong ownership",),
            (
                "the input ownership is consumed",
                "the output may be cloned to extend liveness",
                "the output does not imply mutable access",
            ),
            False,
        ),
        "clone_share": (
            ("the input is a live strong shared capability",),
            (
                "the input remains live",
                "the output refers to the same identity and also maintains liveness",
                "no mutable permission is introduced",
            ),
            False,
        ),
        "downgrade": (
            ("the input is a live strong shared capability",),
            (
                "the input remains live",
                "the output refers to the same identity without maintaining liveness",
            ),
            False,
        ),
        "clone_link": (
            ("the input is a non-owning link",),
            (
                "the input remains usable",
                "the output is another non-owning link to the same identity",
            ),
            False,
        ),
        "resolve_link": (
            ("the input is a non-owning link",),
            (
                "success returns a strong shared capability to the same identity",
                "failure is reported when the target is no longer live",
            ),
            True,
        ),
    }
    return contracts[kind]


def _handler_contract(operation: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    contracts = {
        "timeout": (
            ("the enclosed operation has a declared duration bound",),
            ("timeout is reported according to the declared clock semantics",),
        ),
        "cancel": (
            ("the target is inside a cancellable dynamic scope",),
            ("cancellation follows every declared exit obligation",),
        ),
        "retry": (
            (
                "the target returns Result",
                "the retry count and backoff policy are valid",
                "the retry entry ledger is equivalent to the original entry ledger",
            ),
            (
                "each attempt preserves resource identities",
                "no attempt begins from an undeclared state",
            ),
        ),
        "rollback": (
            ("the named resource is owned by the target",),
            (
                "the resource reaches the declared recovery state or failure is reported",
            ),
        ),
        "compensate": (
            ("the named compensation target is an effect boundary",),
            (
                "the compensation effect follows the declared ordering and failure policy",
            ),
        ),
        "fallback": (
            ("the fallback has the same input and output contract",),
            ("the fallback result is interpreted under the original Contract row",),
        ),
        "return_error": (
            ("an error value exists on the active exit path",),
            ("the error is returned without losing owned resource obligations",),
        ),
    }
    return contracts.get(
        operation,
        (
            ("the operation satisfies its declared Handler preconditions",),
            ("the operation satisfies its declared Handler postconditions",),
        ),
    )


_INVARIANTS = (
    HostInvariant(
        "HOST-REP-001",
        "Representation slots are opaque; the compiler does not choose Rc, Arc, Weak, Mutex, actor IDs, manager handles, transports, executors, or device APIs.",
    ),
    HostInvariant(
        "HOST-SHARE-001",
        "share maintains liveness and is explicitly cloneable, but does not grant mutation permission or direct memory access.",
    ),
    HostInvariant(
        "HOST-LINK-001",
        "link never maintains target liveness and resolution may fail.",
    ),
    HostInvariant(
        "HOST-IDENTITY-001",
        "Capability conversion and Resource transition preserve the symbolic identity declared by Glyph.",
    ),
    HostInvariant(
        "HOST-WORLD-001",
        "World bindings implement locus and Region semantics without prescribing a thread, executor, process, or device mechanism.",
    ),
    HostInvariant(
        "HOST-PROTOCOL-001",
        "Protocol bindings preserve the declared structured trace without prescribing channel, queue, shared-memory, network, or direct-call transport.",
    ),
    HostInvariant(
        "HOST-HANDLER-001",
        "Handler bindings preserve retry and recovery ledgers without prescribing a scheduler, timer, transaction engine, or compensation mechanism.",
    ),
    HostInvariant(
        "HOST-LAW-001",
        "Law bindings deliver canonical runtime events without prescribing the monitor implementation.",
    ),
)


def build_host_requirements(
    capabilities: CapabilityModel,
    runtime: ContractSemanticModel,
    resource_flow: ResourceFlowModel,
) -> HostRequirementModel:
    if not (
        capabilities.resources
        or capabilities.functions
        or capabilities.aggregates
        or capabilities.operations
        or runtime.worlds
        or runtime.protocols
        or runtime.handlers
        or runtime.laws
        or runtime.applications
        or resource_flow.transitions
    ):
        return HostRequirementModel.empty()

    builder = _Builder(capabilities, runtime, resource_flow)
    builder.collect_boundary_representations()
    builder.capability_operations()
    builder.resource_operations()
    builder.runtime_operations()
    return builder.finish()
