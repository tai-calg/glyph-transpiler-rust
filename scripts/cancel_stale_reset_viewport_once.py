from pathlib import Path

path = Path("glyph/diagram_canvas_viewport.py")
content = path.read_text(encoding="utf-8")
old = '''function reset(shell){
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
}'''
new = '''function reset(shell){
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
}'''
if content.count(old) != 1:
    raise SystemExit(f"expected one reset function, found {content.count(old)}")
path.write_text(content.replace(old, new), encoding="utf-8")

unit = Path("tests/test_diagram_canvas_viewport.py")
text = unit.read_text(encoding="utf-8")
anchor = '        self.assertIn("surface.offsetTop+center.y-shell.clientHeight/2", html)\n'
addition = anchor + '        self.assertIn("const token=++viewportGeneration", html)\n        self.assertIn("token!==viewportGeneration", html)\n'
if text.count(anchor) != 1:
    raise SystemExit("unit-test anchor missing")
unit.write_text(text.replace(anchor, addition), encoding="utf-8")

Path(__file__).unlink()
