from __future__ import annotations

from functools import wraps
import threading

from . import diagram_app


_MARKER = "glyph-diagram-live-stability-v2"
_PATCH_LOCK = threading.Lock()
_PATCHED = False


_STYLE = r"""
<style id="glyph-diagram-live-stability-v2-style">
.canvas-shell.diagram-render-pending{position:relative}
.canvas-shell.diagram-render-pending>.graph-stage{visibility:hidden!important}
.canvas-shell.diagram-render-pending::after{content:"Rendering state diagram…";position:absolute;inset:0;display:grid;place-items:center;color:var(--muted);background:var(--panel);font-size:12px;pointer-events:none}
.canvas-shell.diagram-render-pending+.transition-index{visibility:hidden!important}
.canvas-shell.diagram-render-failed::after{content:"State diagram certification failed";color:var(--red)}
</style>
"""


_SCRIPT = r"""
<script id="glyph-diagram-live-stability-v2-script">
(() => {
  const MARKER = "glyph-diagram-live-stability-v2";
  const RENDER_TIMEOUT_MS = 12000;
  const REQUEST_TIMEOUT_MS = 30000;
  const POLL_INTERVAL_MS = 3000;
  const REQUIRED_FLAGS = ["labelLayoutReady", "umlTransitionReady", "transitionInputActionLabelsReady", "stateTransitionIRV2LabelsReady"];
  let renderGeneration = 0;
  let requestGeneration = 0;
  let previewController = null;
  let lastPollAt = 0;
  const fallbackTimers = new WeakMap();

  function stateStage(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
  function renderKey(){try{return JSON.stringify([snapshot?.version??null,snapshot?.digest??"",snapshot?.status??"",activeTab,systemIndex,machineIndex])}catch{return ""}}
  function initialRouteReady(stage){const raw=stage?.querySelector(":scope > svg.edge-svg > path:not(.state-transition-path)");if(!raw)return true;return stage.dataset.initialRouteReady==="true"&&raw.classList.contains("initial-transition-path")}
  function publicationReady(stage){return stage?.dataset.transitionPublicationReady==="true"&&stage.dataset.layoutCertificateState==="valid"}
  function fullyAdjusted(stage){
    if(!stage?.querySelector(".state-node"))return true;
    if(window.glyphLayoutPublicationCertificate)return publicationReady(stage)&&initialRouteReady(stage);
    return REQUIRED_FLAGS.every(name=>stage.dataset[name]==="true")&&initialRouteReady(stage);
  }
  function clearTimer(stage){const timer=fallbackTimers.get(stage);if(timer)clearTimeout(timer);fallbackTimers.delete(stage)}
  function reveal(stage,state="ready"){
    if(!stage?.isConnected||!fullyAdjusted(stage))return false;
    clearTimer(stage);
    stage.dataset.renderStable="true";
    stage.dataset.renderStableState=state;
    const shell=stage.closest(".canvas-shell");
    shell?.classList.remove("diagram-render-pending","diagram-render-failed");
    document.dispatchEvent(new CustomEvent("glyph-diagram-render-stable",{detail:{marker:MARKER,state}}));
    return true;
  }
  function failClosed(stage,generation){
    if(generation!==renderGeneration||!stage?.isConnected||fullyAdjusted(stage))return;
    clearTimer(stage);
    stage.dataset.renderStable="false";
    stage.dataset.renderStableState="certification-timeout";
    const shell=stage.closest(".canvas-shell");
    shell?.classList.add("diagram-render-pending","diagram-render-failed");
    console.error("state diagram publication certification timed out; diagram remains hidden");
    document.dispatchEvent(new CustomEvent("glyph-diagram-render-failed",{detail:{marker:MARKER,state:"certification-timeout"}}));
  }
  function settle(stage=stateStage(),generation=renderGeneration){
    if(!stage?.querySelector(".state-node")||!fullyAdjusted(stage))return;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(generation!==renderGeneration||stage!==stateStage())return;
      reveal(stage,"certified");
    }));
  }
  function markPending(stage=stateStage()){
    if(!stage?.querySelector(".state-node"))return;
    const generation=++renderGeneration;
    clearTimer(stage);
    delete stage.dataset.renderStable;
    stage.dataset.renderStableState="pending";
    const shell=stage.closest(".canvas-shell");
    shell?.classList.remove("diagram-render-failed");
    shell?.classList.add("diagram-render-pending");
    fallbackTimers.set(stage,setTimeout(()=>failClosed(stage,generation),RENDER_TIMEOUT_MS));
    settle(stage,generation);
  }
  function selectDefaultStateTab(){activeTab="state";document.querySelectorAll(".tab").forEach(button=>button.classList.toggle("active",button.dataset.tab==="state"))}
  function applySnapshot(next,{initial=false,updateEditor=false}={}){const currentVersion=Number(snapshot?.version??-1),nextVersion=Number(next?.version??-1);if(!initial&&nextVersion<currentVersion)return false;snapshot=next;if((initial||updateEditor)&&!dirty){editor.value=next.source||"";dirty=false;syncLines()}render();window.GlyphExecutionContext?.refresh?.();return true}
  function abortPreview(){requestGeneration+=1;if(previewController)previewController.abort();previewController=null}
  async function guardedRequest(path,options={},controller=null){const owned=controller||new AbortController();const timeout=setTimeout(()=>owned.abort(),REQUEST_TIMEOUT_MS);try{return await request(path,{...options,signal:owned.signal})}finally{clearTimeout(timeout)}}

  const originalRender=window.render;
  if(typeof originalRender==="function"){
    window.render=function stableRender(...arguments_){const key=renderKey();if(key&&view.dataset.renderKey===key&&view.childElementCount){setStatus(snapshot?.status||"starting");renderSummary();renderDiagnostics();return}const result=originalRender.apply(this,arguments_);view.dataset.renderKey=key;if(activeTab==="state")markPending();return result};
    render=window.render;
  }
  const originalRenderState=window.renderState;
  if(typeof originalRenderState==="function"){
    window.renderState=function stableRenderState(...arguments_){const result=originalRenderState.apply(this,arguments_);view.dataset.renderKey=renderKey();markPending();return result};
    renderState=window.renderState;
  }
  const originalRenderIo=window.renderIo;
  if(typeof originalRenderIo==="function"){
    window.renderIo=function stableRenderIo(...arguments_){const result=originalRenderIo.apply(this,arguments_);view.dataset.renderKey=renderKey();return result};
    renderIo=window.renderIo;
  }

  compile=async function stableCompile(){clearTimeout(previewTimer);previewTimer=null;const generation=++requestGeneration;if(previewController)previewController.abort();const controller=new AbortController();previewController=controller;setStatus("busy");try{const next=await guardedRequest("/api/preview",{method:"POST",body:JSON.stringify({source:editor.value})},controller);if(generation!==requestGeneration)return;applySnapshot(next)}catch(error){if(generation!==requestGeneration)return;setStatus("error");const message=error?.name==="AbortError"?"Compilation request timed out":error.message;diagnostics.innerHTML=`<div class="diagnostic">${esc(message)}</div>`}finally{if(generation===requestGeneration)previewController=null}};
  save=async function stableSave(){abortPreview();const generation=requestGeneration;setStatus("busy");try{const next=await guardedRequest("/api/save",{method:"POST",body:JSON.stringify({source:editor.value})});if(generation!==requestGeneration)return;dirty=false;applySnapshot(next)}catch(error){if(generation!==requestGeneration)return;setStatus("error");diagnostics.innerHTML=`<div class="diagnostic">${esc(error.message)}</div>`}};
  load=async function stableLoad(initial=false){const now=Date.now();if(!initial&&now-lastPollAt<POLL_INTERVAL_MS)return;lastPollAt=now;const generation=requestGeneration;try{const next=await guardedRequest("/api/state");if(generation!==requestGeneration||(!initial&&dirty))return;applySnapshot(next,{initial,updateEditor:initial})}catch(error){if(generation!==requestGeneration||error?.name==="AbortError")return;setStatus("error");diagnostics.innerHTML=`<div class="diagnostic">${esc(error.message)}</div>`}};
  document.getElementById("compile").onclick=()=>compile();
  document.getElementById("save").onclick=()=>save();

  for(const eventName of ["glyph-transition-layout-ready","glyph-uml-transition-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-initial-transition-route-ready","glyph-layout-publication-certificate-ready"]){document.addEventListener(eventName,()=>settle())}
  document.addEventListener("glyph-layout-publication-certificate-failed",()=>failClosed(stateStage(),renderGeneration));
  const root=document.getElementById("view")||document.body;
  new MutationObserver(()=>settle()).observe(root,{subtree:true,attributes:true,attributeFilter:["data-label-layout-ready","data-uml-transition-ready","data-transition-input-action-labels-ready","data-state-transition-ir-v2-labels-ready","data-initial-route-ready","data-transition-publication-ready","data-layout-certificate-state"]});
  selectDefaultStateTab();
  if(snapshot)render();
})();
</script>
"""


def install_serial_compilation() -> None:
    """Serialize compiler access and discard superseded preview requests."""

    global _PATCHED
    with _PATCH_LOCK:
        if _PATCHED:
            return
        app_type = diagram_app.GlyphDiagramApp
        original_init = app_type.__init__
        original_rebuild = app_type.rebuild
        original_save = app_type.save_source

        @wraps(original_init)
        def stable_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self._diagram_compile_lock = threading.RLock()
            self._diagram_preview_lock = threading.Lock()
            self._diagram_preview_ticket = 0

        @wraps(original_rebuild)
        def stable_rebuild(self, source=None):
            with self._diagram_compile_lock:
                return original_rebuild(self, source)

        def stable_preview(self, source: str):
            with self._diagram_preview_lock:
                self._diagram_preview_ticket += 1
                ticket = self._diagram_preview_ticket
            with self._diagram_compile_lock:
                with self._diagram_preview_lock:
                    if ticket != self._diagram_preview_ticket:
                        return self.snapshot
                return original_rebuild(self, source)

        @wraps(original_save)
        def stable_save(self, source: str):
            with self._diagram_preview_lock:
                self._diagram_preview_ticket += 1
            with self._diagram_compile_lock:
                return original_save(self, source)

        app_type.__init__ = stable_init
        app_type.rebuild = stable_rebuild
        app_type.preview_source = stable_preview
        app_type.save_source = stable_save
        _PATCHED = True


def enhance_diagram_live_stability_html(html: str) -> str:
    """Use state-first, stale-safe, publication-certified rendering."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace("</body>", _SCRIPT + "\n</body>")
