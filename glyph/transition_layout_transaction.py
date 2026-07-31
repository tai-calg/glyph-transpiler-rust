from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-v1"

_STYLE = r"""
<style id="glyph-transition-layout-transaction-v1-style">
.transition-io-cluster.transaction-readable-label{
  max-width:none!important;
}
.transition-io-cluster.transaction-readable-label .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.compact-io .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.micro-io .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.nano-io .transition-io-node.io{
  width:var(--transaction-label-width,120px)!important;
  min-width:var(--transaction-label-width,120px)!important;
  max-width:var(--transaction-label-width,120px)!important;
  min-height:28px!important;
  height:auto!important;
  padding:4px 7px!important;
  overflow:visible!important;
}
.transition-io-cluster.transaction-readable-label .transition-io-value{
  display:block!important;
  width:100%!important;
  max-width:100%!important;
  font-size:9px!important;
  line-height:1.28!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:normal!important;
  word-break:normal!important;
  text-align:center!important;
}
.transition-transaction-line{
  display:block;
  min-height:1.28em;
  white-space:pre;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:normal;
  word-break:normal;
}
.graph-stage[data-transition-layout-state="pending"] .transition-io-cluster{
  pointer-events:none;
}
.graph-stage[data-transition-publication-ready="false"] .transition-io-cluster{
  visibility:hidden;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-v1";
const MAX_DISTANCE=96,GAP=6,DENSE_TRANSITIONS=7;
const MIN_CANVAS_WIDTH=760,MIN_CANVAS_HEIGHT=560,CANVAS_PADDING=132;
const LABEL_MIN_WIDTH=108,LABEL_MAX_WIDTH=520,LABEL_RETRY_WIDTH=320,LABEL_LAST_WIDTH=240;
const OPTION_LIMIT=160,SEARCH_STEPS=220000,SEARCH_BUDGET_MS=450;
const PREREQUISITE_TIMEOUT_MS=9000,CLUSTER_TIMEOUT_MS=5000;
const RINGS=[0,12,24,36,48,60,72,84,96],ANGLES=72;
const control=window.glyphTransitionLegacyControl;
if(control)control.ownsScheduling=true;

let stateCache=null,statePromise=null,stateAbort=null,stateRequestVersion=0;
let requestedGeneration=0,completedGeneration=0,running=false,timer=null,lastStage=null;
let resizeObserver=null,lastViewportSize="",destroyed=false,internalClusterRefresh=false;
const generationReasons=new Map();
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const text=value=>String(value??"");
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";

function invalidateState(){
  stateRequestVersion+=1;
  stateCache=null;
  statePromise=null;
  stateAbort?.abort();
  stateAbort=null;
}
async function diagramState(){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live)return live;
  if(stateCache)return stateCache;
  if(statePromise)return statePromise;
  const version=stateRequestVersion,controller=new AbortController();
  stateAbort=controller;
  statePromise=(async()=>{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error(`diagram state unavailable: HTTP ${response.status}`);
    const data=await response.json();
    if(version!==stateRequestVersion||destroyed)throw new DOMException("stale diagram state","AbortError");
    stateCache=data;
    return data;
  })().finally(()=>{
    if(stateAbort===controller)stateAbort=null;
    statePromise=null;
  });
  return statePromise;
}
function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===selected)||machines[0]||null;
}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function machineIndex(){return document.getElementById("machine-select")?.value||0}
function nodeStorageKey(data){return`glyph.diagram.positions.v1:${data?.digest||"source"}:state:${machineIndex()}`}
function labelStorageKey(data){return`glyph.diagram.transition-io.v1:${data?.digest||"source"}:${machineIndex()}`}
function parseStored(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
function writeStored(key,value){
  try{localStorage.setItem(key,JSON.stringify(value));return true}
  catch(error){console.warn("transition layout persistence unavailable",error);return false}
}
function cancelled(token){return destroyed||token!==requestedGeneration}
function stageScale(stage){return window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1}

function clearFailure(stage){
  delete stage.dataset.transitionLayoutError;
  delete stage.dataset.transitionLayoutFailureCode;
  delete stage.dataset.transitionLayoutFailureDetails;
}
function markPending(stage,token,reason){
  clearFailure(stage);
  stage.dataset.transitionLayoutState="pending";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.initialRouteReady="pending";
  delete stage.dataset.initialTransitionRouting;
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionIoCollisionSolved="transaction-pending";
  stage.dataset.transitionIoCollisionCount="-1";
  stage.dataset.transitionSemanticLinesReady="pending";
  stage.dataset.transitionSemanticRoleLinesReady="pending";
}
function markDeferred(stage,token,reason){
  stage.dataset.transitionLayoutState="deferred";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
}
function markFailure(stage,token,reason,error){
  const message=String(error?.message||error);
  stage.dataset.transitionLayoutState="failed";
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionLayoutError=message;
  stage.dataset.transitionLayoutFailureCode=String(error?.code||"layout-failed");
  stage.dataset.transitionLayoutFailureDetails=String(error?.details||"");
  stage.dataset.transitionIoCollisionSolved="failed";
}

async function waitForPrerequisites(token){
  if(activeTab()!=="state")return null;
  const started=performance.now();
  while(performance.now()-started<PREREQUISITE_TIMEOUT_MS){
    if(cancelled(token))return null;
    if(activeTab()!=="state")return null;
    const stage=stageOf();
    if(stage&&stage.dataset.stateTransitionIRV3LabelsReady==="true"&&stage.dataset.editorReady==="true")return stage;
    await wait(40);
  }
  const stage=stageOf();
  const error=Error("state diagram layout prerequisites did not become ready");
  error.code="layout-prerequisite-timeout";
  error.details=JSON.stringify({
    stage:Boolean(stage),
    labels:stage?.dataset.stateTransitionIRV3LabelsReady||"missing",
    editor:stage?.dataset.editorReady||"missing",
    tab:activeTab(),
  });
  throw error;
}
async function waitForFonts(token){
  if(!document.fonts?.ready)return;
  await Promise.race([document.fonts.ready,wait(1800)]);
  if(cancelled(token))throw new DOMException("layout cancelled","AbortError");
}

function viewportDimensions(stage){
  const shell=stage.closest(".canvas-shell"),scale=Math.max(.01,stageScale(stage));
  return{
    width:shell?Math.max(MIN_CANVAS_WIDTH,(shell.clientWidth-24)/scale):MIN_CANVAS_WIDTH,
    height:shell?Math.max(MIN_CANVAS_HEIGHT,(shell.clientHeight-24)/scale):MIN_CANVAS_HEIGHT,
  };
}
function nodeBounds(stage){
  const nodes=[...stage.querySelectorAll(".state-node")];
  return{
    right:Math.max(0,...nodes.map(node=>node.offsetLeft+node.offsetWidth)),
    bottom:Math.max(0,...nodes.map(node=>node.offsetTop+node.offsetHeight)),
  };
}
function labelBounds(stage){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  return{
    width:Math.max(0,...clusters.map(cluster=>cluster.offsetWidth)),
    height:Math.max(0,...clusters.map(cluster=>cluster.offsetHeight)),
  };
}
function setCanvasSize(stage,width,height,transitionCount){
  const nextWidth=Math.ceil(Math.max(MIN_CANVAS_WIDTH,width));
  const nextHeight=Math.ceil(Math.max(MIN_CANVAS_HEIGHT,height));
  stage.style.width=`${nextWidth}px`;
  stage.style.height=`${nextHeight}px`;
  stage.dataset.transitionDenseCanvas=transitionCount>=DENSE_TRANSITIONS?`${nextWidth}x${nextHeight}`:"not-required";
  stage.dataset.transitionCanvasWidth=String(nextWidth);
  stage.dataset.transitionCanvasHeight=String(nextHeight);
}
function ensureCanvas(stage,transitionCount,{growth=1,includeLabels=false}={}){
  const viewport=viewportDimensions(stage),nodes=nodeBounds(stage),labels=includeLabels?labelBounds(stage):{width:0,height:0};
  const densityWidth=transitionCount>=DENSE_TRANSITIONS?Math.max(980,transitionCount*96):0;
  const densityHeight=transitionCount>=DENSE_TRANSITIONS?Math.max(660,Math.ceil(transitionCount/4)*160):0;
  const width=Math.max(viewport.width,nodes.right+CANVAS_PADDING+labels.width/2,densityWidth)*growth;
  const height=Math.max(viewport.height,nodes.bottom+CANVAS_PADDING+labels.height/2,densityHeight)*growth;
  setCanvasSize(stage,width,height,transitionCount);
  return transitionCount>=DENSE_TRANSITIONS;
}

function arrangeInitialDenseNodes(stage,data,machine,dense){
  if(!dense)return false;
  const saved=parseStored(nodeStorageKey(data));
  if(Object.keys(saved).length){
    stage.dataset.semanticDenseLayout=`saved:${machine?.name||"machine"}`;
    return false;
  }
  const nodes=[...stage.querySelectorAll(".state-node")];
  if(nodes.length<2)return false;
  const signature=`${data?.digest||"source"}:${machine?.name||"machine"}:${nodes.length}:${machine?.transitions?.length||0}:${stage.style.width}:${stage.style.height}`;
  if(stage.dataset.semanticDenseLayout===signature)return false;
  const width=num(stage.style.width)||MIN_CANVAS_WIDTH,height=num(stage.style.height)||MIN_CANVAS_HEIGHT;
  const centerX=width/2,centerY=height/2;
  const radiusX=Math.max(230,Math.min(width*.34,470));
  const radiusY=Math.max(170,Math.min(height*.31,330));
  nodes.forEach((node,index)=>{
    const angle=-Math.PI/2+index*2*Math.PI/nodes.length;
    node.style.left=`${Math.round(clamp(centerX+Math.cos(angle)*radiusX-node.offsetWidth/2,32,width-node.offsetWidth-32))}px`;
    node.style.top=`${Math.round(clamp(centerY+Math.sin(angle)*radiusY-node.offsetHeight/2,32,height-node.offsetHeight-32))}px`;
  });
  stage.dataset.semanticDenseLayout=signature;
  return true;
}

function stateCurve(source,target,same,lane,laneCount){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  const centered=lane-(laneCount-1)/2;
  if(same){
    const magnitude=Math.abs(centered),spread=64+magnitude*30,lift=108+magnitude*38,shift=centered*42;
    return`M ${x1-27} ${y1-34} C ${x1-spread+shift} ${y1-lift}, ${x1+spread+shift} ${y1-lift}, ${x1+27} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const startX=x1+dx/length*source.offsetWidth/2,startY=y1+dy/length*source.offsetHeight/2;
  const endX=x2-dx/length*target.offsetWidth/2,endY=y2-dy/length*target.offsetHeight/2;
  const laneOffset=centered*62,normalX=-dy/length,normalY=dx/length;
  return`M ${startX} ${startY} Q ${(startX+endX)/2+normalX*laneOffset} ${(startY+endY)/2+normalY*laneOffset} ${endX} ${endY}`;
}
function reroute(stage,machine){
  const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nodeName(node),node]));
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")];
  const labels=[...stage.querySelectorAll(".transition-label")];
  const transitions=machine?.transitions||[],totals=new Map(),seen=new Map();
  transitions.forEach(transition=>{
    const key=`${transition.source_state}\u001f${transition.target_state}`;
    totals.set(key,(totals.get(key)||0)+1);
  });
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    if(!source||!target)return;
    const key=`${transition.source_state}\u001f${transition.target_state}`,lane=seen.get(key)||0,laneCount=totals.get(key)||1;
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
    if(labels[index]){
      const centered=lane-(laneCount-1)/2;
      labels[index].style.left=`${(source.offsetLeft+target.offsetLeft+source.offsetWidth)/2+centered*46}px`;
      labels[index].style.top=`${(source.offsetTop+target.offsetTop+source.offsetHeight)/2-(source===target?108+Math.abs(centered)*38:0)}px`;
    }
  });
  delete stage.dataset.initialTransitionRouting;
}

async function ensureClusters(stage,machine,token){
  const expected=machine?.transitions?.length||0,started=performance.now();
  while(performance.now()-started<CLUSTER_TIMEOUT_MS){
    if(cancelled(token))return false;
    const count=stage.querySelectorAll(".transition-io-cluster").length;
    if(count===expected)return true;
    window.glyphTransitionIoClusters?.render();
    await wait(60);
  }
  const count=stage.querySelectorAll(".transition-io-cluster").length;
  const error=Error(`transition cluster count did not settle: expected ${expected}, got ${count}`);
  error.code="layout-cluster-timeout";
  error.details=JSON.stringify({expected,count});
  throw error;
}

function graphemeParts(value){
  if(typeof Intl?.Segmenter==="function"){
    return[...new Intl.Segmenter(undefined,{granularity:"grapheme"}).segment(value)].map(item=>item.segment);
  }
  return Array.from(value);
}
function safeBoundary(value,index){
  const before=value[index-1]||"",after=value[index]||"";
  return before===" "||before===","||before===")"||before==="]"||before==="&"||before==="|"||after===" ";
}
function textMeasurer(font){
  const canvas=document.createElement("canvas"),context=canvas.getContext("2d");
  if(context)context.font=font;
  return value=>context?context.measureText(value).width:value.length*5.8;
}
function splitByWidth(value,maxWidth,measure){
  const lines=[];
  let remaining=text(value);
  while(remaining&&measure(remaining)>maxWidth){
    const graphemes=graphemeParts(remaining);
    let offset=0,lastFit=0,lastSafe=0;
    for(const part of graphemes){
      offset+=part.length;
      if(measure(remaining.slice(0,offset))>maxWidth)break;
      lastFit=offset;
      if(safeBoundary(remaining,offset))lastSafe=offset;
    }
    const cut=lastSafe>=Math.max(1,Math.floor(lastFit*.55))?lastSafe:lastFit;
    if(cut<=0)break;
    lines.push(remaining.slice(0,cut));
    remaining=remaining.slice(cut);
  }
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}
function canonicalLabel(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue);
  const left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`.trim();
  return`${left}${output?`${left?" ":""}➞ ${output}`:""}`.trim();
}
function sourceComponents(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue),parts=[];
  if(input)parts.push(input);
  if(guard)parts.push(`${input?" ":""}[${guard}]`);
  if(output)parts.push(`${input||guard?" ":""}➞ ${output}`);
  if(!parts.length)parts.push(text(cluster.dataset.ioValue));
  return parts;
}
function existingCases(cluster){
  const value=cluster.querySelector(".transition-io-value");
  const cases=[...(value?.querySelectorAll(".enabling-case-line")||[])].map(element=>text(element.textContent)).filter(Boolean);
  if(cases.length)return cases;
  return text(cluster.dataset.ioValue).split(" || ").map(item=>item.trim()).filter(Boolean);
}
function renderedCanonical(cluster){
  const value=cluster.querySelector(".transition-io-value");
  if(!value)return"";
  const lines=[...value.querySelectorAll(".transition-transaction-line")];
  if(Number(cluster.dataset.enablingCaseCount||"1")>1){
    const groups=new Map();
    for(const line of lines){
      const index=Number(line.dataset.caseIndex||0);
      if(!groups.has(index))groups.set(index,[]);
      groups.get(index).push(text(line.textContent));
    }
    return[...groups.keys()].sort((a,b)=>a-b).map(index=>groups.get(index).join("")).join(" || ");
  }
  return lines.map(line=>text(line.textContent)).join("");
}
function formatLabels(stage,maxLineWidth=LABEL_MAX_WIDTH){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  for(const cluster of clusters){
    const value=cluster.querySelector(".transition-io-value"),node=cluster.querySelector(".transition-io-node.io");
    if(!value||!node)throw Error(`transition label DOM is incomplete: ${cluster.dataset.transitionId||"unknown"}`);
    const expected=cluster.dataset.ioValue||text(value.textContent),style=getComputedStyle(value);
    const font=style.font&&style.font!==""?style.font:`700 9px ${style.fontFamily||"monospace"}`;
    const measure=textMeasurer(font),fragments=[];
    const multiple=Number(cluster.dataset.enablingCaseCount||"1")>1;
    if(multiple){
      existingCases(cluster).forEach((item,caseIndex)=>{
        splitByWidth(item,maxLineWidth,measure).forEach((line,fragmentIndex)=>fragments.push({line,caseIndex,fragmentIndex}));
      });
    }else{
      sourceComponents(cluster).forEach((component,componentIndex)=>{
        splitByWidth(component,maxLineWidth,measure).forEach((line,fragmentIndex)=>fragments.push({line,componentIndex,fragmentIndex}));
      });
    }
    value.replaceChildren(...fragments.map(fragment=>{
      const span=document.createElement("span");
      span.className=`transition-semantic-line transition-role-line transition-transaction-line${multiple?" enabling-case-line":""}`;
      span.textContent=fragment.line;
      if(multiple)span.dataset.caseIndex=String(fragment.caseIndex);
      else span.dataset.componentIndex=String(fragment.componentIndex);
      span.dataset.fragmentIndex=String(fragment.fragmentIndex);
      return span;
    }));
    const actual=renderedCanonical(cluster);
    if(actual!==expected){
      const error=Error(`transition label formatting changed structured semantics: ${expected}`);
      error.code="layout-label-semantic-mismatch";
      error.details=JSON.stringify({id:cluster.dataset.transitionId||"",expected,actual});
      throw error;
    }
    const longest=Math.max(1,...fragments.map(fragment=>measure(fragment.line)));
    const width=clamp(Math.ceil(longest+22),LABEL_MIN_WIDTH,maxLineWidth+22);
    cluster.style.setProperty("--transaction-label-width",`${width}px`);
    cluster.style.setProperty("--semantic-label-width",`${width}px`);
    cluster.style.setProperty("--semantic-role-width",`${width}px`);
    cluster.classList.add("transaction-readable-label","semantic-readable-label","semantic-role-lines");
    cluster.classList.remove("compact-io","micro-io","nano-io","stacked");
    cluster.dataset.semanticLineCount=String(fragments.length);
    cluster.dataset.semanticLongestLine=String(Math.ceil(longest));
    cluster.dataset.semanticLineFallback=maxLineWidth<LABEL_MAX_WIDTH?"narrow-retry":"measured";
    node.title=expected;
    node.setAttribute("aria-label",expected);
  }
  stage.dataset.transitionSemanticLinesReady="formatted";
  stage.dataset.transitionSemanticRoleLinesReady="formatted";
}

function pathFor(stage,id,index){
  const escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&");
  return stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`)
    ||[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")][index]
    ||null;
}
function anchorFor(stage,id,index,fraction=.5){
  const path=pathFor(stage,id,index);
  if(path&&typeof path.getTotalLength==="function"){
    try{
      const length=path.getTotalLength(),offset=clamp(fraction,.18,.82)*length,mid=path.getPointAtLength(offset);
      const before=path.getPointAtLength(Math.max(0,offset-2)),after=path.getPointAtLength(Math.min(length,offset+2));
      return{x:mid.x,y:mid.y,normal:Math.atan2(after.x-before.x,-(after.y-before.y)),fraction,path};
    }catch{}
  }
  return{x:(num(stage.style.width)||stage.clientWidth)/2,y:(num(stage.style.height)||stage.clientHeight)/2,normal:-Math.PI/2,fraction:.5,path:null};
}
function project(point,anchor){
  const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);
  if(!distance||distance<=MAX_DISTANCE)return point;
  const ratio=MAX_DISTANCE/distance;
  return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio};
}
function constrain(point,cluster,stage){
  const width=num(stage.style.width)||stage.scrollWidth,height=num(stage.style.height)||stage.scrollHeight;
  return{
    x:clamp(point.x,cluster.offsetWidth/2+8,width-cluster.offsetWidth/2-8),
    y:clamp(point.y,cluster.offsetHeight/2+8,height-cluster.offsetHeight/2-8),
  };
}
function feasiblePoint(raw,entry,stage){
  let point=constrain(project(raw,entry.anchor),entry.cluster,stage);
  point=project(point,entry.anchor);
  point=constrain(point,entry.cluster,stage);
  if(Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y)>MAX_DISTANCE+.25)return null;
  return point;
}
function rectAt(cluster,point){return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function nodeRect(node){return{x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}}
function intersects(left,right,gap=GAP){return!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y)}
function inside(rect,stage){
  const width=num(stage.style.width)||stage.scrollWidth,height=num(stage.style.height)||stage.scrollHeight;
  return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=width-8&&rect.y+rect.height<=height-8;
}
function candidatePoints(anchor,preferred){
  const result=[],seen=new Set();
  const add=raw=>{
    const point=project(raw,anchor),key=`${Math.round(point.x*10)}:${Math.round(point.y*10)}`;
    if(!seen.has(key)){seen.add(key);result.push(point)}
  };
  add(preferred);
  for(const radius of RINGS){
    for(let index=0;index<ANGLES;index+=1){
      const angle=anchor.normal+index*2*Math.PI/ANGLES;
      add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius});
    }
  }
  return result;
}
function samplePaths(stage){
  return[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")].map(path=>{
    const points=[];
    try{
      const length=path.getTotalLength();
      for(let index=1;index<12;index+=1){const point=path.getPointAtLength(length*index/12);points.push({x:point.x,y:point.y})}
    }catch{}
    return{id:path.dataset.transitionId||"",points};
  });
}
function pointInsideRect(point,rect,padding=2){return point.x>=rect.x-padding&&point.x<=rect.x+rect.width+padding&&point.y>=rect.y-padding&&point.y<=rect.y+rect.height+padding}
function optionsFor(entry,stage,nodes,pathSamples){
  const values=[],seen=new Set();
  for(const raw of candidatePoints(entry.anchor,entry.preferred)){
    const point=feasiblePoint(raw,entry,stage);
    if(!point)continue;
    const rect=rectAt(entry.cluster,point);
    if(!inside(rect,stage)||nodes.some(node=>intersects(rect,node)))continue;
    const key=`${Math.round(point.x*10)}:${Math.round(point.y*10)}`;
    if(seen.has(key))continue;
    seen.add(key);
    const displacement=Math.hypot(point.x-entry.preferred.x,point.y-entry.preferred.y);
    const anchorDistance=Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y);
    const foreignEdgeHits=pathSamples.reduce((count,path)=>count+(path.id!==entry.id&&path.points.some(sample=>pointInsideRect(sample,rect))?1:0),0);
    const score=displacement*(entry.manual?6:1)+anchorDistance*.02+foreignEdgeHits*36;
    values.push({point,rect,score,foreignEdgeHits});
  }
  values.sort((left,right)=>left.score-right.score||left.point.y-right.point.y||left.point.x-right.point.x);
  return values.slice(0,OPTION_LIMIT);
}
function layoutEntries(stage,data,machine){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")],nodes=[...stage.querySelectorAll(".state-node")].map(nodeRect);
  const saved=parseStored(labelStorageKey(data)),transitions=machine?.transitions||[],pathSamples=samplePaths(stage);
  const groups=new Map(),fractions=new Map();
  transitions.forEach((transition,index)=>{
    const key=`${transition.source_state||"?"}→${transition.target_state||"?"}`;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(index);
  });
  groups.forEach(indices=>indices.forEach((transitionIndex,rank)=>{
    fractions.set(transitionIndex,indices.length===1?.5:(rank+1)/(indices.length+1));
  }));
  const entries=clusters.map((cluster,index)=>{
    const id=cluster.dataset.transitionId||`T${index+1}`,fraction=fractions.get(index)??.5,anchor=anchorFor(stage,id,index,fraction),record=saved[id];
    const manual=Boolean(record);
    const restored=finite(record?.dx)&&finite(record?.dy)
      ?{x:anchor.x+record.dx,y:anchor.y+record.dy}
      :finite(record?.x)&&finite(record?.y)?{x:record.x,y:record.y}
      :{x:num(cluster.style.left)||anchor.x,y:num(cluster.style.top)||anchor.y};
    const entry={cluster,index,id,anchor,manual,preferred:project(restored,anchor),options:[],congestion:0};
    entry.options=optionsFor(entry,stage,nodes,pathSamples);
    return entry;
  });
  entries.forEach(entry=>{
    entry.congestion=entries.reduce((count,other)=>count+(other!==entry&&Math.hypot(entry.anchor.x-other.anchor.x,entry.anchor.y-other.anchor.y)<220?1:0),0);
  });
  return entries;
}
function entryOrder(entries){
  return[...entries].sort((left,right)=>Number(right.manual)-Number(left.manual)||right.congestion-left.congestion||left.options.length-right.options.length||left.index-right.index);
}
function greedyEntries(entries){
  const assignment=new Map(),placed=[];
  for(const entry of entryOrder(entries)){
    const option=entry.options.find(candidate=>!placed.some(rect=>intersects(candidate.rect,rect)));
    if(!option)return null;
    assignment.set(entry.cluster,option);placed.push(option.rect);
  }
  return assignment;
}
function solveEntries(entries,token){
  const ordered=entryOrder(entries),assignment=new Map(),placed=[],remaining=new Set(ordered);
  const deadline=performance.now()+SEARCH_BUDGET_MS;
  let steps=0,timedOut=false;
  function visit(){
    if(!remaining.size)return true;
    steps+=1;
    if(steps>SEARCH_STEPS||performance.now()>deadline||cancelled(token)){timedOut=true;return false}
    let selected=null,viable=null;
    for(const entry of remaining){
      const options=entry.options.filter(option=>!placed.some(rect=>intersects(option.rect,rect)));
      if(!options.length)return false;
      if(!viable||options.length<viable.length||(options.length===viable.length&&entry.congestion>(selected?.congestion||0))){selected=entry;viable=options}
    }
    remaining.delete(selected);
    for(const option of viable){
      assignment.set(selected.cluster,option);placed.push(option.rect);
      if(visit())return true;
      placed.pop();assignment.delete(selected.cluster);
      if(timedOut)break;
    }
    remaining.add(selected);
    return false;
  }
  return{assignment:visit()?assignment:null,steps,timedOut};
}
function applyAssignment(stage,data,entries,assignment){
  const saved=parseStored(labelStorageKey(data));
  for(const entry of entries){
    const option=assignment.get(entry.cluster);
    if(!option)throw Error(`missing transition placement: ${entry.id}`);
    const point=option.point;
    entry.cluster.style.left=`${point.x}px`;
    entry.cluster.style.top=`${point.y}px`;
    entry.cluster.dataset.anchorX=String(entry.anchor.x);
    entry.cluster.dataset.anchorY=String(entry.anchor.y);
    entry.cluster.dataset.ioDistance=String(Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y));
    entry.cluster.dataset.maxIoDistance=String(MAX_DISTANCE);
    entry.cluster.dataset.manualIo=entry.manual?"true":"false";
    entry.cluster.dataset.ioCollisionSolved="true";
    entry.cluster.dataset.foreignEdgeHits=String(option.foreignEdgeHits||0);
    entry.cluster.classList.remove("layout-constrained","compact-io","micro-io","nano-io","stacked");
    if(entry.manual)saved[entry.id]={x:point.x,y:point.y,dx:point.x-entry.anchor.x,dy:point.y-entry.anchor.y};
  }
  writeStored(labelStorageKey(data),saved);
  stage.dataset.transitionIoCollisionSolved="true";
  stage.dataset.transitionIoCollisionCount="0";
}

function audit(stage=stageOf()){
  if(!stage)return{ok:false,count:0,violations:[{id:"stage",reasons:["missing-stage"]}]};
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")],nodes=[...stage.querySelectorAll(".state-node")].map(nodeRect),violations=[];
  const rects=clusters.map(cluster=>rectAt(cluster,{x:num(cluster.style.left),y:num(cluster.style.top)}));
  const ids=new Set();
  clusters.forEach((cluster,index)=>{
    const id=cluster.dataset.transitionId||String(index),value=cluster.querySelector(".transition-io-value"),node=cluster.querySelector(".transition-io-node.io"),style=value?getComputedStyle(value):null;
    const expected=cluster.dataset.ioValue||"",actual=renderedCanonical(cluster),rect=rects[index],reasons=[];
    if(ids.has(id))reasons.push("duplicate-transition-id");ids.add(id);
    if(!value||!node)reasons.push("missing-label-dom");
    if(actual!==expected)reasons.push("text-mismatch");
    if((Number.parseFloat(style?.fontSize||"0")||0)<9)reasons.push("font-too-small");
    if(style?.textOverflow==="ellipsis")reasons.push("ellipsis");
    if(value&&value.scrollWidth>value.clientWidth+1.5)reasons.push("horizontal-clipping");
    if(value&&value.scrollHeight>value.clientHeight+1.5)reasons.push("vertical-clipping");
    if(node&&value){
      const nodeBox=node.getBoundingClientRect(),valueBox=value.getBoundingClientRect();
      if(valueBox.left<nodeBox.left-1.5||valueBox.right>nodeBox.right+1.5||valueBox.top<nodeBox.top-1.5||valueBox.bottom>nodeBox.bottom+1.5)reasons.push("outside-label-box");
      if(node.getAttribute("aria-label")!==expected)reasons.push("missing-accessible-label");
    }
    if(!finite(rect.x)||!finite(rect.y)||!finite(rect.width)||!finite(rect.height)||rect.width<=0||rect.height<=0)reasons.push("invalid-geometry");
    if(!inside(rect,stage))reasons.push("outside-stage");
    if(nodes.some(item=>intersects(rect,item,1)))reasons.push("node-collision");
    for(let other=0;other<index;other+=1){if(intersects(rect,rects[other],1))reasons.push(`label-collision:${other}`)}
    if(num(cluster.dataset.ioDistance)>MAX_DISTANCE+.5)reasons.push("tether-distance");
    if(!pathFor(stage,id,index))reasons.push("missing-transition-path");
    cluster.dataset.transitionReadability=reasons.length?"failed":"true";
    if(reasons.length)violations.push({id,reasons});
  });
  const expectedCount=Number(stage.dataset.transitionExpectedCount||clusters.length);
  if(clusters.length!==expectedCount)violations.push({id:"stage",reasons:[`transition-count:${clusters.length}/${expectedCount}`]});
  return{ok:clusters.length===expectedCount&&violations.length===0,count:clusters.length,expectedCount,violations};
}

function assignmentFailure(entries,solver,attempt){
  const error=Error("no collision-free transition label assignment exists within the bounded publication layout");
  error.code="layout-assignment-unsatisfied";
  error.details=JSON.stringify({
    attempt,
    steps:solver?.steps||0,
    timedOut:Boolean(solver?.timedOut),
    entries:entries.map(entry=>({id:entry.id,manual:entry.manual,options:entry.options.length})),
  });
  return error;
}
async function placeWithRetry(stage,data,machine,token){
  const attempts=[
    {maxLineWidth:LABEL_MAX_WIDTH,growth:1},
    {maxLineWidth:LABEL_RETRY_WIDTH,growth:1.18},
    {maxLineWidth:LABEL_LAST_WIDTH,growth:1.32},
  ];
  let lastError=null;
  for(let attempt=0;attempt<attempts.length;attempt+=1){
    const strategy=attempts[attempt];
    formatLabels(stage,strategy.maxLineWidth);
    const dense=ensureCanvas(stage,machine.transitions?.length||0,{growth:strategy.growth,includeLabels:true});
    arrangeInitialDenseNodes(stage,data,machine,dense);
    reroute(stage,machine);
    await nextFrame();
    if(cancelled(token))return null;
    const entries=layoutEntries(stage,data,machine);
    if(entries.some(entry=>!entry.options.length)){
      lastError=assignmentFailure(entries,null,attempt);
      continue;
    }
    const greedy=greedyEntries(entries);
    const solver=greedy?{assignment:greedy,steps:0,timedOut:false}:solveEntries(entries,token);
    if(!solver.assignment){lastError=assignmentFailure(entries,solver,attempt);continue}
    applyAssignment(stage,data,entries,solver.assignment);
    await nextFrame();
    const result=audit(stage);
    if(result.ok)return result;
    const error=Error(`transition layout audit failed: ${JSON.stringify(result.violations)}`);
    error.code="layout-publication-audit-failed";
    error.details=JSON.stringify(result);
    lastError=error;
  }
  throw lastError||Error("transition layout failed without diagnostics");
}

async function transaction(token,reason){
  const stage=await waitForPrerequisites(token);
  if(!stage||cancelled(token))return{status:"deferred",stage};
  const data=await diagramState(),machine=selectedMachine(data);
  if(!machine||cancelled(token))return{status:"deferred",stage};
  markPending(stage,token,reason);
  stage.dataset.diagramDigest=data?.digest||"source";
  stage.dataset.transitionExpectedCount=String(machine.transitions?.length||0);
  await waitForFonts(token);
  const dense=ensureCanvas(stage,machine.transitions?.length||0);
  arrangeInitialDenseNodes(stage,data,machine,dense);
  reroute(stage,machine);
  await nextFrame();
  if(cancelled(token))return{status:"cancelled",stage};
  internalClusterRefresh=true;
  try{await window.glyphTransitionIoClusters?.render?.()}finally{internalClusterRefresh=false}
  await nextFrame();
  if(cancelled(token))return{status:"cancelled",stage};
  await ensureClusters(stage,machine,token);
  ensureCanvas(stage,machine.transitions?.length||0,{includeLabels:true});
  reroute(stage,machine);
  await nextFrame();
  if(cancelled(token))return{status:"cancelled",stage};
  const result=await placeWithRetry(stage,data,machine,token);
  if(!result||cancelled(token))return{status:"cancelled",stage};
  clearFailure(stage);
  stage.dataset.transitionIoReadability="true";
  stage.dataset.transitionIoReadabilityViolations="0";
  stage.dataset.transitionSemanticLinesReady="true";
  stage.dataset.transitionSemanticRoleLinesReady="true";
  stage.dataset.transitionLayoutState="ready";
  stage.dataset.transitionPublicationReady="true";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionLayoutMarker=MARKER;
  completedGeneration=token;
  document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready",{detail:{marker:MARKER,generation:token,reason,labels:result.count,digest:data?.digest||"source"}}));
  window.glyphDiagramViewport?.fitInitial?.();
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
        if(outcome.status==="deferred"){
          if(outcome.stage)markDeferred(outcome.stage,token,reason);
          completedGeneration=token;
        }else if(outcome.status==="cancelled"){
          continue;
        }else{
          completedGeneration=token;
        }
      }catch(error){
        if(error?.name==="AbortError"||destroyed||token!==requestedGeneration)continue;
        const stage=stageOf();
        if(stage)markFailure(stage,token,reason,error);
        console.error("transition layout transaction failed",error);
        completedGeneration=token;
      }finally{
        for(const generation of[...generationReasons.keys()])if(generation<=completedGeneration)generationReasons.delete(generation);
      }
    }
  }finally{running=false}
}
function schedule(reason="scheduled",delay=0){
  if(destroyed)return requestedGeneration;
  requestedGeneration+=1;
  generationReasons.set(requestedGeneration,reason);
  if(window.glyphTransitionLayoutTransaction)window.glyphTransitionLayoutTransaction.lastReason=reason;
  clearTimeout(timer);
  timer=setTimeout(()=>drain(),delay);
  return requestedGeneration;
}

function observeStage(stage){
  resizeObserver?.disconnect();
  resizeObserver=null;
  if(!stage||typeof ResizeObserver!=="function")return;
  const shell=stage.closest(".canvas-shell");
  if(!shell)return;
  lastViewportSize=`${shell.clientWidth}x${shell.clientHeight}`;
  resizeObserver=new ResizeObserver(()=>{
    const size=`${shell.clientWidth}x${shell.clientHeight}`;
    if(size===lastViewportSize)return;
    lastViewportSize=size;
    if(activeTab()==="state")schedule("canvas-resize",120);
  });
  resizeObserver.observe(shell);
}
function synchronizeStage(){
  const stage=stageOf();
  if(stage===lastStage)return;
  lastStage=stage;
  invalidateState();
  observeStage(stage);
  schedule("stage-replaced",0);
}

for(const eventName of[
  "glyph-state-transition-ir-v3-labels-ready",
  "glyph-state-transition-ir-v4-labels-ready",
  "glyph-transition-enabling-cases-ready",
  "glyph-transition-io-clusters-ready",
  "glyph-uml-transition-ready",
  "glyph-execution-context-changed",
  "glyph-locale-changed",
]){
  document.addEventListener(eventName,()=>{
    if(internalClusterRefresh&&(eventName==="glyph-transition-io-clusters-ready"||eventName==="glyph-transition-enabling-cases-ready"))return;
    invalidateState();schedule(eventName,0);
  });
}
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){invalidateState();schedule("machine-change",0)}
});
document.addEventListener("pointerup",event=>{
  if(event.target?.closest?.(".state-node,.transition-io-cluster"))schedule("manual-edit",24);
},true);
const view=document.getElementById("view")||document.body;
new MutationObserver(synchronizeStage).observe(view,{childList:true,subtree:true});
window.addEventListener("resize",()=>schedule("window-resize",120));
if(document.fonts?.ready)document.fonts.ready.then(()=>schedule("fonts-ready",0)).catch(()=>{});
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{
    destroyed=true;
    clearTimeout(timer);
    resizeObserver?.disconnect();
    invalidateState();
  },{once:true});
}

window.glyphTransitionLayoutTransaction={
  marker:MARKER,
  version:2,
  ownsScheduling:true,
  schedule,
  run:()=>schedule("manual-run",0),
  audit:()=>audit(stageOf()),
  get generation(){return requestedGeneration},
  get completedGeneration(){return completedGeneration},
  lastReason:"bootstrap",
};
lastStage=stageOf();
observeStage(lastStage);
schedule("bootstrap",0);
})();
</script>
"""


def enhance_transition_layout_transaction_html(html: str) -> str:
    """Own responsive, bounded, publication-grade transition layout and readiness."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
