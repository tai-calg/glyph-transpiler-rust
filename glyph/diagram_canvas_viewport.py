from __future__ import annotations


_MARKER = "glyph-diagram-canvas-viewport-v1"

_STYLE = r"""
<style id="glyph-diagram-canvas-viewport-v1-style">
.diagram-viewport-tools{display:inline-flex;align-items:center;gap:4px}
.diagram-viewport-tools button{min-width:34px;padding-left:8px;padding-right:8px}
.diagram-viewport-tools .zoom-value{min-width:58px;color:var(--muted);font-variant-numeric:tabular-nums;cursor:default}
.glyph-zoom-surface{position:relative;flex:none;overflow-anchor:none}
.glyph-zoom-surface>.graph-stage{transform-origin:0 0;will-change:transform;overflow-anchor:none}
@media print{
  .glyph-zoom-surface{width:auto!important;height:auto!important}
  .glyph-zoom-surface>.graph-stage{transform:none!important}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-canvas-viewport-v1-script">
(()=>{
const MIN_SCALE=.25,MAX_SCALE=3,STEP=.1,FIT_MARGIN=32,PINCH_SPEED=.0025;
let activeShell=null,resizeTimer=null,gesture=null,viewportGeneration=0,destroyed=false;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const roundScale=value=>Math.round(clamp(value,MIN_SCALE,MAX_SCALE)*100)/100;
function locale(){return localStorage.getItem("glyph.ui.locale")==="en"?"en":"ja"}
function activeStage(){return(activeShell||document.querySelector(".canvas-shell"))?.querySelector(".graph-stage")||document.querySelector(".graph-stage")}
function diagramIdentity(){
  const tab=document.querySelector(".tab.active")?.dataset.tab||"state";
  const index=tab==="state"?document.getElementById("machine-select")?.value||0:document.getElementById("system-select")?.value||0;
  const digest=activeStage()?.dataset.diagramDigest||"source";
  return `${digest}:${tab}:${index}`;
}
function scaleKey(){return `glyph.diagram.viewport-scale.v1:${diagramIdentity()}`}
function modeKey(){return `glyph.diagram.viewport-mode.v1:${diagramIdentity()}`}
function panKey(){return `glyph.diagram.canvas-pan.v1:${diagramIdentity()}`}
function scaleFor(stage){return Number.parseFloat(stage?.dataset.viewportScale||"1")||1}
function stageSize(stage){
  const styledWidth=Number.parseFloat(stage.style.width||"0")||0,styledHeight=Number.parseFloat(stage.style.height||"0")||0;
  const savedWidth=Number.parseFloat(stage.dataset.viewportLogicalWidth||"0")||0,savedHeight=Number.parseFloat(stage.dataset.viewportLogicalHeight||"0")||0;
  const scale=Math.max(.0001,scaleFor(stage)),rect=stage.getBoundingClientRect(),atUnitScale=Math.abs(scale-1)<.001;
  const width=styledWidth>0?styledWidth:Math.max(1,savedWidth,rect.width/scale,atUnitScale?stage.scrollWidth:0);
  const height=styledHeight>0?styledHeight:Math.max(1,savedHeight,rect.height/scale,atUnitScale?stage.scrollHeight:0);
  stage.dataset.viewportLogicalWidth=String(width);stage.dataset.viewportLogicalHeight=String(height);
  return{width,height};
}
function surfaceFor(shell,stage){
  if(stage.parentElement?.classList.contains("glyph-zoom-surface"))return stage.parentElement;
  const surface=document.createElement("div");surface.className="glyph-zoom-surface";
  shell.insertBefore(surface,stage);surface.appendChild(stage);return surface;
}
function setRaw(shell,stage,scale){
  const surface=surfaceFor(shell,stage),size=stageSize(stage),next=roundScale(scale);
  stage.style.transform=`scale(${next})`;stage.dataset.viewportScale=String(next);
  surface.style.width=`${Math.ceil(size.width*next)}px`;surface.style.height=`${Math.ceil(size.height*next)}px`;
  surface.dataset.viewportScale=String(next);updateControls(next);return{surface,size,scale:next};
}
function saveScale(scale,mode="manual"){
  sessionStorage.setItem(scaleKey(),String(scale));sessionStorage.setItem(modeKey(),mode);
}
function savedMode(){return sessionStorage.getItem(modeKey())||""}
function centerCoordinate(shell,surface,scale,clientX=shell.clientWidth/2,clientY=shell.clientHeight/2){
  return{
    x:(shell.scrollLeft+clientX-surface.offsetLeft)/scale,
    y:(shell.scrollTop+clientY-surface.offsetTop)/scale,
  };
}
function occupiedCenter(stage,size){
  const items=[...stage.querySelectorAll(".state-node,.transition-io-cluster,.initial-dot")]
    .filter(item=>item.offsetWidth>0&&item.offsetHeight>0);
  if(!items.length)return{x:size.width/2,y:size.height/2};
  const boxes=items.map(item=>{
    const centered=item.classList.contains("transition-io-cluster");
    const left=item.offsetLeft-(centered?item.offsetWidth/2:0);
    const top=item.offsetTop-(centered?item.offsetHeight/2:0);
    return{left,top,right:left+item.offsetWidth,bottom:top+item.offsetHeight};
  });
  return{
    x:(Math.min(...boxes.map(item=>item.left))+Math.max(...boxes.map(item=>item.right)))/2,
    y:(Math.min(...boxes.map(item=>item.top))+Math.max(...boxes.map(item=>item.bottom)))/2,
  };
}
function localPoint(shell,event){
  const rect=shell.getBoundingClientRect();
  const rawX=Number.isFinite(event?.clientX)?event.clientX-rect.left:shell.clientWidth/2;
  const rawY=Number.isFinite(event?.clientY)?event.clientY-rect.top:shell.clientHeight/2;
  return{clientX:clamp(rawX,0,shell.clientWidth),clientY:clamp(rawY,0,shell.clientHeight)};
}
function applyScale(shell,requested,{mode="manual",clientX=shell.clientWidth/2,clientY=shell.clientHeight/2,centerDiagram=false}={}){
  const stage=shell.querySelector(".graph-stage");if(!stage||destroyed)return;
  const token=++viewportGeneration,oldScale=scaleFor(stage),oldSurface=surfaceFor(shell,stage),anchor=centerCoordinate(shell,oldSurface,oldScale,clientX,clientY);
  const {surface,size,scale}=setRaw(shell,stage,requested);saveScale(scale,mode);
  const position=()=>{
    if(token!==viewportGeneration||!shell.isConnected||!stage.isConnected||destroyed)return;
    if(centerDiagram){
      shell.scrollLeft=Math.max(0,surface.offsetLeft+size.width*scale/2-shell.clientWidth/2);
      shell.scrollTop=Math.max(0,surface.offsetTop+size.height*scale/2-shell.clientHeight/2);
    }else{
      shell.scrollLeft=Math.max(0,surface.offsetLeft+anchor.x*scale-clientX);
      shell.scrollTop=Math.max(0,surface.offsetTop+anchor.y*scale-clientY);
    }
  };
  requestAnimationFrame(()=>{
    position();shell.dispatchEvent(new Event("scroll"));
    document.dispatchEvent(new CustomEvent("glyph-diagram-viewport-change",{detail:{scale,mode,identity:diagramIdentity()}}));
    requestAnimationFrame(position);setTimeout(()=>requestAnimationFrame(position),0);
  });
}
function fit(shell,{persist=true,mode="fit"}={}){
  const stage=shell?.querySelector(".graph-stage");if(!stage||destroyed)return;
  const size=stageSize(stage),availableWidth=Math.max(80,shell.clientWidth-FIT_MARGIN*2),availableHeight=Math.max(80,shell.clientHeight-FIT_MARGIN*2);
  const scale=roundScale(Math.min(availableWidth/size.width,availableHeight/size.height));
  applyScale(shell,scale,{mode:persist?mode:savedMode()||mode,centerDiagram:true});
}
function fitInitial(shell=activeShell||document.querySelector(".canvas-shell")){
  const stage=shell?.querySelector(".graph-stage");if(!stage||stage.dataset.transitionLayoutState!=="ready")return false;
  const mode=savedMode();
  if(!mode){fit(shell,{persist:true,mode:"fit"});return true}
  if(mode==="fit"){fit(shell,{persist:true,mode:"fit"});return true}
  setRaw(shell,stage,scaleFor(stage));
  return false;
}
function reset(shell){
  const stage=shell?.querySelector(".graph-stage");if(!stage)return;
  const token=++viewportGeneration,{surface,size}=setRaw(shell,stage,1),center=occupiedCenter(stage,size);saveScale(1,"reset");sessionStorage.removeItem(panKey());
  requestAnimationFrame(()=>{
    const position=()=>{
      if(token!==viewportGeneration||!shell.isConnected||!stage.isConnected||destroyed)return;
      shell.scrollLeft=Math.max(0,surface.offsetLeft+center.x-shell.clientWidth/2);
      shell.scrollTop=Math.max(0,surface.offsetTop+center.y-shell.clientHeight/2);
    };
    if(token!==viewportGeneration)return;
    position();shell.dispatchEvent(new Event("scroll"));requestAnimationFrame(position);setTimeout(()=>requestAnimationFrame(position),0);
    document.dispatchEvent(new CustomEvent("glyph-diagram-viewport-change",{detail:{scale:1,mode:"reset",identity:diagramIdentity()}}));
  });
}
function updateControls(scale){
  const value=document.getElementById("diagram-zoom-value");if(value)value.textContent=`${Math.round(scale*100)}%`;
  const out=document.getElementById("diagram-zoom-out"),inside=document.getElementById("diagram-zoom-in");
  if(out)out.disabled=scale<=MIN_SCALE+.001;if(inside)inside.disabled=scale>=MAX_SCALE-.001;
}
function localizeControls(){
  const ja=locale()==="ja",set=(id,japanese,english)=>{const element=document.getElementById(id);if(element){element.textContent=ja?japanese:english;element.title=element.textContent;element.setAttribute("aria-label",element.textContent)}};
  set("diagram-fit", "全体表示", "Fit");set("diagram-view-reset", "表示を戻す", "Reset view");
  const out=document.getElementById("diagram-zoom-out"),inside=document.getElementById("diagram-zoom-in");
  if(out){out.title=ja?"縮小":"Zoom out";out.setAttribute("aria-label",out.title)}
  if(inside){inside.title=ja?"拡大":"Zoom in";inside.setAttribute("aria-label",inside.title)}
}
function ensureTools(){
  const tools=document.getElementById("diagram-tools");if(!tools||document.getElementById("diagram-viewport-tools"))return;
  const group=document.createElement("span");group.id="diagram-viewport-tools";group.className="diagram-viewport-tools";
  group.innerHTML='<button id="diagram-zoom-out" type="button">−</button><button id="diagram-zoom-value" class="zoom-value" type="button" tabindex="-1">100%</button><button id="diagram-zoom-in" type="button">＋</button><button id="diagram-fit" type="button"></button><button id="diagram-view-reset" type="button"></button><span class="separator"></span>';
  const themeSeparator=tools.querySelector(".separator");if(themeSeparator)themeSeparator.after(group);else tools.prepend(group);
  document.getElementById("diagram-zoom-out").onclick=()=>{const shell=activeShell||document.querySelector(".canvas-shell");const stage=shell?.querySelector(".graph-stage");if(stage)applyScale(shell,scaleFor(stage)-STEP)};
  document.getElementById("diagram-zoom-in").onclick=()=>{const shell=activeShell||document.querySelector(".canvas-shell");const stage=shell?.querySelector(".graph-stage");if(stage)applyScale(shell,scaleFor(stage)+STEP)};
  document.getElementById("diagram-fit").onclick=()=>fit(activeShell||document.querySelector(".canvas-shell"));
  document.getElementById("diagram-view-reset").onclick=()=>reset(activeShell||document.querySelector(".canvas-shell"));
  localizeControls();
}
function wheelDelta(event,shell){
  if(event.deltaMode===1)return event.deltaY*16;
  if(event.deltaMode===2)return event.deltaY*Math.max(1,shell.clientHeight);
  return event.deltaY;
}
function bindPinch(shell){
  if(shell.dataset.touchpadZoomReady==="true")return;
  shell.dataset.touchpadZoomReady="true";
  shell.addEventListener("wheel",event=>{
    if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
    const stage=shell.querySelector(".graph-stage");if(!stage)return;
    const delta=wheelDelta(event,shell);if(!Number.isFinite(delta)||Math.abs(delta)<.01)return;
    event.preventDefault();activeShell=shell;
    const point=localPoint(shell,event),current=scaleFor(stage),next=roundScale(current*Math.exp(-delta*PINCH_SPEED));
    if(next!==current)applyScale(shell,next,{mode:"manual",...point});
  },{passive:false});
  shell.addEventListener("gesturestart",event=>{
    const stage=shell.querySelector(".graph-stage");if(!stage)return;
    event.preventDefault();activeShell=shell;gesture={shell,startScale:scaleFor(stage),...localPoint(shell,event)};
  },{passive:false});
  shell.addEventListener("gesturechange",event=>{
    if(!gesture||gesture.shell!==shell)return;
    event.preventDefault();const factor=Number.parseFloat(event.scale||"1");if(!Number.isFinite(factor))return;
    applyScale(shell,gesture.startScale*factor,{mode:"manual",clientX:gesture.clientX,clientY:gesture.clientY});
  },{passive:false});
  const finishGesture=()=>{if(gesture?.shell===shell)gesture=null};
  shell.addEventListener("gestureend",finishGesture,{passive:true});shell.addEventListener("gesturecancel",finishGesture,{passive:true});
}
function bind(shell){
  const stage=shell.querySelector(".graph-stage");if(!stage)return;
  activeShell=shell;shell.style.overflowAnchor="none";
  if(shell.dataset.viewportReady!=="true"){
    shell.dataset.viewportReady="true";
    shell.addEventListener("pointerenter",()=>{activeShell=shell});
  }
  bindPinch(shell);
  const saved=Number.parseFloat(sessionStorage.getItem(scaleKey())||"1"),scale=Number.isFinite(saved)?saved:1;
  setRaw(shell,stage,scale);updateControls(scale);
  if(savedMode()==="fit")setTimeout(()=>fit(shell),0);
}
function enhance(){ensureTools();document.querySelectorAll(".canvas-shell").forEach(bind);localizeControls()}
document.addEventListener("glyph-locale-change",localizeControls);
document.addEventListener("glyph-transition-layout-transaction-ready",()=>{
  enhance();
  requestAnimationFrame(()=>fitInitial(activeShell||document.querySelector(".canvas-shell")));
});
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select"))setTimeout(enhance,0)});
document.addEventListener("keydown",event=>{
  if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
  if(event.target?.matches?.("input,textarea,select,[contenteditable=true]"))return;
  const shell=activeShell||document.querySelector(".canvas-shell"),stage=shell?.querySelector(".graph-stage");if(!stage)return;
  if(event.key==="+"||event.key==="="){event.preventDefault();applyScale(shell,scaleFor(stage)+STEP)}
  else if(event.key==="-"){event.preventDefault();applyScale(shell,scaleFor(stage)-STEP)}
  else if(event.key==="0"){event.preventDefault();reset(shell)}
});
window.addEventListener("resize",()=>{
  clearTimeout(resizeTimer);
  resizeTimer=setTimeout(()=>{
    const shell=activeShell||document.querySelector(".canvas-shell");
    if(!shell)return;
    const mode=savedMode();
    if(mode==="fit")fit(shell);
    else if(!mode)fitInitial(shell);
  },100);
});
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;clearTimeout(resizeTimer);gesture=null},{once:true})}
window.glyphDiagramViewport={
  version:2,
  scaleFor,
  fit:()=>fit(activeShell||document.querySelector(".canvas-shell")),
  fitInitial:()=>fitInitial(activeShell||document.querySelector(".canvas-shell")),
  reset:()=>reset(activeShell||document.querySelector(".canvas-shell")),
  mode:()=>savedMode(),
  setScale:value=>{const shell=activeShell||document.querySelector(".canvas-shell");if(shell)applyScale(shell,value)},
};
enhance();
})();
</script>
"""


def enhance_diagram_canvas_viewport_html(html: str) -> str:
    """Add identity-scoped zoom, automatic initial fit, reset, and pinch controls."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
