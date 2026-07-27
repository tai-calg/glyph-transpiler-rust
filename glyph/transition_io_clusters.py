from __future__ import annotations


_MARKER = "glyph-transition-io-clusters-v1"

_STYLE = r"""
<style id="glyph-transition-io-clusters-v1-style">
.transition-label.transition-io-source{
  visibility:hidden!important;
  opacity:0!important;
  pointer-events:none!important;
}
.transition-io-cluster{
  position:absolute;
  transform:translate(-50%,-50%);
  z-index:12;
  display:flex;
  align-items:center;
  justify-content:center;
  max-width:220px;
  cursor:grab;
  touch-action:none;
  user-select:none;
}
.transition-io-cluster.dragging-io{cursor:grabbing;z-index:32}
.transition-io-cluster.selected-io{outline:2px solid var(--blue);outline-offset:3px;border-radius:9px}
.transition-io-cluster.layout-constrained{outline:2px dotted rgba(231,191,98,.72);outline-offset:3px;border-radius:9px}
.transition-io-main{display:flex;align-items:center;justify-content:center}
.transition-io-node.io{
  min-width:92px;
  max-width:196px;
  min-height:26px;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:3px 7px;
  border:1px solid var(--line);
  border-radius:7px;
  background:var(--panel);
  box-shadow:0 3px 10px rgba(0,0,0,.20);
  overflow:hidden;
}
.transition-io-value{max-width:100%;font:700 9px/1.25 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.transition-io-cluster.provisional-trigger .transition-io-node.io{border-style:dashed;border-color:rgba(231,191,98,.86);background:rgba(231,191,98,.10)}
.transition-io-cluster.provisional-trigger .transition-io-value{color:var(--amber)}
.transition-io-cluster.unclassified-condition .transition-io-node.io{border-style:dotted;border-color:rgba(231,191,98,.75)}
.transition-io-cluster.compact-io .transition-io-node.io{min-width:70px;max-width:142px;min-height:23px;padding:2px 5px}
.transition-io-cluster.compact-io .transition-io-value{font-size:8px}
.transition-io-cluster.micro-io .transition-io-node.io{min-width:50px;max-width:104px;min-height:19px;padding:1px 3px;border-radius:5px}
.transition-io-cluster.micro-io .transition-io-value{font-size:7px;line-height:1.1}
.transition-io-cluster.transition-focus .transition-io-node{box-shadow:0 0 0 2px rgba(88,166,255,.23),0 6px 16px rgba(0,0,0,.25)}
.theme-monochrome .transition-io-node{background:#fff!important;border-color:#111!important;color:#111!important;box-shadow:none!important}
.theme-monochrome .transition-io-value{color:#111!important}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-io-clusters-v1-script">
(()=>{
const MARKER="glyph-transition-io-clusters-v1",MAX_DISTANCE=96,GAP=6,RINGS=[0,16,32,48,64,80,96],ANGLES=36;
let cache=null,timer=null,running=false,drag=null,selected=null;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const finite=value=>Number.isFinite(value);
const text=value=>String(value??"").trim();
const esc=value=>String(value??"").replace(/[&<>\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[ch]));
const english=()=>String(window.GlyphI18n?.locale||document.documentElement.lang||"ja").startsWith("en");
const both=(ja,en)=>english()?en:ja;
const scaleFor=stage=>window.glyphDiagramViewport?.scaleFor(stage)||num(stage?.dataset.viewportScale)||1;

async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function triggerOf(transition){const trigger=transition?.trigger;if(trigger&&text(trigger.display))return{display:text(trigger.display),role:text(trigger.role)||"confirmed-trigger",roots:trigger.provenance_roots||[],path:trigger.dataflow_path||[]};const event=text(transition?.event);if(!event)return null;return{display:event.replace(/^\?\s*/,""),role:event.startsWith("? ")?"provisional-trigger":"confirmed-trigger",roots:[],path:[]}}
function guardsOf(transition){if(Array.isArray(transition?.guards))return transition.guards.map(text).filter(Boolean);const guard=text(transition?.guard);return guard?[guard]:[]}
function unknownOf(transition){return(transition?.unclassified_conditions||[]).map(text).filter(Boolean)}
function inputOf(transition){const trigger=triggerOf(transition),unknown=unknownOf(transition);if(trigger)return`${trigger.role==="provisional-trigger"?"? ":""}${trigger.display}`;if(unknown.length)return`? ${unknown.join(" & ")}`;return both("自動","automatic")}
function outputOf(transition){return text(transition?.action)}
function ioOf(transition){const input=inputOf(transition),guard=guardsOf(transition).join(" & "),output=outputOf(transition);return`${input}${guard?` [${guard}]`:""}${output?` / ${output}`:""}`}
function evidenceOf(transition){const trigger=triggerOf(transition),parts=[];if(trigger?.role==="provisional-trigger")parts.push(both("暫定入力: 出来事か継続条件かを確定できない","Provisional input: occurrence semantics are not proven"));else if(trigger?.role==="inferred-trigger")parts.push(both("入力から導出された判別値","Discriminator derived from input"));else if(trigger)parts.push(both("型で確定した入力イベント","Input event confirmed by type"));if(trigger?.roots?.length)parts.push(`origin: ${trigger.roots.join(", ")}`);if(trigger?.path?.length)parts.push(`path: ${trigger.path.join(" → ")}`);return parts.join("\n")}
function fullSummary(transition){return ioOf(transition)}
function signatureOf(machine){return[window.GlyphI18n?.locale||document.documentElement.lang||"ja",machine?.name||"",...(machine?.transitions||[]).map(item=>[item.id||"",JSON.stringify(item.trigger||null),JSON.stringify(item.guards||[]),JSON.stringify(item.unclassified_conditions||[]),item.action||""].join("\u001f"))].join("\u001e")}
function clusterMarkup(transition){const value=ioOf(transition);return`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${esc(value)}</span></div></div>`}
function pathFor(stage,id,index){const escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&"),byId=stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`);if(byId)return byId;return[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")][index]||null}
function anchorFor(stage,id,index){const path=pathFor(stage,id,index);if(path&&typeof path.getTotalLength==="function"){try{const length=path.getTotalLength(),mid=path.getPointAtLength(length/2),before=path.getPointAtLength(Math.max(0,length/2-2)),after=path.getPointAtLength(Math.min(length,length/2+2)),dx=after.x-before.x,dy=after.y-before.y;return{x:mid.x,y:mid.y,normal:Math.atan2(dx,-dy),path}}catch{}}return{x:stage.clientWidth/2,y:stage.clientHeight/2,normal:-Math.PI/2,path:null}}
function rectAt(element,x,y){return{x:x-element.offsetWidth/2,y:y-element.offsetHeight/2,width:element.offsetWidth,height:element.offsetHeight}}
function intersects(a,b,gap=GAP){return!(a.x+a.width+gap<=b.x||b.x+b.width+gap<=a.x||a.y+a.height+gap<=b.y||b.y+b.height+gap<=a.y)}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function project(point,anchor){const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);if(distance<=MAX_DISTANCE||distance===0)return point;const ratio=MAX_DISTANCE/distance;return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio}}
function constrain(point,cluster,stage){return{x:clamp(point.x,cluster.offsetWidth/2+8,stage.scrollWidth-cluster.offsetWidth/2-8),y:clamp(point.y,cluster.offsetHeight/2+8,stage.scrollHeight-cluster.offsetHeight/2-8)}}
function candidates(anchor,preferred=anchor){const values=[],seen=new Set(),add=point=>{const projected=project(point,anchor),key=`${Math.round(projected.x*10)}:${Math.round(projected.y*10)}`;if(!seen.has(key)){seen.add(key);values.push(projected)}};add(preferred);for(const radius of RINGS){for(let index=0;index<ANGLES;index+=1){const angle=anchor.normal+index*2*Math.PI/ANGLES;add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius})}}return values.sort((a,b)=>Math.hypot(a.x-preferred.x,a.y-preferred.y)-Math.hypot(b.x-preferred.x,b.y-preferred.y))}
function obstacles(stage){return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}))}
function collisionCount(rect,nodes,placed){return nodes.reduce((sum,item)=>sum+(intersects(rect,item)?1:0),0)+placed.reduce((sum,item)=>sum+(intersects(rect,item)?1:0),0)}
function setMode(cluster,mode){cluster.classList.toggle("stacked",mode.includes("stacked"));cluster.classList.toggle("compact-io",mode.includes("compact"));cluster.classList.toggle("micro-io",mode.includes("micro"))}
function choose(cluster,anchor,preferred,stage,nodes,placed,dense){const modes=dense?["stacked micro","horizontal micro","stacked compact","horizontal compact","stacked","horizontal"]:["horizontal","stacked","horizontal compact","stacked compact","horizontal micro","stacked micro"];let best=null;for(let modeIndex=0;modeIndex<modes.length;modeIndex+=1){const mode=modes[modeIndex];setMode(cluster,mode);for(const point of candidates(anchor,preferred)){const constrained=constrain(point,cluster,stage),rect=rectAt(cluster,constrained.x,constrained.y);if(!inside(rect,stage))continue;const collisions=collisionCount(rect,nodes,placed),score=collisions*100000+modeIndex*300+Math.hypot(constrained.x-preferred.x,constrained.y-preferred.y);if(!best||score<best.score)best={point:constrained,rect,collisions,mode,score};if(collisions===0)return best}}return best}
function storageKey(data){const digest=data?.digest||"source",index=document.getElementById("machine-select")?.value||0;return`glyph.diagram.transition-io.v1:${digest}:${index}`}
function legacyKeys(data){const digest=data?.digest||"source",index=document.getElementById("machine-select")?.value||0;return[`glyph.diagram.label-positions.v2:${digest}:state:${index}`,`glyph.diagram.label-positions.v1:${digest}:state:${index}`]}
function parse(value){try{return JSON.parse(value||"{}")||{}}catch{return{}}}
function readSaved(data){const current=parse(localStorage.getItem(storageKey(data)));if(Object.keys(current).length)return current;for(const key of legacyKeys(data)){const value=parse(localStorage.getItem(key));if(Object.keys(value).length)return value}return{}}
function writeSaved(data,value){localStorage.setItem(storageKey(data),JSON.stringify(value))}
function restored(saved,id,anchor){const value=saved[id];if(finite(value?.dx)&&finite(value?.dy))return{x:anchor.x+value.dx,y:anchor.y+value.dy};if(finite(value?.x)&&finite(value?.y))return{x:value.x,y:value.y};return anchor}
function place(cluster,choice,anchor,manual,placed){if(!choice)return;setMode(cluster,choice.mode);cluster.style.left=`${choice.point.x}px`;cluster.style.top=`${choice.point.y}px`;cluster.dataset.anchorX=String(anchor.x);cluster.dataset.anchorY=String(anchor.y);cluster.dataset.ioDistance=String(Math.hypot(choice.point.x-anchor.x,choice.point.y-anchor.y));cluster.dataset.maxIoDistance=String(MAX_DISTANCE);cluster.dataset.manualIo=manual?"true":"false";cluster.classList.toggle("layout-constrained",choice.collisions>0);placed.push(choice.rect)}
function arrange(stage,data){const clusters=[...stage.querySelectorAll(".transition-io-cluster")];if(!clusters.length)return;const nodes=obstacles(stage),placed=[],saved=readSaved(data),dense=clusters.length>=7;const entries=clusters.map((cluster,index)=>{const id=cluster.dataset.transitionId||`T${index+1}`,anchor=anchorFor(stage,id,index);return{cluster,index,id,anchor,manual:Boolean(saved[id]),preferred:project(restored(saved,id,anchor),anchor)}});entries.forEach(entry=>{entry.congestion=entries.reduce((sum,other)=>sum+(other!==entry&&Math.hypot(entry.anchor.x-other.anchor.x,entry.anchor.y-other.anchor.y)<80?1:0),0)});entries.sort((left,right)=>right.congestion-left.congestion||left.index-right.index);for(const entry of entries){const choice=choose(entry.cluster,entry.anchor,entry.preferred,stage,nodes,placed,dense||entry.congestion>=2);place(entry.cluster,choice,entry.anchor,entry.manual,placed)}stage.dataset.transitionIoClustersReady="true";stage.dataset.transitionIoMaxDistance=String(MAX_DISTANCE)}
function focus(id,active){document.querySelectorAll(`[data-transition-id="${id}"]`).forEach(item=>item.classList.toggle("transition-focus",active))}
function select(cluster){selected?.classList.remove("selected-io");selected=cluster;selected?.classList.add("selected-io")}
function bindCluster(cluster,stage,index,data){if(cluster.dataset.ioDragReady==="true")return;cluster.dataset.ioDragReady="true";cluster.addEventListener("mouseenter",()=>focus(cluster.dataset.transitionId,true));cluster.addEventListener("mouseleave",()=>focus(cluster.dataset.transitionId,false));cluster.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();select(cluster);cluster.classList.add("dragging-io");cluster.setPointerCapture(event.pointerId);const id=cluster.dataset.transitionId||`T${index+1}`,anchor=anchorFor(stage,id,index);drag={cluster,stage,data,id,index,anchor,startX:event.clientX,startY:event.clientY,left:num(cluster.style.left),top:num(cluster.style.top)}});cluster.addEventListener("pointermove",event=>{if(!drag||drag.cluster!==cluster)return;event.preventDefault();event.stopPropagation();const scale=scaleFor(stage),point=constrain(project({x:drag.left+(event.clientX-drag.startX)/scale,y:drag.top+(event.clientY-drag.startY)/scale},drag.anchor),cluster,stage);cluster.style.left=`${point.x}px`;cluster.style.top=`${point.y}px`});cluster.addEventListener("pointerup",event=>{if(!drag||drag.cluster!==cluster)return;event.preventDefault();event.stopPropagation();cluster.classList.remove("dragging-io");const anchor=anchorFor(stage,drag.id,drag.index),point=project({x:num(cluster.style.left),y:num(cluster.style.top)},anchor),saved=readSaved(data);saved[drag.id]={x:point.x,y:point.y,dx:point.x-anchor.x,dy:point.y-anchor.y};writeSaved(data,saved);drag=null;arrange(stage,data)});cluster.addEventListener("dblclick",event=>{event.preventDefault();event.stopPropagation();const id=cluster.dataset.transitionId||`T${index+1}`,saved=readSaved(data);delete saved[id];writeSaved(data,saved);arrange(stage,data)});cluster.addEventListener("click",event=>{event.stopPropagation();const line=Number(cluster.dataset.line||0);if(line&&typeof jumpToLine==="function")jumpToLine(line)})}
function updateCluster(cluster,transition,id,line){const semantic=JSON.stringify([window.GlyphI18n?.locale||document.documentElement.lang,inputOf(transition),guardsOf(transition),outputOf(transition)]);if(cluster.dataset.semanticSignature!==semantic){cluster.innerHTML=clusterMarkup(transition);cluster.dataset.semanticSignature=semantic}const trigger=triggerOf(transition),unknown=unknownOf(transition).length>0;cluster.dataset.transitionId=id;cluster.dataset.line=String(line||0);cluster.dataset.inputValue=inputOf(transition);cluster.dataset.outputValue=outputOf(transition);cluster.dataset.ioValue=ioOf(transition);cluster.dataset.guardValue=guardsOf(transition).join(" & ");cluster.dataset.fullLabel=fullSummary(transition);cluster.classList.toggle("provisional-trigger",trigger?.role==="provisional-trigger");cluster.classList.toggle("unclassified-condition",unknown);cluster.title=`${fullSummary(transition)}\n${evidenceOf(transition)}`.trim();cluster.setAttribute("role","group");cluster.setAttribute("aria-label",fullSummary(transition))}
function patchExports(){if(window.svg?.__glyphTransitionIoPatched)return;const original=window.svg;if(typeof original!=="function")return;const svgText=(x,y,value,size=9,weight=700,anchor="start")=>`<text x="${x}" y="${y}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="#111">${esc(value)}</text>`;const clusterSvg=stage=>[...stage.querySelectorAll(".transition-io-cluster")].map(cluster=>{const node=cluster.querySelector('.transition-io-node[data-io-kind="io"]');if(!node)return"";const baseX=cluster.offsetLeft-cluster.offsetWidth/2,baseY=cluster.offsetTop-cluster.offsetHeight/2,x=baseX+node.offsetLeft,y=baseY+node.offsetTop,width=node.offsetWidth,height=node.offsetHeight,value=node.querySelector(".transition-io-value")?.textContent||"";return`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="6" fill="#fff" stroke="#2563eb"/>${svgText(x+width/2,y+height/2+3,value,7,700,"middle")}`}).join("");const patched=function(){const stage=document.querySelector(".graph-stage"),labels=stage?[...stage.querySelectorAll(".transition-label.transition-io-source")]:[],markers=labels.map(label=>{const marker=document.createComment("transition-io-source");label.replaceWith(marker);return{label,marker}});let markup;try{markup=original()}finally{markers.forEach(({label,marker})=>marker.replaceWith(label))}if(!stage||!stage.querySelector(".transition-io-cluster"))return markup;return markup.replace("</svg>",`${clusterSvg(stage)}</svg>`)};patched.__glyphTransitionIoPatched=true;window.svg=patched}
function patchReroute(){if(window.reroute?.__glyphTransitionIoPatched)return;const original=window.reroute;if(typeof original!=="function")return;const patched=async function(stage){const result=await original(stage);schedule(stage,0);return result};patched.__glyphTransitionIoPatched=true;window.reroute=patched}
async function render(stage=document.querySelector(".state-node")?.closest(".graph-stage")){if(running||!stage||stage.dataset.stateTransitionIRV3LabelsReady!=="true")return;running=true;try{const data=await state(),machine=selectedMachine(data);if(!machine)return;const labels=[...stage.querySelectorAll(".transition-label")],transitions=machine.transitions||[];transitions.forEach((transition,index)=>{const id=transition.id||`T${index+1}`,line=transition.source?.line||0,source=stage.querySelector(`.transition-label[data-transition-id="${id}"]`)||labels[index];if(source){source.classList.add("transition-io-source");source.setAttribute("aria-hidden","true")}let cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${id}"]`);if(!cluster){cluster=document.createElement("div");cluster.className="transition-io-cluster";cluster.style.left=source?.style.left||"50%";cluster.style.top=source?.style.top||"50%";stage.appendChild(cluster)}updateCluster(cluster,transition,id,line);bindCluster(cluster,stage,index,data)});stage.querySelectorAll(".transition-io-cluster").forEach(cluster=>{if(!transitions.some((item,index)=>(item.id||`T${index+1}`)===cluster.dataset.transitionId))cluster.remove()});stage.dataset.transitionIoSignature=signatureOf(machine);arrange(stage,data);document.dispatchEvent(new CustomEvent("glyph-transition-io-clusters-ready",{detail:{machine:machine.name,transitions:transitions.length,marker:MARKER}}))}finally{running=false}}
function schedule(stage=null,delay=24){clearTimeout(timer);timer=setTimeout(()=>render(stage||document.querySelector(".state-node")?.closest(".graph-stage")).catch(error=>console.error("transition I/O rendering failed",error)),delay)}
for(const event of["glyph-state-transition-ir-v3-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-transition-input-action-labels-ready","glyph-uml-transition-ready","glyph-locale-changed","glyph-diagram-viewport-change"])document.addEventListener(event,()=>{cache=null;schedule(null,0)});document.addEventListener("pointerup",event=>{if(event.target?.closest?.(".state-node"))schedule(null,40)},true);document.addEventListener("click",event=>{if(!event.target?.closest?.(".transition-io-cluster"))select(null)});document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;schedule(null,0)}});new MutationObserver(()=>schedule()).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});patchExports();patchReroute();window.glyphTransitionIoClusters={render:()=>schedule(null,0),maxDistance:MAX_DISTANCE};schedule(null,0);
})();
</script>
"""


def enhance_transition_io_clusters_html(html: str) -> str:
    """Render one UML-style trigger [guard] / effect label per transition."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
