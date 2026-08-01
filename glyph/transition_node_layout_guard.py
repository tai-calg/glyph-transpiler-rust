from __future__ import annotations


_MARKER = "glyph-transition-node-layout-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-node-layout-guard-v1-script">
(()=>{
const MARKER="glyph-transition-node-layout-guard-v1";

function requestLayout(stage=document.querySelector(".state-node")?.closest(".graph-stage"),reason="node-layout-guard-request"){
  if(!stage||!stage.isConnected)return Promise.resolve(false);
  stage.dataset.transitionIoNodeConstraint="delegated";
  stage.dataset.transitionPublicationReady="false";
  const transaction=window.glyphTransitionLayoutTransaction;
  if(!transaction?.schedule){
    stage.dataset.transitionIoNodeConstraint="transaction-unavailable";
    return Promise.resolve(false);
  }
  transaction.schedule(reason,0);
  return Promise.resolve(true);
}

window.glyphTransitionNodeLayoutGuard=Object.freeze({
  marker:MARKER,
  version:2,
  ownsPointerEvents:false,
  ownsPersistence:false,
  ownsRouting:false,
  requestLayout,
});
})();
</script>
"""


def enhance_transition_node_layout_guard_html(html: str) -> str:
    """Delegate legacy node-layout requests to the certified transaction owner."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
