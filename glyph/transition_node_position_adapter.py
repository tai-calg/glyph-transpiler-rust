from __future__ import annotations


_MARKER = "glyph-transition-node-position-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-node-position-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-node-position-adapter-v1";
let active=null,stateCache=null,lastStage=null,restoreGeneration=0;
const num=value=>Number.parseFloat(value||"0")||0;
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";

async function diagramState(){
  if(stateCache)return stateCache;
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)throw Error("diagram state unavailable");
  return stateCache=await response.json();
}
function machineIndex(){return document.getElementById("machine-select")?.value||0}
function canonicalKey(data){return`glyph.diagram.positions.v1:${data?.digest||"source"}:state:${machineIndex()}`}
function legacyKeys(data){
  const index=machineIndex(),digest=data?.digest||"source";
  return[
    `glyph.diagram.positions.v1:source:state:${index}`,
    `glyph.diagram.positions.v1:${digest}:state:${index}`,
  ];
}
function parse(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
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
  const data=await diagramState(),key=canonicalKey(data);
  localStorage.setItem(key,JSON.stringify(record.positions));
  if(record.stage.isConnected)apply(record.stage,record.positions);
  record.stage.dataset.transitionNodePositions=`saved:${Object.keys(record.positions).length}`;
  window.glyphTransitionLayoutTransaction?.schedule("manual-node-persisted",0);
}
async function restore(stage,token){
  if(!stage||!stage.isConnected)return false;
  const data=await diagramState();
  if(token!==restoreGeneration||!stage.isConnected)return false;
  const key=canonicalKey(data);
  let value=parse(key),source=key;
  if(!Object.keys(value).length){
    for(const candidate of legacyKeys(data)){
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
  localStorage.setItem(key,JSON.stringify(value));
  stage.dataset.transitionNodePositions=`restored:${count}`;
  stage.dataset.transitionNodePositionSource=source;
  window.glyphTransitionLayoutTransaction?.schedule("node-positions-restored",0);
  return count>0;
}
function scheduleRestore(stage=null,delay=0){
  const target=stage||document.querySelector(".state-node")?.closest(".graph-stage");
  const token=++restoreGeneration;
  setTimeout(()=>restore(target,token).catch(error=>console.error("transition node position restore failed",error)),delay);
}

document.addEventListener("pointerdown",event=>{
  const node=event.target?.closest?.(".state-node");
  if(!node||event.button!==0)return;
  active={node,stage:node.closest(".graph-stage"),pointerId:event.pointerId};
},true);
document.addEventListener("pointerup",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  const record={...active,positions:snapshot(active.stage)};
  active=null;
  queueMicrotask(()=>persist(record).catch(error=>console.error("transition node position persistence failed",error)));
},true);
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){
    stateCache=null;
    scheduleRestore(null,20);
  }
});
const view=document.getElementById("view")||document.body;
new MutationObserver(()=>{
  const stage=document.querySelector(".state-node")?.closest(".graph-stage")||null;
  if(stage&&stage!==lastStage){lastStage=stage;scheduleRestore(stage,0)}
}).observe(view,{childList:true,subtree:true});
lastStage=document.querySelector(".state-node")?.closest(".graph-stage")||null;
scheduleRestore(lastStage,0);
window.glyphTransitionNodePositionAdapter={marker:MARKER,restore:()=>scheduleRestore(null,0)};
})();
</script>
"""


def enhance_transition_node_position_adapter_html(html: str) -> str:
    """Persist and restore node coordinates in the transaction's canonical key space."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
