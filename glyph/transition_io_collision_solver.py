from __future__ import annotations


_MARKER = "glyph-transition-io-collision-solver-v1"

_STYLE = r"""
<style id="glyph-transition-io-collision-solver-v1-style">
.transition-io-cluster.nano-io .transition-io-node.io{
  min-width:34px;
  max-width:72px;
  min-height:16px;
  padding:1px 2px;
  border-radius:4px;
}
.transition-io-cluster.nano-io .transition-io-value{font-size:6px;line-height:1.05}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-io-collision-solver-v1-script">
(()=>{
const MARKER="glyph-transition-io-collision-solver-v1",MAX_DISTANCE=96,GAP=4;
const RINGS=[0,12,24,36,48,60,72,84,96],ANGLES=72,PER_MODE_LIMIT=72,SEARCH_MS=1600;
let timer=null,running=false,manualPointer=null;
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const intersects=(a,b,gap=GAP)=>!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y);
function setMode(cluster,mode){cluster.classList.toggle("stacked",mode.includes("stacked"));cluster.classList.toggle("compact-io",mode.includes("compact"));cluster.classList.toggle("micro-io",mode.includes("micro"));cluster.classList.toggle("nano-io",mode.includes("nano"))}
function currentMode(cluster){if(cluster.classList.contains("nano-io"))return"nano";if(cluster.classList.contains("micro-io"))return"micro";if(cluster.classList.contains("compact-io"))return"compact";return"normal"}
function anchor(cluster){return{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)}}
function project(point,anchor){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(!distance||distance<=MAX_DISTANCE)return point;const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function storageRecord(cluster,anchor){try{const digest=snapshot?.digest||"source",index=document.getElementById("machine-select")?.value||0,key=`glyph.diagram.transition-io.v1:${digest}:${index}`,saved=JSON.parse(localStorage.getItem(key)||"{}"),value=saved[cluster.dataset.transitionId];if(finite(value?.dx)&&finite(value?.dy))return project({x:anchor.x+value.dx,y:anchor.y+value.dy},anchor);if(finite(value?.x)&&finite(value?.y))return project({x:value.x,y:value.y},anchor)}catch{}return null}
function preferred(cluster,anchor){const saved=cluster.dataset.manualIo==="true"?storageRecord(cluster,anchor):null;if(saved)return saved;return project({x:num(cluster.style.left)||anchor.x,y:num(cluster.style.top)||anchor.y},anchor)}
function rectAt(cluster,x,y){return{x:x-cluster.offsetWidth/2,y:y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function constrain(point,cluster,stage){return{x:Math.max(cluster.offsetWidth/2+8,Math.min(stage.scrollWidth-cluster.offsetWidth/2-8,point.x)),y:Math.max(cluster.offsetHeight/2+8,Math.min(stage.scrollHeight-cluster.offsetHeight/2-8,point.y))}}
function nodeObstacles(stage){return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function points(anchor,preferred){const result=[],seen=new Set(),add=(x,y)=>{const value=project({x,y},anchor),key=`${Math.round(value.x*10)}:${Math.round(value.y*10)}`;if(!seen.has(key)){seen.add(key);result.push(value)}};add(preferred.x,preferred.y);for(const radius of RINGS){for(let index=0;index<ANGLES;index+=1){const angle=index*2*Math.PI/ANGLES;add(anchor.x+Math.cos(angle)*radius,anchor.y+Math.sin(angle)*radius)}}return result}
function modes(dense){return dense?["nano","micro","compact","normal"]:["normal","compact","micro","nano"]}
function optionsFor(entry,stage,nodes,dense){const result=[],dedupe=new Set(),ordered=modes(dense);for(const mode of ordered){setMode(entry.cluster,mode);const modeOptions=[];for(const point of points(entry.anchor,entry.preferred)){const bounded=constrain(point,entry.cluster,stage),rect=rectAt(entry.cluster,bounded.x,bounded.y);if(!inside(rect,stage)||nodes.some(node=>intersects(rect,node)))continue;const key=`${mode}:${Math.round(bounded.x)}:${Math.round(bounded.y)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;if(dedupe.has(key))continue;dedupe.add(key);const distance=Math.hypot(bounded.x-entry.preferred.x,bounded.y-entry.preferred.y),anchorDistance=Math.hypot(bounded.x-entry.anchor.x,bounded.y-entry.anchor.y),modeCost=ordered.indexOf(mode)*35;modeOptions.push({mode,point:bounded,rect,score:distance+anchorDistance*.05+modeCost})}modeOptions.sort((a,b)=>a.score-b.score);result.push(...modeOptions.slice(0,PER_MODE_LIMIT))}result.sort((a,b)=>a.score-b.score);return result}
function solve(entries,index,placed,assignment,deadline){if(index>=entries.length)return true;if(performance.now()>deadline)return false;const entry=entries[index];for(const option of entry.options){if(placed.some(rect=>intersects(option.rect,rect)))continue;assignment.set(entry.cluster,option);placed.push(option.rect);if(solve(entries,index+1,placed,assignment,deadline))return true;placed.pop();assignment.delete(entry.cluster)}return false}
function collisionCount(entries){let count=0;for(let index=0;index<entries.length;index+=1){const left=entries[index].cluster.getBoundingClientRect();for(let other=index+1;other<entries.length;other+=1){if(intersects(left,entries[other].cluster.getBoundingClientRect(),2))count+=1}}return count}
function apply(stage,entries,assignment,state="true"){for(const entry of entries){const option=assignment.get(entry.cluster);if(!option)continue;setMode(entry.cluster,option.mode);entry.cluster.style.left=`${option.point.x}px`;entry.cluster.style.top=`${option.point.y}px`;entry.cluster.dataset.ioDistance=String(Math.hypot(option.point.x-entry.anchor.x,option.point.y-entry.anchor.y));entry.cluster.dataset.ioCollisionSolved="true";entry.cluster.classList.remove("layout-constrained")}stage.dataset.transitionIoCollisionSolved=state;stage.dataset.transitionIoCollisionCount=String(collisionCount(entries));document.dispatchEvent(new CustomEvent("glyph-transition-io-collision-solved",{detail:{marker:MARKER,count:entries.length,state}}))}
function greedy(entries,fixedRects=[]){const assignment=new Map(),placed=[...fixedRects],ordered=[...entries].sort((a,b)=>a.options.length-b.options.length||b.cluster.offsetWidth*b.cluster.offsetHeight-a.cluster.offsetWidth*a.cluster.offsetHeight||a.index-b.index);for(const entry of ordered){const option=entry.options.find(candidate=>!placed.some(rect=>intersects(candidate.rect,rect)));if(!option)return null;assignment.set(entry.cluster,option);placed.push(option.rect)}return assignment}
function run(stage=document.querySelector(".state-node")?.closest(".graph-stage")){if(running||!stage||stage.dataset.transitionIoClustersReady!=="true")return;running=true;try{const clusters=[...stage.querySelectorAll(".transition-io-cluster")];if(!clusters.length)return;const nodes=nodeObstacles(stage),dense=clusters.length>=7,entries=clusters.map((cluster,index)=>{const value=anchor(cluster);return{cluster,index,anchor:value,preferred:preferred(cluster,value),manual:cluster.dataset.manualIo==="true",options:[]}}),assignment=new Map(),fixedRects=[],movable=[];for(const entry of entries){if(entry.manual){const mode=currentMode(entry.cluster);setMode(entry.cluster,mode);const point=constrain(entry.preferred,entry.cluster,stage),rect=rectAt(entry.cluster,point.x,point.y);if(inside(rect,stage)&&!nodes.some(node=>intersects(rect,node))&&!fixedRects.some(other=>intersects(rect,other))){assignment.set(entry.cluster,{mode,point,rect,score:0});fixedRects.push(rect);continue}}entry.options=optionsFor(entry,stage,nodes,dense);movable.push(entry)}movable.sort((a,b)=>a.options.length-b.options.length||b.cluster.offsetWidth*b.cluster.offsetHeight-a.cluster.offsetWidth*a.cluster.offsetHeight||a.index-b.index);const deadline=performance.now()+SEARCH_MS,solved=movable.every(entry=>entry.options.length)&&solve(movable,0,[...fixedRects],assignment,deadline);if(solved){apply(stage,entries,assignment,"true");return}const fallback=greedy(movable,fixedRects);if(fallback){for(const [cluster,option] of fallback)assignment.set(cluster,option);apply(stage,entries,assignment,"fallback");return}stage.dataset.transitionIoCollisionSolved="failed";stage.dataset.transitionIoCollisionCount=String(collisionCount(entries));document.dispatchEvent(new CustomEvent("glyph-transition-io-collision-solved",{detail:{marker:MARKER,count:entries.length,state:"failed"}}))}finally{running=false}}
function schedule(stage=null,delay=0){const target=stage||document.querySelector(".state-node")?.closest(".graph-stage");if(target)target.dataset.transitionIoCollisionSolved="pending";clearTimeout(timer);timer=setTimeout(()=>run(target||document.querySelector(".state-node")?.closest(".graph-stage")),delay)}
document.addEventListener("pointerdown",event=>{const cluster=event.target?.closest?.(".transition-io-cluster");if(!cluster||event.button!==0)return;const stage=cluster.closest(".graph-stage"),value=anchor(cluster);manualPointer={cluster,stage,anchor:value,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top),scale:window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1}},true);
document.addEventListener("pointerup",event=>{if(!manualPointer)return;const value=manualPointer;manualPointer=null;const point=constrain(project({x:value.left+(event.clientX-value.startX)/value.scale,y:value.top+(event.clientY-value.startY)/value.scale},value.anchor),value.cluster,value.stage);queueMicrotask(()=>{if(!value.cluster.isConnected)return;value.cluster.style.left=`${point.x}px`;value.cluster.style.top=`${point.y}px`;value.cluster.dataset.manualIo="true";value.cluster.dataset.ioDistance=String(Math.hypot(point.x-value.anchor.x,point.y-value.anchor.y))});schedule(value.stage,0)},true);
document.addEventListener("glyph-transition-io-clusters-ready",()=>schedule(null,0));document.addEventListener("pointerup",event=>{if(event.target?.closest?.(".state-node")){schedule(null,0);setTimeout(()=>schedule(null,0),140)}},true);document.addEventListener("glyph-diagram-viewport-change",()=>schedule(null,0));window.addEventListener("resize",()=>schedule(null,30));window.glyphTransitionIoCollisionSolver={run:()=>schedule(null,0),maxDistance:MAX_DISTANCE};schedule(null,0);
})();
</script>
"""


def enhance_transition_io_collision_solver_html(html: str) -> str:
    """Find a collision-free placement inside each arrow's 96px tether."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
