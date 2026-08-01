from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from ..artifacts import CompilationModel
from ..state_machine_source_map import canonical_machine_source_line
from .machine_relation import EdgeSpec, MachineRelation, build_machine_relation


VIEW_EDGE_SPECIALIZATION_VERSION = 3


class ViewEdgeBindingStatus(str, Enum):
    EXACT = "exact"
    SYNTHESIZED_FAILURE = "synthesized-failure"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"


@dataclass(frozen=True)
class ViewEdgeBinding:
    view_edge_id: str
    relation_edge_id: str | None
    status: ViewEdgeBindingStatus
    source_state: str
    target_state: str
    source_line: int
    candidate_relation_edges: tuple[str, ...] = ()

    @property
    def analysis_edge_id(self) -> str | None:
        return self.relation_edge_id

    def to_ir(self) -> dict[str, object]:
        return {
            "version": VIEW_EDGE_SPECIALIZATION_VERSION,
            "view_edge_id": self.view_edge_id,
            "relation_edge_id": self.relation_edge_id,
            "status": self.status.value,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "source_line": self.source_line,
            "candidate_relation_edges": list(self.candidate_relation_edges),
        }


def specialize_view_edges(
    model: CompilationModel,
    machine_view: Mapping[str, object],
) -> tuple[ViewEdgeBinding, ...]:
    relation = build_machine_relation(model, str(machine_view.get("name") or ""))
    transitions = _mappings(machine_view.get("transitions"))
    view_ids = tuple(
        _view_edge_id(index, transition)
        for index, transition in enumerate(transitions)
    )
    duplicate_view_ids = {
        view_id
        for view_id, count in Counter(view_ids).items()
        if count > 1
    }
    bindings: list[ViewEdgeBinding] = []
    for index, transition in enumerate(transitions):
        if view_ids[index] in duplicate_view_ids:
            bindings.append(_ambiguous_identity(model, index, transition))
        elif relation is None:
            bindings.append(_unmapped(model, index, transition))
        else:
            bindings.append(_bind_transition(model, relation, index, transition))
    return tuple(bindings)


def attach_view_edge_specialization(
    model: CompilationModel,
    machine_view: Mapping[str, object],
) -> dict[str, object]:
    result = deepcopy(dict(machine_view))
    original_transitions = _mappings(result.get("transitions"))
    bindings = specialize_view_edges(model, result)
    transitions: list[dict[str, object]] = []
    for original, binding in zip(original_transitions, bindings, strict=True):
        transition = dict(original)
        transition["rtai_view_edge_specialization"] = binding.to_ir()
        transitions.append(transition)

    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "rtai_view_edge_specialization_version": (
                VIEW_EDGE_SPECIALIZATION_VERSION
            ),
            "rtai_view_edge_exact_binding_count": sum(
                item.status
                in {
                    ViewEdgeBindingStatus.EXACT,
                    ViewEdgeBindingStatus.SYNTHESIZED_FAILURE,
                }
                for item in bindings
            ),
            "rtai_view_edge_ambiguous_binding_count": sum(
                item.status is ViewEdgeBindingStatus.AMBIGUOUS
                for item in bindings
            ),
            "rtai_view_edge_unmapped_count": sum(
                item.status is ViewEdgeBindingStatus.UNMAPPED
                for item in bindings
            ),
        }
    )
    result["transitions"] = transitions
    result["rtai_view_edge_specialization"] = {
        "version": VIEW_EDGE_SPECIALIZATION_VERSION,
        "bindings": [item.to_ir() for item in bindings],
    }
    result["analysis"] = analysis
    return result


def _bind_transition(
    model: CompilationModel,
    relation: MachineRelation,
    index: int,
    transition: Mapping[str, object],
) -> ViewEdgeBinding:
    view_id = _view_edge_id(index, transition)
    source_state = str(transition.get("source_state") or "")
    target_state = str(transition.get("target_state") or "")
    source_line = canonical_machine_source_line(model, _source_line(transition))
    synthesized_failure = bool(transition.get("synthesized_failure"))
    candidates = tuple(
        edge
        for edge in relation.edges
        if canonical_machine_source_line(model, edge.source_line) == source_line
        and (
            synthesized_failure
            or _target_matches(edge, source_state, target_state)
        )
    )
    candidate_ids = tuple(edge.edge_id for edge in candidates)

    if len(candidates) == 1:
        status = (
            ViewEdgeBindingStatus.SYNTHESIZED_FAILURE
            if synthesized_failure
            else ViewEdgeBindingStatus.EXACT
        )
        return ViewEdgeBinding(
            view_id,
            candidates[0].edge_id,
            status,
            source_state,
            target_state,
            source_line,
            candidate_ids,
        )
    if len(candidates) > 1:
        return ViewEdgeBinding(
            view_id,
            None,
            ViewEdgeBindingStatus.AMBIGUOUS,
            source_state,
            target_state,
            source_line,
            candidate_ids,
        )
    return ViewEdgeBinding(
        view_id,
        None,
        ViewEdgeBindingStatus.UNMAPPED,
        source_state,
        target_state,
        source_line,
        (),
    )


def _target_matches(
    edge: EdgeSpec,
    source_state: str,
    target_state: str,
) -> bool:
    if edge.target_state == "__same__":
        return target_state == source_state
    return edge.target_state == target_state


def _ambiguous_identity(
    model: CompilationModel,
    index: int,
    transition: Mapping[str, object],
) -> ViewEdgeBinding:
    return ViewEdgeBinding(
        _view_edge_id(index, transition),
        None,
        ViewEdgeBindingStatus.AMBIGUOUS,
        str(transition.get("source_state") or ""),
        str(transition.get("target_state") or ""),
        canonical_machine_source_line(model, _source_line(transition)),
        (),
    )


def _unmapped(
    model: CompilationModel,
    index: int,
    transition: Mapping[str, object],
) -> ViewEdgeBinding:
    return ViewEdgeBinding(
        _view_edge_id(index, transition),
        None,
        ViewEdgeBindingStatus.UNMAPPED,
        str(transition.get("source_state") or ""),
        str(transition.get("target_state") or ""),
        canonical_machine_source_line(model, _source_line(transition)),
        (),
    )


def _view_edge_id(index: int, transition: Mapping[str, object]) -> str:
    return str(transition.get("id") or transition.get("edge_id") or f"T{index + 1}")


def _source_line(transition: Mapping[str, object]) -> int:
    source = _mapping(transition.get("source"))
    try:
        return int(source.get("line") or 0)
    except (TypeError, ValueError):
        return 0


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
