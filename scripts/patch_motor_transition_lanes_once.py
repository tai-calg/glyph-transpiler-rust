from pathlib import Path


SOURCE = Path("glyph/transition_io_clusters.py")
TEST = Path("tests/test_transition_layout_transaction.py")

text = SOURCE.read_text(encoding="utf-8")
old_path = '''function ordinaryPath(source,target,same,index){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  if(same){
    const spread=58+index%3*14;
    return`M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const sx=x1+dx/length*(source.offsetWidth/2+1),sy=y1+dy/length*(source.offsetHeight/2);
  const tx=x2-dx/length*(target.offsetWidth/2+1),ty=y2-dy/length*(target.offsetHeight/2);
  const offset=(index%3-1)*22;
  return`M ${sx} ${sy} Q ${(sx+tx)/2-dy*.1+offset} ${(sy+ty)/2+dx*.1+offset} ${tx} ${ty}`;
}'''
new_path = '''function ordinaryPath(source,target,same,lane,stage){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  const rank=Number(lane?.rank||0),centered=Number(lane?.centered||0);
  if(same){
    const width=Math.max(stage.clientWidth,num(stage.style.width),stage.scrollWidth);
    const height=Math.max(stage.clientHeight,num(stage.style.height),stage.scrollHeight);
    let ox=x1-width/2,oy=y1-height/2,length=Math.hypot(ox,oy);
    if(length<1){ox=0;oy=-1;length=1}
    const nx=ox/length,ny=oy/length,tx=-ny,ty=nx;
    const side=rank%2===0?1:-1;
    const tangent=30+Math.floor(rank/2)*12;
    const outward=76+Math.abs(centered)*30+Math.floor(rank/2)*18;
    const sx=x1+tx*tangent*side+nx*10,sy=y1+ty*tangent*side+ny*10;
    const ex=x1-tx*tangent*side+nx*10,ey=y1-ty*tangent*side+ny*10;
    return`M ${sx} ${sy} C ${sx+nx*outward+tx*24*side} ${sy+ny*outward+ty*24*side}, ${ex+nx*outward-tx*24*side} ${ey+ny*outward-ty*24*side}, ${ex} ${ey}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const ux=dx/length,uy=dy/length,nx=-uy,ny=ux;
  const sourceRadius=Math.min(source.offsetWidth,source.offsetHeight)/2+1;
  const targetRadius=Math.min(target.offsetWidth,target.offsetHeight)/2+1;
  const sx=x1+ux*sourceRadius,sy=y1+uy*sourceRadius;
  const ex=x2-ux*targetRadius,ey=y2-uy*targetRadius;
  const directionalOffset=48,laneGap=28;
  const curvature=directionalOffset+centered*laneGap;
  return`M ${sx} ${sy} Q ${(sx+ex)/2+nx*curvature} ${(sy+ey)/2+ny*curvature} ${ex} ${ey}`;
}'''
if text.count(old_path) != 1:
    raise SystemExit("ordinaryPath block did not match exactly")
text = text.replace(old_path, new_path)
old_reroute = '''  const transitions=selected.transitions||[],nodes=nodeMap(stage);
  tagBaseGeometry(stage,transitions);
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    const path=pathFor(stage,transition.id||`T${index+1}`,index);
    if(source&&target&&path)path.setAttribute("d",ordinaryPath(source,target,source===target,index));
  });'''
new_reroute = '''  const transitions=selected.transitions||[],nodes=nodeMap(stage),lanes=pairRanks(transitions);
  tagBaseGeometry(stage,transitions);
  transitions.forEach((transition,index)=>{
    const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
    const path=pathFor(stage,transition.id||`T${index+1}`,index);
    if(source&&target&&path)path.setAttribute("d",ordinaryPath(source,target,source===target,lanes[index],stage));
  });'''
if text.count(old_reroute) != 1:
    raise SystemExit("reroute block did not match exactly")
SOURCE.write_text(text.replace(old_reroute, new_reroute), encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
needle = '        "function ordinaryPath(",\n'
replacement = (
    needle
    + '        "directionalOffset=48",\n'
    + '        "laneGap=28",\n'
    + '        "ordinaryPath(source,target,source===target,lanes[index],stage)",\n'
)
if test.count(needle) != 1:
    raise SystemExit("test insertion point did not match exactly")
TEST.write_text(test.replace(needle, replacement), encoding="utf-8")

Path(__file__).unlink()
