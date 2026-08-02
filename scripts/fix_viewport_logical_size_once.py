from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWPORT = ROOT / "glyph" / "diagram_canvas_viewport.py"
TEST = ROOT / "tests" / "test_diagram_canvas_viewport.py"
SELF = Path(__file__).resolve()

source = VIEWPORT.read_text(encoding="utf-8")
old = '''function stageSize(stage){
  const styledWidth=Number.parseFloat(stage.style.width||"0")||0,styledHeight=Number.parseFloat(stage.style.height||"0")||0;
  return{width:Math.max(1,styledWidth,stage.scrollWidth),height:Math.max(1,styledHeight,stage.scrollHeight)};
}'''
new = '''function stageSize(stage){
  const styledWidth=Number.parseFloat(stage.style.width||"0")||0,styledHeight=Number.parseFloat(stage.style.height||"0")||0;
  const savedWidth=Number.parseFloat(stage.dataset.viewportLogicalWidth||"0")||0,savedHeight=Number.parseFloat(stage.dataset.viewportLogicalHeight||"0")||0;
  const scale=Math.max(.0001,scaleFor(stage)),rect=stage.getBoundingClientRect(),atUnitScale=Math.abs(scale-1)<.001;
  const width=styledWidth>0?styledWidth:Math.max(1,savedWidth,rect.width/scale,atUnitScale?stage.scrollWidth:0);
  const height=styledHeight>0?styledHeight:Math.max(1,savedHeight,rect.height/scale,atUnitScale?stage.scrollHeight:0);
  stage.dataset.viewportLogicalWidth=String(width);stage.dataset.viewportLogicalHeight=String(height);
  return{width,height};
}'''
if source.count(old) != 1:
    raise SystemExit("stageSize implementation did not match exactly")
source = source.replace(old, new)
VIEWPORT.write_text(source, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
needle = '        self.assertIn("glyph-zoom-surface", html)\n'
addition = '''        self.assertIn("viewportLogicalWidth", html)
        self.assertIn("viewportLogicalHeight", html)
        self.assertIn("styledWidth>0?styledWidth", html)
        self.assertNotIn("Math.max(1,styledWidth,stage.scrollWidth)", html)
'''
if test.count(needle) != 1:
    raise SystemExit("viewport test insertion point did not match")
test = test.replace(needle, needle + addition)
TEST.write_text(test, encoding="utf-8")
SELF.unlink()
