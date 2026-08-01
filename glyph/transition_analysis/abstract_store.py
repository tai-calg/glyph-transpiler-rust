from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .abstract_value import AbstractValue, BottomValue, TopValue, join_values
from .exactness import (
    Approximation,
    ApproximationCause,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)


@dataclass(frozen=True, order=True)
class AbstractLocation:
    kind: str
    key: str


@dataclass(frozen=True)
class AbstractAddress:
    locations: frozenset[AbstractLocation]
    singleton_proven: bool = False

    def __post_init__(self) -> None:
        if self.singleton_proven and len(self.locations) != 1:
            raise ValueError("singleton proof requires exactly one abstract location")


@dataclass(frozen=True)
class AbstractStore:
    bindings: tuple[tuple[AbstractLocation, AbstractValue], ...]
    approximation: Approximation

    @classmethod
    def empty(cls) -> "AbstractStore":
        proof = ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.STRUCTURAL,
            "empty abstract store",
        )
        return cls((), Approximation.exact(proof))

    @property
    def mapping(self) -> dict[AbstractLocation, AbstractValue]:
        return dict(self.bindings)

    def read(self, address: AbstractAddress) -> AbstractValue:
        if not address.locations:
            return TopValue("empty-address")
        values = [self.mapping.get(location, BottomValue()) for location in address.locations]
        result = values[0]
        for value in values[1:]:
            result = join_values(result, value)
        return result

    def write(
        self,
        address: AbstractAddress,
        value: AbstractValue,
    ) -> "AbstractStore":
        """Use strong update only for a proven singleton address."""

        if not address.locations:
            return AbstractStore(
                self.bindings,
                self.approximation.degrade(
                    ApproximationCause.MUTABLE_ALIAS,
                    unknown=True,
                ),
            )
        approximation = self.approximation
        if isinstance(value, TopValue):
            approximation = approximation.degrade(value.reason, unknown=True)
        updated = self.mapping
        if address.singleton_proven:
            location = next(iter(address.locations))
            updated[location] = value
            return AbstractStore(_freeze(updated), approximation)
        for location in address.locations:
            updated[location] = join_values(
                updated.get(location, BottomValue()),
                value,
            )
        return AbstractStore(
            _freeze(updated),
            approximation.degrade(ApproximationCause.MUTABLE_ALIAS),
        )

    def havoc(
        self,
        locations: Iterable[AbstractLocation],
        *,
        reason: str,
    ) -> "AbstractStore":
        targets = tuple(locations)
        if not targets:
            return self
        updated = self.mapping
        for location in targets:
            updated[location] = TopValue(reason)
        return AbstractStore(
            _freeze(updated),
            self.approximation.degrade(reason, unknown=True),
        )

    def join(self, other: "AbstractStore") -> "AbstractStore":
        left = self.mapping
        right = other.mapping
        locations = set(left) | set(right)
        joined = {
            location: join_values(
                left.get(location, BottomValue()),
                right.get(location, BottomValue()),
            )
            for location in locations
        }
        approximation = Approximation.combine(
            (self.approximation, other.approximation)
        )
        if self.bindings != other.bindings and approximation.is_exact:
            approximation = approximation.degrade("store-join")
        return AbstractStore(_freeze(joined), approximation)


def _freeze(
    mapping: Mapping[AbstractLocation, AbstractValue],
) -> tuple[tuple[AbstractLocation, AbstractValue], ...]:
    return tuple(sorted(mapping.items(), key=lambda item: item[0]))
