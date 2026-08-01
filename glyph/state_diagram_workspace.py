from __future__ import annotations


_MARKER = "glyph-state-diagram-workspace-v1"

_STYLE = r"""
<style id="glyph-state-diagram-workspace-v1-style">
.graph-stage[data-state-diagram-workspace-ready="true"]{min-width:1600px;min-height:960px}
.transition-index{margin-top:14px;border:1px solid var(--line);border-radius:11px;background:var(--panel);overflow:hidden}
.transition-index-title{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line);background:var(--panel);font-weight:750}
.transition-index-note{color:var(--muted);font-size:11px;font-weight:500}
.transition-index-body{max-height:320px;overflow:auto;overscroll-behavior:contain}
.transition-detail{display:grid;grid-template-columns:minmax(80px,180px) minmax(150px,240px) minmax(0,1fr) auto;align-items:start;gap:10px;padding:9px 12px;border-top:1px solid rgba(255,255,255,.045);cursor:pointer}
.transition-detail:first-child{border-top:0}.transition-detail:hover,.transition-detail.transition-focus{background:rgba(88,166,255,.075)}
.transition-detail-id{display:inline-flex;justify-content:center;align-items:center;min-height:24px;padding:3px 7px;border:1px solid rgba(88,166,255,.55);border-radius:7px;color:var(--blue);font:800 10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;text-align:center}
.transition-detail-route,.transition-detail-condition{font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;word-break:break-word}.transition-detail-route{color:var(--text)}.transition-detail-condition{color:var(--muted)}.transition-detail-line{color:var(--faint);font-size:10px;white-space:nowrap}
.state-transition-path.transition-focus{stroke:var(--blue)!important;stroke-width:4!important;opacity:1!important}.transition-io-cluster.transition-focus{z-index:12;filter:drop-shadow(0 0 5px rgba(88,166,255,.45))}
@media(max-width:1100px){.transition-detail{grid-template-columns:minmax(76px,150px) minmax(0,1fr) auto}.transition-detail-condition{grid-column:2/4}}
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
const liveState=()=>typeof snapshot==="object"&&snapshot?snapshot:null;
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
async function readMachine(){const live=liveState();if(live)return selectedMachine(live);const response=await fetch("/api/state",{cache:"no-store"});return response.ok?selectedMachine(await response.json()):null}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function directPaths(stage){return[...(stage.querySelector(":scope > svg.edge-svg")?.querySelectorAll(":scope > path")||[])]}
function nodesByName(stage){return new Map([...stage.querySelectorAll(".state-node")].map(node=>[stateName(node),node]))}
function stageSize(stage){return{width:Math.max(1,num(stage.style.width),stage.scrollWidth),height:Math.max(1,num(stage.style.height),stage.scrollHeight)}}
function canonicalPositionKey(stage){const digest=liveState()?.digest||stage.dataset.diagramDigest||"source",machine=document.getElementById("machine-select")?.value||0;return`glyph.diagram.positions.v1:${digest}:state:${machine}`}
function legacyPositionKey(){const digest=liveState()?.digest||"source",machine=document.getElementById("machine-select")?.value||0;return`${digest}:state:${machine}`}
function migrationKey(key){return`glyph.diagram.workspace.v1:${key}`}
function isMigrated(key){try{return Boolean(key)&&localStorage.getItem(migrationKey(key))==="1"}catch{return false}}
function markPositionMigration(_stage,key){if(!key)return;try{localStorage.setItem(migrationKey(key),"1")}catch(error){console.warn("state workspace migration marker unavailable",error)}}
function mapRestoredPosition(stage,key,position){
  if(!stage||!position||isMigrated(key))return position;
  return{x:num(position.x)+num(stage.dataset.stateDiagramWorkspaceOriginX),y:num(position.y)+num(stage.dataset.stateDiagramWorkspaceOriginY)};
}
function hasStoredPositions(stage){try{return Boolean(localStorage.getItem(canonicalPositionKey(stage))||localStorage.getItem(legacyPositionKey()))}catch{return false}}
function expandWorkspace(stage){
  if(stage.dataset.stateDiagramWorkspaceReady==="true")return;
  const original=stageSize(stage),width=Math.max(MIN_WIDTH,original.width+HORIZONTAL_MARGIN*2),height=Math.max(MIN_HEIGHT,original.height+VERTICAL_MARGIN*2);
  stage.style.width=`${Math.ceil(width)}px`;stage.style.height=`${Math.ceil(height)}px`;
  const svg=stage.querySelector(":scope > svg.edge-svg");if(svg){svg.setAttribute("width",String(Math.ceil(width)));svg.setAttribute("height",String(Math.ceil(height)))}
  Object.assign(stage.dataset,{stateDiagramWorkspaceReady:"true",stateDiagramWorkspaceOriginalWidth:String(original.width),stateDiagramWorkspaceOriginalHeight:String(original.height),stateDiagramWorkspaceWidth:String(width),stateDiagramWorkspaceHeight:String(height)});
}
function applyWorkspaceOrigin(stage){
  if(stage.dataset.stateDiagramWorkspaceOriginReady==="true")return;
  const dx=Math.max(0,Math.round((num(stage.dataset.stateDiagramWorkspaceWidth)-num(stage.dataset.stateDiagramWorkspaceOriginalWidth))/2));
  const dy=Math.max(0,Math.round((num(stage.dataset.stateDiagramWorkspaceHeight)-num(stage.dataset.stateDiagramWorkspaceOriginalHeight))/2));
  stage.querySelectorAll(".state-node").forEach(node=>{node.style.left=`${num(node.style.left)+dx}px`;node.style.top=`${num(node.style.top)+dy}px`});
  stage.querySelectorAll(".edge-label").forEach(label=>{label.style.left=`${num(label.style.left)+dx}px`;label.style.top=`${num(label.style.top)+dy}px`});
  const dot=stage.querySelector(".initial-dot");if(dot){dot.style.left=`${num(dot.style.left)+dx}px`;dot.style.top=`${num(dot.style.top)+dy}px`}
  Object.assign(stage.dataset,{stateDiagramWorkspaceOriginReady:"true",stateDiagramWorkspaceOriginX:String(dx),stateDiagramWorkspaceOriginY:String(dy)});
  if(!hasStoredPositions(stage))markPositionMigration(stage,canonicalPositionKey(stage));
}
function statePath(a,b,same,index){
  const x1=a.offsetLeft+a.offsetWidth/2,y1=a.offsetTop+a.offsetHeight/2,x2=b.offsetLeft+b.offsetWidth/2,y2=b.offsetTop+b.offsetHeight/2;
  if(same){const spread=58+index%3*14;return`M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`}
  const dx=x2-x1,dy=y2-y1,len=Math.max(1,Math.hypot(dx,dy)),ux=dx/len,uy=dy/len,rx=Math.max(1,a.offsetWidth/2),ry=Math.max(1,a.offsetHeight/2),txr=Math.max(1,b.offsetWidth/2),tyr=Math.max(1,b.offsetHeight/2);
  const sourceRadius=1/Math.sqrt((ux*ux)/(rx*rx)+(uy*uy)/(ry*ry)),targetRadius=1/Math.sqrt((ux*ux)/(txr*txr)+(uy*uy)/(tyr*tyr));
  const sx=x1+ux*Math.min(sourceRadius,len/2),sy=y1+uy*Math.min(sourceRadius,len/2),ex=x2-ux*Math.min(targetRadius,len/2),ey=y2-uy*Math.min(targetRadius,len/2),offset=(index%3-1)*22;
  return`M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${((sx+ex)/2-dy*.1+offset).toFixed(1)} ${((sy+ey)/2+dx*.1+offset).toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;
}
function updateInitialTransition(stage,machine,paths,nodes){
  stage.querySelectorAll(".state-node.initial-target").forEach(node=>node.classList.remove("initial-target"));
  const target=nodes.get(String(machine?.initial_state||"")),dot=stage.querySelector(".initial-dot"),initialPath=paths[(machine?.transitions||[]).length]||paths.find(path=>path.classList.contains("initial-transition-path"));
  if(!target||!dot||!initialPath)return false;
  target.classList.add("initial-target");initialPath.classList.add("initial-transition-path");
  const size=stageSize(stage),left=target.offsetLeft,top=target.offsetTop,right=left+target.offsetWidth,bottom=top+target.offsetHeight,cx=left+target.offsetWidth/2,cy=top+target.offsetHeight/2,spaces={top,left,right:size.width-right,bottom:size.height-bottom};
  const side=spaces.top>=72?"top":Object.entries(spaces).sort((a,b)=>b[1]-a[1])[0][0];
  let dotX=cx,dotY=top-54,startX=cx,startY=dotY+DOT_RADIUS,endX=cx,endY=top-2;
  if(side==="bottom"){dotY=bottom+54;startY=dotY-DOT_RADIUS;endY=bottom+2}else if(side==="left"){dotX=left-54;dotY=cy;startX=dotX+DOT_RADIUS;startY=cy;endX=left-2;endY=cy}else if(side==="right"){dotX=right+54;dotY=cy;startX=dotX-DOT_RADIUS;startY=cy;endX=right+2;endY=cy}
  dotX=Math.max(DOT_RADIUS+8,Math.min(size.width-DOT_RADIUS-8,dotX));dotY=Math.max(DOT_RADIUS+8,Math.min(size.height-DOT_RADIUS-8,dotY));
  if(side==="top")startY=dotY+DOT_RADIUS;else if(side==="bottom")startY=dotY-DOT_RADIUS;else if(side==="left")startX=dotX+DOT_RADIUS;else startX=dotX-DOT_RADIUS;
  initialPath.setAttribute("d",`M ${startX.toFixed(1)} ${startY.toFixed(1)} L ${endX.toFixed(1)} ${endY.toFixed(1)}`);dot.style.left=`${dotX-DOT_RADIUS}px`;dot.style.top=`${dotY-DOT_RADIUS}px`;dot.dataset.routeSide=side;initialPath.dataset.routeSide=side;
  stage.dataset.initialRouteReady="true";stage.dataset.initialRouteCertificate="ordinary-follow";return true;
}
function updateTransitionGeometry(stage,machine){
  const nodes=nodesByName(stage),paths=directPaths(stage),transitions=machine?.transitions||[];
  transitions.forEach((transition,index)=>{const source=nodes.get(String(transition.source_state||"")),target=nodes.get(String(transition.target_state||"")),path=paths[index];if(!source||!target||!path)return;path.classList.add("state-transition-path");path.dataset.transitionId=transition.id||`T${index+1}`;path.setAttribute("d",statePath(source,target,source===target,index))});
  updateInitialTransition(stage,machine,paths,nodes);window.glyphTransitionIoClusters?.reroute?.(stage);stage.dataset.stateDiagramWorkspaceGeometryReady="true";
}
function transitionSummary(transition){return String(transition?.display_label??transition?.condition??transition?.condition_raw??"otherwise").trim()||"otherwise"}
function detailSignature(machine){return[machine?.name||"",...(machine?.transitions||[]).map((transition,index)=>[transition.id||`T${index+1}`,transition.source_state||"",transition.target_state||"",transitionSummary(transition),transition.source?.line||0].join("\u001f"))].join("\u001e")}
function renderTransitionIndex(stage,machine){
  const shell=stage.closest(".canvas-shell");if(!shell)return;let panel=shell.nextElementSibling?.classList?.contains("transition-index")?shell.nextElementSibling:null;if(!panel){panel=document.createElement("section");panel.className="transition-index";shell.after(panel)}
  const signature=detailSignature(machine);if(panel.dataset.transitionIndexSignature===signature)return;
  const ja=!(window.GlyphI18n?.locale||document.documentElement.lang||"ja").startsWith("en"),transitions=machine?.transitions||[];
  panel.innerHTML=`<div class="transition-index-title"><span>${ja?"遷移の詳細":"Transition details"} · ${transitions.length}</span><span class="transition-index-note">${ja?"行を選択すると図中の遷移を強調表示する":"Select a row to highlight the transition"}</span></div><div class="transition-index-body">${transitions.map((transition,index)=>{const id=transition.id||`T${index+1}`,line=transition.source?.line||0;return`<div class="transition-detail" data-transition-id="${esc(id)}" data-line="${line}"><span class="transition-detail-id">${esc(id)}</span><span class="transition-detail-route">${esc(transition.source_state)} → ${esc(transition.target_state)}</span><span class="transition-detail-condition">${esc(transitionSummary(transition))}</span><span class="transition-detail-line">L${line||"?"}</span></div>`}).join("")||`<div class="empty">${ja?"表示できる遷移がない":"No transitions"}</div>`}</div>`;
  panel.dataset.transitionIndexSignature=signature;panel.onclick=event=>{const row=event.target?.closest?.(".transition-detail");if(!row)return;const id=row.dataset.transitionId;document.querySelectorAll(".transition-focus").forEach(item=>item.classList.remove("transition-focus"));row.classList.add("transition-focus");stage.querySelector(`path.state-transition-path[data-transition-id="${CSS.escape(id)}"]`)?.classList.add("transition-focus");stage.querySelector(`.transition-io-cluster[data-transition-id="${CSS.escape(id)}"]`)?.classList.add("transition-focus");const line=Number(row.dataset.line||0);if(line&&typeof jumpToLine==="function")jumpToLine(line)};
}
function preserveOrdinaryScale(stage){
  if(stage.dataset.stateDiagramWorkspaceViewportReady==="true")return;const shell=stage.closest(".canvas-shell"),viewport=window.glyphDiagramViewport;if(!shell||!viewport)return;const mode=viewport.mode?.()||"";if(mode&&mode!=="fit")return;
  const originalWidth=num(stage.dataset.stateDiagramWorkspaceOriginalWidth),originalHeight=num(stage.dataset.stateDiagramWorkspaceOriginalHeight),scale=Math.min(1,Math.max(.25,Math.min((shell.clientWidth-64)/Math.max(1,originalWidth),(shell.clientHeight-64)/Math.max(1,originalHeight))));viewport.setScale?.(scale);
  const x=num(stage.dataset.stateDiagramWorkspaceOriginX)+originalWidth/2,y=num(stage.dataset.stateDiagramWorkspaceOriginY)+originalHeight/2;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{const surface=stage.parentElement;shell.scrollLeft=Math.max(0,(surface?.offsetLeft||0)+x*scale-shell.clientWidth/2);shell.scrollTop=Math.max(0,(surface?.offsetTop||0)+y*scale-shell.clientHeight/2);stage.dataset.stateDiagramWorkspaceViewportReady="true"}));
}
function prepare(stage=stageOf(),machine=selectedMachine(liveState())){
  if(!stage||!machine||!stage.isConnected)return false;expandWorkspace(stage);applyWorkspaceOrigin(stage);updateTransitionGeometry(stage,machine);renderTransitionIndex(stage,machine);preserveOrdinaryScale(stage);stage.dataset.stateDiagramWorkspaceReason="transaction-prepare";return true;
}
async function refresh(reason){if(running||destroyed)return false;const stage=stageOf();if(!stage)return false;running=true;try{const machine=await readMachine();if(!machine||!stage.isConnected)return false;const result=prepare(stage,machine);stage.dataset.stateDiagramWorkspaceReason=reason;document.dispatchEvent(new CustomEvent("glyph-state-diagram-workspace-ready",{detail:{marker:MARKER,machine:machine.name,reason}}));return result}finally{running=false}}
function schedule(reason="scheduled"){if(destroyed)return;pendingReason=reason;cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>refresh(pendingReason).catch(error=>console.error("state diagram workspace refresh failed",error)))}
const view=document.getElementById("view")||document.body;
new MutationObserver(records=>{if(records.some(record=>record.type==="childList"||(record.type==="attributes"&&record.target?.classList?.contains("state-node"))))schedule("diagram-mutation")}).observe(view,{childList:true,subtree:true,attributes:true,attributeFilter:["style"]});
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule("machine-change")});document.addEventListener("pointerup",event=>{if(event.target?.closest?.(".state-node"))setTimeout(()=>schedule("node-drag-complete"),20)},true);document.addEventListener("pointercancel",()=>schedule("node-drag-cancelled"),true);document.addEventListener("glyph-transition-layout-transaction-ready",()=>schedule("layout-ready"));
for(const eventName of["pagehide","beforeunload"])window.addEventListener(eventName,()=>{destroyed=true;cancelAnimationFrame(frame)},{once:true});
window.glyphStateDiagramWorkspace={marker:MARKER,version:2,prepare,schedule,refresh:()=>schedule("api-refresh"),mapRestoredPosition,markPositionMigration,audit:()=>{const stage=stageOf(),panel=stage?.closest(".canvas-shell")?.nextElementSibling;return{ok:Boolean(stage?.dataset.stateDiagramWorkspaceGeometryReady==="true"&&panel?.classList?.contains("transition-index")),width:num(stage?.style.width),height:num(stage?.style.height),initialReady:stage?.dataset.initialRouteReady||""}}};
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
