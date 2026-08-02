from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file_path.write_text(content.replace(old, new), encoding="utf-8")


replace_once(
    "glyph/transition_node_position_adapter.py",
    '''function positionIsClear(record,left,top){
  const right=left+record.node.offsetWidth,bottom=top+record.node.offsetHeight;
  return[...record.stage.querySelectorAll(".state-node")].every(other=>{
    if(other===record.node)return true;
    const otherLeft=other.offsetLeft,otherTop=other.offsetTop;
    const otherRight=otherLeft+other.offsetWidth,otherBottom=otherTop+other.offsetHeight;
    return right+NODE_CLEARANCE<=otherLeft
      || otherRight+NODE_CLEARANCE<=left
      || bottom+NODE_CLEARANCE<=otherTop
      || otherBottom+NODE_CLEARANCE<=top;
  });
}
function constrainPosition(record,left,top){
  if(positionIsClear(record,left,top))return{left,top,constrained:false};
  for(let step=23;step>=0;step-=1){
    const ratio=step/24;
    const candidateLeft=record.startLeft+(left-record.startLeft)*ratio;
    const candidateTop=record.startTop+(top-record.startTop)*ratio;
    if(positionIsClear(record,candidateLeft,candidateTop)){
      return{left:candidateLeft,top:candidateTop,constrained:true};
    }
  }
  return{left:record.startLeft,top:record.startTop,constrained:true};
}''',
    '''function clearancePenalty(record,left,top){
  const right=left+record.node.offsetWidth,bottom=top+record.node.offsetHeight;
  return[...record.stage.querySelectorAll(".state-node")].reduce((total,other)=>{
    if(other===record.node)return total;
    const otherLeft=other.offsetLeft,otherTop=other.offsetTop;
    const otherRight=otherLeft+other.offsetWidth,otherBottom=otherTop+other.offsetHeight;
    const horizontalGap=Math.max(otherLeft-right,left-otherRight,0);
    const verticalGap=Math.max(otherTop-bottom,top-otherBottom,0);
    if(horizontalGap>=NODE_CLEARANCE||verticalGap>=NODE_CLEARANCE)return total;
    return total+(NODE_CLEARANCE-horizontalGap)*(NODE_CLEARANCE-verticalGap);
  },0);
}
function positionIsClear(record,left,top){return clearancePenalty(record,left,top)===0}
function constrainPosition(record,left,top){
  const baseline=clearancePenalty(record,record.startLeft,record.startTop);
  const requested=clearancePenalty(record,left,top);
  if(requested===0||requested<=baseline)return{left,top,constrained:requested>0};
  for(let step=23;step>=0;step-=1){
    const ratio=step/24;
    const candidateLeft=record.startLeft+(left-record.startLeft)*ratio;
    const candidateTop=record.startTop+(top-record.startTop)*ratio;
    const candidatePenalty=clearancePenalty(record,candidateLeft,candidateTop);
    if(candidatePenalty<=baseline){
      return{left:candidateLeft,top:candidateTop,constrained:candidatePenalty>0};
    }
  }
  return{left:record.startLeft,top:record.startTop,constrained:true};
}''',
)

replace_once(
    "tests/test_transition_node_position_adapter.py",
    '''        self.assertIn("function positionIsClear(record,left,top)", html)
        self.assertIn("function constrainPosition(record,left,top)", html)
        self.assertIn("for(let step=23;step>=0;step-=1)", html)
''',
    '''        self.assertIn("function clearancePenalty(record,left,top)", html)
        self.assertIn("function positionIsClear(record,left,top)", html)
        self.assertIn("const baseline=clearancePenalty(record,record.startLeft,record.startTop)", html)
        self.assertIn("requested===0||requested<=baseline", html)
        self.assertIn("candidatePenalty<=baseline", html)
        self.assertIn("function constrainPosition(record,left,top)", html)
        self.assertIn("for(let step=23;step>=0;step-=1)", html)
''',
)

Path(__file__).unlink()
