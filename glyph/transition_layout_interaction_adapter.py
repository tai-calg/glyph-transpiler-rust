from __future__ import annotations


_MARKER = "glyph-transition-layout-interaction-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-interaction-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-layout-interaction-adapter-v1",MAX_DISTANCE=96,DRAG_THRESHOLD=3;
const FOREIGN_ROUTE_CLEARANCE=1,NODE_CLEARANCE=2,LABEL_CLEARANCE=2;
const SNAP_RADII=[0,8,16,24,32,48,64,80,96],SNAP_DIRECTIONS=16;
let active=null,selected=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,destroyed=false,gestureSequence=0;
const num=value=>Number.parseFloat(value||"0")||0;
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const publicationGuard=()=>window.glyphTransitionLabelDragGuard||null;
function escapeId(value){return window.CSS?.escape?CSS.escape(value):String(value).replace(/[^A-Za-z0-9_-]/g,"\\$&")}
function invalidateState(){stateVersion+=1;stateCache=null;statePromise=null;stateAbort?.abort();stateAbort=null}
async function diagramState(){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live)return live;
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
function pointerDistance(record,event){return Math.hypot(event.clientX-record.startX,event.clientY-record.startY)}
function requestedPoint(record,event){return feasible({x:record.left+(event.clientX-record.startX)/record.scale,y:record.top+(event.clientY-record.startY)/record.scale},record.anchor,record.cluster,record.stage)}
function centeredRect(cluster,point,margin=0){return{left:point.x-cluster.offsetWidth/2-margin,top:point.y-cluster.offsetHeight/2-margin,right:point.x+cluster.offsetWidth/2+margin,bottom:point.y+cluster.offsetHeight/2+margin}}
function elementRect(element,margin=0){return{left:element.offsetLeft-margin,top:element.offsetTop-margin,right:element.offsetLeft+element.offsetWidth+margin,bottom:element.offsetTop+element.offsetHeight+margin}}
function clusterRect(cluster,margin=0){const x=num(cluster.style.left),y=num(cluster.style.top);return centeredRect(cluster,{x,y},margin)}
function overlaps(a,b){return!(a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top)}
function liveCluster(record){
  if(record.cluster?.isConnected)return record.cluster;
  if(!record.stage?.isConnected)return null;
  return record.stage.querySelector(`.transition-io-cluster[data-transition-id="${escapeId(record.id)}"]`);
}
function markGesture(record,state,reason=""){
  const cluster=liveCluster(record);
  if(cluster){
    record.cluster=cluster;
    cluster.dataset.manualIoGestureState=state;
    cluster.dataset.manualIoGestureToken=String(record.gestureToken);
    if(reason)cluster.dataset.manualIoGestureReason=reason;
    else delete cluster.dataset.manualIoGestureReason;
  }
  if(record.stage?.isConnected)record.stage.dataset.manualLabelEditState=state;
}
function refreshRecord(record){
  const cluster=liveCluster(record);
  if(!cluster)return false;
  if(cluster!==record.cluster)record.cluster=cluster;
  const anchor={x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)};
  if(record.finalOffset){
    record.finalPoint={x:anchor.x+record.finalOffset.x,y:anchor.y+record.finalOffset.y};
  }
  record.anchor=anchor;
  return true;
}
function manualPlacementViolation(record,point){
  const geometry=window.glyphDiagramGeometry;
  if(!geometry||geometry.version<1)return"geometry-kernel-unavailable";
  const candidate=centeredRect(record.cluster,point,LABEL_CLEARANCE);
  for(const node of record.stage.querySelectorAll(".state-node")){
    if(overlaps(candidate,elementRect(node,NODE_CLEARANCE)))return"label-node-overlap";
  }
  for(const cluster of record.stage.querySelectorAll(".transition-io-cluster")){
    if(cluster===record.cluster)continue;
    if(overlaps(candidate,clusterRect(cluster,LABEL_CLEARANCE)))return"label-label-overlap";
  }
  for(const path of record.stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")){
    if((path.dataset.transitionId||"")===record.id)continue;
    const polyline=geometry.flattenPathElement(path,{tolerance:.35,maxSegmentLength:3});
    if(geometry.polylineHitsRect(polyline,centeredRect(record.cluster,point,FOREIGN_ROUTE_CLEARANCE))){
      return"route-foreign-label";
    }
  }
  return"";
}
function nearestCertifiablePoint(record,requested){
  const seen=new Set(),candidates=[];
  for(const radius of SNAP_RADII){
    const count=radius===0?1:SNAP_DIRECTIONS;
    for(let index=0;index<count;index+=1){
      const angle=count===1?0:index*Math.PI*2/count;
      const raw={x:requested.x+Math.cos(angle)*radius,y:requested.y+Math.sin(angle)*radius};
      const point=feasible(raw,record.anchor,record.cluster,record.stage);
      if(!point)continue;
      const key=`${Math.round(point.x*4)}:${Math.round(point.y*4)}`;
      if(seen.has(key))continue;
      seen.add(key);candidates.push(point);
    }
  }
  candidates.sort((a,b)=>Math.hypot(a.x-requested.x,a.y-requested.y)-Math.hypot(b.x-requested.x,b.y-requested.y));
  return candidates.find(point=>!manualPlacementViolation(record,point))||null;
}
function restoreRecord(record){
  const cluster=liveCluster(record);
  if(!cluster)return false;
  record.cluster=cluster;
  cluster.style.left=`${record.left}px`;
  cluster.style.top=`${record.top}px`;
  cluster.dataset.ioDistance=String(Math.hypot(record.left-record.anchor.x,record.top-record.anchor.y));
  return true;
}
function reject(record,reason){
  restoreRecord(record);
  const cluster=liveCluster(record);
  if(cluster){cluster.dataset.manualIo="false";cluster.dataset.manualIoRejected=reason}
  markGesture(record,"rejected",reason);
  publicationGuard()?.schedule?.("manual-label-rejected");
}
async function persist(record){
  if(!record.dragged||!record.finalPoint)return;
  if(destroyed||!record.stage?.isConnected){markGesture(record,"disconnected","stage-disconnected");return}
  if(!refreshRecord(record)){markGesture(record,"disconnected","cluster-disconnected");publicationGuard()?.schedule?.("manual-label-disconnected");return}
  markGesture(record,"persisting");
  const requested=feasible(record.finalPoint,record.anchor,record.cluster,record.stage);
  if(!requested){reject(record,"outside-tether");return}
  const point=nearestCertifiablePoint(record,requested);
  if(!point){reject(record,manualPlacementViolation(record,requested)||"no-certifiable-position");return}
  delete record.cluster.dataset.manualIoRejected;
  record.cluster.dataset.manualIoAdjusted=String(Math.hypot(point.x-requested.x,point.y-requested.y)>0.5);
  const data=await diagramState();
  if(destroyed||!record.stage?.isConnected){markGesture(record,"disconnected","stage-disconnected-after-state");return}
  if(!refreshRecord(record)){markGesture(record,"disconnected","cluster-disconnected-after-state");publicationGuard()?.schedule?.("manual-label-disconnected");return}
  const refreshedRequested=feasible(record.finalPoint,record.anchor,record.cluster,record.stage);
  if(!refreshedRequested){reject(record,"outside-tether-after-refresh");return}
  const refreshedPoint=nearestCertifiablePoint(record,refreshedRequested);
  if(!refreshedPoint){reject(record,manualPlacementViolation(record,refreshedRequested)||"no-certifiable-position-after-refresh");return}
  const key=storageKey(data),saved=parseStored(key);
  saved[record.id]={x:refreshedPoint.x,y:refreshedPoint.y,dx:refreshedPoint.x-record.anchor.x,dy:refreshedPoint.y-record.anchor.y,anchorFraction:record.anchorFraction};
  if(!writeStored(key,saved)){reject(record,"persistence-unavailable");return}
  record.cluster.style.left=`${refreshedPoint.x}px`;
  record.cluster.style.top=`${refreshedPoint.y}px`;
  record.cluster.dataset.anchorFraction=String(record.anchorFraction);
  record.cluster.dataset.manualIo="true";
  record.cluster.dataset.ioDistance=String(Math.hypot(refreshedPoint.x-record.anchor.x,refreshedPoint.y-record.anchor.y));
  markGesture(record,"persisted");
  window.glyphTransitionLayoutTransaction?.schedule("manual-label-persisted",0);
}
async function resetCluster(cluster){const data=await diagramState(),key=storageKey(data),saved=parseStored(key),id=cluster.dataset.transitionId||"";if(id in saved){delete saved[id];writeStored(key,saved)}cluster.dataset.manualIo="false";delete cluster.dataset.manualIoRejected;delete cluster.dataset.manualIoAdjusted;cluster.dataset.manualIoGestureState="reset";window.glyphTransitionLayoutTransaction?.schedule("manual-label-reset",0)}
function finish(event){
  if(!active||active.pointerId!==event.pointerId)return;
  event.preventDefault();event.stopImmediatePropagation();
  const record=active;active=null;
  record.cluster.releasePointerCapture?.(event.pointerId);
  record.cluster.classList.remove("dragging-io");
  markGesture(record,"released");
  persist(record).catch(error=>{
    restoreRecord(record);
    markGesture(record,"failed",String(error?.message||error));
    publicationGuard()?.schedule?.("manual-label-persist-failed");
    report(error,"manual transition position persistence failed");
  });
}
function cancel(record,reason){
  restoreRecord(record);
  record.cluster?.classList.remove("dragging-io");
  markGesture(record,"cancelled",reason);
  if(record.publicationInvalidated)publicationGuard()?.schedule?.("manual-label-cancelled");
}
document.addEventListener("pointerdown",event=>{
  const cluster=event.target?.closest?.(".transition-io-cluster");if(!cluster||event.button!==0)return;
  const stage=cluster.closest(".graph-stage");if(!stage||stage.dataset.transitionLayoutState!=="ready")return;
  event.preventDefault();event.stopImmediatePropagation();
  select(cluster);cluster.classList.add("dragging-io");cluster.setPointerCapture?.(event.pointerId);
  active={cluster,stage,id:cluster.dataset.transitionId||"",gestureToken:++gestureSequence,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top),anchor:{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)},anchorFraction:clamp(num(cluster.dataset.anchorFraction)||.5,.18,.82),scale:scaleFor(stage),dragged:false,publicationInvalidated:false,finalPoint:null,finalOffset:null};
  markGesture(active,"pressed");
},true);
document.addEventListener("pointermove",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  event.preventDefault();event.stopImmediatePropagation();
  if(!active.dragged&&pointerDistance(active,event)<DRAG_THRESHOLD)return;
  const point=requestedPoint(active,event);if(!point)return;
  if(!active.dragged){active.publicationInvalidated=Boolean(publicationGuard()?.invalidate?.(active.stage,"manual-label-drag"))}
  active.dragged=true;active.finalPoint=point;active.finalOffset={x:point.x-active.anchor.x,y:point.y-active.anchor.y};
  active.cluster.style.left=`${point.x}px`;active.cluster.style.top=`${point.y}px`;active.cluster.dataset.ioDistance=String(Math.hypot(point.x-active.anchor.x,point.y-active.anchor.y));
  markGesture(active,"dragging");
},true);
document.addEventListener("pointerup",finish,true);
document.addEventListener("pointercancel",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  event.stopImmediatePropagation();
  const record=active;active=null;
  record.cluster.releasePointerCapture?.(event.pointerId);
  cancel(record,"pointer-cancelled");
},true);
document.addEventListener("lostpointercapture",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  const record=active;active=null;cancel(record,"pointer-capture-lost");
},true);
document.addEventListener("dblclick",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(cluster)resetCluster(cluster).catch(error=>report(error,"manual transition position reset failed"))},true);
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){selected=null;invalidateState()}});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;active=null;selected=null;invalidateState()},{once:true})}
window.glyphTransitionLayoutInteractionAdapter={marker:MARKER,version:4,validateManualPlacement:manualPlacementViolation,nearestCertifiablePoint};
})();
</script>
"""


def enhance_transition_layout_interaction_adapter_html(html: str) -> str:
    """Own label gestures and persist their arrow-relative final point."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
