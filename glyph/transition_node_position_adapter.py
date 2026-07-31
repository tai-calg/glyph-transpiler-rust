from __future__ import annotations


_MARKER = "glyph-transition-node-position-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-node-position-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-node-position-adapter-v1",DRAG_THRESHOLD=3;
const POSITION_KEY_PREFIX="glyph.diagram.positions.v1:";
let active=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,lastStage=null,restoreGeneration=0,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";

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
function apply(stage,value){
  let count=0;
  stage.querySelectorAll(".state-node").forEach(node=>{
    const position=value[nodeName(node)];
    if(!position||!Number.isFinite(Number(position.x))||!Number.isFinite(Number(position.y)))return;
    node.style.left=`${Number(position.x)}px`;
    node.style.top=`${Number(position.y)}px`;
    count+=1;
  });
  return count;
}
async function persist(record){
  if(destroyed||!record.stage.isConnected)return;
  const data=await diagramState(),key=canonicalKey(data);
  write(key,record.positions);
  if(record.stage.isConnected)apply(record.stage,record.positions);
  record.stage.dataset.transitionNodePositions=`saved:${Object.keys(record.positions).length}`;
  window.glyphTransitionLayoutTransaction?.schedule("manual-node-persisted",0);
}
async function restore(stage,token){
  if(!stage||!stage.isConnected||destroyed)return false;
  const data=await diagramState();
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
  const count=apply(stage,value);
  write(key,value);
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
  if(!stage)return;
  active={
    node,
    stage,
    pointerId:event.pointerId,
    startX:event.clientX,
    startY:event.clientY,
    startLeft:num(node.style.left),
    startTop:num(node.style.top),
    storageBefore:positionStorageState(),
  };
},true);
document.addEventListener("pointerup",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  const record=active;active=null;
  const pointerDistance=Math.hypot(event.clientX-record.startX,event.clientY-record.startY);
  const visualDistance=Math.hypot(num(record.node.style.left)-record.startLeft,num(record.node.style.top)-record.startTop);
  if(pointerDistance<DRAG_THRESHOLD&&visualDistance<1){
    setTimeout(()=>restorePositionStorageState(record.storageBefore),0);
    return;
  }
  record.positions=snapshot(record.stage);
  queueMicrotask(()=>persist(record).catch(error=>report(error,"transition node position persistence failed")));
},true);
document.addEventListener("pointercancel",event=>{
  if(active?.pointerId===event.pointerId)active=null;
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
window.glyphTransitionNodePositionAdapter={marker:MARKER,version:3,restore:()=>scheduleRestore(null,0)};
})();
</script>
"""


def enhance_transition_node_position_adapter_html(html: str) -> str:
    """Persist and restore actual node drags in the canonical diagram key space."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
