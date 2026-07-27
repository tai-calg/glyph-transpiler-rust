from __future__ import annotations


_MARKER = "glyph-transition-readable-layout-v1"

_STYLE = r"""
<style id="glyph-transition-readable-layout-v1-style">
.transition-io-cluster.semantic-readable-label{
  max-width:270px!important;
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
const MARKER="glyph-transition-readable-layout-v1",DENSE_TRANSITIONS=7,MAX_LINE=28;
let timer=null,running=false;
const text=value=>String(value??"");
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

function preferredCut(value,limit){
  const bounded=Math.min(limit,value.length-1),characters=["(",")","[","]",",",".","_","&"," "];
  for(let index=bounded;index>Math.max(5,bounded-12);index-=1){if(characters.includes(value[index]))return index+1}
  for(let index=bounded+1;index<Math.min(value.length,bounded+12);index+=1){if(characters.includes(value[index]))return index+1}
  return Math.min(value.length,limit);
}

function splitExact(value,limit=MAX_LINE){
  const lines=[];
  let remaining=text(value);
  while(remaining.length>limit){const cut=preferredCut(remaining,limit);lines.push(remaining.slice(0,cut));remaining=remaining.slice(cut)}
  if(remaining.length||!lines.length)lines.push(remaining);
  return lines;
}

function semanticLines(cluster){
  const input=text(cluster.dataset.inputValue),guard=text(cluster.dataset.guardValue),output=text(cluster.dataset.outputValue),lines=[];
  const head=`${input}${guard?` [${guard}]`:""}`;
  if(guard&&head.length>MAX_LINE){lines.push(...splitExact(input));lines.push(...splitExact(` [${guard}]`))}else lines.push(...splitExact(head));
  if(output)lines.push(...splitExact(` ➞ ${output}`));
  return lines.filter(line=>line.length>0);
}

function formatCluster(cluster){
  const value=cluster.querySelector(".transition-io-value");if(!value)return;
  const signature=JSON.stringify([cluster.dataset.inputValue||"",cluster.dataset.guardValue||"",cluster.dataset.outputValue||""]);
  if(cluster.dataset.semanticLineSignature===signature)return;
  const lines=semanticLines(cluster),expected=cluster.dataset.ioValue||value.textContent||"";
  value.replaceChildren(...lines.map(line=>{const span=document.createElement("span");span.className="transition-semantic-line";span.textContent=line;return span}));
  if(value.textContent!==expected){value.textContent=expected;cluster.dataset.semanticLineFallback="true"}else delete cluster.dataset.semanticLineFallback;
  const longest=Math.max(1,...lines.map(line=>line.length)),width=clamp(Math.ceil(longest*5.65+18),104,260);
  cluster.style.setProperty("--semantic-label-width",`${width}px`);
  cluster.dataset.semanticLineCount=String(lines.length);
  cluster.dataset.semanticLongestLine=String(longest);
  cluster.dataset.semanticLineSignature=signature;
  cluster.classList.add("semantic-readable-label");
}

function hasSavedNodes(){
  const index=document.getElementById("machine-select")?.value||0;
  return Object.keys(localStorage).some(key=>key.startsWith("glyph.diagram.positions.v1:")&&key.endsWith(`:state:${index}`));
}

function expandDenseStage(stage,clusters){
  const nodes=[...stage.querySelectorAll(".state-node")];
  if(clusters.length<DENSE_TRANSITIONS||nodes.length<2||hasSavedNodes())return false;
  const signature=`${nodes.map(node=>node.querySelector(".state-name")?.textContent||"").join("|")}:${clusters.length}`;
  if(stage.dataset.semanticDenseLayout===signature)return false;
  const stageWidth=Math.max(1180,stage.scrollWidth),stageHeight=Math.max(860,stage.scrollHeight),centerX=stageWidth/2,centerY=stageHeight/2;
  const radiusX=Math.max(330,Math.min(430,stageWidth*.34)),radiusY=Math.max(245,Math.min(320,stageHeight*.32));
  nodes.forEach((node,index)=>{
    const angle=-Math.PI/2+index*2*Math.PI/nodes.length;
    node.style.left=`${Math.round(centerX+Math.cos(angle)*radiusX-node.offsetWidth/2)}px`;
    node.style.top=`${Math.round(centerY+Math.sin(angle)*radiusY-node.offsetHeight/2)}px`;
  });
  stage.style.width=`${stageWidth}px`;stage.style.height=`${stageHeight}px`;
  stage.dataset.semanticDenseLayout=signature;
  return true;
}

async function apply(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(running||!stage||stage.dataset.transitionIoClustersReady!=="true")return;
  running=true;
  try{
    const clusters=[...stage.querySelectorAll(".transition-io-cluster")];
    clusters.forEach(formatCluster);
    const expanded=expandDenseStage(stage,clusters);
    stage.dataset.transitionSemanticLinesReady="true";
    if(expanded){
      await window.glyphTransitionNodeLayoutGuard?.requestLayout(stage);
    }else{
      window.glyphTransitionIoCollisionSolver?.run();
    }
    document.dispatchEvent(new CustomEvent("glyph-transition-readable-layout-ready",{detail:{marker:MARKER,labels:clusters.length,expanded}}));
  }finally{running=false}
}

function schedule(stage=null,delay=0){clearTimeout(timer);timer=setTimeout(()=>apply(stage||document.querySelector(".state-node")?.closest(".graph-stage")).catch(error=>console.error("readable transition layout failed",error)),delay)}
document.addEventListener("glyph-transition-io-clusters-ready",()=>schedule(null,0));
document.addEventListener("glyph-locale-changed",()=>schedule(null,0));
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")schedule(null,0)});
new MutationObserver(()=>schedule(null,30)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphTransitionReadableLayout={marker:MARKER,apply:()=>schedule(null,0),maxLineLength:MAX_LINE};
schedule(null,0);
})();
</script>
"""


def enhance_transition_readable_layout_html(html: str) -> str:
    """Wrap labels at semantic boundaries and expand dense state diagrams."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
