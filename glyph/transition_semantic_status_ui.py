from __future__ import annotations


_MARKER = "glyph-transition-semantic-status-ui-v1"

_STYLE = r"""
<style id="glyph-transition-semantic-status-ui-v1-style">
.transition-io-cluster .rtai-semantic-badge{
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
  background:var(--panel);
  box-shadow:0 1px 5px rgba(15,23,42,.18);
  font:700 9px/1.25 ui-sans-serif,system-ui,sans-serif;
  letter-spacing:.02em;
  white-space:nowrap;
  pointer-events:none;
}
.graph-stage[data-rtai-projection-mode="strict-exact"]
  .transition-io-cluster .rtai-semantic-badge,
.transition-io-cluster:hover .rtai-semantic-badge,
.transition-io-cluster.selected-io .rtai-semantic-badge{
  display:inline-flex;
}
.rtai-semantic-badge.exact{color:#15803d}
.rtai-semantic-badge.may{color:#a16207}
.rtai-semantic-badge.unknown{color:#6b7280}
.theme-monochrome .rtai-semantic-badge{
  color:#111!important;
  background:#fff!important;
  border-color:#111!important;
  box-shadow:none!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-semantic-status-ui-v1-script">
(()=>{
const MARKER="glyph-transition-semantic-status-ui-v1";
let cache=null,timer=null,running=false,lastSignature="";
const text=value=>String(value??"").trim();
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function semanticOf(transition){const raw=transition?.rtai_semantic_status||{},status=["exact","may","unknown"].includes(text(raw.status))?text(raw.status):"unknown";return{status,label:status==="exact"?"Exact":status==="may"?"May":"Unknown",reason:text(raw.reason)||"native Evidence status is unavailable"}}
function escapeId(value){return window.CSS?.escape?CSS.escape(value):value.replace(/[^A-Za-z0-9_-]/g,"\\$&")}
function updateCluster(cluster,semantic){
  let changed=false;
  let badge=cluster.querySelector(":scope > .rtai-semantic-badge");
  if(!badge){badge=document.createElement("span");badge.className="rtai-semantic-badge";badge.setAttribute("aria-hidden","true");cluster.appendChild(badge);changed=true}
  const className=`rtai-semantic-badge ${semantic.status}`,title=`${semantic.label}: ${semantic.reason}`;
  if(badge.className!==className){badge.className=className;changed=true}
  if(badge.textContent!==semantic.label){badge.textContent=semantic.label;changed=true}
  if(badge.dataset.rtaiSemanticStatus!==semantic.status){badge.dataset.rtaiSemanticStatus=semantic.status;changed=true}
  if(badge.dataset.rtaiSemanticReason!==semantic.reason){badge.dataset.rtaiSemanticReason=semantic.reason;changed=true}
  if(badge.title!==title){badge.title=title;changed=true}
  if(cluster.dataset.rtaiSemanticStatus!==semantic.status){cluster.dataset.rtaiSemanticStatus=semantic.status;changed=true}
  if(cluster.dataset.rtaiSemanticReason!==semantic.reason){cluster.dataset.rtaiSemanticReason=semantic.reason;changed=true}
  return changed;
}
function signatureOf(machine){return[window.GlyphI18n?.locale||document.documentElement.lang||"ja",machine?.name||"",machine?.analysis?.evidence_projection_mode||"shadow",...(machine?.transitions||[]).map((transition,index)=>{const semantic=semanticOf(transition);return[text(transition.id)||`T${index+1}`,semantic.status,semantic.reason].join("\u001f")})].join("\u001e")}
async function render(){
  if(running)return;
  const stage=document.querySelector(".state-node")?.closest(".graph-stage");
  if(!stage||stage.dataset.transitionIoClustersReady!=="true")return;
  running=true;
  try{
    const data=await state(),machine=selectedMachine(data);
    if(!machine)return;
    const projectionMode=text(machine?.analysis?.evidence_projection_mode)||"shadow",signature=signatureOf(machine);
    let changed=lastSignature!==signature;
    if(stage.dataset.rtaiProjectionMode!==projectionMode){stage.dataset.rtaiProjectionMode=projectionMode;changed=true}
    const liveIds=new Set();
    (machine.transitions||[]).forEach((transition,index)=>{
      const id=text(transition.id)||`T${index+1}`;
      liveIds.add(id);
      const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escapeId(id)}"]`);
      if(cluster)changed=updateCluster(cluster,semanticOf(transition))||changed;
    });
    stage.querySelectorAll(".transition-io-cluster").forEach(cluster=>{
      if(!liveIds.has(text(cluster.dataset.transitionId))){const badge=cluster.querySelector(":scope > .rtai-semantic-badge");if(badge){badge.remove();changed=true}}
    });
    lastSignature=signature;
    stage.dataset.rtaiSemanticStatusReady="true";
    if(changed)document.dispatchEvent(new CustomEvent("glyph-transition-semantic-status-ready",{detail:{machine:machine.name,marker:MARKER}}));
  }finally{running=false}
}
function schedule(delay=0){clearTimeout(timer);timer=setTimeout(()=>render().catch(error=>console.error("transition semantic status rendering failed",error)),delay)}
for(const event of["glyph-transition-io-clusters-ready","glyph-state-transition-ir-v4-labels-ready","glyph-execution-context-changed","glyph-locale-changed"]){document.addEventListener(event,()=>{cache=null;schedule(0)})}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;lastSignature="";schedule(0)}});
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
