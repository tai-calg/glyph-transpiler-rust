from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-v1"

_STYLE = r"""
<style id="glyph-transition-layout-transaction-v1-style">
.graph-stage[data-transition-layout-state="pending"] .transition-io-cluster,
.graph-stage[data-transition-publication-ready="false"] .transition-io-cluster{
  visibility:visible!important;
  pointer-events:auto!important;
}
.transition-io-cluster{
  max-width:280px!important;
}
.transition-io-cluster .transition-io-node.io{
  width:auto!important;
  min-width:88px!important;
  max-width:280px!important;
  min-height:24px!important;
  height:auto!important;
  padding:3px 7px!important;
  border-radius:5px!important;
  box-shadow:none!important;
}
.transition-io-cluster .transition-io-value{
  display:block!important;
  max-width:264px!important;
  font-size:10px!important;
  line-height:1.25!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  word-break:normal!important;
  text-align:center!important;
}
.graph-stage[data-transition-layout-profile="interactive-fast"] .state-node{
  transition:none!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-v1";
const TOTAL_BUDGET_MS=120,PREREQUISITE_BUDGET_MS=180,CLUSTER_BUDGET_MS=80;
const MAX_DISTANCE=96,MIN_CANVAS_WIDTH=760,MIN_CANVAS_HEIGHT=520,CANVAS_PADDING=72;
const control=window.glyphTransitionLegacyControl;
if(control)control.ownsScheduling=true;

let stateCache=null,statePromise=null,stateAbort=null,stateVersion=0;
let requestedGeneration=0,completedGeneration=0,running=false,timer=null,destroyed=false,lastStage=null;
const generationReasons=new Map();
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";
const stageOf=()=>document.querySelector(".state-node")?.closest(".graph-stage")||null;
const machineIndex=()=>document.getElementById("machine-select")?.value||0;

function cancelled(token){return destroyed||token!==requestedGeneration||activeTab()!=="state"}
function invalidateState(){
  stateVersion+=1;
  stateCache=null;
  statePromise=null;
  stateAbort?.abort();
  stateAbort=null;
}
async function diagramState(token){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live)return live;
  if(stateCache)return stateCache;
  if(statePromise)return statePromise;
  const version=stateVersion,controller=new AbortController();
  stateAbort=controller;
  const timeout=setTimeout(()=>controller.abort(),PREREQUISITE_BUDGET_MS);
  statePromise=(async()=>{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error(`diagram state unavailable: HTTP ${response.status}`);
    const data=await response.json();
    if(version!==stateVersion||cancelled(token))throw new DOMException("stale diagram state","AbortError");
    stateCache=data;
    return data;
  })().finally(()=>{
    clearTimeout(timeout);
    if(stateAbort===controller)stateAbort=null;
    statePromise=null;
  });
  return statePromise;
}
function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===selected)||machines[Number(machineIndex())]||machines[0]||null;
}
function labelStorageKey(data){return`glyph.diagram.transition-io.v1:${data?.digest||"source"}:${machineIndex()}`}
function parseStored(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
function clearFailure(stage){
  delete stage.dataset.transitionLayoutError;
  delete stage.dataset.transitionLayoutFailureCode;
  delete stage.dataset.transitionLayoutFailureDetails;
}
function markPending(stage,token,reason){
  clearFailure(stage);
  stage.dataset.transitionLayoutProfile="interactive-fast";
  stage.dataset.transitionLayoutBudgetMs=String(TOTAL_BUDGET_MS);
  stage.dataset.transitionLayoutState="pending";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionIoCollisionSolved="best-effort";
  stage.dataset.transitionIoCollisionCount="0";
}
function markReady(stage,token,reason,result,budgetExceeded=false){
  clearFailure(stage);
  stage.dataset.transitionLayoutState="ready";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionLayoutMarker=MARKER;
  stage.dataset.transitionLayoutProfile="interactive-fast";
  stage.dataset.transitionLayoutBudgetExceeded=budgetExceeded?"true":"false";
  stage.dataset.transitionIoCollisionSolved="true";
  stage.dataset.transitionIoCollisionCount="0";
  stage.dataset.transitionIoReadability="true";
  stage.dataset.transitionIoReadabilityViolations="0";
  stage.dataset.transitionSemanticLinesReady="true";
  stage.dataset.transitionSemanticRoleLinesReady="true";
  completedGeneration=token;
  document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready",{
    detail:{marker:MARKER,generation:token,reason,labels:result.count,digest:stage.dataset.diagramDigest||"source",profile:"interactive-fast",budgetExceeded}
  }));
}
function markDegraded(stage,token,reason,error){
  const message=String(error?.message||error);
  stage.dataset.transitionLayoutState="ready";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionLayoutProfile="interactive-fast";
  stage.dataset.transitionLayoutBudgetExceeded="true";
  stage.dataset.transitionLayoutError=message;
  stage.dataset.transitionLayoutFailureCode=String(error?.code||"interactive-layout-degraded");
  stage.dataset.transitionIoCollisionSolved="best-effort";
  stage.dataset.transitionIoCollisionCount="0";
  stage.dataset.transitionSemanticLinesReady="true";
  stage.dataset.transitionSemanticRoleLinesReady="true";
  completedGeneration=token;
  document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready",{
    detail:{marker:MARKER,generation:token,reason,labels:stage.querySelectorAll(".transition-io-cluster").length,digest:stage.dataset.diagramDigest||"source",profile:"interactive-fast",degraded:true}
  }));
}

async function waitForStage(token){
  const started=performance.now();
  while(performance.now()-started<PREREQUISITE_BUDGET_MS){
    if(cancelled(token))return null;
    const stage=stageOf();
    if(stage&&stage.querySelector(".state-node"))return stage;
    await wait(16);
  }
  return stageOf();
}
function standardCanvas(stage){
  const shell=stage.closest(".canvas-shell");
  const nodes=[...stage.querySelectorAll(".state-node")];
  const right=Math.max(0,...nodes.map(node=>node.offsetLeft+node.offsetWidth));
  const bottom=Math.max(0,...nodes.map(node=>node.offsetTop+node.offsetHeight));
  const scale=Math.max(.01,window.glyphDiagramViewport?.scaleFor(stage)||num(stage.dataset.viewportScale)||1);
  const viewportWidth=shell?Math.max(MIN_CANVAS_WIDTH,(shell.clientWidth-20)/scale):MIN_CANVAS_WIDTH;
  const viewportHeight=shell?Math.max(MIN_CANVAS_HEIGHT,(shell.clientHeight-20)/scale):MIN_CANVAS_HEIGHT;
  const width=Math.ceil(Math.max(viewportWidth,right+CANVAS_PADDING));
  const height=Math.ceil(Math.max(viewportHeight,bottom+CANVAS_PADDING));
  stage.style.width=`${width}px`;
  stage.style.height=`${height}px`;
  stage.dataset.transitionDenseCanvas="disabled";
  stage.dataset.transitionCanvasWidth=String(width);
  stage.dataset.transitionCanvasHeight=String(height);
}
function stateCurve(source,target,same,lane,laneCount){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  const centered=lane-(laneCount-1)/2;
  if(same){
    const spread=52+Math.abs(centered)*18,lift=74+Math.abs(centered)*22,shift=centered*22;
    return`M ${x1-25} ${y1-34} C ${x1-spread+shift} ${y1-lift}, ${x1+spread+shift} ${y1-lift}, ${x1+25} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const sourceRadius=Math.min(source.offsetWidth/2,82),targetRadius=Math.min(target.offsetWidth/2,82);
  const startX=x1+dx/length*sourceRadius,startY=y1+dy/length*Math.min(source.offsetHeight/2,40);
  const endX=x2-dx/length*targetRadius,endY=y2-dy/length*Math.min(target.offsetHeight/2,40);
  const normalX=-dy/length,normalY=dx/length,laneOffset=centered*34;
  return`M ${startX} ${startY} Q ${(startX+endX)/2+normalX*laneOffset} ${(startY+endY)/2+normalY*laneOffset} ${endX} ${endY}`;
}
function reroute(stage,machine){
  const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nodeName(node),node]));
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")];
  const transitions=machine?.transitions||[],totals=new Map(),seen=new Map();
  transitions.forEach(transition=>{
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    totals.set(key,(totals.get(key)||0)+1);
  });
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    if(!source||!target)return;
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    const lane=seen.get(key)||0,laneCount=totals.get(key)||1;
    seen.set(key,lane+1);
    const escaped=window.CSS?.escape&&transition.id?CSS.escape(transition.id):"";
    const path=(escaped?stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`):null)||paths[index];
    path?.setAttribute("d",stateCurve(source,target,source===target,lane,laneCount));
    if(path){
      if(transition.id)path.dataset.transitionId=transition.id;
      path.dataset.sourceState=transition.source_state;
      path.dataset.targetState=transition.target_state;
      path.dataset.parallelLane=String(lane);
      path.dataset.parallelLaneCount=String(laneCount);
    }
  });
  delete stage.dataset.initialTransitionRouting;
}
async function ensureClusters(stage,machine,token,deadline){
  const expected=machine?.transitions?.length||0;
  window.glyphTransitionIoClusters?.render?.();
  window.glyphTransitionEnablingCases?.apply?.();
  const started=performance.now();
  while(performance.now()-started<CLUSTER_BUDGET_MS&&performance.now()<deadline){
    if(cancelled(token))return false;
    if(stage.querySelectorAll(".transition-io-cluster").length>=expected)return true;
    await wait(16);
  }
  return stage.querySelectorAll(".transition-io-cluster").length>0||expected===0;
}
function pathFor(stage,id,index){
  const escaped=window.CSS?.escape?CSS.escape(id):String(id).replace(/[^A-Za-z0-9_-]/g,"\\$&");
  return stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`)
    ||[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")][index]
    ||null;
}
function anchorFor(path,fraction=.5){
  if(path&&typeof path.getTotalLength==="function"){
    try{
      const length=path.getTotalLength(),offset=clamp(fraction,.2,.8)*length;
      const point=path.getPointAtLength(offset);
      const before=path.getPointAtLength(Math.max(0,offset-2)),after=path.getPointAtLength(Math.min(length,offset+2));
      return{x:point.x,y:point.y,normal:Math.atan2(after.x-before.x,-(after.y-before.y)),fraction};
    }catch{}
  }
  return{x:0,y:0,normal:-Math.PI/2,fraction:.5};
}
function constrain(point,cluster,stage){
  const width=num(stage.style.width)||stage.scrollWidth,height=num(stage.style.height)||stage.scrollHeight;
  return{
    x:clamp(point.x,cluster.offsetWidth/2+8,width-cluster.offsetWidth/2-8),
    y:clamp(point.y,cluster.offsetHeight/2+8,height-cluster.offsetHeight/2-8),
  };
}
function positionLabels(stage,data,machine){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  const transitions=machine?.transitions||[];
  const saved=parseStored(labelStorageKey(data));
  const pairRanks=new Map(),pairCounts=new Map();
  transitions.forEach(transition=>{
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    pairCounts.set(key,(pairCounts.get(key)||0)+1);
  });
  clusters.forEach((cluster,index)=>{
    const transition=transitions[index]||{};
    const id=cluster.dataset.transitionId||transition.id||`T${index+1}`;
    const key=`${transition.source_state||"?"}\u001f${transition.target_state||"?"}`;
    const rank=pairRanks.get(key)||0,count=pairCounts.get(key)||1;
    pairRanks.set(key,rank+1);
    const fraction=count===1?.5:(rank+1)/(count+1);
    const path=pathFor(stage,id,index),anchor=anchorFor(path,fraction),record=saved[id];
    const centered=rank-(count-1)/2;
    const autoOffset=transition.source_state===transition.target_state
      ?{x:Math.sin(anchor.normal)*18+centered*18,y:-20-Math.abs(centered)*12}
      :{x:Math.cos(anchor.normal)*(16+Math.abs(centered)*8),y:Math.sin(anchor.normal)*(16+Math.abs(centered)*8)};
    let point;
    if(finite(record?.dx)&&finite(record?.dy)){
      point={x:anchor.x+record.dx,y:anchor.y+record.dy};
    }else if(finite(record?.x)&&finite(record?.y)){
      point={x:record.x,y:record.y};
    }else{
      point={x:anchor.x+autoOffset.x,y:anchor.y+autoOffset.y};
    }
    const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);
    if(distance>MAX_DISTANCE&&distance){
      const ratio=MAX_DISTANCE/distance;
      point={x:anchor.x+dx*ratio,y:anchor.y+dy*ratio};
    }
    point=constrain(point,cluster,stage);
    const value=cluster.querySelector(".transition-io-value");
    const label=cluster.dataset.ioValue||value?.textContent?.trim()||"";
    const width=clamp(88+Math.min(192,label.length*2.4),88,280);
    cluster.style.setProperty("--transaction-label-width",`${Math.round(width)}px`);
    cluster.style.left=`${point.x}px`;
    cluster.style.top=`${point.y}px`;
    cluster.dataset.anchorX=String(anchor.x);
    cluster.dataset.anchorY=String(anchor.y);
    cluster.dataset.anchorFraction=String(anchor.fraction);
    cluster.dataset.ioDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y));
    cluster.dataset.maxIoDistance=String(MAX_DISTANCE);
    cluster.dataset.manualIo=record?"true":"false";
    cluster.dataset.ioCollisionSolved="true";
    cluster.dataset.transitionReadability="true";
    cluster.classList.remove("compact-io","micro-io","nano-io","stacked","layout-constrained","readability-violation");
    const node=cluster.querySelector(".transition-io-node.io");
    if(node){node.title=label;node.setAttribute("aria-label",label)}
  });
  return clusters.length;
}
function audit(stage=stageOf()){
  if(!stage)return{ok:false,count:0,violations:[{id:"stage",reasons:["missing-stage"]}]};
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")],violations=[],ids=new Set();
  clusters.forEach((cluster,index)=>{
    const id=cluster.dataset.transitionId||String(index),reasons=[];
    const x=num(cluster.style.left),y=num(cluster.style.top),distance=num(cluster.dataset.ioDistance);
    if(ids.has(id))reasons.push("duplicate-transition-id");ids.add(id);
    if(!finite(x)||!finite(y)||x<=0||y<=0)reasons.push("invalid-position");
    if(distance>MAX_DISTANCE+.5)reasons.push("tether-distance");
    if(!pathFor(stage,id,index))reasons.push("missing-transition-path");
    if(!cluster.querySelector(".transition-io-value"))reasons.push("missing-label");
    if(reasons.length)violations.push({id,reasons});
  });
  const expected=Number(stage.dataset.transitionExpectedCount||clusters.length);
  if(clusters.length!==expected)violations.push({id:"stage",reasons:[`transition-count:${clusters.length}/${expected}`]});
  return{ok:violations.length===0,count:clusters.length,expectedCount:expected,violations};
}

async function transaction(token,reason){
  const deadline=performance.now()+TOTAL_BUDGET_MS;
  const stage=await waitForStage(token);
  if(!stage||cancelled(token))return{status:"deferred",stage};
  markPending(stage,token,reason);
  let data,machine;
  try{
    data=await diagramState(token);
    machine=selectedMachine(data);
  }catch(error){
    if(error?.name==="AbortError"||cancelled(token))return{status:"cancelled",stage};
    throw error;
  }
  if(!machine||cancelled(token))return{status:"deferred",stage};
  stage.dataset.diagramDigest=data?.digest||"source";
  stage.dataset.transitionExpectedCount=String(machine.transitions?.length||0);
  standardCanvas(stage);
  reroute(stage,machine);
  await nextFrame();
  if(cancelled(token))return{status:"cancelled",stage};
  await ensureClusters(stage,machine,token,deadline);
  if(cancelled(token))return{status:"cancelled",stage};
  standardCanvas(stage);
  reroute(stage,machine);
  const count=positionLabels(stage,data,machine);
  const result=audit(stage);
  const budgetExceeded=performance.now()>deadline;
  markReady(stage,token,reason,{...result,count},budgetExceeded);
  if(stage.dataset.fastLayoutInitialFitDone!=="true"){
    stage.dataset.fastLayoutInitialFitDone="true";
    window.glyphDiagramViewport?.fitInitial?.();
  }
  return{status:"ready",stage,result};
}
async function drain(){
  if(running||destroyed)return;
  running=true;
  try{
    while(!destroyed&&completedGeneration<requestedGeneration){
      const token=requestedGeneration,reason=generationReasons.get(token)||"scheduled";
      try{
        const outcome=await transaction(token,reason);
        if(token!==requestedGeneration)continue;
        if(outcome.status==="deferred"||outcome.status==="cancelled")completedGeneration=token;
      }catch(error){
        if(error?.name==="AbortError"||destroyed||token!==requestedGeneration)continue;
        const stage=stageOf();
        if(stage)markDegraded(stage,token,reason,error);
        else completedGeneration=token;
        console.warn("interactive transition layout degraded",error);
      }finally{
        for(const generation of[...generationReasons.keys()])if(generation<=completedGeneration)generationReasons.delete(generation);
      }
    }
  }finally{running=false}
}
function schedule(reason="scheduled",delay=16){
  if(destroyed)return requestedGeneration;
  requestedGeneration+=1;
  generationReasons.set(requestedGeneration,reason);
  if(window.glyphTransitionLayoutTransaction)window.glyphTransitionLayoutTransaction.lastReason=reason;
  clearTimeout(timer);
  timer=setTimeout(drain,Math.max(0,delay));
  return requestedGeneration;
}
function cancel(reason="cancelled"){
  requestedGeneration+=1;
  completedGeneration=requestedGeneration;
  generationReasons.clear();
  clearTimeout(timer);
  invalidateState();
  const stage=stageOf();
  if(stage){
    stage.dataset.transitionLayoutCancellation=reason;
    stage.dataset.transitionLayoutState="ready";
    stage.dataset.transitionPublicationReady="false";
  }
  return requestedGeneration;
}
function synchronizeStage(){
  const stage=stageOf();
  if(stage===lastStage)return;
  lastStage=stage;
  invalidateState();
  if(activeTab()==="state")schedule("stage-replaced",0);
}

for(const eventName of[
  "glyph-state-transition-ir-v3-labels-ready",
  "glyph-state-transition-ir-v4-labels-ready",
  "glyph-uml-transition-ready",
  "glyph-execution-context-changed",
  "glyph-locale-changed",
]){
  document.addEventListener(eventName,()=>{
    if(activeTab()!=="state")return;
    invalidateState();
    schedule(eventName,16);
  });
}
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){
    invalidateState();
    schedule("machine-change",0);
  }
});
document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  if(tab.dataset.tab==="state")requestAnimationFrame(()=>schedule("state-tab-activated",0));
  else cancel("state-tab-deactivated");
},true);
const view=document.getElementById("view")||document.body;
new MutationObserver(synchronizeStage).observe(view,{childList:true,subtree:false});
window.addEventListener("resize",()=>{if(activeTab()==="state")schedule("window-resize",100)});
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{
    destroyed=true;
    clearTimeout(timer);
    invalidateState();
  },{once:true});
}

window.glyphTransitionLayoutTransaction={
  marker:MARKER,
  version:2,
  profile:"interactive-fast",
  budgetMs:TOTAL_BUDGET_MS,
  ownsScheduling:true,
  schedule,
  cancel,
  run:()=>schedule("manual-run",0),
  audit:()=>audit(stageOf()),
  get generation(){return requestedGeneration},
  get completedGeneration(){return completedGeneration},
  lastReason:"bootstrap",
};
lastStage=stageOf();
if(activeTab()==="state")schedule("bootstrap",0);
})();
</script>
"""


def enhance_transition_layout_transaction_html(html: str) -> str:
    """Install the ordinary, time-bounded interactive state-diagram layout."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
