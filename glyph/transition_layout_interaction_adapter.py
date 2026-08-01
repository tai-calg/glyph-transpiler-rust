from __future__ import annotations


_MARKER = "glyph-transition-layout-interaction-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-interaction-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-layout-interaction-adapter-v1",MAX_DISTANCE=96,DRAG_THRESHOLD=3;
const FOREIGN_ROUTE_CLEARANCE=1,NODE_CLEARANCE=2,LABEL_CLEARANCE=2;
const SNAP_RADII=[0,8,16,24,32,48,64,80,96],SNAP_DIRECTIONS=16;
let active=null,selected=null,stateCache=null,statePromise=null,stateAbort=null,stateVersion=0,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
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
function reject(record,reason){
  record.cluster.style.left=`${record.left}px`;
  record.cluster.style.top=`${record.top}px`;
  record.cluster.dataset.ioDistance=String(Math.hypot(record.left-record.anchor.x,record.top-record.anchor.y));
  record.cluster.dataset.manualIo="false";
  record.cluster.dataset.manualIoRejected=reason;
  window.glyphTransitionLayoutTransaction?.schedule("manual-label-rejected",0);
}
async function persist(record){
  if(!record.dragged)return;
  await new Promise(resolve=>setTimeout(resolve,0));
  if(destroyed||!record.cluster.isConnected||!record.stage.isConnected)return;
  const current={x:num(record.cluster.style.left),y:num(record.cluster.style.top)},visualDistance=Math.hypot(current.x-record.left,current.y-record.top);
  if(visualDistance<1)return;
  const requested=feasible(current,record.anchor,record.cluster,record.stage);
  if(!requested){reject(record,"outside-tether");return}
  const point=nearestCertifiablePoint(record,requested);
  if(!point){reject(record,manualPlacementViolation(record,requested)||"no-certifiable-position");return}
  delete record.cluster.dataset.manualIoRejected;
  record.cluster.dataset.manualIoAdjusted=String(Math.hypot(point.x-requested.x,point.y-requested.y)>0.5);
  const data=await diagramState(),key=storageKey(data),saved=parseStored(key);
  saved[record.id]={x:point.x,y:point.y,dx:point.x-record.anchor.x,dy:point.y-record.anchor.y,anchorFraction:record.anchorFraction};
  writeStored(key,saved);
  record.cluster.style.left=`${point.x}px`;
  record.cluster.style.top=`${point.y}px`;
  record.cluster.dataset.anchorFraction=String(record.anchorFraction);
  record.cluster.dataset.manualIo="true";
  record.cluster.dataset.ioDistance=String(Math.hypot(point.x-record.anchor.x,point.y-record.anchor.y));
  window.glyphTransitionLayoutTransaction?.schedule("manual-label-persisted",0);
}
async function resetCluster(cluster){const data=await diagramState(),key=storageKey(data),saved=parseStored(key),id=cluster.dataset.transitionId||"";if(id in saved){delete saved[id];writeStored(key,saved)}cluster.dataset.manualIo="false";delete cluster.dataset.manualIoRejected;delete cluster.dataset.manualIoAdjusted;window.glyphTransitionLayoutTransaction?.schedule("manual-label-reset",0)}
function finish(event){if(!active||active.pointerId!==event.pointerId)return;const record=active;active=null;record.cluster.classList.remove("dragging-io");persist(record).catch(error=>report(error,"manual transition position persistence failed"))}
document.addEventListener("pointerdown",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(!cluster||event.button!==0)return;const stage=cluster.closest(".graph-stage");if(!stage||stage.dataset.transitionLayoutState!=="ready")return;select(cluster);cluster.classList.add("dragging-io");active={cluster,stage,id:cluster.dataset.transitionId||"",pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top),anchor:{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)},anchorFraction:clamp(num(cluster.dataset.anchorFraction)||.5,.18,.82),scale:scaleFor(stage),dragged:false}},true);
document.addEventListener("pointermove",event=>{if(!active||active.pointerId!==event.pointerId)return;if(!active.dragged&&pointerDistance(active,event)<DRAG_THRESHOLD)return;active.dragged=true;const point=requestedPoint(active,event);if(!point)return;active.cluster.style.left=`${point.x}px`;active.cluster.style.top=`${point.y}px`;active.cluster.dataset.ioDistance=String(Math.hypot(point.x-active.anchor.x,point.y-active.anchor.y))},true);
document.addEventListener("pointerup",finish,true);
document.addEventListener("pointercancel",event=>{if(!active||active.pointerId!==event.pointerId)return;active.cluster.style.left=`${active.left}px`;active.cluster.style.top=`${active.top}px`;active.cluster.classList.remove("dragging-io");active=null},true);
document.addEventListener("dblclick",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(cluster)resetCluster(cluster).catch(error=>report(error,"manual transition position reset failed"))},true);
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){selected=null;invalidateState()}});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;active=null;selected=null;invalidateState()},{once:true})}
window.glyphTransitionLayoutInteractionAdapter={marker:MARKER,version:4,validateManualPlacement:manualPlacementViolation,nearestCertifiablePoint};
})();
</script>
"""


def enhance_transition_layout_interaction_adapter_html(html: str) -> str:
    """Own label drag and snap persisted placements to certified geometry."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
