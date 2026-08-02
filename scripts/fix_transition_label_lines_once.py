from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "glyph" / "transition_io_clusters.py"
TEST = ROOT / "tests" / "test_transition_io_clusters.py"
SELF = Path(__file__).resolve()

source = CLUSTERS.read_text(encoding="utf-8")

old_style = '''.transition-io-value{
  max-width:264px;
  font:700 9px/1.25 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--text);
  white-space:normal!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  text-align:center;
}
'''
new_style = '''.transition-io-value{
  max-width:264px;
  font:700 9px/1.25 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--text);
  white-space:normal!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  text-align:center;
}
.transition-io-value>.transition-semantic-line{
  display:block;
  max-width:264px;
  white-space:pre;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:normal;
  word-break:normal;
}
'''
if source.count(old_style) != 1:
    raise SystemExit("transition label style block did not match")
source = source.replace(old_style, new_style)

old_helpers = '''const esc=value=>String(value??"").replace(/[&<>\\\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\\\"':"&quot;","'":"&#39;"}[ch]));
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
'''
new_helpers = '''const esc=value=>String(value??"").replace(/[&<>\\\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\\\"':"&quot;","'":"&#39;"}[ch]));
const SEMANTIC_LINE_LIMIT=42;
function semanticCut(value,limit=SEMANTIC_LINE_LIMIT){
  if(value.length<=limit)return value.length;
  const separators=new Set([" ","&",",",".","_","(",")","[","]",";"]);
  for(let index=limit;index>=Math.max(8,limit-14);index-=1){if(separators.has(value[index]))return index+1}
  for(let index=limit+1;index<Math.min(value.length,limit+14);index+=1){if(separators.has(value[index]))return index+1}
  return value.length;
}
function splitSemantic(value){
  const lines=[];
  let remaining=String(value??"");
  while(remaining.length>SEMANTIC_LINE_LIMIT){
    const cut=semanticCut(remaining);
    if(cut>=remaining.length)break;
    lines.push(remaining.slice(0,cut));
    remaining=remaining.slice(cut);
  }
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}
function semanticLines(input,guard,action){
  const left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`.trim(),lines=[];
  if(left)lines.push(...splitSemantic(left));
  if(action)lines.push(...splitSemantic(`${left?" ":""}➞ ${action}`));
  if(!lines.length)lines.push("otherwise");
  return lines;
}
const activeTab=()=>document.querySelector(".tab.active")?.dataset.tab||"state";
'''
if source.count(old_helpers) != 1:
    raise SystemExit("transition label helper insertion point did not match")
source = source.replace(old_helpers, new_helpers)

old_markup = '''function clusterMarkup(value){
  return`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${esc(value)}</span></div></div>`;
}
'''
new_markup = '''function clusterMarkup(value,input,guard,action){
  const lines=semanticLines(input,guard,action);
  const content=lines.map(line=>`<span class="transition-semantic-line">${esc(line)}</span>`).join("");
  return`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${content}</span></div></div>`;
}
'''
if source.count(old_markup) != 1:
    raise SystemExit("clusterMarkup did not match")
source = source.replace(old_markup, new_markup)

old_update = '''function updateCluster(cluster,transition,id,line){
  const value=ioOf(transition);
  if(cluster.dataset.ioValue!==value)cluster.innerHTML=clusterMarkup(value);
  const trigger=triggerOf(transition),unknown=unknownOf(transition).length>0,semantic=semanticOf(transition);
  cluster.dataset.transitionId=id;
  cluster.dataset.line=String(line||0);
  cluster.dataset.inputValue=inputOf(transition);
  cluster.dataset.guardValue=guardsOf(transition).join(" & ");
  cluster.dataset.actionValue=actionOf(transition);
  cluster.dataset.outputValue=actionOf(transition);
  cluster.dataset.ioValue=value;
  cluster.dataset.fullLabel=value;
'''
new_update = '''function updateCluster(cluster,transition,id,line){
  const input=inputOf(transition),guard=guardsOf(transition).join(" & "),action=actionOf(transition),value=ioOf(transition);
  if(cluster.dataset.ioValue!==value)cluster.innerHTML=clusterMarkup(value,input,guard,action);
  const trigger=triggerOf(transition),unknown=unknownOf(transition).length>0,semantic=semanticOf(transition);
  const semanticLines=[...cluster.querySelectorAll(".transition-semantic-line")];
  cluster.dataset.transitionId=id;
  cluster.dataset.line=String(line||0);
  cluster.dataset.inputValue=input;
  cluster.dataset.guardValue=guard;
  cluster.dataset.actionValue=action;
  cluster.dataset.outputValue=action;
  cluster.dataset.ioValue=value;
  cluster.dataset.fullLabel=value;
  cluster.dataset.semanticLineCount=String(semanticLines.length);
  cluster.dataset.semanticLongestLine=String(Math.max(0,...semanticLines.map(item=>(item.textContent||"").length)));
'''
if source.count(old_update) != 1:
    raise SystemExit("updateCluster did not match")
source = source.replace(old_update, new_update)

old_ready = '''    stage.dataset.stateTransitionIRV2LabelsReady="true";
    document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready",{detail:{machine:machine.name,marker:MARKER}}));
'''
new_ready = '''    stage.dataset.stateTransitionIRV2LabelsReady="true";
    stage.dataset.transitionSemanticLinesReady="true";
    document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready",{detail:{machine:machine.name,marker:MARKER}}));
'''
if source.count(old_ready) != 1:
    raise SystemExit("transition semantic readiness insertion point did not match")
source = source.replace(old_ready, new_ready)
CLUSTERS.write_text(source, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
needle = '        self.assertIn(\'data-io-kind="io"\', html)\n'
addition = '''        self.assertIn("transition-semantic-line", html)
        self.assertIn("semanticLines(input,guard,action)", html)
        self.assertIn('stage.dataset.transitionSemanticLinesReady="true"', html)
        self.assertIn('`${left?" ":""}➞ ${action}`', html)
'''
if test.count(needle) != 1:
    raise SystemExit("transition I/O test insertion point did not match")
test = test.replace(needle, needle + addition)
TEST.write_text(test, encoding="utf-8")
SELF.unlink()
