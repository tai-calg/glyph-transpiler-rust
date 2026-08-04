from __future__ import annotations


_MARKER = "glyph-state-node-interaction-layer-v1"

_STYLE = r"""
<style id="glyph-state-node-interaction-layer-v1-style">
/*
 * Transition labels and enabling-case clusters may geometrically cross a state
 * node. The node remains the primary direct-manipulation target.
 */
.graph-stage .state-node{
  z-index:20;
  pointer-events:auto;
}
.graph-stage .state-node.selected-node,
.graph-stage .state-node.dragging{
  z-index:21;
}
.graph-stage .initial-dot{
  z-index:22;
  pointer-events:none;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-state-node-interaction-layer-v1-script">
(()=>{
const MARKER="glyph-state-node-interaction-layer-v1";
function stateNodeAt(stage,x,y){
  const nodes=[...stage.querySelectorAll(".state-node")];
  const candidates=nodes.filter(node=>{
    const rect=node.getBoundingClientRect();
    return x>=rect.left&&x<=rect.right&&y>=rect.top&&y<=rect.bottom;
  });
  candidates.sort((left,right)=>{
    const leftRect=left.getBoundingClientRect();
    const rightRect=right.getBoundingClientRect();
    return leftRect.width*leftRect.height-rightRect.width*rightRect.height;
  });
  return candidates[0]||null;
}
document.addEventListener("pointerdown",event=>{
  if(event.button!==0||event.target?.closest?.(".state-node"))return;
  const stage=event.target?.closest?.(".graph-stage");
  if(!stage||stage.dataset.transitionLayoutState!=="ready")return;
  const node=stateNodeAt(stage,event.clientX,event.clientY);
  if(!node)return;
  const redirected=new PointerEvent("pointerdown",{
    bubbles:true,
    cancelable:true,
    composed:true,
    pointerId:event.pointerId,
    pointerType:event.pointerType,
    isPrimary:event.isPrimary,
    button:event.button,
    buttons:event.buttons,
    clientX:event.clientX,
    clientY:event.clientY,
    screenX:event.screenX,
    screenY:event.screenY,
    ctrlKey:event.ctrlKey,
    shiftKey:event.shiftKey,
    altKey:event.altKey,
    metaKey:event.metaKey,
  });
  node.dispatchEvent(redirected);
  if(redirected.defaultPrevented)event.preventDefault();
  event.stopImmediatePropagation();
},true);
window.glyphStateNodeInteractionLayer={marker:MARKER,version:1};
})();
</script>
"""


def enhance_state_node_interaction_layer_html(html: str) -> str:
    """Keep visible state nodes operable during transient viewport relayout."""

    if _MARKER in html:
        return html
    html = html.replace("</head>", _STYLE + "\n</head>")
    return html.replace("</body>", _SCRIPT + "\n</body>")
