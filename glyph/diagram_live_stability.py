from __future__ import annotations

import threading


_MARKER = "glyph-diagram-live-stability-v2"
_PATCH_LOCK = threading.Lock()
_PATCHED = False


_STYLE = r"""
<style id="glyph-diagram-live-stability-v2-style">
.canvas-shell.diagram-render-pending{position:relative}
.canvas-shell.diagram-render-pending>.graph-stage,
.canvas-shell.diagram-render-failed>.graph-stage{
  visibility:visible!important;
  opacity:1!important;
}
.canvas-shell.diagram-render-pending::after{
  content:"";
  display:none!important;
}
.canvas-shell.diagram-render-failed::after{
  content:"";
  display:none!important;
}
.canvas-shell.diagram-render-pending+.transition-index,
.canvas-shell.diagram-render-failed+.transition-index{
  visibility:visible!important;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-diagram-live-stability-v2-script">
(() => {
  const MARKER = "glyph-diagram-live-stability-v2";
  const RENDER_BUDGET_MS = 180;
  let renderGeneration = 0;
  const fallbackTimers = new WeakMap();

  function stateStage(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
  function renderKey(){try{return JSON.stringify([snapshot?.version??null,snapshot?.digest??"",snapshot?.status??"",activeTab,systemIndex,machineIndex])}catch{return ""}}
  function clearTimer(stage){const timer=fallbackTimers.get(stage);if(timer)clearTimeout(timer);fallbackTimers.delete(stage)}
  function layoutUsable(stage){
    if(!stage?.querySelector(".state-node"))return true;
    return stage.dataset.transitionLayoutState==="ready"
      || stage.dataset.transitionLayoutProfile==="interactive-fast";
  }
  function reveal(stage,state="ready"){
    if(!stage?.isConnected)return false;
    clearTimer(stage);
    stage.dataset.renderStable="true";
    stage.dataset.renderStableState=state;
    const shell=stage.closest(".canvas-shell");
    shell?.classList.remove("diagram-render-pending","diagram-render-failed");
    document.dispatchEvent(new CustomEvent("glyph-diagram-render-stable",{detail:{marker:MARKER,state}}));
    return true;
  }
  function settle(stage=stateStage(),generation=renderGeneration){
    if(!stage?.querySelector(".state-node"))return;
    if(!layoutUsable(stage))return;
    requestAnimationFrame(()=>{
      if(generation!==renderGeneration||stage!==stateStage())return;
      const certificate=stage.dataset.layoutCertificateState;
      reveal(stage,certificate==="valid"?"certified":"interactive");
    });
  }
  function markPending(stage=stateStage()){
    if(!stage?.querySelector(".state-node"))return;
    const generation=++renderGeneration;
    clearTimer(stage);
    stage.dataset.renderStable="false";
    stage.dataset.renderStableState="pending";
    const shell=stage.closest(".canvas-shell");
    shell?.classList.remove("diagram-render-failed");
    shell?.classList.add("diagram-render-pending");
    fallbackTimers.set(stage,setTimeout(()=>{
      if(generation!==renderGeneration||!stage.isConnected)return;
      reveal(stage,"interactive-budget");
    },RENDER_BUDGET_MS));
    settle(stage,generation);
  }
  function selectDefaultStateTab(){
    activeTab="state";
    document.querySelectorAll(".tab").forEach(button=>button.classList.toggle("active",button.dataset.tab==="state"));
  }

  const originalRender=window.render;
  if(typeof originalRender==="function"){
    window.render=function stableRender(...arguments_){
      const key=renderKey();
      if(key&&view.dataset.renderKey===key&&view.childElementCount){
        setStatus(snapshot?.status||"starting");
        renderSummary();
        renderDiagnostics();
        return;
      }
      const result=originalRender.apply(this,arguments_);
      view.dataset.renderKey=key;
      if(activeTab==="state")markPending();
      return result;
    };
    render=window.render;
  }
  const originalRenderState=window.renderState;
  if(typeof originalRenderState==="function"){
    window.renderState=function stableRenderState(...arguments_){
      const result=originalRenderState.apply(this,arguments_);
      view.dataset.renderKey=renderKey();
      markPending();
      return result;
    };
    renderState=window.renderState;
  }
  const originalRenderIo=window.renderIo;
  if(typeof originalRenderIo==="function"){
    window.renderIo=function stableRenderIo(...arguments_){
      const result=originalRenderIo.apply(this,arguments_);
      view.dataset.renderKey=renderKey();
      return result;
    };
    renderIo=window.renderIo;
  }

  for(const eventName of[
    "glyph-transition-layout-transaction-ready",
    "glyph-initial-transition-route-ready",
    "glyph-layout-publication-certificate-ready",
  ]){
    document.addEventListener(eventName,()=>settle());
  }
  document.addEventListener("glyph-layout-publication-certificate-failed",()=>{
    const stage=stateStage();
    if(stage)reveal(stage,"certificate-degraded");
  });
  const root=document.getElementById("view")||document.body;
  new MutationObserver(()=>settle()).observe(root,{
    subtree:true,
    attributes:true,
    attributeFilter:["data-transition-layout-state","data-layout-certificate-state","data-transition-publication-ready"],
  });
  selectDefaultStateTab();
  if(snapshot)render();
})();
</script>
"""


def install_serial_compilation() -> None:
    """Compatibility hook; GlyphDiagramApp now owns operation serialization."""

    global _PATCHED
    with _PATCH_LOCK:
        _PATCHED = True


def enhance_diagram_live_stability_html(html: str) -> str:
    """Keep the state diagram visible while bounded layout work completes."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
