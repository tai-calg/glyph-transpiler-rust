from __future__ import annotations

from pathlib import Path

from glyph.readable_diagram_app import _presentation_pipeline
from glyph.transition_analysis.public_effect_contracts import PUBLIC_STRICT_PROGRAMS


ROOT = Path(__file__).resolve().parents[1]
GLYPH = ROOT / "glyph"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_node_and_label_interactions_have_one_owner_each() -> None:
    node_guard = read("glyph/node_drag_publication_guard.py")
    node_owner = read("glyph/transition_node_position_adapter.py")
    exports = read("glyph/diagram_editor_exports.py")
    label_guard = read("glyph/transition_label_drag_guard.py")
    label_owner = read("glyph/transition_layout_interaction_adapter.py")

    for event_name in ("pointerdown", "pointermove", "pointerup", "pointercancel", "keydown"):
        assert f'document.addEventListener("{event_name}"' not in node_guard
    assert "ownsPointerEvents: false" in node_guard
    assert "ownsKeyboardEvents: false" in node_guard
    assert 'invalidatePublication(active,"manual-node-drag")' in node_owner
    assert 'invalidatePublication(record,"manual-node-keyboard")' in node_owner

    assert 'stage.querySelectorAll(".state-node,.graph-node")' not in exports
    assert 'stage.querySelectorAll(".graph-node").forEach(node=>' in exports
    assert '!selected.matches(".graph-node")' in exports
    assert "function stateCurve(" not in exports
    assert 'stateNodeInteractionOwner:"glyph-transition-node-position-adapter-v7"' in exports

    assert "ownsPointerEvents:false" in label_guard
    assert "ownsPersistence:false" in label_guard
    assert 'document.addEventListener("pointerdown"' in label_owner
    assert 'document.addEventListener("pointermove"' in label_owner
    assert 'document.addEventListener("pointerup"' in label_owner


def test_every_persisted_geometry_has_an_explicit_coordinate_frame() -> None:
    label_owner = read("glyph/transition_layout_interaction_adapter.py")
    transaction = read("glyph/transition_layout_transaction.py")
    node_owner = read("glyph/transition_node_position_adapter.py")
    exports = read("glyph/diagram_editor_exports.py")
    viewport = read("glyph/diagram_canvas_viewport.py")

    assert "anchorFraction:record.anchorFraction" in label_owner
    assert "storedAnchorFraction(record,routeAnchors)" in transaction
    assert "x:record.x-record.dx,y:record.y-record.dy" in transaction

    assert '${data?.digest||"source"}:state:${machineIndex()}' in node_owner
    assert "value[nodeName(node)]={x:num(node.style.left),y:num(node.style.top)}" in node_owner
    assert "ensureCanvas(stage" in transaction
    assert "nodes.right+CANVAS_PADDING" in transaction

    assert '$("#diagram-reset").onclick=async()=>' in exports
    assert "await state();localStorage.removeItem(key(stage))" in exports

    assert "const digest=activeStage()?.dataset.diagramDigest||\"source\"" in viewport
    assert "return `${digest}:${tab}:${index}`" in viewport
    assert "glyph.diagram.viewport-scale.v1" in viewport
    assert "glyph.diagram.viewport-mode.v1" in viewport


def test_public_ready_flags_are_bound_to_the_final_certificate() -> None:
    live = read("glyph/diagram_live_stability.py")
    semantic = read("glyph/transition_semantic_status_ui.py")
    fit = read("glyph/diagram_fit_stability.py")
    certificate = read("glyph/layout_publication_certificate.py")

    for source in (live, semantic):
        assert "transitionPublicationReady" in source
        assert "layoutCertificateState" in source
        assert '==="true"' in source
        assert '==="valid"' in source

    assert "transitionPublicationReady" in fit
    assert "layoutCertificateState" in fit
    assert 'stage.dataset.layoutCertificateState = "valid"' in certificate
    assert 'stage.dataset.transitionPublicationReady = "true"' in certificate
    assert 'stage.dataset.transitionPublicationReady = "false"' in certificate


def test_generation_identity_flows_from_layout_through_route_to_publication() -> None:
    transaction = read("glyph/transition_layout_transaction.py")
    route_bridge = read("glyph/initial_transition_dependency_bridge.py")
    bootstrap = read("glyph/transition_layout_transaction_bootstrap.py")
    certificate = read("glyph/layout_publication_certificate.py")

    assert "transitionLayoutGeneration=String(token)" in transaction
    assert "layoutGeneration: generation" in route_bridge
    assert "initialRouteLayoutGeneration = generation" in route_bridge
    assert "glyphLayoutPublicationCertificate?.schedule?.(" in route_bridge
    assert route_bridge.index("glyphLayoutPublicationCertificate?.schedule?.(") < route_bridge.index(
        'document.dispatchEvent(new CustomEvent("glyph-initial-transition-route-ready"'
    )

    assert "const request=`${generation}:${routeEpoch}:${reason}`" in bootstrap
    assert "geometryFingerprint(stage)" in certificate
    assert 'stage.dataset.transitionLayoutGeneration || "0"' in certificate
    assert "layoutCertificateFingerprint" in certificate


def test_semantic_identity_joins_reject_duplicates_instead_of_overwriting() -> None:
    specialization = read("glyph/transition_analysis/view_edge_specialization.py")
    projection = read("glyph/transition_analysis/evidence_projection.py")
    binding = read("glyph/transition_analysis/witness_binding.py")

    assert "duplicate_view_ids" in specialization
    assert "_ambiguous_identity" in specialization
    assert "zip(original_transitions, bindings, strict=True)" in specialization
    assert "by_view_id =" not in specialization

    assert "duplicate_edge_ids" in projection
    assert '"duplicate-transition-edge-id"' in projection
    assert '"evidence-edge-id-mismatch"' in projection
    assert "readiness_by_transition = report.transitions" in projection
    assert "readiness = {item.edge_id" not in projection

    assert "ambiguous: set[str]" in binding
    assert "result.pop(edge_id, None)" in binding
    assert "ambiguous.add(edge_id)" in binding


def test_public_strict_catalog_identity_is_unambiguous() -> None:
    source_ids = [item.source_id for item in PUBLIC_STRICT_PROGRAMS]
    source_paths = [item.source_path for item in PUBLIC_STRICT_PROGRAMS if item.source_path]
    contexts = [
        (item.source_id, item.system, item.entry)
        for item in PUBLIC_STRICT_PROGRAMS
    ]

    assert len(source_ids) == len(set(source_ids))
    assert len(source_paths) == len(set(source_paths))
    assert len(contexts) == len(set(contexts))


def test_presentation_pipeline_preserves_protocol_ownership_order() -> None:
    names = [enhancer.__name__ for enhancer in _presentation_pipeline()]

    assert names.index("enhance_transition_layout_transaction_bootstrap_html") < names.index(
        "enhance_transition_layout_transaction_html"
    )
    assert names.index("enhance_node_drag_publication_guard_html") < names.index(
        "enhance_transition_node_position_adapter_html"
    )
    assert names.index("enhance_initial_transition_dependency_bridge_html") < names.index(
        "enhance_layout_publication_certificate_html"
    )
    assert names[-1] == "enhance_layout_publication_certificate_html"


def test_certified_workflow_cannot_miss_new_glyph_or_browser_layers() -> None:
    workflow = read(".github/workflows/certified-layout.yml")

    assert '- "glyph/**"' in workflow
    assert '- "tests/**/*.py"' in workflow
    assert '- "tests/**/*.mjs"' in workflow
    assert '- "examples/acceptance/**"' in workflow
    assert '- "examples/state_diagrams/**"' in workflow
    assert "tests/test_public_release_invariants.py" in workflow
    assert "tests/verify_node_drag_layout.mjs" in workflow
