from __future__ import annotations


_MARKER = "glyph-diagram-label-editor-v1"

_STYLE = r"""
<style id="glyph-diagram-label-editor-v1-style">
.edge-label,.transition-label{cursor:grab;touch-action:none;user-select:none;z-index:9}
.edge-label:hover,.transition-label:hover{border-color:var(--blue);box-shadow:0 0 0 2px rgba(88,166,255,.16),0 5px 16px rgba(0,0,0,.28)}
.edge-label.dragging-label,.transition-label.dragging-label{cursor:grabbing;z-index:30;box-shadow:0 0 0 2px rgba(88,166,255,.28),0 10px 24px rgba(0,0,0,.36)}
.edge-label.selected-label,.transition-label.selected-label{outline:2px solid var(--blue);outline-offset:2px}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-label-editor-v1-script">
(()=>{
const LABEL_SELECTOR=".edge-label,.transition-label",NODE_SELECTOR=".state-node,.graph-node",GAP=8;
let drag=null,selected=null,timer=null,cache=null;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const intersects=(a,b,gap=GAP)=>!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y);
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function diagramKey(stage){const tab=document.querySelector(".tab.active")?.dataset.tab||"state";const index=tab==="state"?document.querySelector("#machine-select")?.value||0:document.querySelector("#system-select")?.value||0;return `glyph.diagram.label-positions.v1:${cache?.digest||"source"}:${tab}:${index}`}
function read(stage){try{return JSON.parse(localStorage.getItem(diagramKey(stage))||"{}")||{}}catch{return {}}}
function write(stage,value){localStorage.setItem(diagramKey(stage),JSON.stringify(value))}
function labelId(label,index){const existing=label.dataset.transitionId||label.dataset.glyphLabelId;if(existing)return existing;const line=label.dataset.line||0;const text=(label.dataset.fullLabel||label.textContent||"").trim();const id=`L${index+1}:${line}:${text}`;label.dataset.glyphLabelId=id;return id}
function centerRect(label,x,y){return{x:x-label.offsetWidth/2,y:y-label.offsetHeight/2,width:label.offsetWidth,height:label.offsetHeight}}
function nodeRects(stage){return[...stage.querySelectorAll(NODE_SELECTOR)].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function candidates(x,y){const points=[[0,0]];for(const radius of[24,44,68,96,132,172])points.push([0,-radius],[0,radius],[-radius,0],[radius,0],[-radius,-radius*.6],[radius,-radius*.6],[-radius,radius*.6],[radius,radius*.6]);return points.map(([dx,dy])=>({x:x+dx,y:y+dy}))}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function select(label){selected?.classList.remove("selected-label");selected=label;selected?.classList.add("selected-label")}
function arrange(stage){
  if(!stage?.isConnected)return;
  const labels=[...stage.querySelectorAll(LABEL_SELECTOR)];if(!labels.length)return;
  const saved=read(stage),occupied=nodeRects(stage),placed=[];
  labels.forEach((label,index)=>{
    const id=labelId(label,index),manual=saved[id];
    if(manual&&Number.isFinite(manual.x)&&Number.isFinite(manual.y)){
      const x=clamp(manual.x,label.offsetWidth/2+8,stage.scrollWidth-label.offsetWidth/2-8),y=clamp(manual.y,label.offsetHeight/2+8,stage.scrollHeight-label.offsetHeight/2-8);
      label.style.left=`${x}px`;label.style.top=`${y}px`;label.dataset.manualLabel="true";placed.push(centerRect(label,x,y));return;
    }
    label.dataset.manualLabel="false";
    const preferredX=num(label.style.left)||stage.clientWidth/2,preferredY=num(label.style.top)||stage.clientHeight/2;
    let chosen={x:preferredX,y:preferredY};
    for(const point of candidates(preferredX,preferredY)){
      const rect=centerRect(label,point.x,point.y);
      if(!inside(rect,stage))continue;
      if(occupied.some(item=>intersects(rect,item)))continue;
      if(placed.some(item=>intersects(rect,item)))continue;
      chosen=point;break;
    }
    label.style.left=`${chosen.x}px`;label.style.top=`${chosen.y}px`;label.dataset.autoLeft=String(chosen.x);label.dataset.autoTop=String(chosen.y);placed.push(centerRect(label,chosen.x,chosen.y));
  });
  stage.dataset.labelEditorReady="true";
}
function schedule(stage){clearTimeout(timer);timer=setTimeout(()=>{state().then(()=>arrange(stage||document.querySelector(".graph-stage"))).catch(()=>{})},24)}
function bind(label,stage,index){
  if(label.dataset.labelDragReady==="true")return;label.dataset.labelDragReady="true";const id=labelId(label,index);
  label.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();select(label);label.classList.add("dragging-label");label.setPointerCapture(event.pointerId);drag={label,stage,id,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:num(label.style.left),top:num(label.style.top),moved:false}});
  label.addEventListener("pointermove",event=>{if(!drag||drag.label!==label)return;event.preventDefault();const x=clamp(drag.left+event.clientX-drag.startX,label.offsetWidth/2+8,stage.scrollWidth-label.offsetWidth/2-8),y=clamp(drag.top+event.clientY-drag.startY,label.offsetHeight/2+8,stage.scrollHeight-label.offsetHeight/2-8);label.style.left=`${x}px`;label.style.top=`${y}px`;drag.moved=drag.moved||Math.abs(event.clientX-drag.startX)>3||Math.abs(event.clientY-drag.startY)>3});
  label.addEventListener("pointerup",event=>{if(!drag||drag.label!==label)return;event.preventDefault();event.stopPropagation();label.classList.remove("dragging-label");const saved=read(stage);saved[id]={x:num(label.style.left),y:num(label.style.top)};write(stage,saved);label.dataset.manualLabel="true";drag=null});
  label.addEventListener("click",event=>{if(label.dataset.manualLabel==="true")event.stopPropagation()});
  label.addEventListener("dblclick",event=>{event.preventDefault();event.stopPropagation();const saved=read(stage);delete saved[id];write(stage,saved);label.dataset.manualLabel="false";schedule(stage)});
}
function enhance(){const stage=document.querySelector(".graph-stage");if(!stage)return;[...stage.querySelectorAll(LABEL_SELECTOR)].forEach((label,index)=>bind(label,stage,index));schedule(stage)}
document.addEventListener("pointerup",event=>{const node=event.target?.closest?.(NODE_SELECTOR);if(node)setTimeout(()=>schedule(node.closest(".graph-stage")),0)},true);
document.addEventListener("click",event=>{if(!event.target?.closest?.(LABEL_SELECTOR))select(null)});
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select")){cache=null;setTimeout(enhance,0)}});
for(const name of["glyph-transition-layout-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-uml-transition-ready"])document.addEventListener(name,enhance);
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.addEventListener("resize",enhance);enhance();
})();
</script>
"""


def enhance_diagram_label_editor_html(html: str) -> str:
    """Avoid label collisions and let users drag labels independently of nodes."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
