from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-v1"

_STYLE = r"""
<style id="glyph-transition-layout-transaction-v1-style">
.transition-io-cluster.transaction-readable-label{
  max-width:none!important;
}
.transition-io-cluster.transaction-readable-label .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.compact-io .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.micro-io .transition-io-node.io,
.transition-io-cluster.transaction-readable-label.nano-io .transition-io-node.io{
  width:var(--transaction-label-width,120px)!important;
  min-width:var(--transaction-label-width,120px)!important;
  max-width:var(--transaction-label-width,120px)!important;
  min-height:28px!important;
  padding:4px 7px!important;
  overflow:visible!important;
}
.transition-io-cluster.transaction-readable-label .transition-io-value{
  display:block!important;
  max-width:100%!important;
  font-size:9px!important;
  line-height:1.28!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:normal!important;
  word-break:normal!important;
  text-align:center!important;
}
.transition-transaction-line{
  display:block;
  min-height:1.28em;
  white-space:nowrap;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:normal;
  word-break:normal;
}
.graph-stage[data-transition-layout-state="pending"] .transition-io-cluster{
  pointer-events:none;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-v1";
const MAX_DISTANCE=96,GAP=4,DENSE_TRANSITIONS=7,MIN_WIDTH=1400,MIN_HEIGHT=1000;
const RINGS=[0,12,24,36,48,60,72,84,96],ANGLES=72,OPTION_LIMIT=144,SEARCH_MS=1800;
const control=window.glyphTransitionLegacyControl;
if(control)control.ownsScheduling=true;

let stateCache=null,requestedGeneration=0,completedGeneration=0,running=false,timer=null,lastStage=null;
const num=value=>Number.parseFloat(value||"0")||0;
const finite=value=>Number.isFinite(value);
const text=value=>String(value??"");
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";

async function diagramState(){
  if(stateCache)return stateCache;
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)throw Error("diagram state unavailable");
  return stateCache=await response.json();
}
function selectedMachine(data){
  const machines=data?.views?.state?.machines||[];
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
  return machines.find(machine=>machine.name===selected)||machines[0]||null;
}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function machineIndex(){return document.getElementById("machine-select")?.value||0}
function nodeStorageKey(data){return`glyph.diagram.positions.v1:${data?.digest||"source"}:state:${machineIndex()}`}
function labelStorageKey(data){return`glyph.diagram.transition-io.v1:${data?.digest||"source"}:${machineIndex()}`}
function parseStored(key){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
function writeStored(key,value){localStorage.setItem(key,JSON.stringify(value))}
function cancelled(token){return token!==requestedGeneration}

function markPending(stage,token,reason){
  stage.dataset.transitionLayoutState="pending";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  stage.dataset.transitionIoCollisionSolved="transaction-pending";
  stage.dataset.transitionIoCollisionCount="-1";
  stage.dataset.transitionSemanticLinesReady="pending";
  stage.dataset.transitionSemanticRoleLinesReady="pending";
}

function ensureCanvas(stage,transitionCount){
  const nodes=[...stage.querySelectorAll(".state-node")];
  const requiredWidth=Math.max(...nodes.map(node=>node.offsetLeft+node.offsetWidth+180),0);
  const requiredHeight=Math.max(...nodes.map(node=>node.offsetTop+node.offsetHeight+180),0);
  const dense=transitionCount>=DENSE_TRANSITIONS;
  const width=Math.max(stage.scrollWidth,requiredWidth,dense?MIN_WIDTH:0);
  const height=Math.max(stage.scrollHeight,requiredHeight,dense?MIN_HEIGHT:0);
  stage.style.width=`${Math.ceil(width)}px`;
  stage.style.height=`${Math.ceil(height)}px`;
  stage.dataset.transitionDenseCanvas=dense?`${Math.ceil(width)}x${Math.ceil(height)}`:"not-required";
  return dense;
}

function arrangeInitialDenseNodes(stage,data,machine,dense){
  if(!dense)return false;
  const saved=parseStored(nodeStorageKey(data));
  if(Object.keys(saved).length){
    stage.dataset.semanticDenseLayout=`saved:${machine?.name||"machine"}`;
    return false;
  }
  const nodes=[...stage.querySelectorAll(".state-node")];
  if(nodes.length<2)return false;
  const signature=`${machine?.name||"machine"}:${nodes.length}:${machine?.transitions?.length||0}`;
  if(stage.dataset.semanticDenseLayout===signature)return false;
  const width=Math.max(MIN_WIDTH,stage.scrollWidth),height=Math.max(MIN_HEIGHT,stage.scrollHeight);
  const centerX=width/2,centerY=height/2;
  const radiusX=Math.max(420,Math.min(520,width*.36)),radiusY=Math.max(300,Math.min(380,height*.34));
  nodes.forEach((node,index)=>{
    const angle=-Math.PI/2+index*2*Math.PI/nodes.length;
    node.style.left=`${Math.round(centerX+Math.cos(angle)*radiusX-node.offsetWidth/2)}px`;
    node.style.top=`${Math.round(centerY+Math.sin(angle)*radiusY-node.offsetHeight/2)}px`;
  });
  stage.dataset.semanticDenseLayout=signature;
  return true;
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
function reroute(stage,machine){
  const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nodeName(node),node]));
  const paths=[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")];
  const labels=[...stage.querySelectorAll(".transition-label")];
  (machine?.transitions||[]).forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    if(!source||!target)return;
    const path=paths[index];
    path?.setAttribute("d",stateCurve(source,target,source===target,index));
    if(path&&!path.dataset.transitionId&&transition.id)path.dataset.transitionId=transition.id;
    if(labels[index]){
      labels[index].style.left=`${(source.offsetLeft+target.offsetLeft+source.offsetWidth)/2+(index%3-1)*18}px`;
      labels[index].style.top=`${(source.offsetTop+target.offsetTop+source.offsetHeight)/2-(source===target?80:0)+(index%2)*12}px`;
    }
  });
  delete stage.dataset.initialTransitionRouting;
}

async function ensureClusters(stage,machine,token){
  const expected=machine?.transitions?.length||0;
  for(let attempt=0;attempt<8;attempt+=1){
    if(cancelled(token))return false;
    const count=stage.querySelectorAll(".transition-io-cluster").length;
    if(count===expected&&expected>0)return true;
    window.glyphTransitionIoClusters?.render();
    await wait(80);
  }
  return stage.querySelectorAll(".transition-io-cluster").length===expected;
}

function safeCuts(value){
  const result=[];
  for(let index=1;index<value.length;index+=1){
    const before=value[index-1],after=value[index];
    if(before===" "||before===","||before===")"||before==="]"||before==="&"||after===" ")result.push(index);
  }
  return result;
}
function splitComponent(value,limit=42){
  const lines=[];
  let remaining=text(value);
  while(remaining.length>limit){
    const cuts=safeCuts(remaining).filter(index=>index>=Math.max(8,limit-16)&&index<=limit+16);
    if(!cuts.length)break;
    const cut=cuts.sort((left,right)=>Math.abs(left-limit)-Math.abs(right-limit))[0];
    lines.push(remaining.slice(0,cut));
    remaining=remaining.slice(cut);
  }
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}
function semanticLines(cluster){
  const value=cluster.querySelector(".transition-io-value"),count=Number(cluster.dataset.enablingCaseCount||"1");
  if(count>1){
    const cases=[...(value?.querySelectorAll(".enabling-case-line")||[])].map(element=>text(element.textContent)).filter(Boolean);
    if(cases.length)return cases;
    return text(cluster.dataset.ioValue).split(" || ").map(item=>item.trim()).filter(Boolean);
  }
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue),lines=[];
  if(input)lines.push(...splitComponent(input));
  if(guard)lines.push(...splitComponent(`${input?" ":""}[${guard}]`));
  if(output)lines.push(...splitComponent(`${input||guard?" ":""}➞ ${output}`));
  return lines.filter(line=>line.length>0);
}

function canonicalLabel(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue);
  const left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`.trim();
  return`${left}${output?`${left?" ":""}➞ ${output}`:""}`.trim();
}
function formatLabels(stage){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  for(const cluster of clusters){
    const value=cluster.querySelector(".transition-io-value");
    if(!value)continue;
    const expected=cluster.dataset.ioValue||value.textContent||"";
    const lines=semanticLines(cluster),multiple=Number(cluster.dataset.enablingCaseCount||"1")>1;
    value.replaceChildren(...lines.map(line=>{
      const span=document.createElement("span");
      span.className=`transition-semantic-line transition-role-line transition-transaction-line${multiple?" enabling-case-line":""}`;
      span.textContent=line;
      return span;
    }));
    const actual=multiple?lines.join(" || "):canonicalLabel(cluster);
    if(actual!==expected)throw Error(`transition label formatting changed structured semantics: ${expected}`);
    const longest=Math.max(1,...lines.map(line=>line.length));
    const width=clamp(Math.ceil(longest*5.8+22),108,640);
    cluster.style.setProperty("--transaction-label-width",`${width}px`);
    cluster.style.setProperty("--semantic-label-width",`${width}px`);
    cluster.style.setProperty("--semantic-role-width",`${width}px`);
    cluster.classList.add("transaction-readable-label","semantic-readable-label","semantic-role-lines");
    cluster.classList.remove("compact-io","micro-io","nano-io","stacked");
    cluster.dataset.semanticLineCount=String(lines.length);
    cluster.dataset.semanticLongestLine=String(longest);
    cluster.dataset.semanticLineFallback="";
  }
  stage.dataset.transitionSemanticLinesReady="formatted";
  stage.dataset.transitionSemanticRoleLinesReady="formatted";
}

function pathFor(stage,id,index){
  const escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&");
  return stage.querySelector(`path.state-transition-path[data-transition-id="${escaped}"]`)
    ||[...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")][index]
    ||null;
}
function anchorFor(stage,id,index){
  const path=pathFor(stage,id,index);
  if(path&&typeof path.getTotalLength==="function"){
    try{
      const length=path.getTotalLength(),mid=path.getPointAtLength(length/2);
      const before=path.getPointAtLength(Math.max(0,length/2-2)),after=path.getPointAtLength(Math.min(length,length/2+2));
      return{x:mid.x,y:mid.y,normal:Math.atan2(after.x-before.x,-(after.y-before.y))};
    }catch{}
  }
  return{x:stage.clientWidth/2,y:stage.clientHeight/2,normal:-Math.PI/2};
}
function project(point,anchor){
  const dx=point.x-anchor.x,dy=point.y-anchor.y,distance=Math.hypot(dx,dy);
  if(!distance||distance<=MAX_DISTANCE)return point;
  const ratio=MAX_DISTANCE/distance;
  return{x:anchor.x+dx*ratio,y:anchor.y+dy*ratio};
}
function constrain(point,cluster,stage){
  return{
    x:clamp(point.x,cluster.offsetWidth/2+8,stage.scrollWidth-cluster.offsetWidth/2-8),
    y:clamp(point.y,cluster.offsetHeight/2+8,stage.scrollHeight-cluster.offsetHeight/2-8),
  };
}
function rectAt(cluster,point){return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight}}
function nodeRect(node){return{x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}}
function intersects(left,right,gap=GAP){return!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y)}
function inside(rect,stage){return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=stage.scrollWidth-8&&rect.y+rect.height<=stage.scrollHeight-8}
function candidatePoints(anchor,preferred){
  const result=[],seen=new Set();
  const add=raw=>{
    const point=project(raw,anchor),key=`${Math.round(point.x*10)}:${Math.round(point.y*10)}`;
    if(!seen.has(key)){seen.add(key);result.push(point)}
  };
  add(preferred);
  for(const radius of RINGS){
    for(let index=0;index<ANGLES;index+=1){
      const angle=anchor.normal+index*2*Math.PI/ANGLES;
      add({x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius});
    }
  }
  return result;
}
function optionsFor(entry,stage,nodes){
  const values=[],seen=new Set();
  for(const raw of candidatePoints(entry.anchor,entry.preferred)){
    const point=constrain(raw,entry.cluster,stage),rect=rectAt(entry.cluster,point);
    if(!inside(rect,stage)||nodes.some(node=>intersects(rect,node)))continue;
    const key=`${Math.round(point.x*10)}:${Math.round(point.y*10)}`;
    if(seen.has(key))continue;
    seen.add(key);
    const distance=Math.hypot(point.x-entry.preferred.x,point.y-entry.preferred.y);
    const anchorDistance=Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y);
    values.push({point,rect,score:distance+anchorDistance*.02});
  }
  values.sort((left,right)=>left.score-right.score);
  return values.slice(0,OPTION_LIMIT);
}
function solveEntries(entries,deadline){
  const ordered=[...entries].sort((left,right)=>Number(right.manual)-Number(left.manual)||left.options.length-right.options.length||left.index-right.index);
  const assignment=new Map(),placed=[];
  function visit(index){
    if(index>=ordered.length)return true;
    if(performance.now()>deadline)return false;
    const entry=ordered[index];
    for(const option of entry.options){
      if(placed.some(rect=>intersects(option.rect,rect)))continue;
      assignment.set(entry.cluster,option);placed.push(option.rect);
      if(visit(index+1))return true;
      placed.pop();assignment.delete(entry.cluster);
    }
    return false;
  }
  return visit(0)?assignment:null;
}
function greedyEntries(entries){
  const assignment=new Map(),placed=[];
  const ordered=[...entries].sort((left,right)=>Number(right.manual)-Number(left.manual)||left.options.length-right.options.length||left.index-right.index);
  for(const entry of ordered){
    const option=entry.options.find(candidate=>!placed.some(rect=>intersects(candidate.rect,rect)));
    if(!option)return null;
    assignment.set(entry.cluster,option);placed.push(option.rect);
  }
  return assignment;
}
function layoutEntries(stage,data){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")],nodes=[...stage.querySelectorAll(".state-node")].map(nodeRect);
  const saved=parseStored(labelStorageKey(data));
  return clusters.map((cluster,index)=>{
    const id=cluster.dataset.transitionId||`T${index+1}`,anchor=anchorFor(stage,id,index),record=saved[id];
    const manual=Boolean(record);
    const restored=finite(record?.dx)&&finite(record?.dy)
      ?{x:anchor.x+record.dx,y:anchor.y+record.dy}
      :finite(record?.x)&&finite(record?.y)?{x:record.x,y:record.y}
      :{x:num(cluster.style.left)||anchor.x,y:num(cluster.style.top)||anchor.y};
    const entry={cluster,index,id,anchor,manual,preferred:project(restored,anchor),options:[]};
    entry.options=optionsFor(entry,stage,nodes);
    return entry;
  });
}
function applyAssignment(stage,data,entries,assignment){
  const saved=parseStored(labelStorageKey(data));
  for(const entry of entries){
    const option=assignment.get(entry.cluster);
    if(!option)throw Error(`missing transition placement: ${entry.id}`);
    const point=option.point;
    entry.cluster.style.left=`${point.x}px`;
    entry.cluster.style.top=`${point.y}px`;
    entry.cluster.dataset.anchorX=String(entry.anchor.x);
    entry.cluster.dataset.anchorY=String(entry.anchor.y);
    entry.cluster.dataset.ioDistance=String(Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y));
    entry.cluster.dataset.maxIoDistance=String(MAX_DISTANCE);
    entry.cluster.dataset.manualIo=entry.manual?"true":"false";
    entry.cluster.dataset.ioCollisionSolved="true";
    entry.cluster.classList.remove("layout-constrained","compact-io","micro-io","nano-io","stacked");
    if(entry.manual)saved[entry.id]={x:point.x,y:point.y,dx:point.x-entry.anchor.x,dy:point.y-entry.anchor.y};
  }
  writeStored(labelStorageKey(data),saved);
  stage.dataset.transitionIoCollisionSolved="true";
  stage.dataset.transitionIoCollisionCount="0";
}

function audit(stage){
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")],nodes=[...stage.querySelectorAll(".state-node")].map(nodeRect),violations=[];
  const rects=clusters.map(cluster=>rectAt(cluster,{x:num(cluster.style.left),y:num(cluster.style.top)}));
  clusters.forEach((cluster,index)=>{
    const value=cluster.querySelector(".transition-io-value"),node=cluster.querySelector(".transition-io-node.io"),style=value?getComputedStyle(value):null;
    const expected=cluster.dataset.ioValue||"",multiple=Number(cluster.dataset.enablingCaseCount||"1")>1;
    const actual=multiple?[...value.querySelectorAll(".enabling-case-line")].map(element=>text(element.textContent)).filter(Boolean).join(" || "):canonicalLabel(cluster),rect=rects[index];
    const reasons=[];
    if(actual!==expected)reasons.push("text-mismatch");
    if((Number.parseFloat(style?.fontSize||"0")||0)<9)reasons.push("font-too-small");
    if(style?.textOverflow==="ellipsis")reasons.push("ellipsis");
    if(value&&value.scrollWidth>value.clientWidth+1.5)reasons.push("horizontal-clipping");
    if(value&&value.scrollHeight>value.clientHeight+1.5)reasons.push("vertical-clipping");
    if(node&&value){
      const nodeBox=node.getBoundingClientRect(),valueBox=value.getBoundingClientRect();
      if(valueBox.left<nodeBox.left-1.5||valueBox.right>nodeBox.right+1.5||valueBox.top<nodeBox.top-1.5||valueBox.bottom>nodeBox.bottom+1.5)reasons.push("outside-label-box");
    }
    if(!inside(rect,stage))reasons.push("outside-stage");
    if(nodes.some(item=>intersects(rect,item,1)))reasons.push("node-collision");
    for(let other=0;other<index;other+=1){if(intersects(rect,rects[other],1))reasons.push(`label-collision:${other}`)}
    if(num(cluster.dataset.ioDistance)>MAX_DISTANCE+.5)reasons.push("tether-distance");
    cluster.dataset.transitionReadability=reasons.length?"failed":"true";
    if(reasons.length)violations.push({id:cluster.dataset.transitionId||String(index),reasons});
  });
  return{ok:clusters.length>0&&violations.length===0,count:clusters.length,violations};
}

async function transaction(token,reason){
  const stage=stageOf();
  if(!stage||stage.dataset.stateTransitionIRV3LabelsReady!=="true"||stage.dataset.editorReady!=="true")return false;
  const data=await diagramState(),machine=selectedMachine(data);
  if(!machine||cancelled(token))return false;
  markPending(stage,token,reason);
  const dense=ensureCanvas(stage,machine.transitions?.length||0);
  arrangeInitialDenseNodes(stage,data,machine,dense);
  reroute(stage,machine);
  await nextFrame();
  if(cancelled(token))return false;
  if(!await ensureClusters(stage,machine,token))throw Error("transition clusters were not created");
  ensureCanvas(stage,machine.transitions?.length||0);
  reroute(stage,machine);
  formatLabels(stage);
  await nextFrame();
  if(cancelled(token))return false;
  reroute(stage,machine);
  await nextFrame();
  const entries=layoutEntries(stage,data);
  if(entries.some(entry=>!entry.options.length))throw Error("no valid position exists inside the transition tether");
  const assignment=solveEntries(entries,performance.now()+SEARCH_MS)||greedyEntries(entries);
  if(!assignment)throw Error("no collision-free transition label assignment exists");
  applyAssignment(stage,data,entries,assignment);
  await nextFrame();
  if(cancelled(token))return false;
  const result=audit(stage);
  if(!result.ok)throw Error(`transition layout audit failed: ${JSON.stringify(result.violations)}`);
  stage.dataset.transitionIoReadability="true";
  stage.dataset.transitionIoReadabilityViolations="0";
  stage.dataset.transitionSemanticLinesReady="true";
  stage.dataset.transitionSemanticRoleLinesReady="true";
  stage.dataset.transitionLayoutState="ready";
  stage.dataset.transitionLayoutGeneration=String(token);
  stage.dataset.transitionLayoutReason=reason;
  completedGeneration=token;
  document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready",{detail:{marker:MARKER,generation:token,reason,labels:result.count}}));
  return true;
}

async function drain(){
  if(running)return;
  running=true;
  try{
    while(completedGeneration<requestedGeneration){
      const token=requestedGeneration,reason=window.glyphTransitionLayoutTransaction?.lastReason||"scheduled";
      try{
        const completed=await transaction(token,reason);
        if(!completed&&token===requestedGeneration){await wait(60)}
      }catch(error){
        const stage=stageOf();
        if(token===requestedGeneration&&stage){
          stage.dataset.transitionLayoutState="failed";
          stage.dataset.transitionLayoutError=String(error?.message||error);
          stage.dataset.transitionIoCollisionSolved="failed";
        }
        console.error("transition layout transaction failed",error);
        completedGeneration=token;
      }
      if(token===requestedGeneration&&completedGeneration<token)completedGeneration=token;
    }
  }finally{running=false}
}
function schedule(reason="scheduled",delay=0){
  requestedGeneration+=1;
  if(window.glyphTransitionLayoutTransaction)window.glyphTransitionLayoutTransaction.lastReason=reason;
  clearTimeout(timer);
  timer=setTimeout(()=>drain(),delay);
  return requestedGeneration;
}

for(const eventName of["glyph-state-transition-ir-v3-labels-ready","glyph-transition-enabling-cases-ready","glyph-uml-transition-ready","glyph-locale-changed"]){
  document.addEventListener(eventName,()=>{stateCache=null;schedule(eventName,0)});
}
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select"){stateCache=null;schedule("machine-change",0)}
});
document.addEventListener("pointerup",event=>{
  if(event.target?.closest?.(".state-node,.transition-io-cluster"))schedule("manual-edit",20);
},true);
const view=document.getElementById("view")||document.body;
new MutationObserver(()=>{
  const stage=stageOf();
  if(stage!==lastStage){lastStage=stage;stateCache=null;schedule("stage-replaced",0)}
}).observe(view,{childList:true,subtree:true});

window.glyphTransitionLayoutTransaction={
  marker:MARKER,
  ownsScheduling:true,
  schedule,
  run:()=>schedule("manual-run",0),
  audit:()=>audit(stageOf()),
  get generation(){return requestedGeneration},
  get completedGeneration(){return completedGeneration},
  lastReason:"bootstrap",
};
lastStage=stageOf();
schedule("bootstrap",0);
})();
</script>
"""


def enhance_transition_layout_transaction_html(html: str) -> str:
    """Own transition restoration, formatting, placement, persistence, and readiness."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
