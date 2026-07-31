from __future__ import annotations


_MARKER = "glyph-transition-layout-interaction-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-interaction-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-layout-interaction-adapter-v1",MAX_DISTANCE=96,DRAG_THRESHOLD=3;
let active=null,selected=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function invalidateState(){stateVersion+=1;stateCache=null;statePromise=null;stateAbort?.abort();stateAbort=null}
async function diagramState(){
  if(stateCache)return stateCache;
  if(statePromise)return statePromise;
  const version=stateVersion,controller=new AbortController();stateAbort=controller;
  statePromise=(async()=>{
    const response=await fetch("/api/state",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error(`diagram state unavailable: HTTP ${response.status}`);
    const data=await response.json();
    if(version!==stateVersion||destroyed)throw new DOMException("stale diagram state","AbortError");
    stateCache=data;return data;
  })().finally(()=>{if(stateAbort===controller)stateAbort=null;statePromise=null});
  return statePromise;
}
function storageKey(data){const index=document.getElementById("machine-select")?.value||0;return`glyph.diagram.transition-io.v1:${data?.digest||"source"}:${index}`}
function project(point,anchor){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(!distance||distance<=MAX_DISTANCE)return point;const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function constrain(point,cluster,stage){const width=Number.parseFloat(stage.style.width||"")||stage.scrollWidth,height=Number.parseFloat(stage.style.height||"")||stage.scrollHeight;return{x:clamp(point.x,cluster.offsetWidth/2+8,width-cluster.offsetWidth/2-8),y:clamp(point.y,cluster.offsetHeight/2+8,height-cluster.offsetHeight/2-8)}}
function feasible(point,anchor,cluster,stage){let next=constrain(project(point,anchor),cluster,stage);next=project(next,anchor);next=constrain(next,cluster,stage);return Math.hypot(next.x-anchor.x,next.y-anchor.y)<=MAX_DISTANCE+.25?next:null}
function parseStored(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
function writeStored(key,value){try{localStorage.setItem(key,JSON.stringify(value));return true}catch(error){console.warn("manual transition position persistence unavailable",error);return false}}
function select(cluster){selected?.classList.remove("selected-io");selected=cluster;selected?.classList.add("selected-io")}
function report(error,prefix){if(error?.name!=="AbortError"&&!destroyed)console.error(prefix,error)}
function requestedPoint(record,event){return feasible({x:record.left+(event.clientX-record.startX)/record.scale,y:record.top+(event.clientY-record.startY)/record.scale},record.anchor,record.cluster,record.stage)}
async function persist(record,event){
  await new Promise(resolve=>setTimeout(resolve,0));
  if(destroyed||!record.cluster.isConnected||!record.stage.isConnected)return;
  const pointerDistance=Math.hypot(event.clientX-record.startX,event.clientY-record.startY),current={x:num(record.cluster.style.left),y:num(record.cluster.style.top)},visualDistance=Math.hypot(current.x-record.left,current.y-record.top);
  if(pointerDistance<DRAG_THRESHOLD&&visualDistance<1)return;
  const point=feasible(current,record.anchor,record.cluster,record.stage);if(!point){window.glyphTransitionLayoutTransaction?.schedule("manual-label-outside-tether",0);return}
  const data=await diagramState(),key=storageKey(data),saved=parseStored(key);saved[record.id]={x:point.x,y:point.y,dx:point.x-record.anchor.x,dy:point.y-record.anchor.y};writeStored(key,saved);
  record.cluster.style.left=`${point.x}px`;record.cluster.style.top=`${point.y}px`;record.cluster.dataset.manualIo="true";record.cluster.dataset.ioDistance=String(Math.hypot(point.x-record.anchor.x,point.y-record.anchor.y));window.glyphTransitionLayoutTransaction?.schedule("manual-label-persisted",0);
}
async function resetCluster(cluster){const data=await diagramState(),key=storageKey(data),saved=parseStored(key),id=cluster.dataset.transitionId||"";if(id in saved){delete saved[id];writeStored(key,saved)}cluster.dataset.manualIo="false";window.glyphTransitionLayoutTransaction?.schedule("manual-label-reset",0)}
function finish(event){if(!active||active.pointerId!==event.pointerId)return;const record=active;active=null;record.cluster.classList.remove("dragging-io");persist(record,event).catch(error=>report(error,"manual transition position persistence failed"))}
document.addEventListener("pointerdown",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(!cluster||event.button!==0)return;const stage=cluster.closest(".graph-stage");if(!stage||stage.dataset.transitionLayoutState!=="ready")return;select(cluster);cluster.classList.add("dragging-io");active={cluster,stage,id:cluster.dataset.transitionId||"",pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top),anchor:{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)},scale:scaleFor(stage)}},true);
document.addEventListener("pointermove",event=>{if(!active||active.pointerId!==event.pointerId)return;const point=requestedPoint(active,event);if(!point)return;active.cluster.style.left=`${point.x}px`;active.cluster.style.top=`${point.y}px`;active.cluster.dataset.ioDistance=String(Math.hypot(point.x-active.anchor.x,point.y-active.anchor.y))},true);
document.addEventListener("pointerup",finish,true);
document.addEventListener("pointercancel",event=>{if(!active||active.pointerId!==event.pointerId)return;active.cluster.style.left=`${active.left}px`;active.cluster.style.top=`${active.top}px`;active.cluster.classList.remove("dragging-io");active=null},true);
document.addEventListener("dblclick",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(cluster)resetCluster(cluster).catch(error=>report(error,"manual transition position reset failed"))},true);
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){selected=null;invalidateState()}});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;active=null;selected=null;invalidateState()},{once:true})}
window.glyphTransitionLayoutInteractionAdapter={marker:MARKER,version:3};
})();
</script>
"""


def enhance_transition_layout_interaction_adapter_html(html: str) -> str:
    """Own label drag, reset, selection, and canonical persistence."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
