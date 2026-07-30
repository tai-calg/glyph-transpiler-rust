from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Sequence

from ..artifacts import CompilationModel
from .abstract_evidence_shadow import attach_rtai_abstract_execution_evidence
from .effect_contract import VerifiedEffectContractRegistry
from .evidence_projection import EvidenceProjectionMode, project_machine_from_evidence
from .native_projection_readiness import attach_native_evidence_projection_readiness
from .view_edge_specialization import attach_view_edge_specialization


STRICT_PROJECTION_CAMPAIGN_VERSION = 2


def build_strict_projection_candidate(
    model: CompilationModel,
    machine_view: Mapping[str, object],
    effect_contracts: VerifiedEffectContractRegistry,
    *,
    witness_max_cases: int = 4096,
) -> dict[str, object]:
    """Build a fail-closed native-Evidence projection candidate.

    This lower-level API accepts one already-normalized machine view. It disables
    legacy System Action fallback, retains Machine-owned actions, and publishes an
    explicit campaign report. The full-view builder below is the stronger campaign:
    it constructs the view through the strict pipeline and never runs the legacy
    System Action analyzer.
    """

    specialized = attach_view_edge_specialization(model, dict(machine_view))
    evidenced = attach_rtai_abstract_execution_evidence(
        model,
        specialized,
        effect_contracts=effect_contracts,
        witness_max_cases=witness_max_cases,
    )
    readiness = attach_native_evidence_projection_readiness(evidenced)
    projected = project_machine_from_evidence(
        readiness,
        mode=EvidenceProjectionMode.STRICT_EXACT,
        evidence_field="rtai_execution_evidence_v2",
    )

    result = deepcopy(projected)
    transitions: list[dict[str, object]] = []
    for original in _mappings(result.get("transitions")):
        transition = dict(original)
        strict_action = transition.get("evidence_display_action")
        _remove_legacy_system_projection(transition)
        transition["legacy_system_action_fallback_allowed"] = False
        transition["system_action"] = strict_action
        transition["strict_system_action"] = strict_action
        transition["strict_system_action_projection_source"] = (
            "rtai-execution-evidence-v2"
        )
        transitions.append(transition)

    report = _machine_campaign_report(result)
    analysis = dict(_mapping(result.get("analysis")))
    analysis.update(
        {
            "rtai_strict_projection_campaign_version": (
                STRICT_PROJECTION_CAMPAIGN_VERSION
            ),
            "rtai_strict_projection_campaign_ready": report["ready"],
            "rtai_strict_projection_legacy_fallback_enabled": False,
            "rtai_strict_projection_legacy_analyzer_enabled": None,
            "rtai_strict_projection_blocker_count": len(report["blockers"]),
        }
    )
    result["transitions"] = transitions
    result["strict_projection_campaign"] = report
    result["analysis"] = analysis
    return result


def build_strict_io_state_views(
    model: CompilationModel,
    execution: object,
    effect_contracts: VerifiedEffectContractRegistry,
    *,
    witness_max_cases: int = 4096,
) -> dict[str, object]:
    """Build complete views without executing the legacy System Action analyzer."""

    # Local imports avoid a package initialization cycle. These helpers own the
    # canonical raw I/O view projection; only the final state-transition enrichment
    # is selected as strict native Evidence.
    from ..compiler import AliasDecl, ExternDecl, FunctionDecl, ProductDecl, SumDecl
    from ..io_state_views import (
        IO_STATE_VIEWS_SCHEMA,
        IO_STATE_VIEWS_VERSION,
        _explicit_systems,
        _implicit_program,
        _signature,
        _source_external_names,
        _type_declaration,
        _unconnected_system,
    )
    from ..state_machine_analysis import analyze_machine
    from ..state_machine_source_map import remap_machine_analysis_source_lines
    from ..state_transition_pipeline import enrich_state_transition_ir

    external_names = _source_external_names(model)
    signatures = {
        declaration.name: _signature(declaration, external_names)
        for declaration in model.program.declarations
        if isinstance(declaration, (FunctionDecl, ExternDecl))
    }
    types = [
        _type_declaration(declaration)
        for declaration in model.program.declarations
        if isinstance(declaration, (ProductDecl, SumDecl, AliasDecl))
    ]
    systems, bound = _explicit_systems(model, signatures)
    if systems:
        unconnected = _unconnected_system(signatures, bound)
        if unconnected is not None:
            systems.append(unconnected)
    else:
        systems = [_implicit_program(execution, signatures)]

    raw_machines = [
        analyze_machine(model, machine)
        for machine in getattr(execution, "machines")
    ]
    raw_views = {
        "schema": IO_STATE_VIEWS_SCHEMA,
        "version": IO_STATE_VIEWS_VERSION,
        "source_name": getattr(execution, "source_name"),
        "summary": {
            "systems": len(systems),
            "callables": len(signatures),
            "types": len(types),
            "machines": len(raw_machines),
            "state_warnings": 0,
        },
        "io": {"systems": systems, "types": types},
        "state": {"machines": raw_machines},
    }
    result = enrich_state_transition_ir(
        model,
        raw_views,
        rtai_effect_contracts=effect_contracts,
        rtai_projection_mode=EvidenceProjectionMode.STRICT_EXACT,
        rtai_witness_max_cases=witness_max_cases,
    )
    if result.get("rtai_legacy_system_action_analyzer_enabled") is not False:
        raise AssertionError("strict pipeline executed the legacy System Action analyzer")

    state = dict(_mapping(result.get("state")))
    machines: list[dict[str, object]] = []
    machine_reports: list[dict[str, object]] = []
    for original in _mappings(state.get("machines")):
        machine = remap_machine_analysis_source_lines(model, dict(original))
        report = _machine_campaign_report(machine)
        analysis = dict(_mapping(machine.get("analysis")))
        analysis.update(
            {
                "rtai_strict_projection_campaign_version": (
                    STRICT_PROJECTION_CAMPAIGN_VERSION
                ),
                "rtai_strict_projection_campaign_ready": report["ready"],
                "rtai_strict_projection_legacy_fallback_enabled": False,
                "rtai_strict_projection_legacy_analyzer_enabled": False,
                "rtai_strict_projection_blocker_count": len(report["blockers"]),
            }
        )
        machine["strict_projection_campaign"] = report
        machine["analysis"] = analysis
        machines.append(machine)
        machine_reports.append({"machine": machine.get("name"), **report})

    ready = bool(machines) and all(
        report.get("ready") is True for report in machine_reports
    )
    blockers = [
        {"machine": report.get("machine"), **dict(blocker)}
        for report in machine_reports
        for blocker in _mappings(report.get("blockers"))
    ]
    state["machines"] = machines
    summary = dict(_mapping(result.get("summary")))
    summary["rtai_strict_projection_ready_machines"] = sum(
        report.get("ready") is True for report in machine_reports
    )
    summary["rtai_strict_projection_machine_count"] = len(machine_reports)
    summary["rtai_legacy_system_action_analyzer_enabled"] = False
    result["state"] = state
    result["summary"] = summary
    result["strict_projection_campaign"] = {
        "version": STRICT_PROJECTION_CAMPAIGN_VERSION,
        "ready": ready,
        "projection_source": "rtai-execution-evidence-v2",
        "legacy_fallback_allowed": False,
        "legacy_system_action_analyzer_enabled": False,
        "machines": machine_reports,
        "blockers": blockers,
    }
    return result


def _machine_campaign_report(machine: Mapping[str, object]) -> dict[str, object]:
    native_report = _mapping(
        machine.get("rtai_native_evidence_projection_readiness")
    )
    evidence_payload = _mapping(machine.get("rtai_abstract_execution_evidence_v2"))
    witness_report = _mapping(evidence_payload.get("witness_generation"))
    ready = bool(native_report.get("ready")) and bool(
        witness_report.get("complete")
    )
    return {
        "version": STRICT_PROJECTION_CAMPAIGN_VERSION,
        "ready": ready,
        "projection_source": "rtai-execution-evidence-v2",
        "legacy_fallback_allowed": False,
        "witness_generation_complete": bool(witness_report.get("complete")),
        "blockers": _campaign_blockers(native_report, witness_report),
    }


def _remove_legacy_system_projection(transition: dict[str, object]) -> None:
    """Remove legacy System-only projections without touching Machine actions."""

    transition["execution_action_bindings"] = []
    transition["execution_contexts"] = []
    transition["system_execution_actions"] = []
    transition["system_actions"] = []


def _campaign_blockers(
    native_report: Mapping[str, object],
    witness_report: Mapping[str, object],
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    for item in _mappings(native_report.get("transitions")):
        if item.get("ready") is True:
            continue
        blockers.append(
            {
                "kind": "transition-not-ready",
                "edge_id": item.get("edge_id"),
                "reason": item.get("reason"),
            }
        )
    for item in _mappings(witness_report.get("issues")):
        blockers.append(
            {
                "kind": "witness-generation",
                "entry": item.get("entry"),
                "reason": item.get("code"),
                "detail": item.get("detail"),
            }
        )
    if not witness_report.get("enabled"):
        blockers.append(
            {
                "kind": "witness-generation",
                "reason": "witness-generation-disabled",
            }
        )
    return blockers


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


__all__ = [
    "STRICT_PROJECTION_CAMPAIGN_VERSION",
    "build_strict_io_state_views",
    "build_strict_projection_candidate",
]
