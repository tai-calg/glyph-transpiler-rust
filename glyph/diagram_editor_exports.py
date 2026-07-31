from __future__ import annotations


_MARKER = "glyph-diagram-editor-exports-v1"

_STYLE = r"""
<style id="glyph-diagram-editor-exports-v1-style">
.export-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.export-toolbar button,.export-toolbar select{border:1px solid var(--line);border-radius:9px;background:var(--surface);color:var(--text);padding:7px 10px;font:inherit}.export-toolbar button{cursor:pointer}.export-toolbar button:hover{border-color:var(--accent)}.state-node.editable{cursor:move}.state-node.editable.dragging{opacity:.78}.transition-io-cluster.editable{cursor:move}.transition-io-cluster.editable.dragging{opacity:.72}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-editor-exports-v1-script">
(()=>{
const MARKER="glyph-diagram-editor-exports-v1",POSITION_KEY_PREFIX="glyph.diagram.positions.v1:",TRANSITION_KEY_PREFIX="glyph.diagram.transition-io.v1:",DRAG_THRESHOLD=3;
let drag=null,ioDrag=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,enhanceGeneration=0,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";
const transitionId=cluster=>cluster.dataset.transitionId||"";

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
    if(destroyed||version!==stateVersion)throw new DOMException("stale diagram state","AbortError");
    stateCache=data;
    return data;
  })().finally(()=>{
    if(stateAbort===controller)stateAbort=null;
    statePromise=null;
  });
  return statePromise;
}
function machineIndex(){return document.getElementById("machine-select")?.value||0}
function key(data){return`${POSITION_KEY_PREFIX}${data?.digest||"source"}:state:${machineIndex()}`}
function transitionKey(data){return`${TRANSITION_KEY_PREFIX}${data?.digest||"source"}:state:${machineIndex()}`}
function legacyKeys(){return[`${POSITION_KEY_PREFIX}source:state:${machineIndex()}`]}
function legacyTransitionKeys(){return[`${TRANSITION_KEY_PREFIX}source:state:${machineIndex()}`]}
function parseStored(storageKey){
  try{return JSON.parse(localStorage.getItem(storageKey)||"{}")||{}}
  catch{return{}}
}
function writeStored(storageKey,value){
  try{localStorage.setItem(storageKey,JSON.stringify(value));return true}
  catch(error){console.warn("diagram layout persistence unavailable",error);return false}
}
function current(stage){
  const value={};
  stage.querySelectorAll(".state-node").forEach(node=>{
    value[nodeName(node)]={x:num(node.style.left),y:num(node.style.top)};
  });
  return value;
}
function currentTransitions(stage){
  const value={};
  stage.querySelectorAll(".transition-io-cluster[data-transition-id]").forEach(cluster=>{
    const id=transitionId(cluster),anchorX=num(cluster.dataset.anchorX),anchorY=num(cluster.dataset.anchorY),x=num(cluster.style.left),y=num(cluster.style.top);
    if(id)value[id]={x,y,dx:x-anchorX,dy:y-anchorY};
  });
  return value;
}
function apply(stage,value){
  let count=0;
  stage.querySelectorAll(".state-node").forEach(node=>{
    const position=value[nodeName(node)];
    if(!position)return;
    node.style.left=`${position.x}px`;
    node.style.top=`${position.y}px`;
    count+=1;
  });
  return count;
}
function applyTransitions(stage,value){
  let count=0;
  stage.querySelectorAll(".transition-io-cluster[data-transition-id]").forEach(cluster=>{
    const position=value[transitionId(cluster)];
    if(!position)return;
    const anchorX=num(cluster.dataset.anchorX),anchorY=num(cluster.dataset.anchorY);
    const x=Number.isFinite(Number(position.dx))?anchorX+Number(position.dx):Number(position.x);
    const y=Number.isFinite(Number(position.dy))?anchorY+Number(position.dy):Number(position.y);
    if(!Number.isFinite(x)||!Number.isFinite(y))return;
    cluster.style.left=`${x}px`;
    cluster.style.top=`${y}px`;
    cluster.dataset.ioDistance=String(Math.hypot(x-anchorX,y-anchorY));
    cluster.dataset.manualIo="true";
    count+=1;
  });
  return count;
}
function save(stage){
  diagramState().then(data=>writeStored(key(data),current(stage))).catch(error=>{
    if(error?.name!=="AbortError"&&!destroyed)console.error("diagram position save failed",error);
  });
}
function saveTransitions(stage){
  diagramState().then(data=>writeStored(transitionKey(data),currentTransitions(stage))).catch(error=>{
    if(error?.name!=="AbortError"&&!destroyed)console.error("transition position save failed",error);
  });
}
function dispatchReady(stage){
  document.dispatchEvent(new CustomEvent("glyph-diagram-editor-ready",{detail:{marker:MARKER,stage}}));
}
function reroute(stage){
  delete stage.dataset.initialTransitionRouting;
  window.glyphInitialTransitionRouter?.schedule?.("editor-layout-change",0);
  document.dispatchEvent(new CustomEvent("glyph-state-transition-ir-v3-labels-ready",{detail:{stage,reason:"editor-layout-change"}}));
}
function edit(stage){
  stage.querySelectorAll(".state-node").forEach(node=>{
    if(node.dataset.editorReady===MARKER)return;
    node.dataset.editorReady=MARKER;
    node.classList.add("editable");
    node.onpointerdown=event=>{
      if(event.button!==0)return;
      drag={node,stage,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(node.style.left),top:num(node.style.top),moved:false};
      node.setPointerCapture?.(event.pointerId);
      node.classList.add("dragging");
    };
    node.onpointermove=event=>{
      if(!drag||drag.node!==node||drag.pointerId!==event.pointerId)return;
      const dx=event.clientX-drag.startX,dy=event.clientY-drag.startY;
      if(!drag.moved&&Math.hypot(dx,dy)<DRAG_THRESHOLD)return;
      drag.moved=true;
      node.style.left=`${drag.left+dx}px`;
      node.style.top=`${drag.top+dy}px`;
      reroute(stage);
    };
    node.onpointerup=event=>{
      if(!drag||drag.node!==node||drag.pointerId!==event.pointerId)return;
      const moved=drag.moved;
      node.releasePointerCapture?.(event.pointerId);
      drag=null;
      node.classList.remove("dragging");
      if(!moved)return;
      save(stage);
      reroute(stage);
    };
  });
  stage.querySelectorAll(".transition-io-cluster[data-transition-id]").forEach(cluster=>{
    if(cluster.dataset.editorReady===MARKER)return;
    cluster.dataset.editorReady=MARKER;
    cluster.classList.add("editable");
    cluster.onpointerdown=event=>{
      if(event.button!==0)return;
      ioDrag={cluster,stage,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top),moved:false};
      cluster.setPointerCapture?.(event.pointerId);
      cluster.classList.add("dragging");
    };
    cluster.onpointermove=event=>{
      if(!ioDrag||ioDrag.cluster!==cluster||ioDrag.pointerId!==event.pointerId)return;
      const dx=event.clientX-ioDrag.startX,dy=event.clientY-ioDrag.startY;
      if(!ioDrag.moved&&Math.hypot(dx,dy)<DRAG_THRESHOLD)return;
      ioDrag.moved=true;
      const anchorX=num(cluster.dataset.anchorX),anchorY=num(cluster.dataset.anchorY),maxDistance=Math.max(1,num(cluster.dataset.maxIoDistance)||96);
      let x=ioDrag.left+dx,y=ioDrag.top+dy;
      const distance=Math.hypot(x-anchorX,y-anchorY);
      if(distance>maxDistance){const ratio=maxDistance/distance;x=anchorX+(x-anchorX)*ratio;y=anchorY+(y-anchorY)*ratio}
      cluster.style.left=`${x}px`;
      cluster.style.top=`${y}px`;
      cluster.dataset.ioDistance=String(Math.hypot(x-anchorX,y-anchorY));
    };
    cluster.onpointerup=event=>{
      if(!ioDrag||ioDrag.cluster!==cluster||ioDrag.pointerId!==event.pointerId)return;
      const moved=ioDrag.moved;
      cluster.releasePointerCapture?.(event.pointerId);
      ioDrag=null;
      cluster.classList.remove("dragging");
      if(!moved)return;
      cluster.dataset.manualIo="true";
      saveTransitions(stage);
      reroute(stage);
    };
  });
  stage.dataset.editorReady="true";
  dispatchReady(stage);
}
async function restore(stage,token){
  if(!stage||!stage.isConnected||destroyed)return;
  const data=await diagramState();
  if(token!==enhanceGeneration||!stage.isConnected||destroyed)return;
  const canonicalKey=key(data),canonicalTransitionKey=transitionKey(data);
  let positions=parseStored(canonicalKey),source=canonicalKey;
  if(!Object.keys(positions).length){
    for(const candidate of legacyKeys()){
      const found=parseStored(candidate);
      if(Object.keys(found).length){positions=found;source=candidate;break}
    }
  }
  let transitionPositions=parseStored(canonicalTransitionKey),transitionSource=canonicalTransitionKey;
  if(!Object.keys(transitionPositions).length){
    for(const candidate of legacyTransitionKeys()){
      const found=parseStored(candidate);
      if(Object.keys(found).length){transitionPositions=found;transitionSource=candidate;break}
    }
  }
  const restored=apply(stage,positions),transitionRestored=applyTransitions(stage,transitionPositions);
  if(restored)writeStored(canonicalKey,positions);
  if(transitionRestored)writeStored(canonicalTransitionKey,transitionPositions);
  stage.dataset.positionRestoreSource=source;
  stage.dataset.positionRestoreCount=String(restored);
  stage.dataset.transitionPositionRestoreSource=transitionSource;
  stage.dataset.transitionPositionRestoreCount=String(transitionRestored);
  edit(stage);
  reroute(stage);
}
function enhance(){
  const stage=document.querySelector(".state-node")?.closest(".graph-stage");
  const token=++enhanceGeneration;
  restore(stage,token).catch(error=>{
    if(error?.name!=="AbortError"&&!destroyed)console.error("diagram editor restore failed",error);
  });
}
function toolbar(){
  const controls=document.querySelector(".controls");
  if(!controls||controls.querySelector(".export-toolbar"))return;
  const row=document.createElement("div");
  row.className="export-toolbar";
  row.innerHTML=`<button type="button" data-export="png">PNG</button><button type="button" data-export="svg">SVG</button><button type="button" data-export="pdf">PDF</button><button type="button" data-reset-layout>Reset layout</button>`;
  row.addEventListener("click",async event=>{
    const exportType=event.target?.dataset?.export;
    if(exportType){
      const machine=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent?.trim()||"diagram";
      const response=await fetch(`/api/export?format=${encodeURIComponent(exportType)}&machine=${encodeURIComponent(machine)}`);
      if(!response.ok)throw Error(`export failed: HTTP ${response.status}`);
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=url;link.download=`${machine}.${exportType}`;link.click();URL.revokeObjectURL(url);
      return;
    }
    if(event.target?.hasAttribute("data-reset-layout")){
      const data=await diagramState();
      localStorage.removeItem(key(data));
      localStorage.removeItem(transitionKey(data));
      legacyKeys().forEach(item=>localStorage.removeItem(item));
      legacyTransitionKeys().forEach(item=>localStorage.removeItem(item));
      document.querySelector(".tab.active")?.click();
    }
  });
  controls.appendChild(row);
}
for(const eventName of["glyph-initial-transition-ready","glyph-transition-io-clusters-ready"]){document.addEventListener(eventName,enhance)}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){invalidateState();enhance()}});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;drag=null;ioDrag=null;enhanceGeneration+=1;invalidateState()},{once:true})}
toolbar();enhance();
window.glyphDiagramEditorExports={marker:MARKER,version:2,enhance};
})();
</script>
"""


def enhance_diagram_editor_exports_html(html: str) -> str:
    """Install drag editing and PNG/SVG/PDF export controls."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
