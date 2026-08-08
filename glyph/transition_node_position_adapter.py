from __future__ import annotations


_MARKER = "glyph-transition-node-position-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-node-position-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-node-position-adapter-v1",DRAG_THRESHOLD=3,NODE_CLEARANCE=96;
const POSITION_KEY_PREFIX="glyph.diagram.positions.v1:";
const EDITING_SELECTOR="input,textarea,select,[contenteditable=true]";
let active=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,lastStage=null,restoreGeneration=0,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const publicationGuard=()=>window.glyphNodeDragPublicationGuard||null;
const workspace=()=>window.glyphStateDiagramWorkspace||null;

function invalidateState(){
  stateVersion+=1;
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
  const version=stateVersion,controller=new AbortController();
  stateAbort=controller;
  statePromise=(async()=>{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error(`diagram state unavailable: HTTP ${response.status}`);
    const data=await response.json();
    if(version!==stateVersion||destroyed)throw new DOMException("stale diagram state","AbortError");
    stateCache=data;
    return data;
  })().finally(()=>{
    if(stateAbort===controller)stateAbort=null;
    statePromise=null;
  });
  return statePromise;
}
function machineIndex(){return document.getElementById("machine-select")?.value||0}
function canonicalKey(data){return`${POSITION_KEY_PREFIX}${data?.digest||"source"}:state:${machineIndex()}`}
function legacyKeys(){return[`${POSITION_KEY_PREFIX}source:state:${machineIndex()}`]}
function parse(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
function write(key,value){
  try{localStorage.setItem(key,JSON.stringify(value));return true}
  catch(error){console.warn("transition node position persistence unavailable",error);return false}
}
function positionStorageState(){
  const values=new Map();
  try{
    for(let index=0;index<localStorage.length;index+=1){
      const key=localStorage.key(index);
      if(key?.startsWith(POSITION_KEY_PREFIX))values.set(key,localStorage.getItem(key));
    }
  }catch(error){console.warn("transition node position snapshot unavailable",error)}
  return values;
}
function restorePositionStorageState(values){
  try{
    const current=[];
    for(let index=0;index<localStorage.length;index+=1){
      const key=localStorage.key(index);
      if(key?.startsWith(POSITION_KEY_PREFIX))current.push(key);
    }
    for(const key of current){if(!values.has(key))localStorage.removeItem(key)}
    for(const[key,value]of values){
      if(value===null)localStorage.removeItem(key);
      else localStorage.setItem(key,value);
    }
  }catch(error){console.warn("transition node click persistence rollback unavailable",error)}
}
function snapshot(stage){
  const value={};
  stage.querySelectorAll(".state-node").forEach(node=>{
    value[nodeName(node)]={x:num(node.style.left),y:num(node.style.top)};
  });
  return value;
}
function apply(stage,value,key=null){
  let count=0;
  stage.querySelectorAll(".state-node").forEach(node=>{
    const raw=value[nodeName(node)];
    if(!raw||!Number.isFinite(Number(raw.x))||!Number.isFinite(Number(raw.y)))return;
    const position=workspace()?.mapRestoredPosition?.(stage,key,raw)||raw;
    node.style.left=`${Number(position.x)}px`;
    node.style.top=`${Number(position.y)}px`;
    count+=1;
  });
  return count;
}
function select(node){
  document.querySelector(".state-node.selected-node")?.classList.remove("selected-node");
  node?.classList.add("selected-node");
}
function editingContext(event){
  const target=event.target?.nodeType===1?event.target:null;
  const focused=document.activeElement?.nodeType===1?document.activeElement:null;
  return Boolean(target?.closest?.(EDITING_SELECTOR)||focused?.closest?.(EDITING_SELECTOR));
}
function pointerDistance(record,event){return Math.hypot(event.clientX-record.startX,event.clientY-record.startY)}
function clearancePenalty(record,left,top){
  const right=left+record.node.offsetWidth,bottom=top+record.node.offsetHeight;
  return[...record.stage.querySelectorAll(".state-node")].reduce((total,other)=>{
    if(other===record.node)return total;
    const otherLeft=other.offsetLeft,otherTop=other.offsetTop;
    const otherRight=otherLeft+other.offsetWidth,otherBottom=other.offsetTop+other.offsetHeight;
    const horizontalGap=Math.max(otherLeft-right,left-otherRight,0);
    const verticalGap=Math.max(otherTop-bottom,top-otherBottom,0);
    if(horizontalGap>=NODE_CLEARANCE||verticalGap>=NODE_CLEARANCE)return total;
    return total+(NODE_CLEARANCE-horizontalGap)*(NODE_CLEARANCE-verticalGap);
  },0);
}
function positionIsClear(record,left,top){return clearancePenalty(record,left,top)===0}
function constrainPosition(record,left,top){
  const baseline=clearancePenalty(record,record.startLeft,record.startTop);
  const requested=clearancePenalty(record,left,top);
  if(requested===0||requested<=baseline)return{left,top,constrained:requested>0};
  for(let step=23;step>=0;step-=1){
    const ratio=step/24;
    const candidateLeft=record.startLeft+(left-record.startLeft)*ratio;
    const candidateTop=record.startTop+(top-record.startTop)*ratio;
    const candidatePenalty=clearancePenalty(record,candidateLeft,candidateTop);
    if(candidatePenalty<=baseline){
      return{left:candidateLeft,top:candidateTop,constrained:candidatePenalty>0};
    }
  }
  return{left:record.startLeft,top:record.startTop,constrained:true};
}
function invalidatePublication(record,reason){
  if(record.publicationInvalidated)return true;
  record.publicationInvalidated=Boolean(publicationGuard()?.invalidate?.(record.stage,reason));
  return record.publicationInvalidated;
}
function moveActive(event){
  if(!active||active.pointerId!==event.pointerId)return false;
  if(!active.moved&&pointerDistance(active,event)<DRAG_THRESHOLD)return false;
  const scale=Math.max(.01,active.scale),grid=event.shiftKey?1:8;
  const width=Number.parseFloat(active.stage.style.width||"")||active.stage.scrollWidth;
  const height=Number.parseFloat(active.stage.style.height||"")||active.stage.scrollHeight;
  const left=active.startLeft+(event.clientX-active.startX)/scale;
  const top=active.startTop+(event.clientY-active.startY)/scale;
  const boundedLeft=clamp(left,8,Math.max(8,width-active.node.offsetWidth-8));
  const boundedTop=clamp(top,8,Math.max(8,height-active.node.offsetHeight-8));
  const requestedLeft=Math.round(boundedLeft/grid)*grid;
  const requestedTop=Math.round(boundedTop/grid)*grid;
  const position=constrainPosition(active,requestedLeft,requestedTop);
  if(!active.moved
    &&position.left===active.startLeft
    &&position.top===active.startTop)return false;
  if(!active.moved)invalidatePublication(active,"manual-node-drag");
  active.moved=true;
  active.node.style.left=`${position.left}px`;
  active.node.style.top=`${position.top}px`;
  active.stage.dataset.transitionNodeClearance=String(NODE_CLEARANCE);
  active.stage.dataset.transitionNodeDragConstrained=position.constrained?"true":"false";
  return true;
}
async function persist(record){
  if(destroyed||!record.stage.isConnected)return;
  const data=await diagramState(),key=canonicalKey(data);
  write(key,record.positions);
  workspace()?.markPositionMigration?.(record.stage,key);
  if(record.stage.isConnected)apply(record.stage,record.positions,key);
  record.stage.dataset.transitionNodePositions=`saved:${Object.keys(record.positions).length}`;
  window.glyphTransitionLayoutTransaction?.schedule("manual-node-persisted",0);
}
function nextFrame(){return new Promise(resolve=>requestAnimationFrame(resolve))}
async function waitForWorkspaceOrigin(stage,token){
  if(!workspace())return true;
  for(let attempt=0;attempt<24;attempt+=1){
    if(token!==restoreGeneration||!stage?.isConnected||destroyed)return false;
    if(stage.dataset.stateDiagramWorkspaceOriginReady==="true")return true;
    await nextFrame();
  }
  return stage?.dataset.stateDiagramWorkspaceOriginReady==="true";
}
async function restore(stage,token){
  if(!stage||!stage.isConnected||destroyed)return false;
  const data=await diagramState();
  if(token!==restoreGeneration||!stage.isConnected||destroyed)return false;
  if(!(await waitForWorkspaceOrigin(stage,token))){
    if(token===restoreGeneration&&stage.isConnected&&!destroyed)scheduleRestore(stage,0);
    return false;
  }
  if(token!==restoreGeneration||!stage.isConnected||destroyed)return false;
  const key=canonicalKey(data);
  let value=parse(key),source=key;
  if(!Object.keys(value).length){
    for(const candidate of legacyKeys()){
      const found=parse(candidate);
      if(Object.keys(found).length){value=found;source=candidate;break}
    }
  }
  if(!Object.keys(value).length){
    stage.dataset.transitionNodePositions="none";
    window.glyphTransitionLayoutTransaction?.schedule("node-positions-none",0);
    return false;
  }
  const count=apply(stage,value,source);
  const normalized=snapshot(stage);
  write(key,normalized);
  workspace()?.markPositionMigration?.(stage,source);
  workspace()?.markPositionMigration?.(stage,key);
  stage.dataset.transitionNodePositions=`restored:${count}`;
  stage.dataset.transitionNodePositionSource=source;
  window.glyphTransitionLayoutTransaction?.schedule("node-positions-restored",0);
  return count>0;
}
function report(error,prefix){if(error?.name!=="AbortError"&&!destroyed)console.error(prefix,error)}
function scheduleRestore(stage=null,delay=0){
  const target=stage||document.querySelector(".state-node")?.closest(".graph-stage");
  const token=++restoreGeneration;
  setTimeout(()=>restore(target,token).catch(error=>report(error,"transition node position restore failed")),delay);
}

document.addEventListener("pointerdown",event=>{
  const node=event.target?.closest?.(".state-node");
  if(!node||event.button!==0)return;
  const stage=node.closest(".graph-stage");
  if(!stage||stage.dataset.transitionLayoutState!=="ready")return;
  event.preventDefault();
  event.stopImmediatePropagation();
  select(node);
  node.classList.add("dragging");
  node.setPointerCapture?.(event.pointerId);
  active={
    node,
    stage,
    pointerId:event.pointerId,
    startX:event.clientX,
    startY:event.clientY,
    startLeft:num(node.style.left),
    startTop:num(node.style.top),
    scale:scaleFor(stage),
    moved:false,
    publicationInvalidated:false,
    storageBefore:positionStorageState(),
  };
},true);
document.addEventListener("pointermove",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  event.preventDefault();
  event.stopImmediatePropagation();
  moveActive(event);
},true);
document.addEventListener("pointerup",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const record=active;active=null;
  record.node.releasePointerCapture?.(event.pointerId);
  record.node.classList.remove("dragging");
  if(!record.moved){
    setTimeout(()=>restorePositionStorageState(record.storageBefore),0);
    return;
  }
  record.positions=snapshot(record.stage);
  queueMicrotask(()=>persist(record).catch(error=>{
    publicationGuard()?.schedule?.("manual-node-persist-failed");
    report(error,"transition node position persistence failed");
  }));
},true);
document.addEventListener("pointercancel",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  event.stopImmediatePropagation();
  const record=active;active=null;
  record.node.style.left=`${record.startLeft}px`;
  record.node.style.top=`${record.startTop}px`;
  record.node.classList.remove("dragging");
  if(record.publicationInvalidated)publicationGuard()?.schedule?.("manual-node-cancelled");
},true);
document.addEventListener("keydown",event=>{
  if(!event.key.startsWith("Arrow"))return;
  if(editingContext(event))return;
  const node=document.querySelector(".state-node.selected-node");
  const stage=node?.closest(".graph-stage");
  if(!node||!stage||stage.dataset.transitionLayoutState!=="ready")return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const step=event.shiftKey?1:8;
  const dx=event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0;
  const dy=event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0;
  const width=Number.parseFloat(stage.style.width||"")||stage.scrollWidth;
  const height=Number.parseFloat(stage.style.height||"")||stage.scrollHeight;
  const record={
    node,
    stage,
    startLeft:num(node.style.left),
    startTop:num(node.style.top),
    publicationInvalidated:false,
  };
  const requestedLeft=clamp(record.startLeft+dx,8,Math.max(8,width-node.offsetWidth-8));
  const requestedTop=clamp(record.startTop+dy,8,Math.max(8,height-node.offsetHeight-8));
  const position=constrainPosition(record,requestedLeft,requestedTop);
  if(position.left===record.startLeft&&position.top===record.startTop)return;
  invalidatePublication(record,"manual-node-keyboard");
  node.style.left=`${position.left}px`;
  node.style.top=`${position.top}px`;
  stage.dataset.transitionNodeClearance=String(NODE_CLEARANCE);
  stage.dataset.transitionNodeDragConstrained=position.constrained?"true":"false";
  record.positions=snapshot(stage);
  queueMicrotask(()=>persist(record).catch(error=>{
    publicationGuard()?.schedule?.("manual-node-keyboard-persist-failed");
    report(error,"transition node keyboard persistence failed");
  }));
},true);
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){
    invalidateState();
    scheduleRestore(null,20);
  }
});
const view=document.getElementById("view")||document.body;
new MutationObserver(()=>{
  const stage=document.querySelector(".state-node")?.closest(".graph-stage")||null;
  if(stage&&stage!==lastStage){lastStage=stage;scheduleRestore(stage,0)}
}).observe(view,{childList:true,subtree:true});
for(const eventName of["pagehide","beforeunload"]){
  window.addEventListener(eventName,()=>{
    destroyed=true;
    active=null;
    restoreGeneration+=1;
    invalidateState();
  },{once:true});
}
lastStage=document.querySelector(".state-node")?.closest(".graph-stage")||null;
scheduleRestore(lastStage,0);
window.glyphTransitionNodePositionAdapter={marker:MARKER,version:8,restore:()=>scheduleRestore(null,0)};
})();
</script>
"""


def enhance_transition_node_position_adapter_html(html: str) -> str:
    """Own, persist, migrate, and restore state-node positions."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")