from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "glyph" / "transition_io_clusters.py"
ENABLING = ROOT / "glyph" / "transition_enabling_case_rendering.py"
TEST = ROOT / "tests" / "test_transition_io_clusters.py"
SELF = Path(__file__).resolve()

clusters = CLUSTERS.read_text(encoding="utf-8")
old = '''function arrange(stage,data,machine){
  const transitions=machine?.transitions||[],lanes=pairRanks(transitions),saved=parseSaved(data);
  transitions.forEach((transition,index)=>{
    const id=transition.id||`T${index+1}`;
    const escaped=window.CSS?.escape?CSS.escape(id):id;
    const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
    if(!cluster)return;
    const anchor=anchorFor(pathFor(stage,id,index),stage);
    placeCluster(cluster,anchor,lanes[index],saved,id,stage);
  });
  stage.dataset.transitionIoClustersReady="true";
  stage.dataset.transitionIoMaxDistance=String(MAX_DISTANCE);
}
'''
new = '''const COLLISION_GAP=4;
const COLLISION_RINGS=[0,16,32,48,64,80,96];
const COLLISION_ANGLES=24;
const COLLISION_BUDGET_MS=10;
function localRect(cluster,point){
  return{x:point.x-cluster.offsetWidth/2,y:point.y-cluster.offsetHeight/2,width:cluster.offsetWidth,height:cluster.offsetHeight};
}
function intersects(left,right,gap=COLLISION_GAP){
  return!(left.x+left.width+gap<=right.x||right.x+right.width+gap<=left.x||left.y+left.height+gap<=right.y||right.y+right.height+gap<=left.y);
}
function insideStage(rect,stage){
  const width=Math.max(stage.clientWidth,num(stage.style.width),stage.scrollWidth),height=Math.max(stage.clientHeight,num(stage.style.height),stage.scrollHeight);
  return rect.x>=8&&rect.y>=8&&rect.x+rect.width<=width-8&&rect.y+rect.height<=height-8;
}
function nodeObstacles(stage){
  return[...stage.querySelectorAll(".state-node")].map(node=>({x:node.offsetLeft,y:node.offsetTop,width:node.offsetWidth,height:node.offsetHeight}));
}
function candidatePoints(entry,stage){
  const points=[],seen=new Set(),add=point=>{
    const bounded=constrain(project(point,entry.anchor),entry.cluster,stage);
    const key=`${Math.round(bounded.x)}:${Math.round(bounded.y)}`;
    if(seen.has(key))return;
    seen.add(key);
    points.push(bounded);
  };
  add(entry.preferred);
  for(const radius of COLLISION_RINGS){
    for(let index=0;index<COLLISION_ANGLES;index+=1){
      const angle=2*Math.PI*index/COLLISION_ANGLES;
      add({x:entry.anchor.x+Math.cos(angle)*radius,y:entry.anchor.y+Math.sin(angle)*radius});
    }
  }
  return points.map(point=>({
    point,
    rect:localRect(entry.cluster,point),
    score:Math.hypot(point.x-entry.preferred.x,point.y-entry.preferred.y)+Math.hypot(point.x-entry.anchor.x,point.y-entry.anchor.y)*.04,
  })).sort((left,right)=>left.score-right.score);
}
function collisionCount(entries){
  let count=0;
  for(let index=0;index<entries.length;index+=1){
    const left=localRect(entries[index].cluster,{x:num(entries[index].cluster.style.left),y:num(entries[index].cluster.style.top)});
    for(let other=index+1;other<entries.length;other+=1){
      const right=localRect(entries[other].cluster,{x:num(entries[other].cluster.style.left),y:num(entries[other].cluster.style.top)});
      if(intersects(left,right,1))count+=1;
    }
  }
  return count;
}
function repairCollisions(stage,entries){
  const nodes=nodeObstacles(stage),fixed=[],movable=[];
  for(const entry of entries){
    const preferredRect=localRect(entry.cluster,entry.preferred);
    if(entry.manual&&insideStage(preferredRect,stage)&&!nodes.some(node=>intersects(preferredRect,node))&&!fixed.some(rect=>intersects(preferredRect,rect))){
      fixed.push(preferredRect);
      continue;
    }
    entry.options=candidatePoints(entry,stage).filter(option=>insideStage(option.rect,stage)&&!nodes.some(node=>intersects(option.rect,node)));
    movable.push(entry);
  }
  movable.sort((left,right)=>left.options.length-right.options.length||right.cluster.offsetWidth*right.cluster.offsetHeight-left.cluster.offsetWidth*left.cluster.offsetHeight||left.index-right.index);
  const assignment=new Map(),deadline=performance.now()+COLLISION_BUDGET_MS;
  function solve(index,placed){
    if(index>=movable.length)return true;
    if(performance.now()>deadline)return false;
    const entry=movable[index];
    for(const option of entry.options){
      if(placed.some(rect=>intersects(option.rect,rect)))continue;
      assignment.set(entry,option);
      placed.push(option.rect);
      if(solve(index+1,placed))return true;
      placed.pop();
      assignment.delete(entry);
    }
    return false;
  }
  let solved=movable.every(entry=>entry.options.length>0)&&solve(0,[...fixed]);
  if(!solved){
    assignment.clear();
    const placed=[...fixed];
    solved=true;
    for(const entry of movable){
      const option=entry.options.find(candidate=>!placed.some(rect=>intersects(candidate.rect,rect)));
      if(!option){solved=false;break}
      assignment.set(entry,option);
      placed.push(option.rect);
    }
  }
  if(solved){
    for(const [entry,option] of assignment){
      entry.cluster.style.left=`${option.point.x}px`;
      entry.cluster.style.top=`${option.point.y}px`;
      entry.cluster.dataset.ioDistance=String(Math.hypot(option.point.x-entry.anchor.x,option.point.y-entry.anchor.y));
    }
  }
  const count=collisionCount(entries);
  stage.dataset.transitionIoCollisionSolved=count===0?"true":"fallback";
  stage.dataset.transitionIoCollisionCount=String(count);
  stage.dataset.transitionIoCollisionBudgetMs=String(COLLISION_BUDGET_MS);
  return count===0;
}
function arrange(stage,data,machine){
  const transitions=machine?.transitions||[],lanes=pairRanks(transitions),saved=parseSaved(data),entries=[];
  transitions.forEach((transition,index)=>{
    const id=transition.id||`T${index+1}`;
    const escaped=window.CSS?.escape?CSS.escape(id):id;
    const cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);
    if(!cluster)return;
    const anchor=anchorFor(pathFor(stage,id,index),stage);
    placeCluster(cluster,anchor,lanes[index],saved,id,stage);
    entries.push({cluster,index,anchor,preferred:{x:num(cluster.style.left),y:num(cluster.style.top)},manual:cluster.dataset.manualIo==="true",options:[]});
  });
  repairCollisions(stage,entries);
  stage.dataset.transitionIoClustersReady="true";
  stage.dataset.transitionIoMaxDistance=String(MAX_DISTANCE);
}
'''
if clusters.count(old) != 1:
    raise SystemExit(f"arrange replacement count={clusters.count(old)}")
CLUSTERS.write_text(clusters.replace(old, new), encoding="utf-8")

enabling = ENABLING.read_text(encoding="utf-8")
old_event = '''    document.dispatchEvent(new CustomEvent("glyph-transition-enabling-cases-ready",{detail:{marker:MARKER,changed}}));
    return{ok:true,changed};
'''
new_event = '''    document.dispatchEvent(new CustomEvent("glyph-transition-enabling-cases-ready",{detail:{marker:MARKER,changed}}));
    if(changed>0)requestAnimationFrame(()=>window.glyphTransitionLayoutTransaction?.schedule?.("enabling-case-lines",0));
    return{ok:true,changed};
'''
if enabling.count(old_event) != 1:
    raise SystemExit(f"enabling event replacement count={enabling.count(old_event)}")
ENABLING.write_text(enabling.replace(old_event, new_event), encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
needle = '        self.assertIn("transition-semantic-line", html)\n'
addition = '''        self.assertIn("function repairCollisions(stage,entries)", html)
        self.assertIn("COLLISION_BUDGET_MS=10", html)
        self.assertIn("stage.dataset.transitionIoCollisionCount", html)
        self.assertNotIn("nano-io", html)
'''
if test.count(needle) != 1:
    raise SystemExit("collision test insertion point missing")
TEST.write_text(test.replace(needle, needle + addition), encoding="utf-8")
SELF.unlink()
