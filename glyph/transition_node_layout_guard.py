from __future__ import annotations


_MARKER = "glyph-transition-node-layout-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-node-layout-guard-v1-script">
(()=>{
const MARKER="glyph-transition-node-layout-guard-v1";
let drag=null,stateCache=null,generation=0;
const num=value=>Number.parseFloat(value||"0")||0;
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";

async function diagramState(){
  if(stateCache)return stateCache;
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)throw Error("diagram state unavailable");
  return stateCache=await response.json();
}

function stateCurve(source,target,same,index){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  if(same){
    const spread=58+index%3*14;
    return`M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const startX=x1+dx/length*source.offsetWidth/2,startY=y1+dy/length*source.offsetHeight/2;
  const endX=x2-dx/length*target.offsetWidth/2,endY=y2-dy/length*target.offsetHeight/2;
  const offset=(index%3-1)*22;
  return`M ${startX} ${startY} Q ${(startX+endX)/2-dy*.1+offset} ${(startY+endY)/2+dx*.1+offset} ${endX} ${endY}`;
}

async function rerouteState(stage){
  const data=await diagramState(),machines=data.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  const machine=machines.find(item=>item.name===selected)||machines[0];
  const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nodeName(node),node]));
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")];
  const labels=[...stage.querySelectorAll(".transition-label")];
  (machine?.transitions||[]).forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    if(!source||!target)return;
    paths[index]?.setAttribute("d",stateCurve(source,target,source===target,index));
    if(labels[index]){
      labels[index].style.left=`${(source.offsetLeft+target.offsetLeft+source.offsetWidth)/2+(index%3-1)*18}px`;
      labels[index].style.top=`${(source.offsetTop+target.offsetTop+source.offsetHeight)/2-(source===target?80:0)+(index%2)*12}px`;
    }
  });
  delete stage.dataset.initialTransitionRouting;
  document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready"));
}

async function persist(stage){
  const data=await diagramState(),index=document.getElementById("machine-select")?.value||0;
  const key=`glyph.diagram.positions.v1:${data?.digest||"source"}:state:${index}`,value={};
  stage.querySelectorAll(".state-node").forEach(node=>{
    value[nodeName(node)]={x:num(node.style.left),y:num(node.style.top)};
  });
  localStorage.setItem(key,JSON.stringify(value));
}

function layoutReady(stage){
  return["true","fallback"].includes(stage.dataset.transitionIoCollisionSolved)
    && Number(stage.dataset.transitionIoCollisionCount||0)===0;
}

async function waitForResolution(stage,timeout=2600){
  const started=performance.now();
  while(performance.now()-started<timeout){
    const state=stage.dataset.transitionIoCollisionSolved;
    if(state==="true"||state==="fallback"||state==="failed")return state;
    await wait(80);
  }
  return stage.dataset.transitionIoCollisionSolved||"timeout";
}

async function requestLayout(stage){
  await rerouteState(stage);
  await wait(180);
  window.glyphTransitionIoClusters?.render();
  await wait(180);
  window.glyphTransitionIoCollisionSolver?.run();
  const state=await waitForResolution(stage);
  if(state==="failed"||state==="timeout"){
    window.glyphTransitionLabelReadability?.repair(stage);
    await wait(280);
  }
  return layoutReady(stage);
}

async function settle(record){
  const token=++generation;
  await wait(900);
  if(token!==generation||!record.node.isConnected||!record.stage.isConnected)return;
  if(layoutReady(record.stage)){await persist(record.stage);return}

  for(const ratio of[.75,.5,.25,0]){
    if(token!==generation)return;
    record.node.style.left=`${record.originalLeft+(record.draggedLeft-record.originalLeft)*ratio}px`;
    record.node.style.top=`${record.originalTop+(record.draggedTop-record.originalTop)*ratio}px`;
    if(await requestLayout(record.stage)){
      record.stage.dataset.transitionIoNodeConstraint=ratio===0?"restored":"adjusted";
      await persist(record.stage);
      return;
    }
  }

  record.node.style.left=`${record.originalLeft}px`;
  record.node.style.top=`${record.originalTop}px`;
  await requestLayout(record.stage);
  record.stage.dataset.transitionIoNodeConstraint="restored";
  await persist(record.stage);
}

document.addEventListener("pointerdown",event=>{
  const node=event.target?.closest?.(".state-node");
  if(!node||event.button!==0)return;
  generation+=1;
  drag={
    node,
    stage:node.closest(".graph-stage"),
    pointerId:event.pointerId,
    originalLeft:num(node.style.left),
    originalTop:num(node.style.top),
  };
},true);

document.addEventListener("pointerup",event=>{
  if(!drag||drag.pointerId!==event.pointerId)return;
  const record={...drag,draggedLeft:num(drag.node.style.left),draggedTop:num(drag.node.style.top)};
  drag=null;
  setTimeout(()=>settle(record).catch(error=>console.error("transition node layout settlement failed",error)),0);
},true);

document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){stateCache=null;generation+=1}
});

window.glyphTransitionNodeLayoutGuard={marker:MARKER,requestLayout};
})();
</script>
"""


def enhance_transition_node_layout_guard_html(html: str) -> str:
    """Keep node edits within the readable, collision-free transition layout domain."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
