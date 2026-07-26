from __future__ import annotations


_MARKER = "glyph-diagram-label-editor-v1"

_STYLE = r"""
<style id="glyph-diagram-label-editor-v1-style">
.edge-label,.transition-label{cursor:grab;touch-action:none;user-select:none;z-index:9}
.edge-label:hover,.transition-label:hover{border-color:var(--blue);box-shadow:0 0 0 2px rgba(88,166,255,.16),0 5px 16px rgba(0,0,0,.28)}
.edge-label.dragging-label,.transition-label.dragging-label{cursor:grabbing;z-index:30;box-shadow:0 0 0 2px rgba(88,166,255,.28),0 10px 24px rgba(0,0,0,.36)}
.edge-label.selected-label,.transition-label.selected-label{outline:2px solid var(--blue);outline-offset:2px}
.edge-label.layout-constrained,.transition-label.layout-constrained{border-color:rgba(231,191,98,.72)}
.edge-label.compact,.transition-label.compact{max-width:100px}
.edge-label.compact-tight,.transition-label.compact-tight{max-width:76px}
.edge-label.compact-micro,.transition-label.compact-micro{max-width:54px}
.edge-label.compact-nano,.transition-label.compact-nano{max-width:38px}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-label-editor-v1-script">
(()=>{
const LABEL_SELECTOR=".edge-label,.transition-label",NODE_SELECTOR=".state-node,.graph-node",GAP=8,PREFERRED_ANCHOR_RADIUS=96,MAX_ANCHOR_RADIUS=160;
let drag=null,selected=null,timer=null,cache=null;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const intersects=(a,b,gap=GAP)=>!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y);
const overlapArea=(a,b,gap=GAP)=>Math.max(0,Math.min(a.x+a.width+gap,b.x+b.width+gap)-Math.max(a.x-gap,b.x-gap))*Math.max(0,Math.min(a.y+a.height+gap,b.y+b.height+gap)-Math.max(a.y-gap,b.y-gap));
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function diagramKey(stage){const tab=document.querySelector(".tab.active")?.dataset.tab||"state";const index=tab==="state"?document.querySelector("#machine-select")?.value||0:document.querySelector("#system-select")?.value||0;return `glyph.diagram.label-positions.v1:${cache?.digest||"source"}:${tab}:${index}`}
function read(stage){try{return JSON.parse(localStorage.getItem(diagramKey(stage))||"{}")||{}}catch{return {}}}
function write(stage,value){localStorage.setItem(diagramKey(stage),JSON.stringify(value))}
function labelId(label,index){const existing=label.dataset.transitionId||label.dataset.glyphLabelId;if(existing)return existing;const line=label.dataset.line||0;const text=(label.dataset.fullLabel||label.textContent||"").trim();const id=`L${index+1}:${line}:${text}`;label.dataset.glyphLabelId=id;return id}
function centerRect(label,x,y){return{x:x-label.offsetWidth/2,y:y-label.offsetHeight/2,width:label.offsetWidth,height:label.offsetHeight}}
function nodeRects(stage){return[...stage.querySelectorAll(NODE_SELECTOR)].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function pathFor(label,stage,index){
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path")],id=label.dataset.transitionId;
  if(id){const match=paths.find(path=>path.dataset.transitionId===id);if(match)return match}
  return paths[index]||null;
}
function anchorFor(label,stage,index){
  const path=pathFor(label,stage,index),fallback={x:num(label.style.left)||stage.clientWidth/2,y:num(label.style.top)||stage.clientHeight/2,nx:0,ny:-1,tx:1,ty:0};
  if(!path||typeof path.getTotalLength!=="function")return fallback;
  try{
    const length=path.getTotalLength(),middle=length/2,point=path.getPointAtLength(middle),before=path.getPointAtLength(Math.max(0,middle-2)),after=path.getPointAtLength(Math.min(length,middle+2)),dx=after.x-before.x,dy=after.y-before.y,norm=Math.max(1,Math.hypot(dx,dy)),svg=path.ownerSVGElement;
    return{x:point.x+(svg?.offsetLeft||0),y:point.y+(svg?.offsetTop||0),tx:dx/norm,ty:dy/norm,nx:-dy/norm,ny:dx/norm};
  }catch{return fallback}
}
function candidates(anchor){
  const points=[],base=Math.atan2(anchor.ny,anchor.nx);
  for(const radius of[20,32,44,56,72,88,PREFERRED_ANCHOR_RADIUS,112,128,144,MAX_ANCHOR_RADIUS]){
    for(let step=0;step<24;step+=1){
      const angle=base+step*Math.PI/12;
      points.push({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius,radius});
    }
  }
  return points;
}
function inside(rect,width,height){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=width-8&&rect.y+rect.height<=height-8}
function select(label){selected?.classList.remove("selected-label");selected=label;selected?.classList.add("selected-label")}
function compact(label,className){
  if(label.classList.contains(className))return false;
  label.dataset.fullLabel=label.dataset.fullLabel||label.textContent||"";label.dataset.compact="true";label.dataset.anchorCompacted="true";label.classList.add(className);return true;
}
function choose(label,anchor,occupied,placed,width,height){
  const points=candidates(anchor),valid=[];
  for(const point of points){
    const rect=centerRect(label,point.x,point.y);if(!inside(rect,width,height))continue;
    const collisions=[...occupied,...placed].filter(item=>intersects(rect,item));
    if(!collisions.length)return{point,rect,constrained:false};
    valid.push({point,rect,score:collisions.reduce((sum,item)=>sum+overlapArea(rect,item),0)});
  }
  if(!valid.length)return null;
  valid.sort((a,b)=>a.score-b.score||a.point.radius-b.point.radius);
  return{point:valid[0].point,rect:valid[0].rect,constrained:true};
}
function arrange(stage){
  if(!stage?.isConnected)return;
  const labels=[...stage.querySelectorAll(LABEL_SELECTOR)];if(!labels.length)return;
  const saved=read(stage),occupied=nodeRects(stage),placed=[],width=stage.scrollWidth,height=stage.scrollHeight;
  labels.forEach((label,index)=>{
    const id=labelId(label,index),manual=saved[id];
    if(manual&&Number.isFinite(manual.x)&&Number.isFinite(manual.y)){
      const x=clamp(manual.x,label.offsetWidth/2+8,width-label.offsetWidth/2-8),y=clamp(manual.y,label.offsetHeight/2+8,height-label.offsetHeight/2-8);
      label.style.left=`${x}px`;label.style.top=`${y}px`;label.dataset.manualLabel="true";label.classList.remove("layout-constrained");placed.push(centerRect(label,x,y));return;
    }
    label.dataset.manualLabel="false";
    const anchor=anchorFor(label,stage,index);label.dataset.anchorX=String(anchor.x);label.dataset.anchorY=String(anchor.y);label.dataset.preferredAnchorRadius=String(PREFERRED_ANCHOR_RADIUS);label.dataset.maxAnchorRadius=String(MAX_ANCHOR_RADIUS);
    let chosen=choose(label,anchor,occupied,placed,width,height);
    if(chosen?.constrained){compact(label,"compact");chosen=choose(label,anchor,occupied,placed,width,height)}
    if(chosen?.constrained){compact(label,"compact-tight");chosen=choose(label,anchor,occupied,placed,width,height)}
    if(chosen?.constrained){compact(label,"compact-micro");chosen=choose(label,anchor,occupied,placed,width,height)}
    if(chosen?.constrained){compact(label,"compact-nano");chosen=choose(label,anchor,occupied,placed,width,height)}
    if(!chosen)return;
    label.style.left=`${chosen.point.x}px`;label.style.top=`${chosen.point.y}px`;label.dataset.autoLeft=String(chosen.point.x);label.dataset.autoTop=String(chosen.point.y);label.dataset.anchorRadius=String(chosen.point.radius);label.classList.toggle("layout-constrained",chosen.constrained);placed.push(chosen.rect);
  });
  stage.dataset.labelEditorReady="true";stage.dataset.preferredLabelAnchorRadius=String(PREFERRED_ANCHOR_RADIUS);stage.dataset.labelAnchorRadius=String(MAX_ANCHOR_RADIUS);
}
function schedule(stage,delay=0){clearTimeout(timer);timer=setTimeout(()=>{state().then(()=>arrange(stage||document.querySelector(".graph-stage"))).catch(()=>{})},delay)}
function bind(label,stage,index){
  if(label.dataset.labelDragReady==="true")return;label.dataset.labelDragReady="true";
  label.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();select(label);label.classList.add("dragging-label");label.setPointerCapture(event.pointerId);drag={label,stage,startX:event.clientX,startY:event.clientY,left:num(label.style.left),top:num(label.style.top)}});
  label.addEventListener("pointermove",event=>{if(!drag||drag.label!==label)return;event.preventDefault();const x=clamp(drag.left+event.clientX-drag.startX,label.offsetWidth/2+8,stage.scrollWidth-label.offsetWidth/2-8),y=clamp(drag.top+event.clientY-drag.startY,label.offsetHeight/2+8,stage.scrollHeight-label.offsetHeight/2-8);label.style.left=`${x}px`;label.style.top=`${y}px`});
  label.addEventListener("pointerup",event=>{if(!drag||drag.label!==label)return;event.preventDefault();event.stopPropagation();label.classList.remove("dragging-label");const id=labelId(label,index),saved=read(stage);saved[id]={x:num(label.style.left),y:num(label.style.top)};write(stage,saved);label.dataset.manualLabel="true";label.classList.remove("layout-constrained");drag=null});
  label.addEventListener("click",event=>{if(label.dataset.manualLabel==="true")event.stopPropagation()});
  label.addEventListener("dblclick",event=>{event.preventDefault();event.stopPropagation();const id=labelId(label,index),saved=read(stage);delete saved[id];write(stage,saved);label.dataset.manualLabel="false";schedule(stage)});
}
function enhance(){const stage=document.querySelector(".graph-stage");if(!stage)return;[...stage.querySelectorAll(LABEL_SELECTOR)].forEach((label,index)=>bind(label,stage,index));schedule(stage)}
document.addEventListener("pointerup",event=>{const node=event.target?.closest?.(NODE_SELECTOR);if(!node)return;const stage=node.closest(".graph-stage");for(const delay of[0,32,96])setTimeout(()=>schedule(stage),delay)},true);
document.addEventListener("click",event=>{if(!event.target?.closest?.(LABEL_SELECTOR))select(null)});
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select")){cache=null;setTimeout(enhance,0)}});
for(const name of["glyph-transition-layout-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-uml-transition-ready"])document.addEventListener(name,enhance);
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.addEventListener("resize",enhance);enhance();
})();
</script>
"""


def enhance_diagram_label_editor_html(html: str) -> str:
    """Place labels near edge midpoints, avoid collisions, and allow manual drag."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
