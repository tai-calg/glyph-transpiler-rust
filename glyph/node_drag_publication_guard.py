from __future__ import annotations


_MARKER = "glyph-node-drag-publication-guard-v1"


_SCRIPT = r"""
<script id="glyph-node-drag-publication-guard-v1-script">
(() => {
  const MARKER = "glyph-node-drag-publication-guard-v1";
  const DRAG_THRESHOLD = 3;
  let active = null;
  let destroyed = false;

  function invalidate(stage, reason) {
    if (!stage || !stage.isConnected) return false;
    stage.dataset.transitionLayoutState = "pending";
    stage.dataset.transitionPublicationReady = "false";
    stage.dataset.transitionIoCollisionSolved = "transaction-pending";
    stage.dataset.transitionIoCollisionCount = "-1";
    stage.dataset.transitionSemanticLinesReady = "pending";
    stage.dataset.transitionSemanticRoleLinesReady = "pending";
    stage.dataset.initialRouteReady = "pending";
    stage.dataset.layoutCertificateRequestState = "invalidated";
    stage.dataset.transitionLayoutReason = reason;
    return true;
  }

  function pointerDistance(record, event) {
    return Math.hypot(
      event.clientX - record.startX,
      event.clientY - record.startY,
    );
  }

  document.addEventListener("pointerdown", event => {
    const node = event.target?.closest?.(".state-node");
    const stage = node?.closest?.(".graph-stage");
    if (!node
      || event.button !== 0
      || !stage
      || stage.dataset.transitionLayoutState !== "ready") return;
    active = {
      pointerId: event.pointerId,
      stage,
      startX: event.clientX,
      startY: event.clientY,
      invalidated: false,
    };
  }, true);

  document.addEventListener("pointermove", event => {
    if (!active
      || active.pointerId !== event.pointerId
      || active.invalidated
      || pointerDistance(active, event) < DRAG_THRESHOLD) return;
    active.invalidated = invalidate(active.stage, "manual-node-drag");
  }, true);

  document.addEventListener("pointerup", event => {
    if (active?.pointerId === event.pointerId) active = null;
  }, true);

  document.addEventListener("pointercancel", event => {
    if (!active || active.pointerId !== event.pointerId) return;
    const record = active;
    active = null;
    if (record.invalidated) {
      setTimeout(() => {
        window.glyphTransitionLayoutTransaction?.schedule?.(
          "manual-node-cancelled",
          0,
        );
      }, 0);
    }
  }, true);

  document.addEventListener("keydown", event => {
    if (!event.key.startsWith("Arrow")) return;
    const node = document.querySelector(".state-node.selected-node");
    const stage = node?.closest(".graph-stage");
    if (!node || !stage || stage.dataset.transitionLayoutState !== "ready") return;
    invalidate(stage, "manual-node-keyboard");
  }, true);

  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      active = null;
    }, {once: true});
  }

  window.glyphNodeDragPublicationGuard = {
    marker: MARKER,
    version: 1,
    invalidate,
    get active() { return Boolean(active) && !destroyed; },
  };
})();
</script>
"""


def enhance_node_drag_publication_guard_html(html: str) -> str:
    """Invalidate stale publication state as soon as a node actually moves."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
