from __future__ import annotations


_MARKER = "glyph-adaptive-state-focus-v1"

_SCRIPT = r"""
<script id="glyph-adaptive-state-focus-v1-script">
(()=>{
const MARKER="glyph-adaptive-state-focus-v1";
const MIN_STAGE_WIDTH=1600,MIN_STAGE_HEIGHT=960,HORIZONTAL_PADDING=500,VERTICAL_PADDING=420;
const MIN_FOCUS_SCALE=.55,MAX_FOCUS_SCALE=.9,FOCUS_MARGIN=54;
let timer=0,running=false,destroyed=false;
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const text=value=>String(value??"").trim();
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function selectedMachine(){
  const data=typeof snapshot==="object"&&snapshot?snapshot:null;
  const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===name)||machines[0]||null;
}
function stateGeometry(stage){
  const nodes=[...stage.querySelectorAll(".state-node")];
  const centers=nodes.map(node=>({node,x:node.offsetLeft+node.offsetWidth/2,y:node.offsetTop+node.offsetHeight/2}));
  if(!centers.length)return null;
  const minX=Math.min(...centers.map(item=>item.x)),maxX=Math.max(...centers.map(item=>item.x));
  const minY=Math.min(...centers.map(item=>item.y)),maxY=Math.max(...centers.map(item=>item.y));
  return{nodes,centers,minX,maxX,minY,maxY,centerX:(minX+maxX)/2,centerY:(minY+maxY)/2,spanX:maxX-minX,spanY:maxY-minY};
}
function targetGeometry(machine,geometry){
  const transitions=machine?.transitions||[],stateCount=Math.max(1,geometry.nodes.length),selfLoops=transitions.filter(item=>item.source_state===item.target_state).length;
  const labelWeight=transitions.reduce((total,item)=>total+Math.min(180,text(item.display_label||item.condition||item.condition_raw||"otherwise").length),0)/70;
  const complexity=(transitions.length+selfLoops*1.4+labelWeight)/stateCount;
  const targetSpanX=clamp(470+transitions.length*48+selfLoops*34+labelWeight*12,620,1260);
  const targetSpanY=clamp(320+transitions.length*24+selfLoops*28+labelWeight*7,420,820);
  return{
    transitions:transitions.length,selfLoops,labelWeight,complexity,targetSpanX,targetSpanY,
    factorX:clamp(targetSpanX/Math.max(1,geometry.spanX),1,3.4),
    factorY:clamp(targetSpanY/Math.max(1,geometry.spanY),1,2.5),
  };
}
function setStageSize(stage,width,height){
  stage.style.width=`${Math.ceil(width)}px`;stage.style.height=`${Math.ceil(height)}px`;
  const svg=stage.querySelector(":scope > svg.edge-svg");
  if(svg){svg.setAttribute("width",String(Math.ceil(width)));svg.setAttribute("height",String(Math.ceil(height)))}
  stage.dataset.viewportLogicalWidth=String(Math.ceil(width));stage.dataset.viewportLogicalHeight=String(Math.ceil(height));
}
function spreadAdaptiveNodes(stage,machine){
  if(stage.dataset.adaptiveStateSpreadReady==="true")return false;
  if(stage.dataset.stateDiagramWorkspaceAdaptive!=="true"||stage.dataset.stateDiagramWorkspaceManualLayout==="true"){
    stage.dataset.adaptiveStateSpreadReady="skipped";return false;
  }
  const geometry=stateGeometry(stage);if(!geometry)return false;
  const target=targetGeometry(machine,geometry);
  const stageWidth=Math.max(MIN_STAGE_WIDTH,target.targetSpanX+HORIZONTAL_PADDING),stageHeight=Math.max(MIN_STAGE_HEIGHT,target.targetSpanY+VERTICAL_PADDING);
  const centerX=stageWidth/2,centerY=stageHeight/2;
  stage.dataset.adaptiveStateSpreadReady="true";
  geometry.centers.forEach(item=>{
    const nextX=centerX+(item.x-geometry.centerX)*target.factorX,nextY=centerY+(item.y-geometry.centerY)*target.factorY;
    item.node.style.left=`${nextX-item.node.offsetWidth/2}px`;item.node.style.top=`${nextY-item.node.offsetHeight/2}px`;
  });
  setStageSize(stage,stageWidth,stageHeight);
  Object.assign(stage.dataset,{
    adaptiveStateSpreadFactorX:target.factorX.toFixed(3),
    adaptiveStateSpreadFactorY:target.factorY.toFixed(3),
    adaptiveStateTargetSpanX:target.targetSpanX.toFixed(1),
    adaptiveStateTargetSpanY:target.targetSpanY.toFixed(1),
    adaptiveStateComplexity:target.complexity.toFixed(3),
  });
  window.glyphStateDiagramWorkspace?.prepare?.(stage,machine);
  window.glyphTransitionIoClusters?.reroute?.(stage);
  return true;
}
function elementBox(element){
  const centered=element.classList.contains("edge-label")||element.classList.contains("transition-io-cluster");
  const left=element.offsetLeft-(centered?element.offsetWidth/2:0),top=element.offsetTop-(centered?element.offsetHeight/2:0);
  return{left,top,right:left+element.offsetWidth,bottom:top+element.offsetHeight};
}
function occupiedBounds(stage){
  const items=[...stage.querySelectorAll(".state-node,.transition-io-cluster,.initial-dot")].filter(item=>item.offsetWidth>0&&item.offsetHeight>0);
  if(!items.length)return null;
  const boxes=items.map(elementBox),left=Math.min(...boxes.map(item=>item.left)),top=Math.min(...boxes.map(item=>item.top)),right=Math.max(...boxes.map(item=>item.right)),bottom=Math.max(...boxes.map(item=>item.bottom));
  return{left,top,right,bottom,width:right-left,height:bottom-top,centerX:(left+right)/2,centerY:(top+bottom)/2,count:items.length};
}
function viewportIdentity(stage){
  const tab=document.querySelector(".tab.active")?.dataset.tab||"state";
  const index=tab==="state"?document.getElementById("machine-select")?.value||0:document.getElementById("system-select")?.value||0;
  return`${stage.dataset.diagramDigest||"source"}:${tab}:${index}`;
}
function focusOccupied(stage,bounds){
  const shell=stage.closest(".canvas-shell"),surface=stage.parentElement?.classList.contains("glyph-zoom-surface")?stage.parentElement:null;
  if(!shell||!surface||!bounds)return false;
  const availableWidth=Math.max(120,shell.clientWidth-FOCUS_MARGIN*2),availableHeight=Math.max(120,shell.clientHeight-FOCUS_MARGIN*2);
  const fit=Math.min(availableWidth/Math.max(1,bounds.width),availableHeight/Math.max(1,bounds.height));
  const scale=Math.round(clamp(fit,MIN_FOCUS_SCALE,MAX_FOCUS_SCALE)*100)/100;
  const stageWidth=Math.max(1,num(stage.style.width),num(stage.dataset.viewportLogicalWidth)),stageHeight=Math.max(1,num(stage.style.height),num(stage.dataset.viewportLogicalHeight));
  stage.style.transform=`scale(${scale})`;stage.dataset.viewportScale=String(scale);
  surface.style.width=`${Math.ceil(stageWidth*scale)}px`;surface.style.height=`${Math.ceil(stageHeight*scale)}px`;surface.dataset.viewportScale=String(scale);
  const identity=viewportIdentity(stage);
  sessionStorage.setItem(`glyph.diagram.viewport-scale.v1:${identity}`,String(scale));
  sessionStorage.setItem(`glyph.diagram.viewport-mode.v1:${identity}`,"adaptive-fit");
  const zoom=document.getElementById("diagram-zoom-value");if(zoom)zoom.textContent=`${Math.round(scale*100)}%`;
  const position=()=>{
    if(destroyed||!stage.isConnected||!shell.isConnected)return;
    shell.scrollLeft=Math.max(0,surface.offsetLeft+bounds.centerX*scale-shell.clientWidth/2);
    shell.scrollTop=Math.max(0,surface.offsetTop+bounds.centerY*scale-shell.clientHeight/2);
    shell.dispatchEvent(new Event("scroll"));
  };
  position();requestAnimationFrame(()=>{position();requestAnimationFrame(position)});setTimeout(()=>requestAnimationFrame(position),24);
  Object.assign(stage.dataset,{
    adaptiveStateFocusReady:"true",adaptiveStateFocusScale:String(scale),
    adaptiveStateOccupiedLeft:bounds.left.toFixed(1),adaptiveStateOccupiedTop:bounds.top.toFixed(1),
    adaptiveStateOccupiedWidth:bounds.width.toFixed(1),adaptiveStateOccupiedHeight:bounds.height.toFixed(1),
    adaptiveStateOccupiedCount:String(bounds.count),
  });
  document.dispatchEvent(new CustomEvent("glyph-adaptive-state-focus-ready",{detail:{marker:MARKER,scale,bounds}}));
  return true;
}
function run(reason="scheduled"){
  if(running||destroyed)return false;
  const stage=stageOf(),machine=selectedMachine();
  if(!stage||!machine||stage.dataset.transitionIoClustersReady!=="true"||stage.dataset.transitionPublicationReady!=="true")return false;
  running=true;
  try{
    spreadAdaptiveNodes(stage,machine);
    window.glyphStateDiagramWorkspace?.prepare?.(stage,machine);
    const complete=()=>{
      window.glyphTransitionIoClusters?.reroute?.(stage);
      const bounds=occupiedBounds(stage);if(bounds)focusOccupied(stage,bounds);
      stage.dataset.adaptiveStateFocusReason=reason;
    };
    requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(complete,0)));
    return true;
  }finally{running=false}
}
function schedule(reason="scheduled",delay=32){
  if(destroyed)return;clearTimeout(timer);timer=setTimeout(()=>{if(!run(reason))schedule(reason,32)},Math.max(0,delay));
}
for(const event of["glyph-state-diagram-workspace-ready","glyph-transition-io-clusters-ready","glyph-transition-layout-transaction-ready","glyph-transition-enabling-cases-ready"]){document.addEventListener(event,()=>schedule(event,24))}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule("machine-change",0)});
for(const event of["pagehide","beforeunload"]){window.addEventListener(event,()=>{destroyed=true;clearTimeout(timer)},{once:true})}
window.glyphAdaptiveStateFocus={marker:MARKER,version:1,schedule,refresh:()=>schedule("api-refresh",0),audit:()=>{const stage=stageOf();return{ready:stage?.dataset.adaptiveStateFocusReady||"",scale:num(stage?.dataset.adaptiveStateFocusScale),occupiedWidth:num(stage?.dataset.adaptiveStateOccupiedWidth),occupiedHeight:num(stage?.dataset.adaptiveStateOccupiedHeight),factorX:num(stage?.dataset.adaptiveStateSpreadFactorX),factorY:num(stage?.dataset.adaptiveStateSpreadFactorY)}}};
schedule("bootstrap",0);
})();
</script>
"""


def enhance_adaptive_state_focus_html(html: str) -> str:
    """Spread dense automatic state layouts and focus their occupied geometry."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_adaptive_state_focus_html"]
