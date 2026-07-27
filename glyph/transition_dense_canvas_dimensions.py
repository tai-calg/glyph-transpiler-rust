from __future__ import annotations


_MARKER = "glyph-transition-dense-canvas-dimensions-v1"

_SCRIPT = r"""
<script id="glyph-transition-dense-canvas-dimensions-v1-script">
(()=>{
const MARKER="glyph-transition-dense-canvas-dimensions-v1",DENSE_TRANSITIONS=7,MIN_WIDTH=1400,MIN_HEIGHT=1000;
let timer=null;

function apply(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage||stage.dataset.transitionIoClustersReady!=="true")return false;
  const count=stage.querySelectorAll(".transition-io-cluster").length;
  if(count<DENSE_TRANSITIONS){
    stage.dataset.transitionDenseCanvas="not-required";
    return false;
  }
  const width=Math.max(MIN_WIDTH,stage.scrollWidth),height=Math.max(MIN_HEIGHT,stage.scrollHeight);
  const changed=stage.scrollWidth<width||stage.scrollHeight<height||stage.style.width!==`${width}px`||stage.style.height!==`${height}px`;
  stage.style.width=`${width}px`;
  stage.style.height=`${height}px`;
  stage.dataset.transitionDenseCanvas=`${width}x${height}`;
  if(changed){
    stage.dataset.transitionIoCollisionSolved="dense-canvas-pending";
    stage.dataset.transitionIoCollisionCount="-1";
    setTimeout(()=>window.glyphTransitionIoCollisionSolver?.run(),0);
  }
  document.dispatchEvent(new CustomEvent("glyph-transition-dense-canvas-ready",{detail:{marker:MARKER,count,width,height,changed}}));
  return changed;
}

function schedule(stage=null,delay=0){
  clearTimeout(timer);
  timer=setTimeout(()=>apply(stage||document.querySelector(".state-node")?.closest(".graph-stage")),delay);
}
document.addEventListener("glyph-transition-io-clusters-ready",()=>schedule(null,0));
document.addEventListener("glyph-transition-readable-layout-ready",()=>schedule(null,0));
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule(null,0)});
new MutationObserver(()=>schedule(null,30)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphTransitionDenseCanvasDimensions={marker:MARKER,apply:()=>schedule(null,0),minimum:{width:MIN_WIDTH,height:MIN_HEIGHT},denseTransitions:DENSE_TRANSITIONS};
schedule(null,0);
})();
</script>
"""


def enhance_transition_dense_canvas_dimensions_html(html: str) -> str:
    """Keep the coordinate domain stable for dense diagrams and saved node positions."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
