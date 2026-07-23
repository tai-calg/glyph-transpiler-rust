from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CapabilityKind, CapabilityModel
from .contract_semantics import ContractSemanticModel


@dataclass(frozen=True)
class VerificationItem:
    subject: str
    axis: str
    classes: tuple[str, ...]
    statement: str
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "axis": self.axis,
            "classes": list(self.classes),
            "statement": self.statement,
            "line": self.line,
        }


@dataclass(frozen=True)
class VerificationReport:
    items: tuple[VerificationItem, ...]

    @classmethod
    def empty(cls) -> "VerificationReport":
        return cls(())

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for item in self.items:
            for verification_class in item.classes:
                counts[verification_class] = counts.get(verification_class, 0) + 1
        return {
            "schema": "glyph.verification-report",
            "version": 1,
            "summary": counts,
            "items": [item.to_dict() for item in self.items],
        }


def _classes(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split("+") if part)


def build_verification_report(
    capabilities: CapabilityModel,
    runtime: ContractSemanticModel,
) -> VerificationReport:
    items: list[VerificationItem] = []

    for resource in capabilities.resources:
        items.append(
            VerificationItem(
                resource.name,
                "resource",
                ("static",),
                "state membership and capability-qualified use are checked",
                resource.line,
            )
        )
        items.append(
            VerificationItem(
                resource.name,
                "resource",
                ("trusted",),
                "physical allocation, release, and driver behavior remain Host obligations",
                resource.line,
            )
        )

    for function in capabilities.functions:
        if any(param.type.capability is not CapabilityKind.PLAIN for param in function.params):
            items.append(
                VerificationItem(
                    function.name,
                    "capability",
                    ("static",),
                    "move, borrow, capability conversion, and resource obligations are checked",
                    function.line,
                )
            )

    if any(
        param.type.capability is CapabilityKind.LINK
        for function in capabilities.functions
        for param in function.params
    ):
        items.append(
            VerificationItem(
                "link resolution",
                "capability",
                ("static", "trusted"),
                "resolution failure is represented statically; liveness is supplied by the Host adapter",
            )
        )

    for world in runtime.worlds:
        items.append(
            VerificationItem(
                world.name,
                "world",
                ("static",),
                "affinity crossings and Region containment are checked in the Glyph call/value graph",
                world.line,
            )
        )
        items.append(
            VerificationItem(
                world.name,
                "world",
                ("trusted",),
                f"Host must dispatch on locus {world.locus} and close Region {'/'.join(world.region)}",
                world.line,
            )
        )

    for protocol in runtime.protocols:
        items.append(
            VerificationItem(
                protocol.name,
                "protocol",
                ("static",),
                "protocol syntax, composition, signature compatibility, and borrowed cross-World transfer are checked",
                protocol.line,
            )
        )
        items.append(
            VerificationItem(
                protocol.name,
                "protocol",
                ("trusted",),
                "Host transport must preserve the declared send/receive trace",
                protocol.line,
            )
        )

    for handler in runtime.handlers:
        for step in handler.steps:
            items.append(
                VerificationItem(
                    f"{handler.name}.{step.operation}",
                    "handler",
                    _classes(step.verification),
                    "Handler operation after Contract expansion",
                    step.line,
                )
            )

    for law in runtime.laws:
        items.append(
            VerificationItem(
                law.name,
                "law",
                _classes(law.verification),
                "temporal Law verification class",
                law.line,
            )
        )

    for application in runtime.applications:
        items.append(
            VerificationItem(
                application.target,
                "application",
                ("static",),
                "Bundle expansion and kind conflicts are checked at this application place",
                application.line,
            )
        )

    return VerificationReport(tuple(items))
