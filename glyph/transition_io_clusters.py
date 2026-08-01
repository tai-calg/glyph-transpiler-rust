from __future__ import annotations


_MARKER = "glyph-transition-io-clusters-v1"

_STYLE = r"""
<style id="glyph-transition-io-clusters-v1-style">
.edge-label.transition-io-source{
  visibility:hidden!important;
  opacity:0!important;
  pointer-events:none!important;
}
.transition-io-cluster{
  position:absolute;
  transform:translate(-50%,-50%);
  z-index:12;
  display:flex;
  align-items:center;
  justify-content:center;
  max-width:280px;
  cursor:grab;
  touch-action:none;
  user-select:none;
}
.transition-io-cluster.dragging-io{cursor:grabbing;z-index:32}
.transition-io-cluster.selected-io{outline:2px solid var(--blue);outline-offset:3px;border-radius:9px}
.transition-io-main{display:flex;align-items:center;justify-content:center}
.transition-io-node.io{
  width:auto;
  min-width:88px;
  max-width:280px;
  min-height:24px;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:3px 7px;
  border:1px solid var(--line);
  border-radius:6px;
  background:var(--panel);
  box-shadow:0 3px 10px rgba(0,0,0,.18);
  overflow:hidden;
}
.transition-io-value{
  max-width:264px;
  font:700 9px/1.25 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--text);
  white-space:normal!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  text-align:center;
}
.transition-io-cluster.provisional-trigger .transition-io-node.io{
  border-style:dashed;
  border-color:rgba(231,191,98,.86);
  background:rgba(231,191,98,.10);
}
.transition-io-cluster.unclassified-condition .transition-io-node.io{
  border-style:dotted;
  border-color:rgba(231,191,98,.75);
}
.transition-io-cluster.failure-transition .transition-io-node.io{
  border-color:rgba(255,122,139,.8);
}
.transition-io-cluster.rtai-semantic-exact .transition-io-node.io{border-color:#15803d}
.transition-io-cluster.rtai-semantic-may .transition-io-node.io{border-color:#a16207}
.transition-io-cluster.rtai-semantic-unknown .transition-io-node.io{border-color:#6b7280}
.theme-monochrome .transition-io-node.io{
  background:#fff!important;
  border-color:#111!important;
  color:#111!important;
  box-shadow:none!important;
}
.theme-monochrome .transition-io-value{color:#111!important}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-io-clusters-v1-script">
(()=>{
const MARKER="glyph-transition-io-clusters-v1";
const RENDER_BUDGET_MS=16;
const STATE_REQUEST_TIMEOUT_MS=48;
const MAX_DISTANCE=96;
const AUTO_OFFSET=18;
const LANE_GAP=34;
let cache=null,running=false,queued=false,destroyed=false,generation=0,raf=0;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const finite=value=>Number.isFinite(value);
const text=value=>String(value??"").trim();
const esc=value=>String(value??"").replace(/[&<>\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[ch]));
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
const stageOf=()=>document.querySelector(".state-node")?.closest(".graph-stage")||null;

async function diagramState(){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live){cache=live;return live}
  if(cache)return cache;
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),STATE_REQUEST_TIMEOUT_MS);
  try{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error(`diagram state unavailable: HTTP ${response.status}`);
    cache=await response.json();
    return cache;
  }finally{
    clearTimeout(timeout);
  }
}
function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===selected)||machines[Number(document.getElementById("machine-select")?.value||0)]||machines[0]||null;
}
function triggerOf(transition){
  const trigger=transition?.trigger;
  if(trigger&&text(trigger.display))return{
    display:text(trigger.display),
    role:text(trigger.role)||"confirmed-trigger",
    roots:trigger.provenance_roots||[],
    path:trigger.dataflow_path||[],
  };
  const event=text(transition?.event);
  if(!event)return null;
  return{display:event.replace(/^\?\s*/,""),role:event.startsWith("? ")?"provisional-trigger":"confirmed-trigger",roots:[],path:[]};
}
function guardsOf(transition){
  if(Array.isArray(transition?.guards))return transition.guards.map(text).filter(Boolean);
  const guard=text(transition?.guard);
  return guard?[guard]:[];
}
function unknownOf(transition){return(transition?.unclassified_conditions||[]).map(text).filter(Boolean)}
function inputOf(transition){
  const trigger=triggerOf(transition),unknown=unknownOf(transition);
  if(trigger)return`${trigger.role==="provisional-trigger"?"? ":""}${trigger.display}`;
  if(unknown.length)return`? ${unknown.join(" & ")}`;
  const raw=text(transition?.event)||text(transition?.condition_raw);
  if(!raw)return"otherwise";
  return raw;
}
function projectionOf(transition){
  return window.GlyphExecutionContext?.projectionFor?.(transition)||{action:transition?.action,status:"auto"};
}
function actionOf(transition){
  const action=window.GlyphExecutionContext?.actionFor?.(transition)??projectionOf(transition).action;
  if(typeof action==="string")return text(action);
  if(action?.kind==="effect-trace"&&Array.isArray(action.events)){
    return action.events.map(event=>text(event?.expression)||text(event?.display)||text(event?.operation)).filter(Boolean).join("; ");
  }
  return text(action?.display)||text(action?.expression);
}
function semanticOf(transition){
  const status=text(transition?.rtai_semantic_status?.status);
  return["exact","may","unknown"].includes(status)?status:"unknown";
}
function ioOf(transition){
  const input=inputOf(transition),guard=guardsOf(transition).join(" & "),action=actionOf(transition);
  return`${input}${guard?` [${guard}]`:""}${action?` ➞ ${action}`:""}`;
}
function signatureOf(machine){
  return[
    machine?.name||"",
    window.GlyphI18n?.locale||document.documentElement.lang||"ja",
    window.GlyphExecutionContext?.signature?.()||"auto",
    ...(machine?.transitions||[]).map(item=>[
      item.id||"",
      item.source_state||"",
      item.target_state||"",
      JSON.stringify(item.trigger||null),
      JSON.stringify(item.guards||[]),
      JSON.stringify(item.unclassified_conditions||[]),
      JSON.stringify(item.rtai_semantic_status||null),
      actionOf(item),
    ].join("\u001f")),
  ].join("\u001e");
}
function storageKey(data){
  const digest=data?.digest||"source",index=document.getElementById("machine-select")?.value||0;
  return`glyph.diagram.transition-io.v1:${digest}:${index}`;
}
function parseSaved(data){try{return JSON.parse(localStorage.getItem(storageKey(data))||"{}")||{}}catch{return{}}}
function pathFor(stage,id,index){
  const escaped=window.CSS?.escape?CSS.escape(id):String(id).replace(/[^A-Za-z0-9_-]/g,"\\$&");
  return stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`)
    ||[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")][index]
    ||null;
}
function anchorFor(path,stage){
  if(path&&typeof path.getTotalLength==="function"){
    try{
      const length=path.getTotalLength();
      const offset=length/2;
      const point=path.getPointAtLength(offset);
      const before=path.getPointAtLength(Math.max(0,offset-2));
      const after=path.getPointAtLength(Math.min(length,offset+2));
      const dx=after.x-before.x,dy=after.y-before.y,size=Math.max(1,Math.hypot(dx,dy));
      return{x:point.x,y:point.y,tx:dx/size,ty:dy/size,nx:-dy/size,ny:dx/size,fraction:.5};
    }catch{}
  }
  return{x:stage.clientWidth/2,y:stage.clientHeight/2,tx:1,ty:0,nx:0,ny:-1,fraction:.5};
}
function project(point,anchor){
  const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);
  if(!distance||distance<=MAX_DISTANCE)return point;
  const ratio=MAX_DISTANCE/distance;
  return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio};
}
function constrain(point,cluster,stage){
  const width=Math.max(stage.clientWidth,num(stage.style.width),stage.scrollWidth);
  const height=Math.max(stage.clientHeight,num(stage.style.height),stage.scrollHeight);
  return{
    x:clamp(point.x,cluster.offsetWidth/2+8,Math.max(cluster.offsetWidth/2+8,width-cluster.offsetWidth/2-8)),
    y:clamp(point.y,cluster.offsetHeight/2+8,Math.max(cluster.offsetHeight/2+8,height-cluster.offsetHeight/2-8)),
  };
}
function pairRanks(transitions){
  const totals=new Map(),seen=new Map(),result=[];
  for(const transition of transitions){
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    totals.set(key,(totals.get(key)||0)+1);
  }
  for(const transition of transitions){
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    const rank=seen.get(key)||0,total=totals.get(key)||1;
    seen.set(key,rank+1);
    result.push({rank,total,centered:rank-(total-1)/2});
  }
  return result;
}
function restored(saved,id,anchor){
  const record=saved[id];
  if(finite(record?.dx)&&finite(record?.dy))return{x:anchor.x+record.dx,y:anchor.y+record.dy,manual:true};
  if(finite(record?.x)&&finite(record?.y))return{x:record.x,y:record.y,manual:true};
  return null;
}
function placeCluster(cluster,anchor,lane,saved,id,stage){
  const manual=restored(saved,id,anchor);
  const automatic={
    x:anchor.x+anchor.nx*(AUTO_OFFSET+Math.abs(lane.centered)*5)+anchor.tx*lane.centered*LANE_GAP,
    y:anchor.y+anchor.ny*(AUTO_OFFSET+Math.abs(lane.centered)*5)+anchor.ty*lane.centered*LANE_GAP,
  };
  const point=constrain(project(manual||automatic,anchor),cluster,stage);
  cluster.style.left=`${point.x}px`;
  cluster.style.top=`${point.y}px`;
  cluster.dataset.anchorX=String(anchor.x);
  cluster.dataset.anchorY=String(anchor.y);
  cluster.dataset.anchorFraction=String(anchor.fraction);
  cluster.dataset.ioDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y));
  cluster.dataset.maxIoDistance=String(MAX_DISTANCE);
  cluster.dataset.manualIo=manual?"true":"false";
}
function nodeMap(stage){
  return new Map([...stage.querySelectorAll(".state-node")].map(node=>[
    node.querySelector(".state-name")?.textContent?.trim()||"",
    node,
  ]));
}
function ordinaryPath(source,target,same,index){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  if(same){
    const spread=58+index%3*14;
    return`M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const sx=x1+dx/length*(source.offsetWidth/2+1),sy=y1+dy/length*(source.offsetHeight/2);
  const tx=x2-dx/length*(target.offsetWidth/2+1),ty=y2-dy/length*(target.offsetHeight/2);
  const offset=(index%3-1)*22;
  return`M ${sx} ${sy} Q ${(sx+tx)/2-dy*.1+offset} ${(sy+ty)/2+dx*.1+offset} ${tx} ${ty}`;
}
function tagBaseGeometry(stage,transitions){
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path")];
  const labels=[...stage.querySelectorAll(":scope > .edge-label")];
  transitions.forEach((transition,index)=>{
    const id=transition.id||`T${index+1}`;
    const path=paths[index],label=labels[index];
    if(path){
      path.classList.add("state-transition-path");
      path.dataset.transitionId=id;
      path.dataset.sourceState=transition.source_state||"";
      path.dataset.targetState=transition.target_state||"";
      path.classList.toggle("failure-transition",transition.outcome==="failure");
    }
    if(label){
      label.classList.add("transition-label","transition-io-source");
      label.dataset.transitionId=id;
      label.setAttribute("aria-hidden","true");
    }
  });
}
function reroute(stage=stageOf(),machine=null){
  if(!stage)return false;
  const data=typeof snapshot==="object"&&snapshot?snapshot:cache;
  const selected=machine||selectedMachine(data);
  if(!selected)return false;
  const transitions=selected.transitions||[],nodes=nodeMap(stage);
  tagBaseGeometry(stage,transitions);
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    const path=pathFor(stage,transition.id||`T${index+1}`,index);
    if(source&&target&&path)path.setAttribute("d",ordinaryPath(source,target,source===target,index));
  });
  arrange(stage,data,selected);
  return true;
}
function clusterMarkup(value){
  return`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${esc(value)}</span></div></div>`;
}
function focus(id,active){
  document.querySelectorAll(`[data-transition-id="${id}"]`).forEach(item=>item.classList.toggle("transition-focus",active));
}
function bindCluster(cluster){
  if(cluster.dataset.ioDragReady==="true")return;
  cluster.dataset.ioDragReady="true";
  cluster.dataset.interactionOwner="glyph-transition-layout-interaction-adapter-v4";
  cluster.addEventListener("mouseenter",()=>focus(cluster.dataset.transitionId,true));
  cluster.addEventListener("mouseleave",()=>focus(cluster.dataset.transitionId,false));
}
function updateCluster(cluster,transition,id,line){
  const value=ioOf(transition);
  if(cluster.dataset.ioValue!==value)cluster.innerHTML=clusterMarkup(value);
  const trigger=triggerOf(transition),unknown=unknownOf(transition).length>0,semantic=semanticOf(transition);
  cluster.dataset.transitionId=id;
  cluster.dataset.line=String(line||0);
  cluster.dataset.inputValue=inputOf(transition);
  cluster.dataset.guardValue=guardsOf(transition).join(" & ");
  cluster.dataset.actionValue=actionOf(transition);
  cluster.dataset.outputValue=actionOf(transition);
  cluster.dataset.ioValue=value;
  cluster.dataset.fullLabel=value;
  cluster.dataset.rtaiSemanticStatus=semantic;
  cluster.classList.toggle("provisional-trigger",trigger?.role==="provisional-trigger");
  cluster.classList.toggle("unclassified-condition",unknown);
  cluster.classList.toggle("failure-transition",transition.outcome==="failure");
  for(const status of["exact","may","unknown"])cluster.classList.toggle(`rtai-semantic-${status}`,semantic===status);
  cluster.title=value;
  cluster.setAttribute("role","group");
  cluster.setAttribute("aria-label",value);
  bindCluster(cluster);
}
function arrange(stage,data,machine){
  const transitions=machine?.transitions||[],lanes=pairRanks(transitions),saved=parseSaved(data);
  transitions.forEach((transition,index)=>{
    const id=transition.id||`T${index+1}`;
    const escaped=window.CSS?.escape?CSS.escape(id):id;
    const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
    if(!cluster)return;
    const anchor=anchorFor(pathFor(stage,id,index),stage);
    placeCluster(cluster,anchor,lanes[index],saved,id,stage);
  });
  stage.dataset.transitionIoClustersReady="true";
  stage.dataset.transitionIoMaxDistance=String(MAX_DISTANCE);
}
async function render(stage=stageOf(),reason="scheduled"){
  if(destroyed||activeTab()!=="state"||!stage)return{ok:false,skipped:true};
  if(running){queued=true;return{ok:false,queued:true}}
  running=true;
  const token=++generation,started=performance.now();
  try{
    const data=await diagramState();
    if(destroyed||token!==generation||!stage.isConnected)return{ok:false,cancelled:true};
    const machine=selectedMachine(data);
    if(!machine)return{ok:false,missingMachine:true};
    const transitions=machine.transitions||[];
    tagBaseGeometry(stage,transitions);
    const labels=[...stage.querySelectorAll(".transition-label")];
    transitions.forEach((transition,index)=>{
      const id=transition.id||`T${index+1}`,line=transition.source?.line||0;
      const escaped=window.CSS?.escape?CSS.escape(id):id;
      const source=stage.querySelector(`.transition-label[data-transition-id="${escaped}"]`)||labels[index];
      if(source){source.classList.add("transition-io-source");source.setAttribute("aria-hidden","true")}
      let cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
      if(!cluster){
        cluster=document.createElement("div");
        cluster.className="transition-io-cluster";
        stage.appendChild(cluster);
      }
      updateCluster(cluster,transition,id,line);
    });
    stage.querySelectorAll(".transition-io-cluster").forEach(cluster=>{
      if(!transitions.some((item,index)=>(item.id||`T${index+1}`)===cluster.dataset.transitionId))cluster.remove();
    });
    reroute(stage,machine);
    const duration=performance.now()-started;
    stage.dataset.transitionIoSignature=signatureOf(machine);
    stage.dataset.transitionIoRenderDurationMs=duration.toFixed(2);
    stage.dataset.transitionIoRenderBudgetMs=String(RENDER_BUDGET_MS);
    stage.dataset.transitionIoRenderBudgetExceeded=duration>RENDER_BUDGET_MS?"true":"false";
    stage.dataset.labelLayoutReady="true";
    stage.dataset.umlTransitionReady="true";
    stage.dataset.transitionInputActionLabelsReady="true";
    stage.dataset.stateTransitionIRV4LabelsReady="true";
    stage.dataset.stateTransitionIRV3LabelsReady="true";
    stage.dataset.stateTransitionIRV2LabelsReady="true";
    document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready",{detail:{machine:machine.name,marker:MARKER}}));
    document.dispatchEvent(new CustomEvent("glyph-state-transition-ir-v4-labels-ready",{detail:{machine:machine.name,marker:MARKER}}));
    document.dispatchEvent(new CustomEvent("glyph-transition-io-clusters-ready",{detail:{machine:machine.name,transitions:transitions.length,marker:MARKER,durationMs:duration}}));
    window.glyphTransitionLayoutTransaction?.schedule?.(`io-clusters:${reason}`,0);
    return{ok:true,transitions:transitions.length,durationMs:duration};
  }catch(error){
    if(error?.name!=="AbortError")console.error("transition I/O rendering failed",error);
    return{ok:false,error:String(error?.message||error)};
  }finally{
    running=false;
    if(queued){queued=false;schedule(null,"queued")}
  }
}
function schedule(stage=null,reason="scheduled"){
  if(destroyed)return 0;
  cancelAnimationFrame(raf);
  raf=requestAnimationFrame(()=>render(stage||stageOf(),reason));
  return generation+1;
}
function invalidate(reason="invalidated"){
  cache=null;
  generation+=1;
  schedule(null,reason);
}
const view=document.getElementById("view");
if(view)new MutationObserver(()=>{if(activeTab()==="state")invalidate("view-rendered")}).observe(view,{childList:true});
for(const eventName of["glyph-locale-changed","glyph-execution-context-changed"]){
  document.addEventListener(eventName,()=>invalidate(eventName));
}
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select")invalidate("machine-change");
});
let rerouteRaf=0;
document.addEventListener("pointermove",event=>{
  if(!event.target?.closest?.(".state-node"))return;
  cancelAnimationFrame(rerouteRaf);
  rerouteRaf=requestAnimationFrame(()=>reroute());
},true);
document.addEventListener("pointerup",event=>{
  if(event.target?.closest?.(".state-node"))schedule(null,"node-drag-end");
},true);
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{destroyed=true;generation+=1;cancelAnimationFrame(raf);cancelAnimationFrame(rerouteRaf)},{once:true});
}
window.glyphTransitionIoClusters={
  marker:MARKER,
  version:3,
  profile:"ordinary",
  budgetMs:RENDER_BUDGET_MS,
  maxDistance:MAX_DISTANCE,
  render:()=>render(stageOf(),"api"),
  schedule,
  reroute,
};
schedule(null,"initial");
})();
</script>
"""


def enhance_transition_io_clusters_html(html: str) -> str:
    """Render semantic I/O labels with O(T) placement on the base state diagram."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
