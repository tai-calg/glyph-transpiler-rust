from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable

from .capabilities import CapabilityKind, CapabilityModel, CapabilityType
from .contract_semantics import ContractSemanticModel, ProtocolNode
from .resource_flow import ResourceEndpoint, ResourceFlowModel
from .schema import HOST_REQUIREMENTS_IR_SCHEMA, IR_SCHEMA_VERSION


def _pascal(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    rendered = "".join(part[:1].upper() + part[1:] for part in parts)
    return rendered or "Value"


@dataclass(frozen=True)
class HostTypeRef:
    name: str
    capability: str = "plain"
    state: str | None = None
    arguments: tuple["HostTypeRef", ...] = ()

    @classmethod
    def from_capability(cls, value: CapabilityType) -> "HostTypeRef":
        return cls(
            value.name,
            value.capability.value,
            value.state,
            tuple(cls.from_capability(argument) for argument in value.args),
        )

    @classmethod
    def from_endpoint(cls, value: ResourceEndpoint) -> "HostTypeRef":
        return cls(value.resource, value.capability, value.state)

    def key(self) -> str:
        arguments = ""
        if self.arguments:
            arguments = "<" + ",".join(argument.key() for argument in self.arguments) + ">"
        state = "" if self.state is None else f"[{self.state}]"
        return f"{self.capability}:{self.name}{arguments}{state}"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "capability": self.capability,
            "state": self.state,
            "arguments": [argument.to_dict() for argument in self.arguments],
        }


@dataclass(frozen=True)
class RepresentationSlot:
    id: str
    associated_type: str
    type: HostTypeRef
    world: str | None
    origins: tuple[str, ...]
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "associated_type": self.associated_type,
            "type": self.type.to_dict(),
            "world": self.world,
            "origins": list(self.origins),
            "line": self.line,
        }


@dataclass(frozen=True)
class HostPort:
    name: str
    type: HostTypeRef
    representation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type.to_dict(),
            "representation": self.representation,
        }


@dataclass(frozen=True)
class HostOperationRequirement:
    id: str
    kind: str
    subject: str
    contract: str | None
    inputs: tuple[HostPort, ...]
    outputs: tuple[HostPort, ...]
    attributes: tuple[tuple[str, str], ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    may_fail: bool
    verification_classes: tuple[str, ...]
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "subject": self.subject,
            "contract": self.contract,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "attributes": {key: value for key, value in self.attributes},
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "may_fail": self.may_fail,
            "verification_classes": list(self.verification_classes),
            "line": self.line,
        }


@dataclass(frozen=True)
class HostInvariant:
    id: str
    statement: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "statement": self.statement}


@dataclass(frozen=True)
class HostRequirementModel:
    representations: tuple[RepresentationSlot, ...] = ()
    operations: tuple[HostOperationRequirement, ...] = ()
    invariants: tuple[HostInvariant, ...] = ()

    @classmethod
    def empty(cls) -> "HostRequirementModel":
        return cls()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": HOST_REQUIREMENTS_IR_SCHEMA,
            "version": IR_SCHEMA_VERSION,
            "representations": [item.to_dict() for item in self.representations],
            "operations": [item.to_dict() for item in self.operations],
            "invariants": [item.to_dict() for item in self.invariants],
        }


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
    ) -> str | None:
        if ty.capability not in {"own", "share", "link"}:
            return None
        key = f"{ty.key()}@{world or '_'}"
        slot_id = "repr:" + key
        current = self._slots.get(slot_id)
        if current is not None:
            if origin not in current.origins:
                self._slots[slot_id] = RepresentationSlot(
                    current.id,
                    current.associated_type,
                    current.type,
                    current.world,
                    (*current.origins, origin),
                    current.line if current.line is not None else line,
                )
            return slot_id
        digest = hashlib.sha1(slot_id.encode("utf-8")).hexdigest()[:8]
        associated = (
            "Repr"
            + _pascal(ty.capability)
            + _pascal(ty.name)
            + ("" if ty.state is None else _pascal(ty.state))
            + ("" if world is None else _pascal(world))
            + digest.upper()
        )
        self._slots[slot_id] = RepresentationSlot(
            slot_id,
            associated,
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
    ) -> HostPort:
        return HostPort(name, ty, self._slot(ty, world, origin, line))

    def _walk_type(
        self,
        ty: CapabilityType,
        world: str | None,
        origin: str,
        line: int | None,
    ) -> None:
        ref = HostTypeRef.from_capability(ty)
        self._slot(ref, world, origin, line)
        for argument in ty.args:
            self._walk_type(argument, world, origin, line)

    def collect_representations(self) -> None:
        for function in self.capabilities.functions:
            application = self._applications.get(function.name)
            world = None if application is None else application.row.world
            for parameter in function.params:
                self._walk_type(
                    parameter.type,
                    world,
                    f"function:{function.name}:param:{parameter.name}",
                    parameter.line,
                )
            self._walk_type(
                function.result,
                world,
                f"function:{function.name}:result",
                function.line,
            )
        for aggregate in self.capabilities.aggregates:
            for index, member in enumerate(aggregate.members):
                self._walk_type(
                    member,
                    None,
                    f"aggregate:{aggregate.name}:member:{index}",
                    aggregate.line,
                )

    def capability_operations(self) -> None:
        by_function: dict[str, dict[str, CapabilityType]] = {}
        for function in self.capabilities.functions:
            by_function[function.name] = {
                parameter.name: parameter.type for parameter in function.params
            }

        counts: dict[tuple[str, str], int] = {}
        for operation in self.capabilities.operations:
            env = by_function.setdefault(operation.function, {})
            source_name = operation.source
            if operation.kind == "move":
                if source_name is not None and operation.target is not None:
                    source_ty = env.get(source_name)
                    if source_ty is not None:
                        env[operation.target] = source_ty
                continue
            if operation.kind != "capability_cast" or source_name is None:
                continue

            source_ty = env.get(source_name)
            if source_ty is None:
                source_ty = env.get(source_name.split(".", 1)[0])
            if source_ty is None or operation.capability is None:
                continue
            target_kind = CapabilityKind(operation.capability)
            target_ty = CapabilityType(
                target_kind,
                source_ty.name,
                source_ty.args,
                source_ty.state,
                source_ty.raw,
            )
            if operation.target is not None:
                env[operation.target] = target_ty

            mapping = {
                (CapabilityKind.OWN, CapabilityKind.SHARE): "publish",
                (CapabilityKind.SHARE, CapabilityKind.SHARE): "clone_share",
                (CapabilityKind.SHARE, CapabilityKind.LINK): "downgrade",
                (CapabilityKind.LINK, CapabilityKind.LINK): "clone_link",
                (CapabilityKind.LINK, CapabilityKind.SHARE): "resolve_link",
            }
            kind = mapping.get((source_ty.capability, target_kind))
            if kind is None:
                continue

            application = self._applications.get(operation.function)
            world = None if application is None else application.row.world
            key = (operation.function, kind)
            index = counts.get(key, 0)
            counts[key] = index + 1
            source_ref = HostTypeRef.from_capability(source_ty)
            target_ref = HostTypeRef.from_capability(target_ty)
            input_port = self._port(
                "value",
                source_ref,
                world,
                f"operation:{operation.function}:{kind}:input",
                operation.line,
            )
            output_port = self._port(
                "value",
                target_ref,
                world,
                f"operation:{operation.function}:{kind}:output",
                operation.line,
            )
            pre, post, may_fail = _capability_contract(kind)
            self.operations.append(
                HostOperationRequirement(
                    f"cap:{operation.function}:{kind}:{index}",
                    kind,
                    operation.function,
                    None,
                    (input_port,),
                    (output_port,),
                    (),
                    pre,
                    post,
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
            key = (transition.function, transition.kind)
            index = counts.get(key, 0)
            counts[key] = index + 1
            inputs: tuple[HostPort, ...] = ()
            if transition.source is not None:
                source_ref = HostTypeRef.from_endpoint(transition.source)
                inputs = (
                    self._port(
                        "source",
                        source_ref,
                        world,
                        f"resource:{transition.function}:{transition.identity}:source",
                        transition.line,
                    ),
                )
            target_ref = HostTypeRef.from_endpoint(transition.target)
            outputs = (
                self._port(
                    "target",
                    target_ref,
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
                world = self._worlds[row.world]
                self.operations.append(
                    HostOperationRequirement(
                        f"world:{application.target}:{row.world}",
                        "world_scope",
                        application.target,
                        row.world,
                        (),
                        (),
                        (
                            ("locus", world.locus),
                            ("region", "/".join(world.region)),
                            ("target_kind", application.target_kind),
                        ),
                        (
                            f"execution begins in locus {world.locus}",
                            f"Region {'/'.join(world.region)} is entered before the target runs",
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

            if row.protocol is not None:
                protocol = self._protocols[row.protocol]
                for step, node in enumerate(_protocol_events(protocol.root)):
                    assert node.type_name is not None
                    ty = HostTypeRef(node.type_name)
                    inputs = (HostPort("value", ty, None),) if node.kind == "send" else ()
                    outputs = (HostPort("value", ty, None),) if node.kind == "receive" else ()
                    self.operations.append(
                        HostOperationRequirement(
                            f"protocol:{application.target}:{row.protocol}:{step}",
                            f"protocol_{node.kind}",
                            application.target,
                            row.protocol,
                            inputs,
                            outputs,
                            (("step", str(step)), ("type", node.type_name)),
                            (f"all protocol steps before step {step} have completed",),
                            (f"the {node.kind} event is appended to the declared trace without reordering",),
                            True,
                            ("static", "trusted"),
                            application.line,
                        )
                    )

            if row.handler is not None:
                handler = self._handlers[row.handler]
                for index, step in enumerate(handler.steps):
                    pre, post = _handler_contract(step.operation)
                    classes = tuple(item for item in step.verification.split("+") if item)
                    self.operations.append(
                        HostOperationRequirement(
                            f"handler:{application.target}:{row.handler}:{index}",
                            f"handler_{step.operation}",
                            application.target,
                            row.handler,
                            (),
                            (),
                            tuple((f"arg{argument_index}", argument) for argument_index, argument in enumerate(step.arguments)),
                            pre,
                            post,
                            True,
                            classes or ("trusted",),
                            step.line,
                        )
                    )

            for law_name in row.laws:
                law = self._laws[law_name]
                classes = tuple(item for item in law.verification.split("+") if item)
                self.operations.append(
                    HostOperationRequirement(
                        f"law:{application.target}:{law_name}",
                        "law_observe",
                        application.target,
                        law_name,
                        (),
                        (),
                        (("formula", json.dumps(law.formula, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),),
                        ("runtime events use the canonical Contract identity and target identity",),
                        ("events reach the monitor in execution order without being fabricated or dropped",),
                        False,
                        classes or ("runtime",),
                        application.line,
                    )
                )

    def finish(self) -> HostRequirementModel:
        return HostRequirementModel(
            tuple(sorted(self._slots.values(), key=lambda item: item.id)),
            tuple(self.operations),
            _INVARIANTS,
        )


def _protocol_events(node: ProtocolNode) -> Iterable[ProtocolNode]:
    if node.kind in {"send", "receive"}:
        yield node
    for child in node.children:
        yield from _protocol_events(child)


def _capability_contract(kind: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
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
            ("the resource reaches the declared recovery state or failure is reported",),
        ),
        "compensate": (
            ("the named compensation target is an effect boundary",),
            ("the compensation effect follows the declared ordering and failure policy",),
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
        "Protocol bindings preserve the declared trace without prescribing channel, queue, shared-memory, network, or direct-call transport.",
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
    builder.collect_representations()
    builder.capability_operations()
    builder.resource_operations()
    builder.runtime_operations()
    return builder.finish()
