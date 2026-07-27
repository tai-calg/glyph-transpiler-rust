from __future__ import annotations


_MARKER = "glyph-transition-io-collision-solver-v1"

_STYLE = r"""
<style id="glyph-transition-io-collision-solver-v1-style">
.transition-io-cluster.nano-io{gap:1px}
.transition-io-cluster.nano-io .transition-io-main{gap:1px}
.transition-io-cluster.nano-io .transition-io-node{
  min-width:32px;
  max-width:46px;
  min-height:18px;
  padding:1px 2px;
  border-radius:4px;
}
.transition-io-cluster.nano-io .transition-io-node.guard{min-width:44px;max-width:82px}
.transition-io-cluster.nano-io .transition-io-role{display:none}
.transition-io-cluster.nano-io .transition-io-value{font-size:6px;line-height:1.05}
.transition-io-cluster.nano-io .transition-io-error{font-size:5px;line-height:1}
.transition-io-cluster.nano-io .transition-io-flow{font-size:7px}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-io-collision-solver-v1-script">
(()=>{
const MARKER="glyph-transition-io-collision-solver-v1",MAX_DISTANCE=96,GAP=4;
const RINGS=[0,12,24,36,48,60,72,84,96],ANGLES=48,OPTION_LIMIT=120;
let timer=null,running=false;
const num=value=>Number.parseFloat(value||"0")||0;
const intersects=(a,b,gap=GAP)=>!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y);
function setMode(cluster,mode){
  cluster.classList.toggle("stacked",mode.includes("stacked"));
  cluster.classList.toggle("compact-io",mode.includes("compact"));
  cluster.classList.toggle("micro-io",mode.includes("micro"));
  cluster.classList.toggle("nano-io",mode.includes("nano"));
}
function anchor(cluster){return{x:num(cluster.dataset.anchorX),y:num(cluster.dataset.anchorY)}}
function preferred(cluster,anchor){const x=num(cluster.style.left)||anchor.x,y=num(cluster.style.top)||anchor.y,dx=x-anchor.x,dy=y-anchor.y,distance=Math.hypot(dx,dy);if(!distance||distance<=MAX_DISTANCE)return{x,y};const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function rectAt(cluster,x,y){return{x:x-cluster.offsetWidth/2,y:y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function nodeObstacles(stage){return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function points(anchor,preferred){const result=[],seen=new Set(),add=(x,y)=>{const dx=x-anchor.x,dy=y-anchor.y,distance=Math.hypot(dx,dy),ratio=distance>MAX_DISTANCE?MAX_DISTANCE/distance:1,px=anchor.x+dx*ratio,py=anchor.y+dy*ratio,key=`${Math.round(px*10)}:${Math.round(py*10)}`;if(!seen.has(key)){seen.add(key);result.push({x:px,y:py})}};add(preferred.x,preferred.y);for(const radius of RINGS){for(let index=0;index<ANGLES;index+=1){const angle=index*2*Math.PI/ANGLES;add(anchor.x+Math.cos(angle)*radius,anchor.y+Math.sin(angle)*radius)}}return result}
function modes(dense){return dense?["stacked nano","horizontal nano","stacked micro","horizontal micro","stacked compact","horizontal compact","stacked","horizontal"]:["horizontal","stacked","horizontal compact","stacked compact","horizontal micro","stacked micro","horizontal nano","stacked nano"]}
function optionsFor(entry,stage,nodes,dense){const result=[],dedupe=new Set();for(const mode of modes(dense)){setMode(entry.cluster,mode);for(const point of points(entry.anchor,entry.preferred)){const rect=rectAt(entry.cluster,point.x,point.y);if(!inside(rect,stage)||nodes.some(node=>intersects(rect,node)))continue;const key=`${mode}:${Math.round(point.x)}:${Math.round(point.y)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;if(dedupe.has(key))continue;dedupe.add(key);const distance=Math.hypot(point.x-entry.preferred.x,point.y-entry.preferred.y),anchorDistance=Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y),modeCost=modes(dense).indexOf(mode)*40;result.push({mode,point,rect,score:distance+anchorDistance*.05+modeCost})}}result.sort((a,b)=>a.score-b.score);return result.slice(0,OPTION_LIMIT)}
function solve(entries,index,placed,assignment,deadline){if(index>=entries.length)return true;if(performance.now()>deadline)return false;const entry=entries[index];for(const option of entry.options){if(placed.some(rect=>intersects(option.rect,rect)))continue;assignment.set(entry.cluster,option);placed.push(option.rect);if(solve(entries,index+1,placed,assignment,deadline))return true;placed.pop();assignment.delete(entry.cluster)}return false}
function collisionCount(entries){let count=0;for(let index=0;index<entries.length;index+=1){const left=entries[index].cluster.getBoundingClientRect();for(let other=index+1;other<entries.length;other+=1){if(intersects(left,entries[other].cluster.getBoundingClientRect(),2))count+=1}}return count}
function apply(stage,entries,assignment){for(const entry of entries){const option=assignment.get(entry.cluster);if(!option)continue;setMode(entry.cluster,option.mode);entry.cluster.style.left=`${option.point.x}px`;entry.cluster.style.top=`${option.point.y}px`;entry.cluster.dataset.ioDistance=String(Math.hypot(option.point.x-entry.anchor.x,option.point.y-entry.anchor.y));entry.cluster.dataset.ioCollisionSolved="true";entry.cluster.classList.remove("layout-constrained")}stage.dataset.transitionIoCollisionSolved="true";stage.dataset.transitionIoCollisionCount="0";document.dispatchEvent(new CustomEvent("glyph-transition-io-collision-solved",{detail:{marker:MARKER,count:entries.length}}))}
function greedyFallback(stage,entries,nodes){const placed=[];for(const entry of entries){let selected=null;for(const option of entry.options){const collisions=placed.reduce((sum,item)=>sum+(intersects(option.rect,item)?1:0),0);const candidate={...option,collisions};if(!selected||candidate.collisions<selected.collisions||candidate.collisions===selected.collisions&&candidate.score<selected.score)selected=candidate;if(!collisions)break}if(!selected)continue;setMode(entry.cluster,selected.mode);entry.cluster.style.left=`${selected.point.x}px`;entry.cluster.style.top=`${selected.point.y}px`;entry.cluster.dataset.ioDistance=String(Math.hypot(selected.point.x-entry.anchor.x,selected.point.y-entry.anchor.y));entry.cluster.classList.toggle("layout-constrained",selected.collisions>0);placed.push(selected.rect)}stage.dataset.transitionIoCollisionSolved="fallback";stage.dataset.transitionIoCollisionCount=String(collisionCount(entries))}
function run(stage=document.querySelector(".state-node")?.closest(".graph-stage")){if(running||!stage||stage.dataset.transitionIoClustersReady!=="true")return;running=true;try{const clusters=[...stage.querySelectorAll(".transition-io-cluster")];if(!clusters.length)return;const nodes=nodeObstacles(stage),dense=clusters.length>=7,entries=clusters.map((cluster,index)=>{const value=anchor(cluster);return{cluster,index,anchor:value,preferred:preferred(cluster,value),options:[]}});for(const entry of entries)entry.options=optionsFor(entry,stage,nodes,dense);entries.sort((a,b)=>a.options.length-b.options.length||b.cluster.offsetWidth*b.cluster.offsetHeight-a.cluster.offsetWidth*a.cluster.offsetHeight||a.index-b.index);const assignment=new Map(),deadline=performance.now()+220,solved=entries.every(entry=>entry.options.length)&&solve(entries,0,[],assignment,deadline);if(solved)apply(stage,entries,assignment);else greedyFallback(stage,entries,nodes)}finally{running=false}}
function schedule(stage=null,delay=0){clearTimeout(timer);timer=setTimeout(()=>run(stage||document.querySelector(".state-node")?.closest(".graph-stage")),delay)}
document.addEventListener("glyph-transition-io-clusters-ready",event=>schedule(event.target?.closest?.(".graph-stage")||null,0));document.addEventListener("pointerup",event=>{if(event.target?.closest?.(".transition-io-cluster,.state-node"))schedule(null,60)},true);document.addEventListener("glyph-diagram-viewport-change",()=>schedule(null,0));window.addEventListener("resize",()=>schedule(null,30));window.glyphTransitionIoCollisionSolver={run:()=>schedule(null,0),maxDistance:MAX_DISTANCE};schedule(null,0);
})();
</script>
"""


def enhance_transition_io_collision_solver_html(html: str) -> str:
    """Find a global collision-free placement for arrow-tethered transition I/O."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
