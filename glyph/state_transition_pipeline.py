from __future__ import annotations

from copy import deepcopy

from .artifacts import CompilationModel
from .compiler import FieldExpr, ProductDecl
from .diagnostic_localization import localize_state_views
from .state_transition_block_lowering import lower_analyzed_block_transitions
from .state_transition_compiler import enrich_state_transition_ir as compile_state_transition_ir
from .state_transition_contract import (
    STATE_TRANSITION_IR_VERSION,
    TRANSITION_ACTION_SCOPE_VERSION,
    TRANSITION_ACTION_TARGET_INDEPENDENCE_VERSION,
    TRANSITION_ENABLING_CASES_VERSION,
    TRANSITION_EXECUTION_CONTEXT_CONTROL_FLOW_VERSION,
    TRANSITION_EXECUTION_CONTEXT_PROJECTION_VERSION,
    TRANSITION_EXECUTION_EVIDENCE_VERSION,
    TRANSITION_INPUT_PREIMAGE_VERSION,
    TRANSITION_OPERATION_ACTION_VERSION,
    TRANSITION_RESULT_CONSUMER_ACTION_VERSION,
    TRANSITION_SEMANTICS_VERSION,
    TRANSITION_SYSTEM_EXECUTION_ACTION_VERSION,
    public_transition_ir_marker,
)
from .transition_action_projection import project_machine_transition_actions
from .transition_action_scopes import project_transition_action_scopes
from .transition_action_target_independence import analyze_action_target_independence
from .transition_analysis import (
    RTAI_SEMANTIC_BOOTSTRAP_VERSION,
    attach_execution_evidence_v2,
    attach_rtai_semantic_bootstrap,
)
from .transition_analysis.lowering import lower_compilation_model_report
from .transition_condition_roles import classify_machine_transition_roles
from .transition_enabling_case_compatibility import preserve_legacy_transition_metadata
from .transition_enabling_case_defaults import ensure_machine_enabling_cases
from .transition_enabling_cases import attach_machine_enabling_cases
from .transition_input_provenance import expand_machine_transition_inputs
from .transition_operation_action_finalization import finalize_machine_operation_actions
from .transition_output_action_compatibility import attach_output_action_compatibility
from .transition_system_execution_control_flow import (
    attach_transition_system_execution_actions,
)


def _target_state_projection_type(
    model: CompilationModel,
    machine_name: str,
) -> str | None:
    machine = next((item for item in model.machines if item.name == machine_name), None)
    if machine is None or not isinstance(machine.selector, FieldExpr):
        return None
    state_decl = next(
        (
            item
            for item in model.program.declarations
            if isinstance(item, ProductDecl) and item.name == machine.state_param.ty.name
        ),
        None,
    )
    if state_decl is None:
        return None
    field = next(
        (item for item in state_decl.fields if item.name == machine.selector.field),
        None,
    )
    return field.ty.name if field is not None else None


def _operation_action_type(machine: dict[str, object]) -> str | None:
    for transition in machine.get("transitions", []):
        action = transition.get("display_action") if isinstance(transition, dict) else None
        if not isinstance(action, dict):
            continue
        if action.get("provenance") == "transition-operation-invocation":
            return "OperationInvocation"
    return None


def _attach_action_target_independence(
    model: CompilationModel,
    machine: dict[str, object],
) -> dict[str, object]:
    result = dict(machine)
    action_type = _operation_action_type(result)
    state_type = _target_state_projection_type(model, str(result.get("name") or ""))
    independence, generated = analyze_action_target_independence(
        result.get("transitions", []),
        action_type=action_type,
        state_type=state_type,
    )

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
    seen = {
        (item.get("code"), item.get("line"), item.get("message"))
        for item in diagnostics
    }
    for item in generated:
        key = (item.get("code"), item.get("line"), item.get("message"))
        if key not in seen:
            diagnostics.append(item)
            seen.add(key)

    analysis = dict(result.get("analysis", {}))
    analysis["action_target_independence"] = independence
    result["analysis"] = analysis
    result["diagnostics"] = diagnostics
    return result


def _publish_machine_contract(machine: dict[str, object]) -> dict[str, object]:
    result = dict(machine)
    marker = public_transition_ir_marker()
    result["transition_ir"] = marker
    analysis = dict(result.get("analysis", {}))
    analysis["transition_ir_schema"] = marker["schema"]
    analysis["transition_ir_version"] = marker["version"]
    result["analysis"] = analysis
    return result


def enrich_state_transition_ir(
    model: CompilationModel,
    views: dict[str, object],
) -> dict[str, object]:
    """Compile and publish the complete StateTransitionIR contract."""

    original = deepcopy(views)
    result = compile_state_transition_ir(model, views)
    analyzed_by_name = {
        str(machine.get("name", "")): machine
        for machine in original.get("state", {}).get("machines", [])
    }
    state = dict(result.get("state", {}))
    lowered = [
        lower_analyzed_block_transitions(
            model,
            dict(machine),
            dict(analyzed_by_name.get(str(machine.get("name", "")), {})),
        )
        for machine in state.get("machines", [])
    ]
    projected = [
        project_machine_transition_actions(model, machine) for machine in lowered
    ]
    system_executed = [
        attach_transition_system_execution_actions(model, machine)
        for machine in projected
    ]
    # RTAI Evidence v2 and semantic bootstrap are emitted in shadow mode.
    # Unsupported TEIR constructs are published as lowering issues and never
    # break the ordinary compiler or change the active display projection.
    rtai_report = lower_compilation_model_report(model)
    evidenced = [attach_execution_evidence_v2(machine) for machine in system_executed]
    bootstrapped = [
        attach_rtai_semantic_bootstrap(
            model,
            machine,
            functions=rtai_report.functions,
            lowering_issues=rtai_report.issues,
        )
        for machine in evidenced
    ]
    compatible = [
        attach_output_action_compatibility(machine) for machine in bootstrapped
    ]
    classified = [
        classify_machine_transition_roles(model, machine) for machine in compatible
    ]
    expanded = [
        expand_machine_transition_inputs(model, machine) for machine in classified
    ]
    enabled = [
        ensure_machine_enabling_cases(
            preserve_legacy_transition_metadata(
                attach_machine_enabling_cases(model, machine)
            )
        )
        for machine in expanded
    ]
    finalized = [
        finalize_machine_operation_actions(machine) for machine in enabled
    ]
    scoped = [project_transition_action_scopes(machine) for machine in finalized]
    state["machines"] = [
        _publish_machine_contract(
            _attach_action_target_independence(model, machine)
        )
        for machine in scoped
    ]
    result["state"] = state
    result["state_transition_ir"] = public_transition_ir_marker()
    result["transition_semantics_version"] = TRANSITION_SEMANTICS_VERSION
    result["transition_input_preimage_version"] = TRANSITION_INPUT_PREIMAGE_VERSION
    result["transition_enabling_cases_version"] = TRANSITION_ENABLING_CASES_VERSION
    result["transition_operation_action_version"] = TRANSITION_OPERATION_ACTION_VERSION
    result["transition_result_consumer_action_version"] = (
        TRANSITION_RESULT_CONSUMER_ACTION_VERSION
    )
    result["transition_system_execution_action_version"] = (
        TRANSITION_SYSTEM_EXECUTION_ACTION_VERSION
    )
    result["transition_action_scope_version"] = TRANSITION_ACTION_SCOPE_VERSION
    result["transition_execution_context_control_flow_version"] = (
        TRANSITION_EXECUTION_CONTEXT_CONTROL_FLOW_VERSION
    )
    result["transition_execution_context_projection_version"] = (
        TRANSITION_EXECUTION_CONTEXT_PROJECTION_VERSION
    )
    result["transition_execution_evidence_version"] = (
        TRANSITION_EXECUTION_EVIDENCE_VERSION
    )
    result["rtai_semantic_bootstrap_version"] = RTAI_SEMANTIC_BOOTSTRAP_VERSION
    result["transition_action_target_independence_version"] = (
        TRANSITION_ACTION_TARGET_INDEPENDENCE_VERSION
    )
    summary = dict(result.get("summary", {}))
    summary["state_warnings"] = sum(
        1
        for machine in state["machines"]
        for diagnostic in machine.get("diagnostics", [])
        if diagnostic.get("severity") == "warning"
    )
    result["summary"] = summary
    return localize_state_views(result)
