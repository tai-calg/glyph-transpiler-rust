from __future__ import annotations


_MARKER = "glyph-transition-semantic-status-ui-v2"

_STYLE = r"""
<style id="glyph-transition-semantic-status-ui-v2-style">
.transition-io-cluster[data-rtai-semantic-status]{
  --rtai-semantic-color:#6b7280;
}
.transition-io-cluster[data-rtai-semantic-status="exact"]{--rtai-semantic-color:#15803d}
.transition-io-cluster[data-rtai-semantic-status="may"]{--rtai-semantic-color:#a16207}
.transition-io-cluster[data-rtai-semantic-status="unknown"]{--rtai-semantic-color:#6b7280}
.transition-io-cluster[data-rtai-semantic-status]::after{
  content:attr(data-rtai-semantic-label);
  position:absolute;
  right:-7px;
  top:-9px;
  z-index:18;
  display:none;
  align-items:center;
  justify-content:center;
  min-width:30px;
  padding:1px 5px;
  border:1px solid currentColor;
  border-radius:999px;
  color:var(--rtai-semantic-color);
  background:var(--panel);
  box-shadow:0 1px 5px rgba(15,23,42,.18);
  font:700 9px/1.25 ui-sans-serif,system-ui,sans-serif;
  letter-spacing:.02em;
  white-space:nowrap;
  pointer-events:none;
}
.transition-io-cluster.rtai-semantic-badge-visible[data-rtai-semantic-status]::after,
.transition-io-cluster[data-rtai-semantic-status]:hover::after,
.transition-io-cluster[data-rtai-semantic-status].selected-io::after{
  display:inline-flex!important;
}
.theme-monochrome .transition-io-cluster[data-rtai-semantic-status]::after{
  color:#111!important;
  background:#fff!important;
  border-color:#111!important;
  box-shadow:none!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-semantic-status-ui-v2-script">
(()=>{
const MARKER="glyph-transition-semantic-status-ui-v2";
const STATE_REQUEST_TIMEOUT_MS=48;
let cache=null,timer=null,running=false,lastSignature="",disposed=false,controller=null;
const text=value=>String(value??"").trim();
function liveState(){return typeof snapshot==="object"&&snapshot?snapshot:null}
async function state(){
  const live=liveState();
  if(live)return live;
  if(cache)return cache;
  controller?.abort();
  controller=new AbortController();
  const timeout=setTimeout(()=>controller?.abort(),STATE_REQUEST_TIMEOUT_MS);
  try{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error("diagram state unavailable");
    return cache=await response.json();
  }finally{
    clearTimeout(timeout);
  }
}
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function projectionModeOf(data,machine){return text(data?.views?.rtai_projection_mode)||text(machine?.analysis?.evidence_projection_mode)||"shadow"}
function publicationReady(stage){
  return stage.dataset.transitionPublicationReady==="true"
    &&stage.dataset.transitionLayoutReady==="true"
    &&stage.dataset.transitionEnablingCasesReady==="true"
    &&stage.dataset.transitionIoCollisionCount==="0";
}
function semanticOf(transition){const raw=transition?.rtai_semantic_status||{},status=["exact","may","unknown"].includes(text(raw.status))?text(raw.status):"unknown";return{status,label:status==="exact"?"Exact":status==="may"?"May":"Unknown",reason:text(raw.reason)||"native Evidence status is unavailable"}}
function escapeId(value){return window.CSS?.escape?CSS.escape(value):value.replace(/[^A-Za-z0-9_-]/g,"\\$&")}
function setDataset(element,name,value){if(element.dataset[name]===value)return false;element.dataset[name]=value;return true}
function updateCluster(cluster,semantic,strict){
  let changed=false;
  changed=setDataset(cluster,"rtaiSemanticStatus",semantic.status)||changed;
  changed=setDataset(cluster,"rtaiSemanticLabel",semantic.label)||changed;
  changed=setDataset(cluster,"rtaiSemanticReason",semantic.reason)||changed;
  const title=`${semantic.label}: ${semantic.reason}`;
  if(cluster.dataset.rtaiSemanticTitle!==title){cluster.dataset.rtaiSemanticTitle=title;changed=true}
  const badgeVisible=cluster.classList.contains("rtai-semantic-badge-visible");
  if(badgeVisible!==strict){cluster.classList.toggle("rtai-semantic-badge-visible",strict);changed=true}
  return changed;
}
function clearCluster(cluster){
  let changed=false;
  for(const name of["rtaiSemanticStatus","rtaiSemanticLabel","rtaiSemanticReason","rtaiSemanticTitle"]){if(name in cluster.dataset){delete cluster.dataset[name];changed=true}}
  if(cluster.classList.contains("rtai-semantic-badge-visible")){cluster.classList.remove("rtai-semantic-badge-visible");changed=true}
  return changed;
}
function signatureOf(machine,projectionMode){return[window.GlyphI18n?.locale||document.documentElement.lang||"ja",machine?.name||"",projectionMode,...(machine?.transitions||[]).map((transition,index)=>{const semantic=semanticOf(transition);return[text(transition.id)||`T${index+1}`,semantic.status,semantic.reason].join("\u001f")})].join("\u001e")}
async function render(){
  if(disposed||running)return;
  const stage=document.querySelector(".state-node")?.closest(".graph-stage");
  if(!stage||stage.dataset.transitionIoClustersReady!=="true")return;
  running=true;
  try{
    const data=await state();
    if(disposed)return;
    const machine=selectedMachine(data);
    if(!machine)return;
    const projectionMode=projectionModeOf(data,machine),strict=projectionMode==="strict-exact",signature=signatureOf(machine,projectionMode);
    let changed=lastSignature!==signature;
    if(stage.dataset.rtaiProjectionMode!==projectionMode){stage.dataset.rtaiProjectionMode=projectionMode;changed=true}
    const liveIds=new Set();
    (machine.transitions||[]).forEach((transition,index)=>{
      const id=text(transition.id)||`T${index+1}`;
      liveIds.add(id);
      const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escapeId(id)}"]`);
      if(cluster)changed=updateCluster(cluster,semanticOf(transition),strict)||changed;
    });
    stage.querySelectorAll(".transition-io-cluster").forEach(cluster=>{if(!liveIds.has(text(cluster.dataset.transitionId)))changed=clearCluster(cluster)||changed});
    lastSignature=signature;
    const wasReady=stage.dataset.rtaiSemanticStatusReady==="true",published=publicationReady(stage);
    stage.dataset.rtaiSemanticStatusReady=published?"true":"pending";
    if(published&&(changed||!wasReady))document.dispatchEvent(new CustomEvent("glyph-transition-semantic-status-ready",{detail:{machine:machine.name,marker:MARKER}}));
  }finally{running=false}
}
function expectedShutdown(error){return disposed||error?.name==="AbortError"||document.visibilityState==="hidden"}
function schedule(delay=0){
  if(disposed)return;
  clearTimeout(timer);
  timer=setTimeout(()=>render().catch(error=>{if(!expectedShutdown(error))console.error("transition semantic status rendering failed",error)}),delay)
}
function invalidate(){cache=null;schedule(0)}
for(const event of["glyph-transition-io-clusters-ready","glyph-state-transition-ir-v4-labels-ready","glyph-transition-enabling-cases-ready","glyph-execution-context-changed","glyph-locale-changed"]){document.addEventListener(event,invalidate)}
document.addEventListener("glyph-transition-layout-transaction-ready",()=>schedule(0));
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;lastSignature="";schedule(0)}});
function dispose(){disposed=true;clearTimeout(timer);controller?.abort()}
window.addEventListener("pagehide",dispose,{once:true});
window.addEventListener("beforeunload",dispose,{once:true});
schedule(0);
})();
</script>
"""


def enhance_transition_semantic_status_ui_html(html: str) -> str:
    """Project native Exact / May / Unknown status onto visible I/O cards."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_transition_semantic_status_ui_html"]
