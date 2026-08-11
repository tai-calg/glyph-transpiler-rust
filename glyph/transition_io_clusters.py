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
.transition-io-value>.transition-semantic-line{
  display:block;
  max-width:264px;
  white-space:pre;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:normal;
  word-break:normal;
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
const SEMANTIC_LINE_LIMIT=42;
function semanticCut(value,limit=SEMANTIC_LINE_LIMIT){
  if(value.length<=limit)return value.length;
  const separators=new Set([" ","&",",",".","_","(",")","[","]",";"]);
  for(let index=limit;index>=Math.max(8,limit-14);index-=1){if(separators.has(value[index]))return index+1}
  for(let index=limit+1;index<Math.min(value.length,limit+14);index+=1){if(separators.has(value[index]))return index+1}
  return value.length;
}
function splitSemantic(value){
  const lines=[];
  let remaining=String(value??"");
  while(remaining.length>SEMANTIC_LINE_LIMIT){
    const cut=semanticCut(remaining);
    if(cut>=remaining.length)break;
    lines.push(remaining.slice(0,cut));
    remaining=remaining.slice(cut);
  }
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}
function semanticLines(input,guard,action){
  const left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`.trim(),lines=[];
  if(left)lines.push(...splitSemantic(left));
  if(action)lines.push(...splitSemantic(`${left?" ":""}➞ ${action}`));
  if(!lines.length)lines.push("otherwise");
  return lines;
}
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
function ordinaryPath(source,target,same,lane,stage){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  const rank=Number(lane?.rank||0),centered=Number(lane?.centered||0);
  if(same){
    const width=Math.max(stage.clientWidth,num(stage.style.width),stage.scrollWidth);
    const height=Math.max(stage.clientHeight,num(stage.style.height),stage.scrollHeight);
    let ox=x1-width/2,oy=y1-height/2,length=Math.hypot(ox,oy);
    if(length<1){ox=0;oy=-1;length=1}
    const nx=ox/length,ny=oy/length,tx=-ny,ty=nx;
    const side=rank%2===0?1:-1;
    const tangent=30+Math.floor(rank/2)*12;
    const outward=76+Math.abs(centered)*30+Math.floor(rank/2)*18;
    const sx=x1+tx*tangent*side+nx*10,sy=y1+ty*tangent*side+ny*10;
    const ex=x1-tx*tangent*side+nx*10,ey=y1-ty*tangent*side+ny*10;
    return`M ${sx} ${sy} C ${sx+nx*outward+tx*24*side} ${sy+ny*outward+ty*24*side}, ${ex+nx*outward-tx*24*side} ${ey+ny*outward-ty*24*side}, ${ex} ${ey}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const ux=dx/length,uy=dy/length,nx=-uy,ny=ux;
  const sourceRadius=Math.min(source.offsetWidth,source.offsetHeight)/2+1;
  const targetRadius=Math.min(target.offsetWidth,target.offsetHeight)/2+1;
  const sx=x1+ux*sourceRadius,sy=y1+uy*sourceRadius;
  const ex=x2-ux*targetRadius,ey=y2-uy*targetRadius;
  const directionalOffset=48,laneGap=28;
  const curvature=directionalOffset+centered*laneGap;
  return`M ${sx} ${sy} Q ${(sx+ex)/2+nx*curvature} ${(sy+ey)/2+ny*curvature} ${ex} ${ey}`;
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
  const transitions=selected.transitions||[],nodes=nodeMap(stage),lanes=pairRanks(transitions);
  tagBaseGeometry(stage,transitions);
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    const path=pathFor(stage,transition.id||`T${index+1}`,index);
    if(source&&target&&path)path.setAttribute("d",ordinaryPath(source,target,source===target,lanes[index],stage));
  });
  arrange(stage,data,selected);
  return true;
}
function clusterMarkup(value,input,guard,action){
  const lines=semanticLines(input,guard,action);
  const content=lines.map(line=>`<span class="transition-semantic-line">${esc(line)}</span>`).join("");
  return`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${content}</span></div></div>`;
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
  const input=inputOf(transition),guard=guardsOf(transition).join(" & "),action=actionOf(transition),value=ioOf(transition);
  if(cluster.dataset.ioValue!==value||!cluster.querySelector(".transition-semantic-line"))cluster.innerHTML=clusterMarkup(value,input,guard,action);
  const trigger=triggerOf(transition),unknown=unknownOf(transition).length>0,semantic=semanticOf(transition);
  const semanticLines=[...cluster.querySelectorAll(".transition-semantic-line")];
  cluster.dataset.transitionId=id;
  cluster.dataset.line=String(line||0);
  cluster.dataset.inputValue=input;
  cluster.dataset.guardValue=guard;
  cluster.dataset.actionValue=action;
  cluster.dataset.outputValue=action;
  cluster.dataset.ioValue=value;
  cluster.dataset.fullLabel=value;
  cluster.dataset.semanticLineCount=String(semanticLines.length);
  cluster.dataset.semanticLongestLine=String(Math.max(0,...semanticLines.map(item=>(item.textContent||"").length)));
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
const COLLISION_GAP=4;
const COLLISION_RINGS=[0,16,32,48,64,80,96];
const COLLISION_ANGLES=24;
const COLLISION_BUDGET_MS=10;
function localRect(cluster,point){
  return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight};
}
function intersects(left,right,gap=COLLISION_GAP){
  return!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y);
}
function insideStage(rect,stage){
  const width=Math.max(stage.clientWidth,num(stage.style.width),stage.scrollWidth),height=Math.max(stage.clientHeight,num(stage.style.height),stage.scrollHeight);
  return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=width-8&&rect.y+rect.height<=height-8;
}
function nodeObstacles(stage){
  return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}));
}
function candidatePoints(entry,stage){
  const points=[],seen=new Set(),add=point=>{
    const bounded=constrain(project(point,entry.anchor),entry.cluster,stage);
    const key=`${Math.round(bounded.x)}:${Math.round(bounded.y)}`;
    if(seen.has(key))return;
    seen.add(key);
    points.push(bounded);
  };
  add(entry.preferred);
  for(const radius of COLLISION_RINGS){
    for(let index=0;index<COLLISION_ANGLES;index+=1){
      const angle=2*Math.PI*index/COLLISION_ANGLES;
      add({x:entry.anchor.x+Math.cos(angle)*radius,y:entry.anchor.y+Math.sin(angle)*radius});
    }
  }
  return points.map(point=>({
    point,
    rect:localRect(entry.cluster,point),
    score:Math.hypot(point.x-entry.preferred.x,point.y-entry.preferred.y)+Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y)*.04,
  })).sort((left,right)=>left.score-right.score);
}
function collisionCount(entries){
  let count=0;
  for(let index=0;index<entries.length;index+=1){
    const left=localRect(entries[index].cluster,{x:num(entries[index].cluster.style.left),y:num(entries[index].cluster.style.top)});
    for(let other=index+1;other<entries.length;other+=1){
      const right=localRect(entries[other].cluster,{x:num(entries[other].cluster.style.left),y:num(entries[other].cluster.style.top)});
      if(intersects(left,right,1))count+=1;
    }
  }
  return count;
}
function repairCollisions(stage,entries){
  const nodes=nodeObstacles(stage),fixed=[],movable=[];
  for(const entry of entries){
    const preferredRect=localRect(entry.cluster,entry.preferred);
    if(entry.manual&&insideStage(preferredRect,stage)&&!nodes.some(node=>intersects(preferredRect,node))&&!fixed.some(rect=>intersects(preferredRect,rect))){
      fixed.push(preferredRect);
      continue;
    }
    entry.options=candidatePoints(entry,stage).filter(option=>insideStage(option.rect,stage)&&!nodes.some(node=>intersects(option.rect,node)));
    movable.push(entry);
  }
  movable.sort((left,right)=>left.options.length-right.options.length||right.cluster.offsetWidth*right.cluster.offsetHeight-left.cluster.offsetWidth*left.cluster.offsetHeight||left.index-right.index);
  const assignment=new Map(),deadline=performance.now()+COLLISION_BUDGET_MS;
  function solve(index,placed){
    if(index>=movable.length)return true;
    if(performance.now()>deadline)return false;
    const entry=movable[index];
    for(const option of entry.options){
      if(placed.some(rect=>intersects(option.rect,rect)))continue;
      assignment.set(entry,option);
      placed.push(option.rect);
      if(solve(index+1,placed))return true;
      placed.pop();
      assignment.delete(entry);
    }
    return false;
  }
  let solved=movable.every(entry=>entry.options.length>0)&&solve(0,[...fixed]);
  if(!solved){
    assignment.clear();
    const placed=[...fixed];
    solved=true;
    for(const entry of movable){
      const option=entry.options.find(candidate=>!placed.some(rect=>intersects(candidate.rect,rect)));
      if(!option){solved=false;break}
      assignment.set(entry,option);
      placed.push(option.rect);
    }
  }
  if(solved){
    for(const [entry,option] of assignment){
      entry.cluster.style.left=`${option.point.x}px`;
      entry.cluster.style.top=`${option.point.y}px`;
      entry.cluster.dataset.ioDistance=String(Math.hypot(option.point.x-entry.anchor.x,option.point.y-entry.anchor.y));
    }
  }
  const count=collisionCount(entries);
  stage.dataset.transitionIoCollisionSolved=count===0?"true":"fallback";
  stage.dataset.transitionIoCollisionCount=String(count);
  stage.dataset.transitionIoCollisionBudgetMs=String(COLLISION_BUDGET_MS);
  return count===0;
}
function arrange(stage,data,machine){
  const transitions=machine?.transitions||[],lanes=pairRanks(transitions),saved=parseSaved(data),entries=[];
  transitions.forEach((transition,index)=>{
    const id=transition.id||`T${index+1}`;
    const escaped=window.CSS?.escape?CSS.escape(id):id;
    const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
    if(!cluster)return;
    const anchor=anchorFor(pathFor(stage,id,index),stage);
    placeCluster(cluster,anchor,lanes[index],saved,id,stage);
    entries.push({cluster,index,anchor,preferred:{x:num(cluster.style.left),y:num(cluster.style.top)},manual:cluster.dataset.manualIo==="true",options:[]});
  });
  repairCollisions(stage,entries);
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
    stage.dataset.transitionSemanticLinesReady="true";
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
document.addEventListener("pointerup",event=>{
  if(event.target?.closest?.(".state-node"))schedule(null,"node-drag-end");
},true);
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{destroyed=true;generation+=1;cancelAnimationFrame(raf)},{once:true});
}
window.glyphTransitionIoClusters={
  marker:MARKER,
  version:3,
  profile:"ordinary",
  budgetMs:RENDER_BUDGET_MS,
  maxDistance:MAX_DISTANCE,
  nodeDragRouting:"deferred-full",
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