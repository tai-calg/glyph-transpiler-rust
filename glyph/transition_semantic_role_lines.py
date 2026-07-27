from __future__ import annotations


_MARKER = "glyph-transition-semantic-role-lines-v1"

_STYLE = r"""
<style id="glyph-transition-semantic-role-lines-v1-style">
.transition-io-cluster.semantic-role-lines .transition-io-node.io,
.transition-io-cluster.semantic-role-lines.compact-io .transition-io-node.io,
.transition-io-cluster.semantic-role-lines.micro-io .transition-io-node.io,
.transition-io-cluster.semantic-role-lines.nano-io .transition-io-node.io{
  width:var(--semantic-role-width,112px)!important;
  min-width:var(--semantic-role-width,112px)!important;
  max-width:var(--semantic-role-width,112px)!important;
}
.transition-role-line{
  display:block;
  white-space:nowrap;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:normal;
  word-break:normal;
  min-height:1.28em;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-semantic-role-lines-v1-script">
(()=>{
const MARKER="glyph-transition-semantic-role-lines-v1",MAX_LINE=28;
let timer=null;
const text=value=>String(value??"");
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

function preferredCut(value,limit){
  const bounded=Math.min(limit,value.length-1),characters=["(",")","[","]",",",".","_","&"," "];
  for(let index=bounded;index>Math.max(5,bounded-12);index-=1){if(characters.includes(value[index]))return index+1}
  for(let index=bounded+1;index<Math.min(value.length,bounded+12);index+=1){if(characters.includes(value[index]))return index+1}
  return value.length;
}

function splitExact(value,limit=MAX_LINE){
  const lines=[];
  let remaining=text(value);
  while(remaining.length>limit){
    const cut=preferredCut(remaining,limit);
    lines.push(remaining.slice(0,cut));
    remaining=remaining.slice(cut);
  }
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}

function linesFor(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue),lines=[];
  lines.push(...splitExact(input));
  if(guard)lines.push(...splitExact(` [${guard}]`));
  if(output)lines.push(...splitExact(` ➞ ${output}`));
  return lines.filter(line=>line.length>0);
}

function format(cluster){
  const value=cluster.querySelector(".transition-io-value");
  if(!value)return false;
  const signature=JSON.stringify([cluster.dataset.inputValue||"",cluster.dataset.guardValue||"",cluster.dataset.outputValue||""]);
  if(cluster.dataset.semanticRoleSignature===signature)return false;
  const lines=linesFor(cluster),expected=cluster.dataset.ioValue||value.textContent||"";
  value.replaceChildren(...lines.map(line=>{
    const span=document.createElement("span");
    span.className="transition-semantic-line transition-role-line";
    span.textContent=line;
    return span;
  }));
  if(value.textContent!==expected)throw Error(`transition label role split changed semantics: ${expected}`);
  const longest=Math.max(1,...lines.map(line=>line.length));
  cluster.style.setProperty("--semantic-role-width",`${clamp(Math.ceil(longest*5.65+18),104,360)}px`);
  cluster.dataset.semanticLineCount=String(lines.length);
  cluster.dataset.semanticLongestLine=String(longest);
  cluster.dataset.semanticRoleSignature=signature;
  cluster.classList.add("semantic-role-lines");
  return true;
}

function apply(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage||stage.dataset.transitionIoClustersReady!=="true")return;
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  const changed=clusters.reduce((count,cluster)=>count+(format(cluster)?1:0),0);
  stage.dataset.transitionSemanticRoleLinesReady="true";
  stage.dataset.transitionSemanticLinesReady="true";
  if(changed){
    stage.dataset.transitionIoCollisionSolved="semantic-role-pending";
    stage.dataset.transitionIoCollisionCount="-1";
    window.glyphTransitionIoCollisionSolver?.run();
  }
  document.dispatchEvent(new CustomEvent("glyph-transition-semantic-role-lines-ready",{detail:{marker:MARKER,labels:clusters.length,changed}}));
}

function schedule(stage=null,delay=0){
  clearTimeout(timer);
  timer=setTimeout(()=>apply(stage||document.querySelector(".state-node")?.closest(".graph-stage")),delay);
}
document.addEventListener("glyph-transition-readable-layout-ready",()=>schedule(null,0));
document.addEventListener("glyph-transition-io-clusters-ready",()=>schedule(null,0));
document.addEventListener("glyph-locale-changed",()=>schedule(null,0));
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule(null,0)});
new MutationObserver(()=>schedule(null,30)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphTransitionSemanticRoleLines={marker:MARKER,apply:()=>schedule(null,0),maxLineLength:MAX_LINE};
schedule(null,0);
})();
</script>
"""


def enhance_transition_semantic_role_lines_html(html: str) -> str:
    """Split a single transition label into readable input, guard, and output lines."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
