from __future__ import annotations


_MARKER = "glyph-transition-label-drag-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-label-drag-guard-v1-script">
(()=>{
const MARKER="glyph-transition-label-drag-guard-v1",MAX_DISTANCE=96,MIN_VISIBLE_MOVE=12,GAP=4;
const RINGS=[12,24,36,48,60,72,84,96],ANGLES=72;
let active=null;
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const intersects=(left,right,gap=GAP)=>!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y);

function anchorOf(cluster){return{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)}}
function project(point,anchor){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(!distance||distance<=MAX_DISTANCE)return point;const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function constrain(point,cluster,stage){return{x:Math.max(cluster.offsetWidth/2+8,Math.min(stage.scrollWidth-cluster.offsetWidth/2-8,point.x)),y:Math.max(cluster.offsetHeight/2+8,Math.min(stage.scrollHeight-cluster.offsetHeight/2-8,point.y))}}
function rectAt(cluster,point){return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function nodeObstacles(stage){return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function labelObstacles(stage,current){return[...stage.querySelectorAll(".transition-io-cluster")].filter(cluster=>cluster!==current).map(cluster=>({x:cluster.offsetLeft-cluster.offsetWidth/2,y:cluster.offsetTop-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}))}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}

function candidates(anchor,requested){
  const result=[],seen=new Set(),add=point=>{const value=project(point,anchor),key=`${Math.round(value.x*10)}:${Math.round(value.y*10)}`;if(!seen.has(key)){seen.add(key);result.push(value)}};
  add(requested);
  for(const radius of RINGS){for(let index=0;index<ANGLES;index+=1){const angle=index*2*Math.PI/ANGLES;add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius})}}
  return result.sort((left,right)=>Math.hypot(left.x-requested.x,left.y-requested.y)-Math.hypot(right.x-requested.x,right.y-requested.y));
}

function choose(record){
  const nodes=nodeObstacles(record.stage),labels=labelObstacles(record.stage,record.cluster);
  let nodeSafe=null;
  for(const raw of candidates(record.anchor,record.requested)){
    const point=constrain(raw,record.cluster,record.stage),rect=rectAt(record.cluster,point);
    if(Math.hypot(point.x-record.original.x,point.y-record.original.y)<MIN_VISIBLE_MOVE)continue;
    if(!inside(rect,record.stage)||nodes.some(node=>intersects(rect,node)))continue;
    if(!nodeSafe)nodeSafe={point,rect};
    if(!labels.some(label=>intersects(rect,label)))return{point,rect,state:"accepted"};
  }
  return nodeSafe?{...nodeSafe,state:"reflow"}:null;
}

function storageKey(stage){
  let digest="source";
  try{if(typeof snapshot!=="undefined"&&snapshot?.digest)digest=snapshot.digest}catch{}
  const index=document.getElementById("machine-select")?.value||0;
  return`glyph.diagram.transition-io.v1:${digest}:${index}`;
}
function save(record,point){
  let value={};
  try{value=JSON.parse(localStorage.getItem(storageKey(record.stage))||"{}")||{}}catch{}
  value[record.id]={x:point.x,y:point.y,dx:point.x-record.anchor.x,dy:point.y-record.anchor.y};
  localStorage.setItem(storageKey(record.stage),JSON.stringify(value));
}

function applyFallback(record){
  if(!record.cluster.isConnected||!record.stage.isConnected)return;
  const current={x:num(record.cluster.style.left),y:num(record.cluster.style.top)};
  if(Math.hypot(current.x-record.original.x,current.y-record.original.y)>=MIN_VISIBLE_MOVE){
    record.cluster.dataset.manualIo="true";
    record.cluster.dataset.transitionDragConstraint="accepted";
    return;
  }
  const choice=choose(record);
  if(!choice){record.cluster.dataset.transitionDragConstraint="blocked";return}
  record.cluster.style.left=`${choice.point.x}px`;
  record.cluster.style.top=`${choice.point.y}px`;
  record.cluster.dataset.ioDistance=String(Math.hypot(choice.point.x-record.anchor.x,choice.point.y-record.anchor.y));
  record.cluster.dataset.manualIo="true";
  record.cluster.dataset.transitionDragConstraint=choice.state;
  save(record,choice.point);
  document.dispatchEvent(new CustomEvent("glyph-transition-label-manual-position",{detail:{marker:MARKER,id:record.id,state:choice.state}}));
  setTimeout(()=>window.glyphTransitionIoCollisionSolver?.run(),0);
}

document.addEventListener("pointerdown",event=>{
  const cluster=event.target?.closest?.(".transition-io-cluster");
  if(!cluster||event.button!==0)return;
  const stage=cluster.closest(".graph-stage"),anchor=anchorOf(cluster);
  active={cluster,stage,anchor,id:cluster.dataset.transitionId||"",pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,original:{x:num(cluster.style.left),y:num(cluster.style.top)},scale:scaleFor(stage)};
},true);

document.addEventListener("pointerup",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  const record={...active};active=null;
  record.requested=constrain(project({x:record.original.x+(event.clientX-record.startX)/record.scale,y:record.original.y+(event.clientY-record.startY)/record.scale},record.anchor),record.cluster,record.stage);
  queueMicrotask(()=>applyFallback(record));
});

window.glyphTransitionLabelDragGuard={marker:MARKER,minimumVisibleMove:MIN_VISIBLE_MOVE};
})();
</script>
"""


def enhance_transition_label_drag_guard_html(html: str) -> str:
    """Preserve visible manual label movement while respecting hard layout constraints."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
