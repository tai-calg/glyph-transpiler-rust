from __future__ import annotations


_MARKER = "glyph-state-diagram-workspace-v2"

_STYLE = r"""
<style id="glyph-state-diagram-workspace-v2-style">
.graph-stage[data-state-diagram-workspace-ready="true"]{min-width:1600px;min-height:960px}
.initial-dot{z-index:14}
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
<script id="glyph-state-diagram-workspace-v2-script">
(()=>{
const MARKER="glyph-state-diagram-workspace-v2";
const MIN_WIDTH=1600,MIN_HEIGHT=960,HORIZONTAL_MARGIN=300,VERTICAL_MARGIN=190,DOT_RADIUS=9;
const INITIAL_NODE_CLEARANCE=18,INITIAL_LABEL_CLEARANCE=12,INITIAL_EDGE_MARGIN=18;
const DRAG_FRAME_BUDGET_MS=8;
let frame=0,dragFrame=0,dragNode=null,dragActive=false,deferredFullReason="",running=false,pendingReason="bootstrap",destroyed=false;
let fullGeometryPasses=0,incidentGeometryPasses=0,maxIncidentDurationMs=0;
const incidentIndexCache=new WeakMap();
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const stateName=node=>node.querySelector(".state-name")?.textContent?.trim()||"";
const liveState=()=>typeof snapshot==="object"&&snapshot?snapshot:null;
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
async function readMachine(){const live=liveState();if(live)return selectedMachine(live);const response=await fetch("/api/state",{cache:"no-store"});return response.ok?selectedMachine(await response.json()):null}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function directPaths(stage){return[...(stage.querySelector(":scope > svg.edge-svg")?.querySelectorAll(":scope > path")||[])]}
function nodesByName(stage){return new Map([...stage.querySelectorAll(".state-node")].map(node=>[stateName(node),node]))}
function stageSize(stage){return{width:Math.max(1,num(stage.style.width),stage.scrollWidth),height:Math.max(1,num(stage.style.height),stage.scrollHeight)}}
function inlineStageSize(stage){return{width:Math.max(1,num(stage.style.width)||stage.clientWidth),height:Math.max(1,num(stage.style.height)||stage.clientHeight)}}
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
function transitionSummary(transition){return String(transition?.display_label??transition?.condition??transition?.condition_raw??"otherwise").trim()||"otherwise"}
function adaptiveLayoutMetrics(stage,machine){
  const original=inlineStageSize(stage),transitions=machine?.transitions||[],stateCount=Math.max(1,(machine?.states||[]).length||stage.querySelectorAll(".state-node").length);
  const selfLoops=transitions.filter(item=>item.source_state===item.target_state).length;
  const semanticWeight=transitions.reduce((total,item)=>total+Math.min(180,transitionSummary(item).length),0)/44;
  const complexity=(transitions.length+selfLoops*1.35+semanticWeight)/stateCount;
  const manual=hasStoredPositions(stage);
  const spreadX=manual?1:clamp(1+Math.max(0,complexity-2.4)*.72,1,3.8);
  const spreadY=manual?1:clamp(1+Math.max(0,complexity-2.8)*.24,1,2.2);
  const contentWidth=Math.ceil(original.width*spreadX),contentHeight=Math.ceil(original.height*spreadY);
  const width=Math.max(MIN_WIDTH,contentWidth+HORIZONTAL_MARGIN*2),height=Math.max(MIN_HEIGHT,contentHeight+VERTICAL_MARGIN*2);
  return{original,transitions:transitions.length,stateCount,selfLoops,semanticWeight,complexity,spreadX,spreadY,contentWidth,contentHeight,width,height,adaptive:spreadX>1.02||spreadY>1.02,manual};
}
function expandWorkspace(stage,machine){
  if(stage.dataset.stateDiagramWorkspaceReady==="true")return;
  const metrics=adaptiveLayoutMetrics(stage,machine);
  stage.style.width=`${Math.ceil(metrics.width)}px`;stage.style.height=`${Math.ceil(metrics.height)}px`;
  const svg=stage.querySelector(":scope > svg.edge-svg");if(svg){svg.setAttribute("width",String(Math.ceil(metrics.width)));svg.setAttribute("height",String(Math.ceil(metrics.height)))}
  Object.assign(stage.dataset,{
    stateDiagramWorkspaceReady:"true",
    stateDiagramWorkspaceOriginalWidth:String(metrics.original.width),
    stateDiagramWorkspaceOriginalHeight:String(metrics.original.height),
    stateDiagramWorkspaceContentWidth:String(metrics.contentWidth),
    stateDiagramWorkspaceContentHeight:String(metrics.contentHeight),
    stateDiagramWorkspaceWidth:String(metrics.width),
    stateDiagramWorkspaceHeight:String(metrics.height),
    stateDiagramWorkspaceSpreadX:metrics.spreadX.toFixed(3),
    stateDiagramWorkspaceSpreadY:metrics.spreadY.toFixed(3),
    stateDiagramWorkspaceComplexity:metrics.complexity.toFixed(3),
    stateDiagramWorkspaceAdaptive:metrics.adaptive?"true":"false",
    stateDiagramWorkspaceManualLayout:metrics.manual?"true":"false",
  });
}
function transformBox(element,centerX,centerY,originX,originY,spreadX,spreadY){
  const oldCenterX=num(element.style.left)+element.offsetWidth/2,oldCenterY=num(element.style.top)+element.offsetHeight/2;
  const nextCenterX=originX+(oldCenterX-centerX)*spreadX,nextCenterY=originY+(oldCenterY-centerY)*spreadY;
  element.style.left=`${nextCenterX-element.offsetWidth/2}px`;element.style.top=`${nextCenterY-element.offsetHeight/2}px`;
}
function transformPoint(element,centerX,centerY,originX,originY,spreadX,spreadY){
  element.style.left=`${originX+(num(element.style.left)-centerX)*spreadX}px`;element.style.top=`${originY+(num(element.style.top)-centerY)*spreadY}px`;
}
function applyWorkspaceOrigin(stage){
  if(stage.dataset.stateDiagramWorkspaceOriginReady==="true")return;
  const originalWidth=num(stage.dataset.stateDiagramWorkspaceOriginalWidth),originalHeight=num(stage.dataset.stateDiagramWorkspaceOriginalHeight),contentWidth=num(stage.dataset.stateDiagramWorkspaceContentWidth)||originalWidth,contentHeight=num(stage.dataset.stateDiagramWorkspaceContentHeight)||originalHeight;
  const spreadX=num(stage.dataset.stateDiagramWorkspaceSpreadX)||1,spreadY=num(stage.dataset.stateDiagramWorkspaceSpreadY)||1;
  const offsetX=Math.max(0,(num(stage.dataset.stateDiagramWorkspaceWidth)-contentWidth)/2),offsetY=Math.max(0,(num(stage.dataset.stateDiagramWorkspaceHeight)-contentHeight)/2);
  const originalCenterX=originalWidth/2,originalCenterY=originalHeight/2,contentCenterX=offsetX+contentWidth/2,contentCenterY=offsetY+contentHeight/2;
  stage.querySelectorAll(".state-node").forEach(node=>transformBox(node,originalCenterX,originalCenterY,contentCenterX,contentCenterY,spreadX,spreadY));
  stage.querySelectorAll(".edge-label").forEach(label=>transformPoint(label,originalCenterX,originalCenterY,contentCenterX,contentCenterY,spreadX,spreadY));
  const dot=stage.querySelector(".initial-dot");if(dot)transformBox(dot,originalCenterX,originalCenterY,contentCenterX,contentCenterY,spreadX,spreadY);
  Object.assign(stage.dataset,{stateDiagramWorkspaceOriginReady:"true",stateDiagramWorkspaceOriginX:String(offsetX),stateDiagramWorkspaceOriginY:String(offsetY)});
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
function elementRect(element,margin=0){
  const centered=element.classList.contains("edge-label")||element.classList.contains("transition-io-cluster"),left=element.offsetLeft-(centered?element.offsetWidth/2:0),top=element.offsetTop-(centered?element.offsetHeight/2:0);
  return{left:left-margin,top:top-margin,right:left+element.offsetWidth+margin,bottom:top+element.offsetHeight+margin};
}
function rectOverlap(a,b){return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top}
function pointInRect(point,rect){return point.x>=rect.left&&point.x<=rect.right&&point.y>=rect.top&&point.y<=rect.bottom}
function orientation(a,b,c){const value=(b.y-a.y)*(c.x-b.x)-(b.x-a.x)*(c.y-b.y);return Math.abs(value)<.001?0:(value>0?1:2)}
function onSegment(a,b,c){return b.x<=Math.max(a.x,c.x)+.001&&b.x+0.001>=Math.min(a.x,c.x)&&b.y<=Math.max(a.y,c.y)+.001&&b.y+0.001>=Math.min(a.y,c.y)}
function segmentsCross(a,b,c,d){const o1=orientation(a,b,c),o2=orientation(a,b,d),o3=orientation(c,d,a),o4=orientation(c,d,b);if(o1!==o2&&o3!==o4)return true;if(o1===0&&onSegment(a,c,b))return true;if(o2===0&&onSegment(a,d,b))return true;if(o3===0&&onSegment(c,a,d))return true;return o4===0&&onSegment(c,b,d)}
function segmentHitsRect(a,b,rect){
  if(pointInRect(a,rect)||pointInRect(b,rect))return true;
  const tl={x:rect.left,y:rect.top},tr={x:rect.right,y:rect.top},br={x:rect.right,y:rect.bottom},bl={x:rect.left,y:rect.bottom};
  return segmentsCross(a,b,tl,tr)||segmentsCross(a,b,tr,br)||segmentsCross(a,b,br,bl)||segmentsCross(a,b,bl,tl);
}
function routeHitsRect(points,rect){return points.slice(1).some((item,index)=>segmentHitsRect(points[index],item,rect))}
function initialPlacementCandidates(target,size){
  const left=target.offsetLeft,top=target.offsetTop,right=left+target.offsetWidth,bottom=top+target.offsetHeight,cx=left+target.offsetWidth/2,cy=top+target.offsetHeight/2;
  const sides=[
    {name:"top",out:{x:0,y:-1},tan:{x:1,y:0},port:{x:cx,y:top-2}},
    {name:"right",out:{x:1,y:0},tan:{x:0,y:1},port:{x:right+2,y:cy}},
    {name:"bottom",out:{x:0,y:1},tan:{x:1,y:0},port:{x:cx,y:bottom+2}},
    {name:"left",out:{x:-1,y:0},tan:{x:0,y:1},port:{x:left-2,y:cy}},
  ];
  const candidates=[];
  for(const side of sides){
    for(const distance of[92,124,156])for(const tangent of[0,-48,48,-96,96,-144,144]){
      const dot={x:side.port.x+side.out.x*distance+side.tan.x*tangent,y:side.port.y+side.out.y*distance+side.tan.y*tangent};
      const lane={x:side.port.x+side.out.x*34,y:side.port.y+side.out.y*34};
      const elbow=(side.name==="top"||side.name==="bottom")?{x:dot.x,y:lane.y}:{x:lane.x,y:dot.y};
      const route=[dot,elbow,lane,side.port].filter((item,index,items)=>index===0||Math.hypot(item.x-items[index-1].x,item.y-items[index-1].y)>.5);
      const dotRect={left:dot.x-DOT_RADIUS,top:dot.y-DOT_RADIUS,right:dot.x+DOT_RADIUS,bottom:dot.y+DOT_RADIUS};
      const inside=dotRect.left>=INITIAL_EDGE_MARGIN&&dotRect.top>=INITIAL_EDGE_MARGIN&&dotRect.right<=size.width-INITIAL_EDGE_MARGIN&&dotRect.bottom<=size.height-INITIAL_EDGE_MARGIN;
      candidates.push({side:side.name,dot,route,dotRect,inside,distance,tangent});
    }
  }
  return candidates;
}
function routePath(points){
  const route=points.map(item=>({x:item.x,y:item.y}));
  if(route.length>1){const dx=route[1].x-route[0].x,dy=route[1].y-route[0].y,length=Math.max(1,Math.hypot(dx,dy));route[0]={x:route[0].x+dx/length*DOT_RADIUS,y:route[0].y+dy/length*DOT_RADIUS}}
  return route.map((item,index)=>`${index?"L":"M"} ${item.x.toFixed(1)} ${item.y.toFixed(1)}`).join(" ");
}
function updateInitialTransition(stage,machine,paths,nodes){
  stage.querySelectorAll(".state-node.initial-target").forEach(node=>node.classList.remove("initial-target"));
  const transitions=machine?.transitions||[],target=nodes.get(String(machine?.initial_state||"")),dot=stage.querySelector(".initial-dot"),initialPath=paths[transitions.length]||paths.find(path=>path.classList.contains("initial-transition-path"));
  if(!target||!dot||!initialPath)return false;
  target.classList.add("initial-target");initialPath.classList.add("initial-transition-path");
  const size=stageSize(stage),nodeObstacles=[...stage.querySelectorAll(".state-node")].filter(node=>node!==target).map(node=>elementRect(node,INITIAL_NODE_CLEARANCE));
  const labelObstacles=[...stage.querySelectorAll(".edge-label.transition-label,.transition-io-cluster")].filter(item=>item.offsetWidth&&item.offsetHeight).map(item=>elementRect(item,INITIAL_LABEL_CLEARANCE));
  const obstacles=[...nodeObstacles,...labelObstacles],candidates=initialPlacementCandidates(target,size);
  let best=null;
  for(const candidate of candidates){
    if(!candidate.inside)continue;
    const dotCollisions=obstacles.filter(rect=>rectOverlap(candidate.dotRect,rect)).length;
    const routeCollisions=obstacles.filter(rect=>routeHitsRect(candidate.route,rect)).length;
    const collisionCount=dotCollisions+routeCollisions;
    const score=collisionCount*100000+candidate.distance+Math.abs(candidate.tangent)*.18+(candidate.side==="top"?0:18);
    if(!best||score<best.score)best={...candidate,score,collisionCount,dotCollisions,routeCollisions};
  }
  if(!best)return false;
  initialPath.setAttribute("d",routePath(best.route));
  dot.style.left=`${best.dot.x-DOT_RADIUS}px`;dot.style.top=`${best.dot.y-DOT_RADIUS}px`;
  dot.dataset.routeSide=best.side;initialPath.dataset.routeSide=best.side;
  Object.assign(stage.dataset,{
    initialRouteReady:"true",
    initialRouteCertificate:best.collisionCount===0?"ordinary-obstacle-free":"ordinary-degraded",
    initialRouteCandidateCount:String(candidates.length),
    initialRouteObstacleCount:String(obstacles.length),
    initialRouteCollisionCount:String(best.collisionCount),
    initialRouteDotCollisionCount:String(best.dotCollisions),
    initialRoutePathCollisionCount:String(best.routeCollisions),
  });
  return true;
}
function fastInitialPath(dot,target){
  const x1=dot.offsetLeft+dot.offsetWidth/2,y1=dot.offsetTop+dot.offsetHeight/2,x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy)),ux=dx/length,uy=dy/length;
  const rx=Math.max(1,target.offsetWidth/2),ry=Math.max(1,target.offsetHeight/2),targetRadius=1/Math.sqrt((ux*ux)/(rx*rx)+(uy*uy)/(ry*ry));
  const sx=x1+ux*Math.min(DOT_RADIUS,length/2),sy=y1+uy*Math.min(DOT_RADIUS,length/2),ex=x2-ux*Math.min(targetRadius,length/2),ey=y2-uy*Math.min(targetRadius,length/2);
  return`M ${sx.toFixed(1)} ${sy.toFixed(1)} L ${ex.toFixed(1)} ${ey.toFixed(1)}`;
}
function geometrySignature(machine){return[machine?.name||"",...(machine?.transitions||[]).map((transition,index)=>[transition.id||`T${index+1}`,transition.source_state||"",transition.target_state||""].join("\u001f"))].join("\u001e")}
function incidentIndexes(stage,machine){
  const signature=geometrySignature(machine),cached=incidentIndexCache.get(stage);
  if(cached?.signature===signature)return cached.byState;
  const byState=new Map();
  (machine?.transitions||[]).forEach((transition,index)=>{
    for(const name of new Set([String(transition.source_state||""),String(transition.target_state||"")])){
      if(!name)continue;
      if(!byState.has(name))byState.set(name,[]);
      byState.get(name).push(index);
    }
  });
  incidentIndexCache.set(stage,{signature,byState});
  return byState;
}
function updateTransitionGeometry(stage,machine){
  const nodes=nodesByName(stage),paths=directPaths(stage),transitions=machine?.transitions||[];
  transitions.forEach((transition,index)=>{const source=nodes.get(String(transition.source_state||"")),target=nodes.get(String(transition.target_state||"")),path=paths[index];if(!source||!target||!path)return;path.classList.add("state-transition-path");path.dataset.transitionId=transition.id||`T${index+1}`;path.setAttribute("d",statePath(source,target,source===target,index))});
  window.glyphTransitionIoClusters?.reroute?.(stage);
  updateInitialTransition(stage,machine,paths,nodes);
  fullGeometryPasses+=1;
  stage.dataset.stateDiagramWorkspaceFullGeometryPasses=String(fullGeometryPasses);
  stage.dataset.stateDiagramWorkspaceGeometryReady="true";
}
function updateIncidentTransitionGeometry(stage,machine,node){
  if(!stage||!machine||!node||!stage.isConnected||!node.isConnected)return false;
  const movedName=stateName(node),indexes=incidentIndexes(stage,machine).get(movedName)||[];
  if(!movedName||!indexes.length)return false;
  const started=performance.now(),nodes=nodesByName(stage),paths=directPaths(stage),transitions=machine.transitions||[];
  for(const index of indexes){
    const transition=transitions[index],source=nodes.get(String(transition?.source_state||"")),target=nodes.get(String(transition?.target_state||"")),path=paths[index];
    if(!transition||!source||!target||!path)continue;
    path.classList.add("state-transition-path");path.dataset.transitionId=transition.id||`T${index+1}`;path.setAttribute("d",statePath(source,target,source===target,index));
  }
  if(movedName===String(machine.initial_state||"")){
    const dot=stage.querySelector(".initial-dot"),initialPath=paths[transitions.length]||paths.find(path=>path.classList.contains("initial-transition-path")),target=nodes.get(movedName);
    if(dot&&initialPath&&target)initialPath.setAttribute("d",fastInitialPath(dot,target));
  }
  const duration=performance.now()-started;
  incidentGeometryPasses+=1;maxIncidentDurationMs=Math.max(maxIncidentDurationMs,duration);
  stage.dataset.stateDiagramWorkspaceIncidentGeometryPasses=String(incidentGeometryPasses);
  stage.dataset.stateDiagramWorkspaceIncidentEdgeCount=String(indexes.length);
  stage.dataset.stateDiagramWorkspaceDragDurationMs=duration.toFixed(2);
  stage.dataset.stateDiagramWorkspaceDragMaxDurationMs=maxIncidentDurationMs.toFixed(2);
  stage.dataset.stateDiagramWorkspaceDragBudgetMs=String(DRAG_FRAME_BUDGET_MS);
  stage.dataset.stateDiagramWorkspaceDragBudgetExceeded=duration>DRAG_FRAME_BUDGET_MS?"true":"false";
  return true;
}
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
  const contentWidth=num(stage.dataset.stateDiagramWorkspaceContentWidth)||num(stage.dataset.stateDiagramWorkspaceOriginalWidth),contentHeight=num(stage.dataset.stateDiagramWorkspaceContentHeight)||num(stage.dataset.stateDiagramWorkspaceOriginalHeight),scale=Math.min(1,Math.max(.25,Math.min((shell.clientWidth-64)/Math.max(1,contentWidth),(shell.clientHeight-64)/Math.max(1,contentHeight))));viewport.setScale?.(scale);
  const x=num(stage.dataset.stateDiagramWorkspaceOriginX)+contentWidth/2,y=num(stage.dataset.stateDiagramWorkspaceOriginY)+contentHeight/2;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{const surface=stage.parentElement;shell.scrollLeft=Math.max(0,(surface?.offsetLeft||0)+x*scale-shell.clientWidth/2);shell.scrollTop=Math.max(0,(surface?.offsetTop||0)+y*scale-shell.clientHeight/2);stage.dataset.stateDiagramWorkspaceViewportReady="true"}));
}
function prepare(stage=stageOf(),machine=selectedMachine(liveState())){
  if(!stage||!machine||!stage.isConnected)return false;expandWorkspace(stage,machine);applyWorkspaceOrigin(stage);updateTransitionGeometry(stage,machine);renderTransitionIndex(stage,machine);preserveOrdinaryScale(stage);stage.dataset.stateDiagramWorkspaceReason="transaction-prepare";return true;
}
async function refresh(reason){if(running||destroyed)return false;const stage=stageOf();if(!stage)return false;running=true;try{const machine=await readMachine();if(!machine||!stage.isConnected)return false;const result=prepare(stage,machine);stage.dataset.stateDiagramWorkspaceReason=reason;document.dispatchEvent(new CustomEvent("glyph-state-diagram-workspace-ready",{detail:{marker:MARKER,machine:machine.name,reason}}));return result}finally{running=false}}
function schedule(reason="scheduled"){
  if(destroyed)return;
  if(dragActive){deferredFullReason=reason;return}
  pendingReason=reason;cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>refresh(pendingReason).catch(error=>console.error("state diagram workspace refresh failed",error)));
}
function scheduleIncident(node){
  if(destroyed||!node)return;dragNode=node;cancelAnimationFrame(dragFrame);dragFrame=requestAnimationFrame(()=>{
    const current=dragNode;dragNode=null;if(!current?.isConnected)return;
    const stage=current.closest(".graph-stage"),machine=selectedMachine(liveState());
    if(stage&&machine)updateIncidentTransitionGeometry(stage,machine,current);
  });
}
function beginNodeDrag(event){
  const node=event.target?.closest?.(".state-node");if(!node)return;
  dragActive=true;deferredFullReason="";
}
function finishNodeDrag(event,cancelled=false){
  const node=event.target?.closest?.(".state-node");
  if(!dragActive&&!node)return;
  dragActive=false;cancelAnimationFrame(dragFrame);dragNode=null;
  const reason=deferredFullReason||(cancelled?"node-drag-cancelled":"node-drag-complete");deferredFullReason="";
  setTimeout(()=>schedule(reason),cancelled?0:20);
}
const view=document.getElementById("view")||document.body;
new MutationObserver(records=>{if(records.some(record=>record.type==="childList"))schedule("diagram-mutation")}).observe(view,{childList:true,subtree:true});
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule("machine-change")});
document.addEventListener("pointerdown",beginNodeDrag,true);
document.addEventListener("pointermove",event=>{const node=event.target?.closest?.(".state-node");if(node)scheduleIncident(node)},true);
document.addEventListener("pointerup",event=>finishNodeDrag(event,false),true);
document.addEventListener("pointercancel",event=>finishNodeDrag(event,true),true);
for(const eventName of["pagehide","beforeunload"])window.addEventListener(eventName,()=>{destroyed=true;cancelAnimationFrame(frame);cancelAnimationFrame(dragFrame);dragNode=null;dragActive=false;deferredFullReason=""},{once:true});
window.glyphStateDiagramWorkspace={marker:MARKER,version:4,prepare,schedule,refresh:()=>schedule("api-refresh"),updateNodeGeometry:updateIncidentTransitionGeometry,mapRestoredPosition,markPositionMigration,audit:()=>{const stage=stageOf(),panel=stage?.closest(".canvas-shell")?.nextElementSibling;return{ok:Boolean(stage?.dataset.stateDiagramWorkspaceGeometryReady==="true"&&panel?.classList?.contains("transition-index")),width:num(stage?.style.width),height:num(stage?.style.height),spreadX:num(stage?.dataset.stateDiagramWorkspaceSpreadX),spreadY:num(stage?.dataset.stateDiagramWorkspaceSpreadY),adaptive:stage?.dataset.stateDiagramWorkspaceAdaptive||"",initialReady:stage?.dataset.initialRouteReady||"",initialCollisions:num(stage?.dataset.initialRouteCollisionCount),fullGeometryPasses,incidentGeometryPasses,dragActive,dragMaxDurationMs:maxIncidentDurationMs,dragBudgetMs:DRAG_FRAME_BUDGET_MS}}};
schedule("bootstrap");
})();
</script>
"""


def enhance_state_diagram_workspace_html(html: str) -> str:
    """Provide adaptive state spacing, collision-free initial routing, and details."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )