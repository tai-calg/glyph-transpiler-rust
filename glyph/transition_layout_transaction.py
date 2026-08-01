from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-v1"

_STYLE = r"""
<style id="glyph-transition-layout-transaction-v1-style">
.graph-stage[data-transition-layout-state="pending"] .transition-io-cluster,
.graph-stage[data-transition-publication-ready="false"] .transition-io-cluster{
  visibility:visible!important;
  pointer-events:auto!important;
}
.graph-stage[data-transition-layout-profile="ordinary"] .state-node{
  transition:none!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-v1";
const TRANSACTION_DEADLINE_MS=48;
const MAX_FRAME_BUDGET=2;
const MAX_RETRIES=0;
let generation=0,completedGeneration=0,destroyed=false,timer=0,lastPromise=Promise.resolve({ok:true,skipped:true});
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
const stageOf=()=>document.querySelector(".state-node")?.closest(".graph-stage")||null;

function clearFailure(stage){
  delete stage.dataset.transitionLayoutError;
  delete stage.dataset.transitionLayoutFailureCode;
  delete stage.dataset.transitionLayoutFailureDetails;
}
function markReady(stage,token,reason,degraded=false){
  clearFailure(stage);
  stage.dataset.transitionLayoutState="ready";
  stage.dataset.transitionLayoutReady="true";
  stage.dataset.transitionPublicationReady="true";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionLayoutMarker=MARKER;
  stage.dataset.transitionLayoutProfile="ordinary";
  stage.dataset.transitionLayoutMode="base";
  stage.dataset.transitionDenseCanvas="disabled";
  stage.dataset.transitionLayoutBudgetMs=String(TRANSACTION_DEADLINE_MS);
  stage.dataset.transitionLayoutBudgetExceeded=degraded?"true":"false";
  stage.setAttribute("data-transition-layout-ready","true");
  stage.setAttribute("data-transition-publication-ready","true");
  completedGeneration=Math.max(completedGeneration,token);
  document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready",{
    detail:{marker:MARKER,generation:token,reason,profile:"ordinary",degraded}
  }));
  return {ok:true,generation:token,reason,degraded};
}
function nextFrame(deadline){
  return new Promise(resolve=>{
    let settled=false;
    const finish=()=>{if(settled)return;settled=true;clearTimeout(timeout);resolve()};
    const timeout=setTimeout(finish,Math.max(0,deadline-performance.now()));
    requestAnimationFrame(finish);
  });
}
async function run(token,reason){
  const started=performance.now();
  if(destroyed||token!==generation)return{ok:false,cancelled:true,generation:token};
  if(activeTab()!=="state"){
    completedGeneration=Math.max(completedGeneration,token);
    return{ok:true,skipped:true,generation:token,reason};
  }
  const deadline=started+TRANSACTION_DEADLINE_MS;
  for(let frame=0;frame<=MAX_FRAME_BUDGET;frame+=1){
    if(destroyed||token!==generation)return{ok:false,cancelled:true,generation:token};
    const stage=stageOf();
    if(stage&&stage.querySelector(".state-node")){
      window.glyphTransitionIoClusters?.reroute?.(stage);
      return markReady(stage,token,reason,false);
    }
    if(frame<MAX_FRAME_BUDGET&&performance.now()<deadline)await nextFrame(deadline);
  }
  const stage=stageOf();
  if(stage)return markReady(stage,token,reason,true);
  completedGeneration=Math.max(completedGeneration,token);
  return{ok:false,missingStage:true,generation:token,reason};
}
function schedule(reason="scheduled",delay=0){
  if(destroyed)return generation;
  const token=++generation;
  clearTimeout(timer);
  const boundedDelay=Math.max(0,Math.min(Number(delay)||0,TRANSACTION_DEADLINE_MS));
  lastPromise=new Promise(resolve=>{
    timer=setTimeout(()=>run(token,reason).then(resolve),boundedDelay);
  });
  return token;
}
function requestAndWait(reason="requested"){
  schedule(reason,0);
  return lastPromise;
}
function cancel(reason="cancelled"){
  generation+=1;
  completedGeneration=generation;
  clearTimeout(timer);
  const stage=stageOf();
  if(stage){
    stage.dataset.transitionLayoutReason=reason;
    stage.dataset.transitionLayoutState="ready";
    stage.dataset.transitionLayoutReady="true";
    stage.dataset.transitionPublicationReady="true";
    stage.dataset.transitionDenseCanvas="disabled";
  }
  return generation;
}
function audit(){
  const stage=stageOf();
  return{
    ok:Boolean(stage&&stage.querySelector(".state-node")),
    profile:"ordinary",
    geometryOwner:"base-renderer",
    nodeCount:stage?.querySelectorAll(".state-node").length||0,
    transitionCount:stage?.querySelectorAll("path.state-transition-path").length||0,
  };
}

const view=document.getElementById("view");
if(view)new MutationObserver(()=>{
  if(activeTab()==="state")schedule("view-rendered",0);
}).observe(view,{childList:true});
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select")schedule("machine-change",0);
});
document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  if(tab.dataset.tab==="state")requestAnimationFrame(()=>schedule("state-tab-activated",0));
  else cancel("state-tab-deactivated");
},true);
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{destroyed=true;clearTimeout(timer);generation+=1},{once:true});
}
const control=window.glyphTransitionLegacyControl;
if(control)control.ownsScheduling=true;
window.glyphTransitionLayoutTransaction={
  marker:MARKER,
  version:8,
  profile:"ordinary",
  budgetMs:TRANSACTION_DEADLINE_MS,
  maxFrames:MAX_FRAME_BUDGET,
  maxRetries:MAX_RETRIES,
  schedule,
  request:schedule,
  requestAndWait,
  cancel,
  audit,
  get generation(){return generation},
  get completedGeneration(){return completedGeneration},
};
schedule("initial",0);
})();
</script>
"""


def enhance_transition_layout_transaction_html(html: str) -> str:
    """Install a bounded readiness transaction without changing diagram geometry."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
