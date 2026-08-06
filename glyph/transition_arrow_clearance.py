from __future__ import annotations


_MARKER = "glyph-transition-arrow-clearance-v1"

_SCRIPT = r"""
<script id="glyph-transition-arrow-clearance-v1-script">
(()=>{
const MARKER="glyph-transition-arrow-clearance-v1",NODE_GAP=6,MARKER_SIZE=12,MAX_STARTUP_ATTEMPTS=4;
let frame=0,timer=0,destroyed=false,lastAudit={ready:false,paths:0,minClearance:0,reason:"bootstrap"};
const num=value=>Number.parseFloat(value||"0")||0;
const stateName=node=>node.querySelector(".state-name")?.textContent?.trim()||"";
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function selectedMachine(){
  const data=typeof snapshot==="object"&&snapshot?snapshot:null,machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===name)||machines[0]||null;
}
function directPaths(stage){return[...(stage.querySelector(":scope > svg.edge-svg")?.querySelectorAll(":scope > path")||[])]}
function nodesByName(stage){return new Map([...stage.querySelectorAll(".state-node")].map(node=>[stateName(node),node]))}
function center(node){return{x:node.offsetLeft+node.offsetWidth/2,y:node.offsetTop+node.offsetHeight/2}}
function unit(dx,dy,fallback={x:1,y:0}){const length=Math.hypot(dx,dy);return length>.0001?{x:dx/length,y:dy/length}:fallback}
function cornerRadius(node){
  const style=getComputedStyle(node),radius=num(style.borderTopLeftRadius);
  return Math.max(0,Math.min(radius,node.offsetWidth/2,node.offsetHeight/2));
}
function boundaryDistance(node,direction){
  const ux=direction.x,uy=direction.y,ax=Math.abs(ux),ay=Math.abs(uy),halfWidth=Math.max(1,node.offsetWidth/2),halfHeight=Math.max(1,node.offsetHeight/2),radius=cornerRadius(node),epsilon=.0001;
  const vertical=ax>epsilon?halfWidth/ax:Number.POSITIVE_INFINITY;
  if(Number.isFinite(vertical)&&ay*vertical<=halfHeight-radius+.01)return vertical;
  const horizontal=ay>epsilon?halfHeight/ay:Number.POSITIVE_INFINITY;
  if(Number.isFinite(horizontal)&&ax*horizontal<=halfWidth-radius+.01)return horizontal;
  if(radius<=epsilon)return Math.min(vertical,horizontal);
  const cornerX=(ux<0?-1:1)*(halfWidth-radius),cornerY=(uy<0?-1:1)*(halfHeight-radius),projection=ux*cornerX+uy*cornerY;
  const discriminant=Math.max(0,projection*projection-(cornerX*cornerX+cornerY*cornerY-radius*radius));
  return Math.max(0,projection+Math.sqrt(discriminant));
}
function anchor(node,direction,gap=NODE_GAP){
  const c=center(node),u=unit(direction.x,direction.y),distance=boundaryDistance(node,u)+gap;
  return{x:c.x+u.x*distance,y:c.y+u.y*distance,clearance:gap};
}
function curveControl(start,end,dx,dy,index){
  const offset=(index%3-1)*22;
  return{x:(start.x+end.x)/2-dy*.1+offset,y:(start.y+end.y)/2+dx*.1+offset};
}
function ordinaryPath(source,target,index){
  const sourceCenter=center(source),targetCenter=center(target),dx=targetCenter.x-sourceCenter.x,dy=targetCenter.y-sourceCenter.y,forward=unit(dx,dy);
  let start=anchor(source,forward),end=anchor(target,{x:-forward.x,y:-forward.y}),control=curveControl(start,end,dx,dy,index);
  for(let pass=0;pass<3;pass+=1){
    start=anchor(source,unit(control.x-sourceCenter.x,control.y-sourceCenter.y,forward));
    end=anchor(target,unit(control.x-targetCenter.x,control.y-targetCenter.y,{x:-forward.x,y:-forward.y}));
    control=curveControl(start,end,dx,dy,index);
  }
  return{d:`M ${start.x.toFixed(1)} ${start.y.toFixed(1)} Q ${control.x.toFixed(1)} ${control.y.toFixed(1)} ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,clearance:end.clearance};
}
function selfLoopPath(node,index){
  const c=center(node),startDirection=unit(-.55,-.835),endDirection=unit(.55,-.835),start=anchor(node,startDirection),end=anchor(node,endDirection);
  const lift=64+(index%3)*18,spread=node.offsetWidth/2+34+(index%3)*14,top=c.y-node.offsetHeight/2-lift;
  return{d:`M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${(c.x-spread).toFixed(1)} ${top.toFixed(1)}, ${(c.x+spread).toFixed(1)} ${top.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,clearance:end.clearance};
}
function configureMarker(stage){
  const marker=stage.querySelector("#state-arrow");if(!marker)return false;
  marker.setAttribute("refX","10");marker.setAttribute("refY","5");marker.setAttribute("markerUnits","userSpaceOnUse");marker.setAttribute("markerWidth",String(MARKER_SIZE));marker.setAttribute("markerHeight",String(MARKER_SIZE));marker.setAttribute("orient","auto");
  return true;
}
function applyGeometry(reason="scheduled",stage=stageOf(),machine=selectedMachine()){
  if(!stage||!machine||!stage.isConnected)return false;
  const nodes=nodesByName(stage),paths=directPaths(stage),transitions=machine.transitions||[];let updated=0,minClearance=Number.POSITIVE_INFINITY;
  configureMarker(stage);
  transitions.forEach((transition,index)=>{
    const source=nodes.get(String(transition.source_state||"")),target=nodes.get(String(transition.target_state||"")),path=paths[index];if(!source||!target||!path)return;
    const geometry=source===target?selfLoopPath(source,index):ordinaryPath(source,target,index);
    path.setAttribute("d",geometry.d);path.classList.add("state-transition-path");path.dataset.arrowNodeClearance=geometry.clearance.toFixed(1);updated+=1;minClearance=Math.min(minClearance,geometry.clearance);
  });
  if(!updated)return false;
  Object.assign(stage.dataset,{transitionArrowClearanceReady:"true",transitionArrowClearanceVersion:"1",transitionArrowClearanceMin:(Number.isFinite(minClearance)?minClearance:0).toFixed(1),transitionArrowClearancePathCount:String(updated),transitionArrowClearanceReason:reason});
  lastAudit={ready:true,paths:updated,minClearance:Number.isFinite(minClearance)?minClearance:0,reason};
  document.dispatchEvent(new CustomEvent("glyph-transition-arrow-clearance-ready",{detail:{marker:MARKER,paths:updated,minClearance:lastAudit.minClearance,reason}}));
  return true;
}
function installRerouteGuard(){
  const api=window.glyphTransitionIoClusters;if(!api||typeof api.reroute!=="function")return false;if(api.arrowClearanceWrapped===MARKER)return true;
  const original=api.reroute.bind(api);
  api.reroute=(stage=null,machine=null)=>{const resolvedStage=stage||stageOf(),resolvedMachine=machine||selectedMachine();const result=original(resolvedStage,resolvedMachine);applyGeometry("transition-io-reroute",resolvedStage,resolvedMachine);return result};
  api.arrowClearanceWrapped=MARKER;return true;
}
function refresh(reason="scheduled"){
  installRerouteGuard();
  return applyGeometry(reason);
}
function schedule(reason="scheduled",attempt=0){
  if(destroyed)return;cancelAnimationFrame(frame);clearTimeout(timer);frame=requestAnimationFrame(()=>{if(!refresh(reason)&&attempt<MAX_STARTUP_ATTEMPTS)timer=setTimeout(()=>schedule(reason,attempt+1),32)});
}
function refreshNow(reason){
  if(destroyed)return false;
  try{return refresh(reason)}catch(error){console.error("transition arrow clearance refresh failed",error);return false}
}
for(const eventName of["glyph-state-diagram-workspace-ready","glyph-transition-io-clusters-ready","glyph-transition-layout-transaction-ready"]){document.addEventListener(eventName,()=>refreshNow(eventName))}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule("machine-change")});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;cancelAnimationFrame(frame);clearTimeout(timer)},{once:true})}
window.glyphTransitionArrowClearance={marker:MARKER,version:1,refresh:()=>schedule("api-refresh"),refreshNow:()=>refreshNow("api-refresh-now"),audit:()=>({...lastAudit})};
schedule("bootstrap");
})();
</script>
"""


def enhance_transition_arrow_clearance_html(html: str) -> str:
    """Keep transition arrowheads outside the rendered state-node boundary."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_transition_arrow_clearance_html"]
