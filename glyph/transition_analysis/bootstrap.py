from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from .._transition_branch_semantics import substitute_expr
from ..artifacts import CompilationModel
from ..compiler import Expr, NameExpr
from .lowering import lower_compilation_model
from .machine_relation import build_machine_relation
from .preimage import compute_transition_call_preimage
from .teir import Assign, EffectCall, Function, TransitionCall


RTAI_SEMANTIC_BOOTSTRAP_VERSION = 1


def attach_rtai_semantic_bootstrap(
    model: CompilationModel,
    machine_view: dict[str, object],
    *,
    functions: Mapping[str, Function] | None = None,
) -> dict[str, object]:
    """Publish additive TEIR/Relation data without changing UI projection."""

    result = deepcopy(machine_view)
    machine_name = str(result.get("name") or "")
    relation = build_machine_relation(model, machine_name)
    lowered = dict(functions) if functions is not None else lower_compilation_model(model)
    entry_names = frozenset(system.entry_name for system in model.systems)
    call_sites: list[dict[str, object]] = []
    if relation is not None:
        for function_name in sorted(entry_names):
            function = lowered.get(function_name)
            if function is None:
                continue
            for block in function.blocks:
                environment: dict[str, Expr] = {}
                for instruction in block.instructions:
                    if isinstance(instruction, Assign):
                        environment[instruction.target] = substitute_expr(
                            instruction.expression,
                            environment,
                        )
                        continue
                    if isinstance(instruction, EffectCall):
                        if instruction.target is not None:
                            environment[instruction.target] = NameExpr(instruction.target)
                        continue
                    if not isinstance(instruction, TransitionCall):
                        continue
                    actual_arguments = tuple(
                        substitute_expr(argument, environment)
                        for argument in instruction.arguments
                    )
                    if instruction.machine != relation.machine_id:
                        environment[instruction.target] = NameExpr(instruction.target)
                        continue
                    preimage = compute_transition_call_preimage(
                        model,
                        relation.machine_id,
                        actual_arguments,
                    )
                    call_sites.append(
                        {
                            "function": function_name,
                            "block_id": block.block_id,
                            "line": instruction.line,
                            "target": instruction.target,
                            "propagate_failure": instruction.propagate_failure,
                            "alias_resolution": "block-local",
                            "actual_arguments": [repr(item) for item in actual_arguments],
                            "preimage": preimage.to_ir() if preimage is not None else None,
                        }
                    )
                    environment[instruction.target] = NameExpr(instruction.target)

    relevant_functions = sorted(
        {
            *(entry_names & lowered.keys()),
            *(
                (relation.transition_function,)
                if relation is not None and relation.transition_function in lowered
                else ()
            ),
        }
    )
    bootstrap = {
        "version": RTAI_SEMANTIC_BOOTSTRAP_VERSION,
        "projection_source": False,
        "machine_relation": relation.to_ir() if relation is not None else None,
        "functions": [lowered[name].to_ir() for name in relevant_functions],
        "transition_call_preimages": call_sites,
    }
    analysis = dict(result.get("analysis", {}))
    analysis.update(
        {
            "rtai_semantic_bootstrap_version": RTAI_SEMANTIC_BOOTSTRAP_VERSION,
            "rtai_semantic_bootstrap_is_projection_source": False,
            "rtai_teir_function_count": len(relevant_functions),
            "rtai_transition_call_preimage_count": len(call_sites),
            "rtai_machine_relation_edge_count": (
                len(relation.edges) if relation is not None else 0
            ),
            "rtai_machine_relation_approximation": (
                relation.approximation.kind.value if relation is not None else "unknown"
            ),
        }
    )
    result["rtai_semantic_bootstrap"] = bootstrap
    result["analysis"] = analysis
    return result
