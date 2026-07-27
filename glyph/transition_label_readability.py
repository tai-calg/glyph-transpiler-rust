from __future__ import annotations


_MARKER = "glyph-transition-label-readability-v1"

_STYLE = r"""
<style id="glyph-transition-label-readability-v1-style">
.transition-io-cluster{
  max-width:240px!important;
}
.transition-io-node.io{
  min-width:88px!important;
  max-width:176px!important;
  min-height:28px!important;
  padding:4px 7px!important;
  overflow:visible!important;
}
.transition-io-value{
  display:block!important;
  max-width:100%!important;
  min-width:0!important;
  font-size:9px!important;
  line-height:1.3!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  word-break:break-word!important;
  text-align:center!important;
}
.transition-io-cluster.compact-io .transition-io-node.io{
  min-width:76px!important;
  max-width:132px!important;
  min-height:26px!important;
  padding:3px 6px!important;
}
.transition-io-cluster.micro-io .transition-io-node.io{
  min-width:64px!important;
  max-width:96px!important;
  min-height:24px!important;
  padding:3px 5px!important;
  border-radius:6px!important;
}
.transition-io-cluster.nano-io .transition-io-node.io{
  min-width:56px!important;
  max-width:72px!important;
  min-height:24px!important;
  padding:3px 4px!important;
  border-radius:5px!important;
}
.transition-io-cluster.compact-io .transition-io-value,
.transition-io-cluster.micro-io .transition-io-value,
.transition-io-cluster.nano-io .transition-io-value{
  font-size:9px!important;
  line-height:1.25!important;
}
.transition-io-cluster.readability-violation{
  outline:3px solid var(--red)!important;
  outline-offset:4px!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-label-readability-v1-script">
(()=>{
const MARKER="glyph-transition-label-readability-v1",MIN_FONT_SIZE=9,TOLERANCE=1.5,MAX_DISTANCE=96,GAP=4;
const RINGS=[0,12,24,36,48,60,72,84,96],ANGLES=48,OPTIONS_PER_MODE=64;
let timer=null,repairing=false;
const esc=value=>String(value??"").replace(/[&<>\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[ch]));
const text=value=>String(value??"").trim();
const rectContains=(outer,inner,tolerance=TOLERANCE)=>inner.left>=outer.left-tolerance&&inner.top>=outer.top-tolerance&&inner.right<=outer.right+tolerance&&inner.bottom<=outer.bottom+tolerance;

function inspect(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage)return{ok:false,violations:[{reason:"missing-stage"}]};
  const violations=[];
  const values=[...stage.querySelectorAll(".transition-io-cluster .transition-io-value")];
  for(const value of values){
    const cluster=value.closest(".transition-io-cluster"),node=value.closest(".transition-io-node.io"),style=getComputedStyle(value);
    const expected=text(cluster?.dataset.ioValue||node?.getAttribute("title"));
    const actual=text(value.textContent);
    const fontSize=Number.parseFloat(style.fontSize||"0")||0;
    const valueRect=value.getBoundingClientRect(),nodeRect=node?.getBoundingClientRect();
    const reasons=[];
    if(!actual||actual!==expected)reasons.push("text-mismatch");
    if(fontSize+0.01<MIN_FONT_SIZE)reasons.push("font-too-small");
    if(style.whiteSpace==="nowrap")reasons.push("nowrap");
    if(style.textOverflow==="ellipsis")reasons.push("ellipsis");
    if(value.scrollWidth>value.clientWidth+TOLERANCE)reasons.push("horizontal-clipping");
    if(value.scrollHeight>value.clientHeight+TOLERANCE)reasons.push("vertical-clipping");
    if(nodeRect&&!rectContains(nodeRect,valueRect))reasons.push("outside-label-box");
    cluster?.classList.toggle("readability-violation",reasons.length>0);
    cluster?.setAttribute("data-transition-readability",reasons.length?"failed":"true");
    if(reasons.length)violations.push({id:cluster?.dataset.transitionId||"",label:expected,reasons});
  }
  const ok=values.length>0&&violations.length===0;
  stage.dataset.transitionIoReadability=ok?"true":"failed";
  stage.dataset.transitionIoReadabilityViolations=String(violations.length);
  document.dispatchEvent(new CustomEvent("glyph-transition-label-readability-audited",{detail:{marker:MARKER,ok,count:values.length,violations}}));
  return{ok,count:values.length,violations};
}

function numberValue(value){return Number.parseFloat(value||"0")||0}
function intersects(left,right,gap=GAP){return!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y)}
function overlapArea(left,right){const width=Math.max(0,Math.min(left.x+left.width,right.x+right.width)-Math.max(left.x,right.x)),height=Math.max(0,Math.min(left.y+left.height,right.y+right.height)-Math.max(left.y,right.y));return width*height}
function setReadableMode(cluster,mode){cluster.classList.toggle("compact-io",mode==="compact");cluster.classList.toggle("micro-io",mode==="micro");cluster.classList.toggle("nano-io",mode==="nano");cluster.classList.remove("stacked")}
function project(point,anchor){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(!distance||distance<=MAX_DISTANCE)return point;const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function constrain(point,cluster,stage){return{x:Math.max(cluster.offsetWidth/2+8,Math.min(stage.scrollWidth-cluster.offsetWidth/2-8,point.x)),y:Math.max(cluster.offsetHeight/2+8,Math.min(stage.scrollHeight-cluster.offsetHeight/2-8,point.y))}}
function rectAt(cluster,point){return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function candidatePoints(anchor,preferred){const values=[],seen=new Set(),add=point=>{const value=project(point,anchor),key=`${Math.round(value.x*10)}:${Math.round(value.y*10)}`;if(!seen.has(key)){seen.add(key);values.push(value)}};add(preferred);for(const radius of RINGS){for(let index=0;index<ANGLES;index+=1){const angle=index*2*Math.PI/ANGLES;add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius})}}return values}
function nodeObstacles(stage){return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function optionsFor(cluster,anchor,preferred,stage,nodes){const result=[],dedupe=new Set(),modes=["normal","compact","micro","nano"];for(let modeIndex=0;modeIndex<modes.length;modeIndex+=1){const mode=modes[modeIndex];setReadableMode(cluster,mode);const modeValues=[];for(const rawPoint of candidatePoints(anchor,preferred)){const point=constrain(rawPoint,cluster,stage),rect=rectAt(cluster,point);if(!inside(rect,stage)||nodes.some(node=>intersects(rect,node)))continue;const key=`${mode}:${Math.round(point.x)}:${Math.round(point.y)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;if(dedupe.has(key))continue;dedupe.add(key);modeValues.push({mode,point,rect,distance:Math.hypot(point.x-preferred.x,point.y-preferred.y),modeCost:modeIndex*24})}modeValues.sort((left,right)=>left.distance-right.distance);result.push(...modeValues.slice(0,OPTIONS_PER_MODE))}return result}
function assignmentScore(entryIndex,option,assignment,entries){let conflicts=0,area=0;for(let index=0;index<assignment.length;index+=1){if(index===entryIndex||!assignment[index])continue;const other=assignment[index];if(intersects(option.rect,other.rect)){conflicts+=1;area+=overlapArea(option.rect,other.rect)}}return{conflicts,area,score:conflicts*1000000+area*100+option.modeCost+option.distance}}
function totalConflicts(assignment){let count=0,area=0;for(let index=0;index<assignment.length;index+=1){for(let other=index+1;other<assignment.length;other+=1){if(intersects(assignment[index].rect,assignment[other].rect)){count+=1;area+=overlapArea(assignment[index].rect,assignment[other].rect)}}}return{count,area}}
function applyReadableAssignment(stage,entries,assignment){for(let index=0;index<entries.length;index+=1){const entry=entries[index],option=assignment[index];setReadableMode(entry.cluster,option.mode);entry.cluster.style.left=`${option.point.x}px`;entry.cluster.style.top=`${option.point.y}px`;entry.cluster.dataset.ioDistance=String(Math.hypot(option.point.x-entry.anchor.x,option.point.y-entry.anchor.y));entry.cluster.dataset.ioCollisionSolved="true";entry.cluster.classList.remove("layout-constrained")}stage.dataset.transitionIoCollisionSolved="fallback";stage.dataset.transitionIoCollisionCount="0";stage.dataset.transitionIoReadableRepair="true";document.dispatchEvent(new CustomEvent("glyph-transition-io-collision-solved",{detail:{marker:MARKER,count:entries.length,state:"fallback",readableRepair:true}}));queueMicrotask(()=>inspect(stage))}
function repairCollisions(stage=document.querySelector(".state-node")?.closest(".graph-stage")){if(repairing||!stage)return false;repairing=true;try{const clusters=[...stage.querySelectorAll(".transition-io-cluster")],nodes=nodeObstacles(stage);if(!clusters.length)return false;const entries=clusters.map((cluster,index)=>{const anchor={x:numberValue(cluster.dataset.anchorX),y:numberValue(cluster.dataset.anchorY)},preferred=project({x:numberValue(cluster.style.left)||anchor.x,y:numberValue(cluster.style.top)||anchor.y},anchor);return{cluster,index,anchor,preferred,options:optionsFor(cluster,anchor,preferred,stage,nodes)}});if(entries.some(entry=>!entry.options.length)){stage.dataset.transitionIoReadableRepair="no-options";return false}let best=null;for(let restart=0;restart<32;restart+=1){const assignment=Array(entries.length).fill(null),order=[...entries.keys()].sort((left,right)=>entries[left].options.length-entries[right].options.length||((left*17+restart*13)%31)-((right*17+restart*13)%31));for(const index of order){let choice=null,choiceScore=null;const options=entries[index].options;const offset=(restart*(index+3))%Math.min(options.length,23);for(let optionIndex=0;optionIndex<options.length;optionIndex+=1){const option=options[(optionIndex+offset)%options.length],value=assignmentScore(index,option,assignment,entries);if(!choiceScore||value.score<choiceScore.score){choice=option;choiceScore=value;if(value.conflicts===0&&optionIndex>24)break}}assignment[index]=choice}for(let iteration=0;iteration<360;iteration+=1){const total=totalConflicts(assignment);if(!best||total.count<best.total.count||total.count===best.total.count&&total.area<best.total.area)best={assignment:[...assignment],total};if(total.count===0){applyReadableAssignment(stage,entries,assignment);return true}const conflicted=[];for(let index=0;index<assignment.length;index+=1){if(assignmentScore(index,assignment[index],assignment,entries).conflicts>0)conflicted.push(index)}const index=conflicted[(iteration+restart)%conflicted.length];let choice=assignment[index],choiceScore=assignmentScore(index,choice,assignment,entries);for(const option of entries[index].options){const value=assignmentScore(index,option,assignment,entries);if(value.score<choiceScore.score){choice=option;choiceScore=value;if(value.conflicts===0)break}}assignment[index]=choice}}if(best?.total.count===0){applyReadableAssignment(stage,entries,best.assignment);return true}stage.dataset.transitionIoReadableRepair=`failed:${best?.total.count??"unknown"}`;return false}finally{repairing=false}}

function renderedLines(element){
  const value=element?.textContent||"",node=element?.firstChild;
  if(!value||!node||node.nodeType!==Node.TEXT_NODE)return[value];
  const lines=[];
  let current="",currentTop=null;
  for(let index=0;index<value.length;index+=1){
    const range=document.createRange();
    range.setStart(node,index);range.setEnd(node,index+1);
    const rect=range.getBoundingClientRect();
    if(currentTop===null)currentTop=rect.top;
    if(Math.abs(rect.top-currentTop)>1){lines.push(current);current="";currentTop=rect.top}
    current+=value[index];
  }
  if(current)lines.push(current);
  return lines.map(line=>line.trim()).filter(Boolean);
}

function exportSnapshot(stage){
  return[...stage.querySelectorAll(".transition-io-cluster")].map(cluster=>{
    const node=cluster.querySelector('.transition-io-node[data-io-kind="io"]'),valueElement=node?.querySelector(".transition-io-value");
    if(!node||!valueElement)return null;
    const baseX=cluster.offsetLeft-cluster.offsetWidth/2,baseY=cluster.offsetTop-cluster.offsetHeight/2;
    return{x:baseX+node.offsetLeft,y:baseY+node.offsetTop,width:node.offsetWidth,height:node.offsetHeight,value:valueElement.textContent||"",lines:renderedLines(valueElement)};
  }).filter(Boolean);
}

function exportMarkup(items){
  return items.map(item=>{
    const lineHeight=11.5,startY=item.y+item.height/2-((item.lines.length-1)*lineHeight)/2+3;
    const tspans=item.lines.map((line,index)=>`<tspan x="${item.x+item.width/2}" y="${startY+index*lineHeight}">${esc(line)}</tspan>`).join("");
    return`<g class="transition-io-export-label" data-full-label="${esc(item.value)}"><title>${esc(item.value)}</title><rect x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="6" fill="#fff" stroke="#2563eb"/><text font-family="Arial,Helvetica,sans-serif" font-size="9" font-weight="700" text-anchor="middle" fill="#111">${tspans}</text></g>`;
  }).join("");
}

function patchExports(){
  const original=window.svg;
  if(typeof original!=="function"||original.__glyphReadableTransitionLabels)return;
  const patched=function(){
    const stage=document.querySelector(".graph-stage"),items=stage?exportSnapshot(stage):[];
    const clusters=stage?[...stage.querySelectorAll(".transition-io-cluster")]:[];
    const markers=clusters.map(cluster=>{const marker=document.createComment("readable-transition-label");cluster.replaceWith(marker);return{cluster,marker}});
    let markup;
    try{markup=original()}finally{markers.forEach(({cluster,marker})=>marker.replaceWith(cluster))}
    if(!items.length)return markup;
    return markup.replace("</svg>",`${exportMarkup(items)}</svg>`);
  };
  patched.__glyphReadableTransitionLabels=true;
  window.svg=patched;
}

function schedule(stage=null,delay=40){
  clearTimeout(timer);
  timer=setTimeout(()=>inspect(stage||document.querySelector(".state-node")?.closest(".graph-stage")),delay);
}

for(const event of["glyph-transition-io-clusters-ready","glyph-diagram-viewport-change","glyph-locale-changed"]){
  document.addEventListener(event,()=>schedule(null,0));
}
document.addEventListener("glyph-transition-io-collision-solved",event=>{
  const stage=document.querySelector(".state-node")?.closest(".graph-stage");
  if(event.detail?.state==="failed"){repairCollisions(stage);return}
  schedule(stage,0);
});
window.addEventListener("resize",()=>schedule(null,30));
new MutationObserver(()=>schedule()).observe(document.getElementById("view")||document.body,{childList:true,subtree:true,characterData:true});
patchExports();
window.glyphTransitionLabelReadability={inspect,repair:repairCollisions,minimumFontSize:MIN_FONT_SIZE,marker:MARKER};
schedule(null,0);
})();
</script>
"""


def enhance_transition_label_readability_html(html: str) -> str:
    """Keep every transition label fully visible and auditable at readable size."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
