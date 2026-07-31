from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from ..artifacts import CompilationModel
from .analysis_evidence import VerifiedReachabilityWitness
from .concrete import ConstructorValue, ResultValue, VariantValue
from .effect_contract import VerifiedEffectContractRegistry
from .machine_relation import build_machine_relation
from .program_identity import RTAI_SEMANTIC_KERNEL_VERSION
from .witness_generation import (
    BoundedWitnessGenerationReport,
    GeneratedWitness,
)


WITNESS_BINDING_VERSION = 1


@dataclass(frozen=True)
class WitnessBinding:
    program_fingerprint: str
    edge_fingerprint: str
    contract_digest: str
    interpreter_version: str
    input_digest: str

    def to_ir(self) -> dict[str, object]:
        return {
            "version": WITNESS_BINDING_VERSION,
            "program_fingerprint": self.program_fingerprint,
            "edge_fingerprint": self.edge_fingerprint,
            "contract_digest": self.contract_digest,
            "interpreter_version": self.interpreter_version,
            "input_digest": self.input_digest,
        }


@dataclass(frozen=True)
class BoundReachabilityWitness:
    witness: VerifiedReachabilityWitness
    binding: WitnessBinding

    @property
    def edge_id(self) -> str:
        return self.witness.edge_id

    @property
    def arguments(self) -> tuple[object, ...]:
        return self.witness.arguments

    @property
    def completion(self) -> str:
        return self.witness.completion

    @property
    def transition_edges(self) -> tuple[str, ...]:
        return self.witness.transition_edges

    @property
    def source(self) -> str:
        return self.witness.source

    def to_ir(self) -> dict[str, object]:
        result = self.witness.to_ir()
        result["binding"] = self.binding.to_ir()
        result["arguments"] = [typed_concrete_value_ir(item) for item in self.arguments]
        return result


@dataclass(frozen=True)
class BoundGeneratedWitness:
    generated: GeneratedWitness
    witness: BoundReachabilityWitness

    @property
    def entry(self) -> str:
        return self.generated.entry

    @property
    def edge_id(self) -> str:
        return self.generated.edge_id

    @property
    def completion(self) -> str:
        return self.generated.completion

    @property
    def generation_strategy(self) -> str:
        return self.generated.generation_strategy

    @property
    def case_source(self) -> str | None:
        return self.generated.case_source

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "edge_id": self.edge_id,
            "completion": self.completion,
            "generation_strategy": self.generation_strategy,
            "case_source": self.case_source,
            "binding": self.witness.binding.to_ir(),
            "witness": self.witness.to_ir(),
        }


@dataclass(frozen=True)
class BoundWitnessGenerationReport:
    base: BoundedWitnessGenerationReport
    program_fingerprint: str
    contract_digest: str
    witnesses: tuple[BoundGeneratedWitness, ...]

    @property
    def entries(self) -> tuple[str, ...]:
        return self.base.entries

    @property
    def max_cases_per_entry(self) -> int:
        return self.base.max_cases_per_entry

    @property
    def attempted_case_count(self) -> int:
        return self.base.attempted_case_count

    @property
    def completed_case_count(self) -> int:
        return self.base.completed_case_count

    @property
    def issues(self):  # type: ignore[no-untyped-def]
        return self.base.issues

    @property
    def entry_coverage(self):  # type: ignore[no-untyped-def]
        return self.base.entry_coverage

    @property
    def complete(self) -> bool:
        return self.base.complete and len(self.witnesses) == len(self.base.witnesses)

    @property
    def exhaustive(self) -> bool:
        return self.complete and self.base.exhaustive

    def witness_for(
        self,
        entry: str,
        edge_id: str,
        completion_filter: frozenset[str] | None = None,
    ) -> BoundReachabilityWitness | None:
        for item in self.witnesses:
            if item.entry != entry or item.edge_id != edge_id:
                continue
            if completion_filter is not None and item.completion not in completion_filter:
                continue
            return item.witness
        return None

    def to_ir(self) -> dict[str, object]:
        result = self.base.to_ir()
        result.update(
            {
                "binding_version": WITNESS_BINDING_VERSION,
                "program_fingerprint": self.program_fingerprint,
                "contract_digest": self.contract_digest,
                "complete": self.complete,
                "exhaustive": self.exhaustive,
                "witnesses": [item.to_ir() for item in self.witnesses],
            }
        )
        return result


def bind_witness_generation_report(
    report: BoundedWitnessGenerationReport,
    model: CompilationModel,
    contracts: VerifiedEffectContractRegistry,
) -> BoundWitnessGenerationReport:
    program_fingerprint = runtime_program_fingerprint(model)
    contract_digest = canonical_digest(contracts.to_ir())
    edge_fingerprints = relation_edge_fingerprints(model)
    bound: list[BoundGeneratedWitness] = []
    for generated in report.witnesses:
        edge_fingerprint = edge_fingerprints.get(generated.edge_id)
        if edge_fingerprint is None:
            continue
        binding = WitnessBinding(
            program_fingerprint=program_fingerprint,
            edge_fingerprint=edge_fingerprint,
            contract_digest=contract_digest,
            interpreter_version="teir-concrete-v1",
            input_digest=canonical_digest(
                [typed_concrete_value_ir(item) for item in generated.witness.arguments]
            ),
        )
        bound.append(
            BoundGeneratedWitness(
                generated,
                BoundReachabilityWitness(generated.witness, binding),
            )
        )
    return BoundWitnessGenerationReport(
        report,
        program_fingerprint,
        contract_digest,
        tuple(bound),
    )


def runtime_program_fingerprint(model: CompilationModel) -> str:
    return canonical_digest(
        {
            "kernel": RTAI_SEMANTIC_KERNEL_VERSION,
            "compiler_input_sha256": hashlib.sha256(
                model.preprocess.source.encode("utf-8")
            ).hexdigest(),
            "relations": relation_edge_fingerprints(model),
        }
    )


def relation_edge_fingerprints(model: CompilationModel) -> dict[str, str]:
    result: dict[str, str] = {}
    for machine in sorted(model.machines, key=lambda item: item.name):
        relation = build_machine_relation(model, machine.name)
        if relation is None:
            continue
        for edge in relation.edges:
            result[edge.edge_id] = canonical_digest(
                {
                    "machine": relation.machine_id,
                    "transition_function": relation.transition_function,
                    "formals": list(relation.formals),
                    "ordinal": edge.ordinal,
                    "effective_guard": repr(edge.effective_guard),
                    "result_expression": repr(edge.result_expression),
                    "target_state": edge.target_state,
                    "completion": edge.completion,
                }
            )
    return result


def typed_concrete_value_ir(value: object) -> object:
    if value is None:
        return {"kind": "none"}
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"kind": "int", "value": str(value)}
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite concrete witness values are unsupported")
        return {"kind": "float", "value": value.hex()}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, ConstructorValue):
        return {
            "kind": "constructor",
            "type": value.type_name,
            "fields": [
                {"name": name, "value": typed_concrete_value_ir(item)}
                for name, item in value.fields
            ],
        }
    if isinstance(value, VariantValue):
        return {
            "kind": "variant",
            "name": value.name,
            "arguments": [typed_concrete_value_ir(item) for item in value.arguments],
        }
    if isinstance(value, ResultValue):
        return {
            "kind": "result",
            "success": value.success,
            "value": typed_concrete_value_ir(value.value),
        }
    if isinstance(value, tuple):
        return {"kind": "tuple", "items": [typed_concrete_value_ir(item) for item in value]}
    if isinstance(value, list):
        return {"kind": "list", "items": [typed_concrete_value_ir(item) for item in value]}
    if isinstance(value, Mapping):
        return {
            "kind": "mapping",
            "items": [
                {
                    "key": typed_concrete_value_ir(key),
                    "value": typed_concrete_value_ir(item),
                }
                for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
            ],
        }
    raise TypeError(f"unsupported concrete witness value: {type(value).__name__}")


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "WITNESS_BINDING_VERSION",
    "BoundGeneratedWitness",
    "BoundReachabilityWitness",
    "BoundWitnessGenerationReport",
    "WitnessBinding",
    "bind_witness_generation_report",
    "canonical_digest",
    "relation_edge_fingerprints",
    "runtime_program_fingerprint",
    "typed_concrete_value_ir",
]
