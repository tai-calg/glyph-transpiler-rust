from __future__ import annotations


_MARKER = "glyph-transition-readable-layout-v1"

_STYLE = r"""
<style id="glyph-transition-readable-layout-v1-style">
.transition-io-cluster.semantic-readable-label{
  max-width:380px!important;
}
.transition-io-cluster.semantic-readable-label .transition-io-node.io,
.transition-io-cluster.semantic-readable-label.compact-io .transition-io-node.io,
.transition-io-cluster.semantic-readable-label.micro-io .transition-io-node.io,
.transition-io-cluster.semantic-readable-label.nano-io .transition-io-node.io{
  width:var(--semantic-label-width,120px)!important;
  min-width:var(--semantic-label-width,120px)!important;
  max-width:var(--semantic-label-width,120px)!important;
  min-height:28px!important;
  padding:4px 7px!important;
}
.transition-io-cluster.semantic-readable-label .transition-io-value{
  font-size:9px!important;
  line-height:1.28!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:normal!important;
  word-break:normal!important;
}
.transition-semantic-line{
  display:block;
  white-space:nowrap;
  overflow:visible;
  text-overflow:clip;
  min-height:1.28em;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-readable-layout-v1-script">
(()=>{
const MARKER="glyph-transition-readable-layout-v1",MAX_LINE=28;
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

function semanticLines(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue),lines=[];
  const head=`${input}${guard?` [${guard}]`:""}`;
  if(guard&&head.length>MAX_LINE){
    lines.push(...splitExact(input));
    lines.push(...splitExact(` [${guard}]`));
  }else{
    lines.push(...splitExact(head));
  }
  if(output)lines.push(...splitExact(` ➞ ${output}`));
  return lines.filter(line=>line.length>0);
}

function formatCluster(cluster){
  const value=cluster.querySelector(".transition-io-value");if(!value)return false;
  const signature=JSON.stringify([cluster.dataset.inputValue||"",cluster.dataset.guardValue||"",cluster.dataset.outputValue||""]);
  if(cluster.dataset.semanticLineSignature===signature)return false;
  const lines=semanticLines(cluster),expected=cluster.dataset.ioValue||value.textContent||"";
  value.replaceChildren(...lines.map(line=>{
    const span=document.createElement("span");
    span.className="transition-semantic-line";
    span.textContent=line;
    return span;
  }));
  if(value.textContent!==expected){
    value.textContent=expected;
    cluster.dataset.semanticLineFallback="true";
  }else{
    delete cluster.dataset.semanticLineFallback;
  }
  const longest=Math.max(1,...lines.map(line=>line.length));
  const width=clamp(Math.ceil(longest*5.65+18),104,360);
  cluster.style.setProperty("--semantic-label-width",`${width}px`);
  cluster.dataset.semanticLineCount=String(lines.length);
  cluster.dataset.semanticLongestLine=String(longest);
  cluster.dataset.semanticLineSignature=signature;
  cluster.classList.add("semantic-readable-label");
  return true;
}

function apply(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage||!stage.isConnected)return 0;
  const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
  const changed=clusters.reduce((count,cluster)=>count+Number(formatCluster(cluster)),0);
  stage.dataset.transitionSemanticLinesReady="formatted";
  if(changed){
    window.glyphTransitionLayoutTransaction?.schedule?.("semantic-line-format-updated",0);
  }
  return changed;
}

window.glyphTransitionReadableLayout=Object.freeze({
  marker:MARKER,
  version:2,
  ownsNodeLayout:false,
  ownsScheduling:false,
  apply,
  maxLineLength:MAX_LINE,
});
})();
</script>
"""


def enhance_transition_readable_layout_html(html: str) -> str:
    """Provide semantic label wrapping without owning node layout or scheduling."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
