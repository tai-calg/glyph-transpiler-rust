from __future__ import annotations


_MARKER = "glyph-state-diagram-workspace-v1"

_STYLE = r"""
<style id="glyph-state-diagram-workspace-v1-style">
.graph-stage[data-state-diagram-workspace-ready="true"]{
  min-width:1600px;
  min-height:960px;
}
.transition-index{
  margin-top:14px;
  border:1px solid var(--line);
  border-radius:11px;
  background:var(--panel);
  overflow:hidden;
}
.transition-index-title{
  position:sticky;
  top:0;
  z-index:2;
  display:flex;
  justify-content:space-between;
  gap:12px;
  padding:10px 12px;
  border-bottom:1px solid var(--line);
  background:var(--panel);
  font-weight:750;
}
.transition-index-note{color:var(--muted);font-size:11px;font-weight:500}
.transition-index-body{max-height:320px;overflow:auto;overscroll-behavior:contain}
.transition-detail{
  display:grid;
  grid-template-columns:minmax(80px,180px) minmax(150px,240px) minmax(0,1fr) auto;
  align-items:start;
  gap:10px;
  padding:9px 12px;
  border-top:1px solid rgba(255,255,255,.045);
  cursor:pointer;
}
.transition-detail:first-child{border-top:0}
.transition-detail:hover,.transition-detail.transition-focus{background:rgba(88,166,255,.075)}
.transition-detail-id{
  display:inline-flex;
  justify-content:center;
  align-items:center;
  min-height:24px;
  padding:3px 7px;
  border:1px solid rgba(88,166,255,.55);
  border-radius:7px;
  color:var(--blue);
  font:800 10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-wrap:anywhere;
  text-align:center;
}
.transition-detail-route,.transition-detail-condition{
  font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-wrap:anywhere;
  word-break:break-word;
}
.transition-detail-route{color:var(--text)}
.transition-detail-condition{color:var(--muted)}
.transition-detail-line{color:var(--faint);font-size:10px;white-space:nowrap}
.state-transition-path.transition-focus{stroke:var(--blue)!important;stroke-width:4!important;opacity:1!important}
.transition-io-cluster.transition-focus{z-index:12;filter:drop-shadow(0 0 5px rgba(88,166,255,.45))}
@media(max-width:1100px){
  .transition-detail{grid-template-columns:minmax(76px,150px) minmax(0,1fr) auto}
  .transition-detail-condition{grid-column:2/4}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-state-diagram-workspace-v1-script">
(()=>{
const MARKER="glyph-state-diagram-workspace-v1";
const MIN_WIDTH=1600,MIN_HEIGHT=960,HORIZONTAL_MARGIN=360,VERTICAL_MARGIN=220,DOT_RADIUS=9;
let frame=0,running=false,pendingReason="bootstrap",destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const stateName=node=>node.querySelector(".state-name")?.textContent?.trim()||"";

function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===selected)||machines[0]||null;
}
async function readMachine(){
  const live=typeof snapshot==="object"&&snapshot?snapshot:null;
  if(live)return selectedMachine(live);
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)return null;
  return selectedMachine(await response.json());
}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function directPaths(stage){return[...(stage.querySelector(":scope > svg.edge-svg")?.querySelectorAll(":scope > path")||[])]}
function nodesByName(stage){return new Map([...stage.querySelectorAll(".state-node")].map(node=>[stateName(node),node]))}
function stageSize(stage){
  return{
    width:Math.max(1,num(stage.style.width),stage.scrollWidth),
    height:Math.max(1,num(stage.style.height),stage.scrollHeight),
  };
}
function persistShiftedPositions(stage,dx,dy){
  const source=stage.dataset.transitionNodePositionSource||"";
  if(!source||!source.startsWith("glyph.diagram.positions.v1:"))return;
  const migrationKey=`glyph.diagram.workspace.v1:${source}`;
  try{
    if(localStorage.getItem(migrationKey)==="1")return;
    const positions={};
    stage.querySelectorAll(".state-node").forEach(node=>{
      positions[stateName(node)]={x:num(node.style.left),y:num(node.style.top)};
    });
    localStorage.setItem(source,JSON.stringify(positions));
    localStorage.setItem(migrationKey,"1");
    stage.dataset.stateDiagramWorkspacePositionMigration=`${dx},${dy}`;
  }catch(error){console.warn("state diagram workspace position migration unavailable",error)}
}
function expandWorkspace(stage){
  if(stage.dataset.stateDiagramWorkspaceReady==="true")return true;
  const original=stageSize(stage);
  const width=Math.max(MIN_WIDTH,original.width+HORIZONTAL_MARGIN*2);
  const height=Math.max(MIN_HEIGHT,original.height+VERTICAL_MARGIN*2);
  stage.style.width=`${Math.ceil(width)}px`;
  stage.style.height=`${Math.ceil(height)}px`;
  const svg=stage.querySelector(":scope > svg.edge-svg");
  if(svg){svg.setAttribute("width",String(Math.ceil(width)));svg.setAttribute("height",String(Math.ceil(height)))}
  stage.dataset.stateDiagramWorkspaceReady="true";
  stage.dataset.stateDiagramWorkspaceOriginalWidth=String(original.width);
  stage.dataset.stateDiagramWorkspaceOriginalHeight=String(original.height);
  stage.dataset.stateDiagramWorkspaceWidth=String(width);
  stage.dataset.stateDiagramWorkspaceHeight=String(height);
  return true;
}
function applyWorkspaceOrigin(stage){
  if(stage.dataset.stateDiagramWorkspaceOriginReady==="true")return true;
  const positionState=stage.dataset.transitionNodePositions||"";
  if(!positionState){setTimeout(()=>schedule("await-node-position-restore"),20);return false}
  const originalWidth=num(stage.dataset.stateDiagramWorkspaceOriginalWidth);
  const originalHeight=num(stage.dataset.stateDiagramWorkspaceOriginalHeight);
  const width=num(stage.dataset.stateDiagramWorkspaceWidth);
  const height=num(stage.dataset.stateDiagramWorkspaceHeight);
  const dx=Math.max(0,Math.round((width-originalWidth)/2));
  const dy=Math.max(0,Math.round((height-originalHeight)/2));
  const source=stage.dataset.transitionNodePositionSource||"";
  let alreadyMigrated=false;
  if(source){
    try{alreadyMigrated=localStorage.getItem(`glyph.diagram.workspace.v1:${source}`)==="1"}catch{}
  }
  if(!alreadyMigrated){
    stage.querySelectorAll(".state-node").forEach(node=>{
      node.style.left=`${num(node.style.left)+dx}px`;
      node.style.top=`${num(node.style.top)+dy}px`;
    });
    stage.querySelectorAll(".edge-label").forEach(label=>{
      label.style.left=`${num(label.style.left)+dx}px`;
      label.style.top=`${num(label.style.top)+dy}px`;
    });
    const dot=stage.querySelector(".initial-dot");
    if(dot){dot.style.left=`${num(dot.style.left)+dx}px`;dot.style.top=`${num(dot.style.top)+dy}px`}
    if(positionState.startsWith("restored:"))persistShiftedPositions(stage,dx,dy);
  }
  stage.dataset.stateDiagramWorkspaceOriginReady="true";
  stage.dataset.stateDiagramWorkspaceOriginX=String(dx);
  stage.dataset.stateDiagramWorkspaceOriginY=String(dy);
  return true;
}
function statePath(a,b,same,index){
  const x1=a.offsetLeft+a.offsetWidth/2,y1=a.offsetTop+a.offsetHeight/2;
  const x2=b.offsetLeft+b.offsetWidth/2,y2=b.offsetTop+b.offsetHeight/2;
  if(same){const spread=58+index%3*14;return`M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`}
  const dx=x2-x1,dy=y2-y1,len=Math.max(1,Math.hypot(dx,dy));
  const rx=Math.max(1,a.offsetWidth/2),ry=Math.max(1,a.offsetHeight/2);
  const txr=Math.max(1,b.offsetWidth/2),tyr=Math.max(1,b.offsetHeight/2);
  const sourceScale=1/Math.max(Math.abs(dx)/(rx||1),Math.abs(dy)/(ry||1),1/Math.max(rx,ry));
  const targetScale=1/Math.max(Math.abs(dx)/(txr||1),Math.abs(dy)/(tyr||1),1/Math.max(txr,tyr));
  const sx=x1+dx/len*Math.min(sourceScale,len/2),sy=y1+dy/len*Math.min(sourceScale,len/2);
  const ex=x2-dx/len*Math.min(targetScale,len/2),ey=y2-dy/len*Math.min(targetScale,len/2);
  const offset=(index%3-1)*22;
  return`M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${((sx+ex)/2-dy*.1+offset).toFixed(1)} ${((sy+ey)/2+dx*.1+offset).toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;
}
function updateInitialTransition(stage,machine,paths,nodes){
  stage.querySelectorAll(".state-node.initial-target").forEach(node=>node.classList.remove("initial-target"));
  const target=nodes.get(String(machine?.initial_state||""));
  const dot=stage.querySelector(".initial-dot");
  const initialPath=paths[(machine?.transitions||[]).length]||paths.find(path=>path.classList.contains("initial-transition-path"));
  if(!target||!dot||!initialPath)return false;
  target.classList.add("initial-target");
  initialPath.classList.add("initial-transition-path");
  const size=stageSize(stage),left=target.offsetLeft,top=target.offsetTop,right=left+target.offsetWidth,bottom=top+target.offsetHeight;
  const cx=left+target.offsetWidth/2,cy=top+target.offsetHeight/2;
  const spaces={top,left,right:size.width-right,bottom:size.height-bottom};
  let side=spaces.top>=72?"top":Object.entries(spaces).sort((a,b)=>b[1]-a[1])[0][0];
  let dotX=cx,dotY=top-54,startX=cx,startY=dotY+DOT_RADIUS,endX=cx,endY=top-2;
  if(side==="bottom"){dotY=bottom+54;startY=dotY-DOT_RADIUS;endY=bottom+2}
  else if(side==="left"){dotX=left-54;dotY=cy;startX=dotX+DOT_RADIUS;startY=cy;endX=left-2;endY=cy}
  else if(side==="right"){dotX=right+54;dotY=cy;startX=dotX-DOT_RADIUS;startY=cy;endX=right+2;endY=cy}
  dotX=Math.max(DOT_RADIUS+8,Math.min(size.width-DOT_RADIUS-8,dotX));
  dotY=Math.max(DOT_RADIUS+8,Math.min(size.height-DOT_RADIUS-8,dotY));
  if(side==="top"){startY=dotY+DOT_RADIUS}else if(side==="bottom"){startY=dotY-DOT_RADIUS}
  else if(side==="left"){startX=dotX+DOT_RADIUS}else{startX=dotX-DOT_RADIUS}
  initialPath.setAttribute("d",`M ${startX.toFixed(1)} ${startY.toFixed(1)} L ${endX.toFixed(1)} ${endY.toFixed(1)}`);
  dot.style.left=`${dotX-DOT_RADIUS}px`;dot.style.top=`${dotY-DOT_RADIUS}px`;
  dot.dataset.routeSide=side;initialPath.dataset.routeSide=side;
  stage.dataset.initialRouteReady="true";
  stage.dataset.initialRouteCertificate="ordinary-follow";
  return true;
}
function updateTransitionGeometry(stage,machine){
  const nodes=nodesByName(stage),paths=directPaths(stage),transitions=machine?.transitions||[];
  transitions.forEach((transition,index)=>{
    const source=nodes.get(String(transition.source_state||"")),target=nodes.get(String(transition.target_state||"")),path=paths[index];
    if(!source||!target||!path)return;
    path.classList.add("state-transition-path");
    const id=transition.id||`T${index+1}`;
    path.dataset.transitionId=id;
    path.setAttribute("d",statePath(source,target,source===target,index));
  });
  updateInitialTransition(stage,machine,paths,nodes);
  window.glyphTransitionIoClusters?.reroute?.(stage);
  stage.dataset.stateDiagramWorkspaceGeometryReady="true";
}
function transitionSummary(transition){
  const value=transition?.display_label??transition?.condition??transition?.condition_raw??"otherwise";
  return String(value||"otherwise").trim()||"otherwise";
}
function detailSignature(machine){
  return[machine?.name||"",...(machine?.transitions||[]).map((transition,index)=>[
    transition.id||`T${index+1}`,transition.source_state||"",transition.target_state||"",transitionSummary(transition),transition.source?.line||0,
  ].join("\u001f"))].join("\u001e");
}
function renderTransitionIndex(stage,machine){
  const shell=stage.closest(".canvas-shell");if(!shell)return;
  let panel=shell.nextElementSibling?.classList?.contains("transition-index")?shell.nextElementSibling:null;
  if(!panel){panel=document.createElement("section");panel.className="transition-index";shell.after(panel)}
  const signature=detailSignature(machine);if(panel.dataset.transitionIndexSignature===signature)return;
  const ja=!(window.GlyphI18n?.locale||document.documentElement.lang||"ja").startsWith("en");
  const transitions=machine?.transitions||[];
  panel.innerHTML=`<div class="transition-index-title"><span>${ja?"遷移の詳細":"Transition details"} · ${transitions.length}</span><span class="transition-index-note">${ja?"行を選択すると図中の遷移を強調表示する":"Select a row to highlight the transition"}</span></div><div class="transition-index-body">${transitions.map((transition,index)=>{
    const id=transition.id||`T${index+1}`,line=transition.source?.line||0;
    return`<div class="transition-detail" data-transition-id="${esc(id)}" data-line="${line}"><span class="transition-detail-id">${esc(id)}</span><span class="transition-detail-route">${esc(transition.source_state)} → ${esc(transition.target_state)}</span><span class="transition-detail-condition">${esc(transitionSummary(transition))}</span><span class="transition-detail-line">L${line||"?"}</span></div>`;
  }).join("")||`<div class="empty">${ja?"表示できる遷移がない":"No transitions"}</div>`}</div>`;
  panel.dataset.transitionIndexSignature=signature;
  panel.onclick=event=>{
    const row=event.target?.closest?.(".transition-detail");if(!row)return;
    const id=row.dataset.transitionId;
    document.querySelectorAll(".transition-focus").forEach(item=>item.classList.remove("transition-focus"));
    row.classList.add("transition-focus");
    stage.querySelector(`path.state-transition-path[data-transition-id="${CSS.escape(id)}"]`)?.classList.add("transition-focus");
    stage.querySelector(`.transition-io-cluster[data-transition-id="${CSS.escape(id)}"]`)?.classList.add("transition-focus");
    const line=Number(row.dataset.line||0);if(line&&typeof jumpToLine==="function")jumpToLine(line);
  };
}
function preserveOrdinaryScale(stage){
  if(stage.dataset.stateDiagramWorkspaceViewportReady==="true")return;
  const shell=stage.closest(".canvas-shell"),viewport=window.glyphDiagramViewport;if(!shell||!viewport)return;
  const mode=viewport.mode?.()||"";if(mode&&mode!=="fit")return;
  const originalWidth=num(stage.dataset.stateDiagramWorkspaceOriginalWidth),originalHeight=num(stage.dataset.stateDiagramWorkspaceOriginalHeight);
  const scale=Math.min(1,Math.max(.25,Math.min((shell.clientWidth-64)/Math.max(1,originalWidth),(shell.clientHeight-64)/Math.max(1,originalHeight))));
  viewport.setScale?.(scale);
  const x=num(stage.dataset.stateDiagramWorkspaceOriginX)+originalWidth/2,y=num(stage.dataset.stateDiagramWorkspaceOriginY)+originalHeight/2;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    const surface=stage.parentElement;
    shell.scrollLeft=Math.max(0,(surface?.offsetLeft||0)+x*scale-shell.clientWidth/2);
    shell.scrollTop=Math.max(0,(surface?.offsetTop||0)+y*scale-shell.clientHeight/2);
    stage.dataset.stateDiagramWorkspaceViewportReady="true";
  }));
}
async function refresh(reason){
  if(running||destroyed)return;const stage=stageOf();if(!stage)return;
  running=true;
  try{
    const machine=await readMachine();if(!machine||!stage.isConnected)return;
    expandWorkspace(stage);
    applyWorkspaceOrigin(stage);
    updateTransitionGeometry(stage,machine);
    renderTransitionIndex(stage,machine);
    preserveOrdinaryScale(stage);
    stage.dataset.stateDiagramWorkspaceReason=reason;
    document.dispatchEvent(new CustomEvent("glyph-state-diagram-workspace-ready",{detail:{marker:MARKER,machine:machine.name,reason}}));
  }finally{running=false}
}
function schedule(reason="scheduled"){
  if(destroyed)return;pendingReason=reason;cancelAnimationFrame(frame);
  frame=requestAnimationFrame(()=>refresh(pendingReason).catch(error=>console.error("state diagram workspace refresh failed",error)));
}
const view=document.getElementById("view")||document.body;
new MutationObserver(records=>{
  if(records.some(record=>record.type==="childList"||record.target?.classList?.contains("state-node")||record.target?.classList?.contains("graph-stage")))schedule("diagram-mutation");
}).observe(view,{childList:true,subtree:true,attributes:true,attributeFilter:["style"]});
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule("machine-change")});
document.addEventListener("pointerup",event=>{if(event.target?.closest?.(".state-node"))schedule("node-drag-complete")},true);
document.addEventListener("pointercancel",()=>schedule("node-drag-cancelled"),true);
document.addEventListener("glyph-transition-layout-transaction-ready",()=>schedule("layout-ready"));
document.addEventListener("glyph-diagram-viewport-change",()=>schedule("viewport-change"));
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;cancelAnimationFrame(frame)},{once:true})}
window.glyphStateDiagramWorkspace={
  marker:MARKER,version:1,schedule,refresh:()=>schedule("api-refresh"),
  audit:()=>{const stage=stageOf();return{ok:Boolean(stage?.dataset.stateDiagramWorkspaceGeometryReady==="true"&&stage?.nextElementSibling?.classList?.contains("transition-index")),width:num(stage?.style.width),height:num(stage?.style.height),initialReady:stage?.dataset.initialRouteReady||""}}
};
schedule("bootstrap");
})();
</script>
"""


def enhance_state_diagram_workspace_html(html: str) -> str:
    """Provide a broad editable workspace, live initial transition, and transition details."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
