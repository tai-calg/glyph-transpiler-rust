from __future__ import annotations


_MARKER = "glyph-transition-label-drag-guard-v2"

_STYLE = r"""
<style id="glyph-transition-label-drag-guard-v2-style">
.graph-stage[data-transition-publication-ready="false"] .transition-io-cluster.dragging-io{
  visibility:visible!important;
  pointer-events:auto!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-label-drag-guard-v2-script">
(()=>{
const MARKER="glyph-transition-label-drag-guard-v2";
if(window.glyphTransitionLabelDragGuard?.marker===MARKER)return;

function invalidate(stage,reason){
  if(!stage||!stage.isConnected)return false;
  // Keep the current layout generation alive for the duration of pointer capture.
  // Only the published certificate becomes invalid; the transaction starts after
  // the owner has captured and persisted the final point.
  stage.dataset.manualLabelEditState="dragging";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionIoCollisionSolved="editing";
  stage.dataset.transitionIoCollisionCount="-1";
  stage.dataset.layoutCertificateState="invalidated";
  stage.dataset.layoutCertificateRequestState="invalidated";
  stage.dataset.transitionLayoutReason=reason;
  return true;
}
function schedule(reason){
  setTimeout(()=>window.glyphTransitionLayoutTransaction?.schedule?.(reason,0),0);
}

// Pointer ownership, movement thresholds, constraint projection, persistence, and
// reset remain exclusively implemented by glyphTransitionLayoutInteractionAdapter.
window.glyphTransitionLabelDragGuard=Object.freeze({
  marker:MARKER,
  version:3,
  interactionOwner:"glyph-transition-layout-interaction-adapter-v4",
  ownsPointerEvents:false,
  ownsPersistence:false,
  invalidate,
  schedule,
});
})();
</script>
"""


def enhance_transition_label_drag_guard_html(html: str) -> str:
    """Invalidate publication without terminating the active label gesture."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
