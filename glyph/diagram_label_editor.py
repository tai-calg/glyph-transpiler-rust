from __future__ import annotations


_MARKER = "glyph-diagram-label-editor-v2"

_STYLE = r"""
<style id="glyph-diagram-label-editor-v2-style">
.edge-label,.transition-label{cursor:grab;touch-action:none;user-select:none;z-index:9}
.edge-label:hover,.transition-label:hover{border-color:var(--blue);box-shadow:0 0 0 2px rgba(88,166,255,.16),0 5px 16px rgba(0,0,0,.28)}
.edge-label.dragging-label,.transition-label.dragging-label{cursor:grabbing;z-index:30;box-shadow:0 0 0 2px rgba(88,166,255,.28),0 10px 24px rgba(0,0,0,.36)}
.edge-label.selected-label,.transition-label.selected-label{outline:2px solid var(--blue);outline-offset:2px}
.edge-label.layout-constrained,.transition-label.layout-constrained{border-style:dotted;box-shadow:0 0 0 2px rgba(231,191,98,.18),0 5px 16px rgba(0,0,0,.24)}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-label-editor-v2-script">
(()=>{
const LABEL_SELECTOR=".edge-label,.transition-label",NODE_SELECTOR=".state-node,.graph-node",GAP=8,MAX_DISTANCE=96;
const RINGS=[0,24,48,72,96],ANGLE_COUNT=24;
let drag=null,selected=null,timer=null,cache=null;
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const intersects=(a,b,gap=GAP)=>!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y);
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function keyParts(){const tab=document.querySelector(".tab.active")?.dataset.tab||"state";const index=tab==="state"?document.querySelector("#machine-select")?.value||0:document.querySelector("#system-select")?.value||0;return{digest:cache?.digest||"source",tab,index}}
function diagramKey(stage){const{digest,tab,index}=keyParts();return `glyph.diagram.label-positions.v2:${digest}:${tab}:${index}`}
function legacyKey(stage){const{digest,tab,index}=keyParts();return `glyph.diagram.label-positions.v1:${digest}:${tab}:${index}`}
function parse(value){try{return JSON.parse(value||"{}")||{}}catch{return {}}}
function read(stage){const current=parse(localStorage.getItem(diagramKey(stage)));if(Object.keys(current).length)return current;return parse(localStorage.getItem(legacyKey(stage)))}
function write(stage,value){const serialized=JSON.stringify(value);localStorage.setItem(diagramKey(stage),serialized);localStorage.setItem(legacyKey(stage),serialized)}
function labelId(label,index){const existing=label.dataset.transitionId||label.dataset.glyphLabelId;if(existing)return existing;const line=label.dataset.line||0;const text=(label.dataset.fullLabel||label.dataset.inputActionLabel||label.textContent||"").trim();const id=`L${index+1}:${line}:${text}`;label.dataset.glyphLabelId=id;return id}
function labelIds(label,index){return[...new Set([label.dataset.transitionId,label.dataset.glyphLabelId,labelId(label,index)].filter(Boolean))]}
function centerRect(label,x,y){return{x:x-label.offsetWidth/2,y:y-label.offsetHeight/2,width:label.offsetWidth,height:label.offsetHeight}}
function nodeRects(stage){return[...stage.querySelectorAll(NODE_SELECTOR)].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function pathFor(label,index,stage){const id=label.dataset.transitionId;if(id){const escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&");const found=stage.querySelector(`path[data-transition-id="${escaped}"]`);if(found)return found}const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path,:scope > svg.edge-svg > path")].filter((item,pos,array)=>array.indexOf(item)===pos);return paths[index]||null}
function anchorFor(label,index,stage){const path=pathFor(label,index,stage);if(path&&typeof path.getTotalLength==="function"){try{const length=path.getTotalLength(),point=path.getPointAtLength(length/2);return{x:point.x,y:point.y,path}}catch{}}return{x:num(label.style.left)||stage.clientWidth/2,y:num(label.style.top)||stage.clientHeight/2,path:null}}
function project(point,anchor,radius=MAX_DISTANCE){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(distance<=radius||distance===0)return point;const scale=radius/distance;return{x:anchor.x+dx*scale,y:anchor.y+dy*scale}}
function constrain(point,label,stage){return{x:clamp(point.x,label.offsetWidth/2+8,stage.scrollWidth-label.offsetWidth/2-8),y:clamp(point.y,label.offsetHeight/2+8,stage.scrollHeight-label.offsetHeight/2-8)}}
function restoredPoint(manual,anchor){if(finite(manual?.dx)&&finite(manual?.dy))return{x:anchor.x+manual.dx,y:anchor.y+manual.dy};if(finite(manual?.x)&&finite(manual?.y))return{x:manual.x,y:manual.y};return null}
function storedPoint(point,anchor){return{x:point.x,y:point.y,dx:point.x-anchor.x,dy:point.y-anchor.y}}
function candidates(anchor,preferred=anchor){const values=[],seen=new Set();const add=point=>{const projected=project(point,anchor);const key=`${Math.round(projected.x*10)},${Math.round(projected.y*10)}`;if(!seen.has(key)){seen.add(key);values.push(projected)}};add(preferred);for(const radius of RINGS){for(let index=0;index<ANGLE_COUNT;index+=1){const angle=2*Math.PI*index/ANGLE_COUNT;add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius})}}return values.sort((a,b)=>Math.hypot(a.x-preferred.x,a.y-preferred.y)-Math.hypot(b.x-preferred.x,b.y-preferred.y))}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function collisionCount(rect,obstacles,placed){return obstacles.reduce((count,item)=>count+(intersects(rect,item)?1:0),0)+placed.reduce((count,item)=>count+(intersects(rect,item)?1:0),0)}
function select(label){selected?.classList.remove("selected-label");selected=label;selected?.classList.add("selected-label")}
function compact(label,id){if(label.classList.contains("compact"))return;label.dataset.fullLabel=label.dataset.fullLabel||label.dataset.inputActionLabel||label.textContent||"";label.classList.add("compact");label.dataset.compact="true";label.textContent=id}
function choose(label,anchor,preferred,stage,obstacles,placed){let fallback=null;for(const point of candidates(anchor,preferred)){const rect=centerRect(label,point.x,point.y);if(!inside(rect,stage))continue;const collisions=collisionCount(rect,obstacles,placed);const score=collisions*100000+Math.hypot(point.x-preferred.x,point.y-preferred.y);if(!fallback||score<fallback.score)fallback={point,rect,score,collisions};if(collisions===0)return{point,rect,collisions:0}}return fallback}
function place(label,point,anchor,manual,obstacles,placed){const rect=centerRect(label,point.x,point.y),collisions=collisionCount(rect,obstacles,placed);label.style.left=`${point.x}px`;label.style.top=`${point.y}px`;label.dataset.manualLabel=manual?"true":"false";label.dataset.labelDistance=String(Math.hypot(point.x-anchor.x,point.y-anchor.y));label.classList.toggle("layout-constrained",collisions>0);placed.push(rect)}
function arrange(stage){
 if(!stage?.isConnected)return;
 const labels=[...stage.querySelectorAll(LABEL_SELECTOR)];if(!labels.length)return;
 const saved=read(stage),obstacles=nodeRects(stage),placed=[];
 labels.forEach((label,index)=>{
   const ids=labelIds(label,index),id=ids[0],anchor=anchorFor(label,index,stage),manual=ids.map(value=>saved[value]).find(Boolean),restored=restoredPoint(manual,anchor);
   label.dataset.anchorX=String(anchor.x);label.dataset.anchorY=String(anchor.y);label.dataset.maxLabelDistance=String(MAX_DISTANCE);label.classList.remove("layout-constrained");
   if(restored){const point=constrain(project(restored,anchor),label,stage);place(label,point,anchor,true,obstacles,placed);return}
   let selectedPosition=choose(label,anchor,anchor,stage,obstacles,placed);
   if((!selectedPosition||selectedPosition.collisions>0)&&!label.classList.contains("compact")){compact(label,id);selectedPosition=choose(label,anchor,anchor,stage,obstacles,placed)}
   if(!selectedPosition)return;
   place(label,selectedPosition.point,anchor,false,obstacles,placed);
 });
 stage.dataset.labelEditorReady="true";stage.dataset.labelMaxDistance=String(MAX_DISTANCE);
}
function schedule(stage,delay=80){clearTimeout(timer);timer=setTimeout(()=>{state().then(()=>arrange(stage||document.querySelector(".graph-stage"))).catch(()=>{})},delay)}
function bind(label,stage,index){
 if(label.dataset.labelDragReady==="true")return;label.dataset.labelDragReady="true";
 label.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();select(label);label.classList.add("dragging-label");label.setPointerCapture(event.pointerId);const anchor=anchorFor(label,index,stage);drag={label,stage,ids:labelIds(label,index),index,anchor,startX:event.clientX,startY:event.clientY,left:num(label.style.left),top:num(label.style.top)}});
 label.addEventListener("pointermove",event=>{if(!drag||drag.label!==label)return;event.preventDefault();const desired={x:drag.left+event.clientX-drag.startX,y:drag.top+event.clientY-drag.startY},point=constrain(project(desired,drag.anchor),label,stage);label.style.left=`${point.x}px`;label.style.top=`${point.y}px`});
 label.addEventListener("pointerup",event=>{if(!drag||drag.label!==label)return;event.preventDefault();event.stopPropagation();label.classList.remove("dragging-label");const saved=read(stage),anchor=anchorFor(label,index,stage),point=constrain(project({x:num(label.style.left),y:num(label.style.top)},anchor),label,stage),stored=storedPoint(point,anchor);for(const id of new Set([...drag.ids,...labelIds(label,index)]))saved[id]=stored;write(stage,saved);label.dataset.manualLabel="true";drag=null;schedule(stage)});
 label.addEventListener("click",event=>{if(label.dataset.manualLabel==="true")event.stopPropagation()});
 label.addEventListener("dblclick",event=>{event.preventDefault();event.stopPropagation();const saved=read(stage);for(const id of labelIds(label,index))delete saved[id];write(stage,saved);label.dataset.manualLabel="false";schedule(stage,0)});
}
function enhance(){const stage=document.querySelector(".graph-stage");if(!stage)return;[...stage.querySelectorAll(LABEL_SELECTOR)].forEach((label,index)=>bind(label,stage,index));schedule(stage)}
document.addEventListener("pointerup",event=>{const node=event.target?.closest?.(NODE_SELECTOR);if(node){const stage=node.closest(".graph-stage");schedule(stage,80);setTimeout(()=>schedule(stage,0),180)}},true);
document.addEventListener("click",event=>{if(!event.target?.closest?.(LABEL_SELECTOR))select(null)});
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select")){cache=null;setTimeout(enhance,0)}});
for(const name of["glyph-transition-layout-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-state-transition-ir-v3-labels-ready","glyph-uml-transition-ready"])document.addEventListener(name,enhance);
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.addEventListener("resize",enhance);enhance();
})();
</script>
"""


def enhance_diagram_label_editor_html(html: str) -> str:
    """Keep labels close to their arrows, avoid collisions and persist manual edits."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
