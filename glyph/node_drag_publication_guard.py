from __future__ import annotations


_MARKER = "glyph-node-drag-publication-guard-v1"


_SCRIPT = r"""
<script id="glyph-node-drag-publication-guard-v1-script">
(() => {
  const MARKER = "glyph-node-drag-publication-guard-v1";

  function invalidate(stage, reason) {
    if (!stage || !stage.isConnected) return false;
    stage.dataset.transitionLayoutState = "pending";
    stage.dataset.transitionPublicationReady = "false";
    stage.dataset.transitionIoCollisionSolved = "transaction-pending";
    stage.dataset.transitionIoCollisionCount = "-1";
    stage.dataset.layoutCertificateRequestState = "invalidated";
    stage.dataset.transitionLayoutReason = reason;
    return true;
  }

  function schedule(reason) {
    setTimeout(() => {
      window.glyphTransitionLayoutTransaction?.schedule?.(reason, 0);
    }, 0);
  }

  window.glyphNodeDragPublicationGuard = Object.freeze({
    marker: MARKER,
    version: 3,
    interactionOwner: "glyph-transition-node-position-adapter-v7",
    ownsPointerEvents: false,
    ownsKeyboardEvents: false,
    invalidate,
    schedule,
  });
})();
</script>
"""


def enhance_node_drag_publication_guard_html(html: str) -> str:
    """Expose publication invalidation to the unified node interaction owner."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
