from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ApproximationKind(str, Enum):
    """解析結果が具体意味論をどの精度で表すか。"""

    EXACT = "exact"
    OVER_APPROXIMATE = "over-approximate"
    UNKNOWN = "unknown"


class ApproximationCause(str, Enum):
    """精度を失った理由。原因は消去せず、後段へ単調に伝播させる。"""

    LEGACY_ADAPTER = "legacy-adapter"
    LEGACY_UNRESOLVED = "legacy-unresolved"
    PARTITION_MERGE = "partition-merge"
    WIDENING = "widening"
    RESOURCE_LIMIT = "resource-limit"
    SOLVER_UNKNOWN = "solver-unknown"
    UNSUPPORTED_EXPRESSION = "unsupported-expression"
    UNKNOWN_EFFECT_RESULT = "unknown-effect-result"
    UNKNOWN_EFFECT_FOOTPRINT = "unknown-effect-footprint"
    RECURSIVE_SUMMARY_LIMIT = "recursive-summary-limit"
    MUTABLE_ALIAS = "mutable-alias"
    CONTEXT_MERGE = "context-merge"


class ExactnessProofKind(str, Enum):
    """Exactを構築できる根拠の生成方式。"""

    STRUCTURAL_IDENTITY = "structural-identity"
    LOWERING_EQUIVALENCE = "lowering-equivalence"
    EXHAUSTIVE_FINITE_ORACLE = "exhaustive-finite-oracle"
    SOLVER_CERTIFICATE = "solver-certificate"


class ExactnessProofScope(str, Enum):
    """証拠が保証する性質。別の性質へ流用してはならない。"""

    STRUCTURAL = "structural"
    LOWERING = "lowering"
    MACHINE_RELATION = "machine-relation"
    TEIR_EXECUTION = "teir-execution"
    REACHABILITY = "reachability"
    CARDINALITY = "cardinality"
    EFFECT_TRACE = "effect-trace"
    COMPLETION = "completion"


@dataclass(frozen=True)
class ExactnessProof:
    kind: ExactnessProofKind
    scope: ExactnessProofScope
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValueError("Exactness proof detail must not be empty")

    def to_ir(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "scope": self.scope.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Approximation:
    """精度情報。

    Exactは明示的な証拠を必須とする。OverApproximateまたはUnknownへ一度
    劣化した値は、正規化やjoinによってExactへ戻らない。
    """

    kind: ApproximationKind
    causes: tuple[str, ...] = ()
    proofs: tuple[ExactnessProof, ...] = ()

    def __post_init__(self) -> None:
        normalized_causes = tuple(sorted(set(self.causes)))
        object.__setattr__(self, "causes", normalized_causes)
        if self.kind is ApproximationKind.EXACT:
            if self.causes:
                raise ValueError("Exact approximation must not contain loss causes")
            if not self.proofs:
                raise ValueError("Exact approximation requires explicit proof evidence")
        elif self.proofs:
            raise ValueError("Non-exact approximation must not retain exactness proofs")

    @classmethod
    def exact(cls, *proofs: ExactnessProof) -> "Approximation":
        if not proofs:
            raise ValueError("Exact approximation requires at least one proof")
        return cls(ApproximationKind.EXACT, proofs=tuple(proofs))

    @classmethod
    def over_approximate(
        cls,
        *causes: str | ApproximationCause,
    ) -> "Approximation":
        normalized = _normalize_causes(causes)
        if not normalized:
            raise ValueError("Over-approximation requires at least one cause")
        return cls(ApproximationKind.OVER_APPROXIMATE, causes=normalized)

    @classmethod
    def unknown(
        cls,
        *causes: str | ApproximationCause,
    ) -> "Approximation":
        normalized = _normalize_causes(causes)
        if not normalized:
            raise ValueError("Unknown approximation requires at least one cause")
        return cls(ApproximationKind.UNKNOWN, causes=normalized)

    @property
    def is_exact(self) -> bool:
        return self.kind is ApproximationKind.EXACT

    def degrade(
        self,
        cause: str | ApproximationCause,
        *,
        unknown: bool = False,
    ) -> "Approximation":
        """精度を安全方向へだけ劣化させる。Exactへの回復は提供しない。"""

        cause_text = _cause_text(cause)
        causes = (*self.causes, cause_text)
        if unknown or self.kind is ApproximationKind.UNKNOWN:
            return Approximation.unknown(*causes)
        return Approximation.over_approximate(*causes)

    @classmethod
    def combine(cls, values: Iterable["Approximation"]) -> "Approximation":
        """複数の解析結果をjoinするときの精度を計算する。"""

        items = tuple(values)
        if not items:
            raise ValueError("Cannot combine an empty approximation sequence")
        causes = tuple(cause for item in items for cause in item.causes)
        if any(item.kind is ApproximationKind.UNKNOWN for item in items):
            return cls.unknown(*causes)
        if any(item.kind is ApproximationKind.OVER_APPROXIMATE for item in items):
            return cls.over_approximate(*causes)
        proofs = tuple(proof for item in items for proof in item.proofs)
        return cls.exact(*proofs)

    def to_ir(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "causes": list(self.causes),
            "proofs": [proof.to_ir() for proof in self.proofs],
        }


def _cause_text(cause: str | ApproximationCause) -> str:
    return cause.value if isinstance(cause, ApproximationCause) else str(cause)


def _normalize_causes(
    causes: Iterable[str | ApproximationCause],
) -> tuple[str, ...]:
    return tuple(sorted({_cause_text(cause) for cause in causes if _cause_text(cause)}))
