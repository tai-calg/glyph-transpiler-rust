from __future__ import annotations


_MARKER = "glyph-transition-enabling-cases-v1"

_SCRIPT = r'''
<script id="glyph-transition-enabling-cases-v1-script">
(()=>{
const MARKER="glyph-transition-enabling-cases-v1";
const STATE_REQUEST_TIMEOUT_MS=48;
let cache=null,timer=0,running=false,queued=false,disposed=false,controller=null;
const text=value=>String(value??"").trim();
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
const stageOf=()=>document.querySelector(".state-node")?.closest(".graph-stage")||null;
async function state(){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live){cache=live;return live}
  if(cache)return cache;
  controller?.abort();
  controller=new AbortController();
  const timeout=setTimeout(()=>controller?.abort(),STATE_REQUEST_TIMEOUT_MS);
  try{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error("diagram state unavailable");
    return cache=await response.json();
  }finally{clearTimeout(timeout)}
}
function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===name)||machines[0]||null;
}
function actionOf(transition){
  const action=window.GlyphExecutionContext?.actionFor?.(transition)??transition?.action;
  if(typeof action==="string")return text(action);
  return text(action?.display)||text(action?.expression);
}
function casesOf(transition){return Array.isArray(transition?.enabling_cases)?transition.enabling_cases:[]}
function inputOf(item){
  const input=item?.input_pattern;
  return input?`${input.confidence==="fallback"?"? ":""}${text(input.display)||text(input.expression)}`:"";
}
function guardOf(item){return text(item?.guard?.display)||text(item?.guard?.expression).replace(/^true$/i,"")}
function lineOf(item,action){
  const input=inputOf(item),guard=guardOf(item),left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`.trim();
  return`${left}${action?`${left?" ":""}➞ ${action}`:""}`.trim();
}
function update(cluster,transition){
  const cases=casesOf(transition);
  if(!cases.length)return false;
  const action=actionOf(transition),lines=cases.map(item=>lineOf(item,action)).filter(Boolean);
  const value=cluster.querySelector(".transition-io-value");
  if(!value)return false;
  const signature=JSON.stringify([cases,action,window.GlyphExecutionContext?.signature?.()||""]);
  if(cluster.dataset.enablingCaseSignature===signature
    &&cluster.dataset.ioValue===lines.join(" || "))return false;
  value.replaceChildren(...lines.map(line=>{
    const span=document.createElement("span");
    span.className="transition-semantic-line transition-role-line enabling-case-line";
    span.textContent=line;
    return span;
  }));
  const first=cases[0]||{};
  cluster.dataset.inputValue=inputOf(first);
  cluster.dataset.guardValue=guardOf(first);
  cluster.dataset.actionValue=action;
  cluster.dataset.outputValue=action;
  cluster.dataset.ioValue=lines.join(" || ");
  cluster.dataset.fullLabel=lines.join("\n");
  cluster.dataset.enablingCaseCount=String(cases.length);
  cluster.dataset.legacyProjectionLossy=String(Boolean(transition?.legacy_projection_lossy));
  cluster.dataset.enablingCaseSignature=signature;
  cluster.title=lines.join("\n");
  cluster.setAttribute("aria-label",lines.join("; "));
  cluster.classList.toggle("multiple-enabling-cases",cases.length>1);
  return true;
}
async function apply(){
  if(disposed||activeTab()!=="state")return{ok:false,skipped:true};
  if(running){queued=true;return{ok:false,queued:true}}
  const stage=stageOf();
  if(!stage||stage.dataset.transitionIoClustersReady!=="true")return{ok:false,missingStage:true};
  running=true;
  try{
    const data=await state();
    if(disposed||!stage.isConnected)return{ok:false,cancelled:true};
    const machine=selectedMachine(data);
    if(!machine)return{ok:false,missingMachine:true};
    let changed=0;
    (machine.transitions||[]).forEach((transition,index)=>{
      const id=transition.id||`T${index+1}`;
      const escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&");
      const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
      if(cluster&&update(cluster,transition))changed+=1;
    });
    stage.dataset.transitionEnablingCasesReady="true";
    document.dispatchEvent(new CustomEvent("glyph-transition-enabling-cases-ready",{detail:{marker:MARKER,changed}}));
    return{ok:true,changed};
  }finally{
    running=false;
    if(queued){queued=false;schedule(0)}
  }
}
function markPending(){
  const stage=stageOf();
  if(stage)stage.dataset.transitionEnablingCasesReady="pending";
}
function schedule(delay=0){
  if(disposed)return;
  clearTimeout(timer);
  timer=setTimeout(()=>apply().catch(error=>{
    if(error?.name!=="AbortError"&&!disposed)console.error("enabling-case rendering failed",error);
  }),Math.max(0,Math.min(Number(delay)||0,STATE_REQUEST_TIMEOUT_MS)));
}
for(const event of["glyph-transition-io-clusters-ready","glyph-locale-changed","glyph-state-transition-ir-v3-labels-ready","glyph-execution-context-changed"]){
  document.addEventListener(event,()=>{cache=null;markPending();schedule(0)});
}
document.addEventListener("change",event=>{
  if(event.target?.id!=="machine-select")return;
  cache=null;
  markPending();
  schedule(0);
});
const view=document.getElementById("view");
if(view)new MutationObserver(()=>{if(activeTab()==="state"){markPending();schedule(0)}}).observe(view,{childList:true});
function dispose(){disposed=true;clearTimeout(timer);controller?.abort()}
window.addEventListener("pagehide",dispose,{once:true});
window.addEventListener("beforeunload",dispose,{once:true});
window.glyphTransitionEnablingCases={marker:MARKER,version:4,apply};
schedule(0);
})();
</script>
'''


def enhance_transition_enabling_case_rendering_html(html: str) -> str:
    """Render Input Pattern and Guard from StateTransitionIR without polling."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
