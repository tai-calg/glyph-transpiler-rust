from __future__ import annotations


_MARKER = "glyph-transition-layout-interaction-adapter-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-interaction-adapter-v1-script">
(()=>{
const MARKER="glyph-transition-layout-interaction-adapter-v1",MAX_DISTANCE=96;
let active=null,stateCache=null;
const num=value=>Number.parseFloat(value||"0")||0;
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

async function diagramState(){
  if(stateCache)return stateCache;
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)throw Error("diagram state unavailable");
  return stateCache=await response.json();
}
function storageKey(data){
  const index=document.getElementById("machine-select")?.value||0;
  return`glyph.diagram.transition-io.v1:${data?.digest||"source"}:${index}`;
}
function project(point,anchor){
  const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);
  if(!distance||distance<=MAX_DISTANCE)return point;
  const ratio=MAX_DISTANCE/distance;
  return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio};
}
function constrain(point,cluster,stage){
  return{
    x:clamp(point.x,cluster.offsetWidth/2+8,stage.scrollWidth-cluster.offsetWidth/2-8),
    y:clamp(point.y,cluster.offsetHeight/2+8,stage.scrollHeight-cluster.offsetHeight/2-8),
  };
}
async function persist(record,event){
  await new Promise(resolve=>setTimeout(resolve,0));
  if(!record.cluster.isConnected||!record.stage.isConnected)return;
  const anchor={x:num(record.cluster.dataset.anchorX),y:num(record.cluster.dataset.anchorY)};
  const current={x:num(record.cluster.style.left),y:num(record.cluster.style.top)};
  const moved=Math.hypot(current.x-record.left,current.y-record.top)>1;
  const requested=moved?current:{
    x:record.left+(event.clientX-record.startX)/record.scale,
    y:record.top+(event.clientY-record.startY)/record.scale,
  };
  const point=constrain(project(requested,anchor),record.cluster,record.stage);
  const data=await diagramState(),key=storageKey(data);
  let saved={};
  try{saved=JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{}
  saved[record.id]={x:point.x,y:point.y,dx:point.x-anchor.x,dy:point.y-anchor.y};
  localStorage.setItem(key,JSON.stringify(saved));
  record.cluster.style.left=`${point.x}px`;
  record.cluster.style.top=`${point.y}px`;
  record.cluster.dataset.manualIo="true";
  record.cluster.dataset.ioDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y));
  window.glyphTransitionLayoutTransaction?.schedule("manual-label-persisted",0);
}

document.addEventListener("pointerdown",event=>{
  const cluster=event.target?.closest?.(".transition-io-cluster");
  if(!cluster||event.button!==0)return;
  const stage=cluster.closest(".graph-stage");
  active={
    cluster,
    stage,
    id:cluster.dataset.transitionId||"",
    pointerId:event.pointerId,
    startX:event.clientX,
    startY:event.clientY,
    left:num(cluster.style.left),
    top:num(cluster.style.top),
    scale:scaleFor(stage),
  };
},true);

document.addEventListener("pointerup",event=>{
  if(!active||active.pointerId!==event.pointerId)return;
  const record=active;active=null;
  persist(record,event).catch(error=>console.error("manual transition position persistence failed",error));
},true);

document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select")stateCache=null;
});
window.glyphTransitionLayoutInteractionAdapter={marker:MARKER};
})();
</script>
"""


def enhance_transition_layout_interaction_adapter_html(html: str) -> str:
    """Persist label drag intent before the deterministic layout transaction runs."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
