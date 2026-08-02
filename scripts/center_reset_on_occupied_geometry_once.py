from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file_path.write_text(content.replace(old, new), encoding="utf-8")


replace_once(
    "glyph/diagram_canvas_viewport.py",
    '''function centerCoordinate(shell,surface,scale,clientX=shell.clientWidth/2,clientY=shell.clientHeight/2){
  return{
    x:(shell.scrollLeft+clientX-surface.offsetLeft)/scale,
    y:(shell.scrollTop+clientY-surface.offsetTop)/scale,
  };
}
function localPoint(shell,event){''',
    '''function centerCoordinate(shell,surface,scale,clientX=shell.clientWidth/2,clientY=shell.clientHeight/2){
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
function localPoint(shell,event){''',
)

replace_once(
    "glyph/diagram_canvas_viewport.py",
    '''function reset(shell){
  const stage=shell?.querySelector(".graph-stage");if(!stage)return;
  viewportGeneration+=1;const {surface}=setRaw(shell,stage,1);saveScale(1,"reset");sessionStorage.removeItem(panKey());
  requestAnimationFrame(()=>{
    shell.scrollLeft=Math.max(0,surface.offsetLeft-24);shell.scrollTop=Math.max(0,surface.offsetTop-24);shell.dispatchEvent(new Event("scroll"));
    document.dispatchEvent(new CustomEvent("glyph-diagram-viewport-change",{detail:{scale:1,mode:"reset",identity:diagramIdentity()}}));
  });
}''',
    '''function reset(shell){
  const stage=shell?.querySelector(".graph-stage");if(!stage)return;
  viewportGeneration+=1;const {surface,size}=setRaw(shell,stage,1),center=occupiedCenter(stage,size);saveScale(1,"reset");sessionStorage.removeItem(panKey());
  requestAnimationFrame(()=>{
    const position=()=>{
      if(!shell.isConnected||!stage.isConnected||destroyed)return;
      shell.scrollLeft=Math.max(0,surface.offsetLeft+center.x-shell.clientWidth/2);
      shell.scrollTop=Math.max(0,surface.offsetTop+center.y-shell.clientHeight/2);
    };
    position();shell.dispatchEvent(new Event("scroll"));requestAnimationFrame(position);setTimeout(()=>requestAnimationFrame(position),0);
    document.dispatchEvent(new CustomEvent("glyph-diagram-viewport-change",{detail:{scale:1,mode:"reset",identity:diagramIdentity()}}));
  });
}''',
)

replace_once(
    "tests/test_diagram_canvas_viewport.py",
    '''        self.assertIn("localPoint(shell,event)", html)
        self.assertIn("全体表示", html)
''',
    '''        self.assertIn("localPoint(shell,event)", html)
        self.assertIn("function occupiedCenter(stage,size)", html)
        self.assertIn('.state-node,.transition-io-cluster,.initial-dot', html)
        self.assertIn("surface.offsetLeft+center.x-shell.clientWidth/2", html)
        self.assertIn("surface.offsetTop+center.y-shell.clientHeight/2", html)
        self.assertNotIn("surface.offsetLeft-24", html)
        self.assertIn("全体表示", html)
''',
)

Path(__file__).unlink()
