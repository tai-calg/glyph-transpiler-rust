from __future__ import annotations


_MARKER = "glyph-transition-label-readability-v1"

_STYLE = r"""
<style id="glyph-transition-label-readability-v1-style">
.transition-io-cluster{
  max-width:240px!important;
}
.transition-io-node.io{
  min-width:96px!important;
  max-width:200px!important;
  min-height:28px!important;
  padding:4px 7px!important;
  overflow:visible!important;
}
.transition-io-value{
  display:block!important;
  max-width:100%!important;
  min-width:0!important;
  font-size:9px!important;
  line-height:1.3!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  overflow-wrap:anywhere!important;
  word-break:break-word!important;
  text-align:center!important;
}
.transition-io-cluster.compact-io .transition-io-node.io{
  min-width:84px!important;
  max-width:164px!important;
  min-height:26px!important;
  padding:3px 6px!important;
}
.transition-io-cluster.micro-io .transition-io-node.io{
  min-width:76px!important;
  max-width:140px!important;
  min-height:24px!important;
  padding:3px 5px!important;
  border-radius:6px!important;
}
.transition-io-cluster.nano-io .transition-io-node.io{
  min-width:72px!important;
  max-width:116px!important;
  min-height:24px!important;
  padding:3px 4px!important;
  border-radius:5px!important;
}
.transition-io-cluster.compact-io .transition-io-value,
.transition-io-cluster.micro-io .transition-io-value,
.transition-io-cluster.nano-io .transition-io-value{
  font-size:9px!important;
  line-height:1.25!important;
}
.transition-io-cluster.readability-violation{
  outline:3px solid var(--red)!important;
  outline-offset:4px!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-label-readability-v1-script">
(()=>{
const MARKER="glyph-transition-label-readability-v1",MIN_FONT_SIZE=9,TOLERANCE=1.5;
let timer=null;
const esc=value=>String(value??"").replace(/[&<>\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[ch]));
const text=value=>String(value??"").trim();
const rectContains=(outer,inner,tolerance=TOLERANCE)=>inner.left>=outer.left-tolerance&&inner.top>=outer.top-tolerance&&inner.right<=outer.right+tolerance&&inner.bottom<=outer.bottom+tolerance;

function inspect(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage)return{ok:false,violations:[{reason:"missing-stage"}]};
  const violations=[];
  const values=[...stage.querySelectorAll(".transition-io-cluster .transition-io-value")];
  for(const value of values){
    const cluster=value.closest(".transition-io-cluster"),node=value.closest(".transition-io-node.io"),style=getComputedStyle(value);
    const expected=text(cluster?.dataset.ioValue||node?.getAttribute("title"));
    const actual=text(value.textContent);
    const fontSize=Number.parseFloat(style.fontSize||"0")||0;
    const valueRect=value.getBoundingClientRect(),nodeRect=node?.getBoundingClientRect();
    const reasons=[];
    if(!actual||actual!==expected)reasons.push("text-mismatch");
    if(fontSize+0.01<MIN_FONT_SIZE)reasons.push("font-too-small");
    if(style.whiteSpace==="nowrap")reasons.push("nowrap");
    if(style.textOverflow==="ellipsis")reasons.push("ellipsis");
    if(value.scrollWidth>value.clientWidth+TOLERANCE)reasons.push("horizontal-clipping");
    if(value.scrollHeight>value.clientHeight+TOLERANCE)reasons.push("vertical-clipping");
    if(nodeRect&&!rectContains(nodeRect,valueRect))reasons.push("outside-label-box");
    cluster?.classList.toggle("readability-violation",reasons.length>0);
    cluster?.setAttribute("data-transition-readability",reasons.length?"failed":"true");
    if(reasons.length)violations.push({id:cluster?.dataset.transitionId||"",label:expected,reasons});
  }
  const ok=values.length>0&&violations.length===0;
  stage.dataset.transitionIoReadability=ok?"true":"failed";
  stage.dataset.transitionIoReadabilityViolations=String(violations.length);
  document.dispatchEvent(new CustomEvent("glyph-transition-label-readability-audited",{detail:{marker:MARKER,ok,count:values.length,violations}}));
  return{ok,count:values.length,violations};
}

function renderedLines(element){
  const value=element?.textContent||"",node=element?.firstChild;
  if(!value||!node||node.nodeType!==Node.TEXT_NODE)return[value];
  const lines=[];
  let current="",currentTop=null;
  for(let index=0;index<value.length;index+=1){
    const range=document.createRange();
    range.setStart(node,index);range.setEnd(node,index+1);
    const rect=range.getBoundingClientRect();
    if(currentTop===null)currentTop=rect.top;
    if(Math.abs(rect.top-currentTop)>1){lines.push(current);current="";currentTop=rect.top}
    current+=value[index];
  }
  if(current)lines.push(current);
  return lines.map(line=>line.trim()).filter(Boolean);
}

function exportSnapshot(stage){
  return[...stage.querySelectorAll(".transition-io-cluster")].map(cluster=>{
    const node=cluster.querySelector('.transition-io-node[data-io-kind="io"]'),valueElement=node?.querySelector(".transition-io-value");
    if(!node||!valueElement)return null;
    const baseX=cluster.offsetLeft-cluster.offsetWidth/2,baseY=cluster.offsetTop-cluster.offsetHeight/2;
    return{x:baseX+node.offsetLeft,y:baseY+node.offsetTop,width:node.offsetWidth,height:node.offsetHeight,value:valueElement.textContent||"",lines:renderedLines(valueElement)};
  }).filter(Boolean);
}

function exportMarkup(items){
  return items.map(item=>{
    const lineHeight=11.5,startY=item.y+item.height/2-((item.lines.length-1)*lineHeight)/2+3;
    const tspans=item.lines.map((line,index)=>`<tspan x="${item.x+item.width/2}" y="${startY+index*lineHeight}">${esc(line)}</tspan>`).join("");
    return`<g class="transition-io-export-label" data-full-label="${esc(item.value)}"><title>${esc(item.value)}</title><rect x="${item.x}" y="${item.y}" width="${item.width}" height="${item.height}" rx="6" fill="#fff" stroke="#2563eb"/><text font-family="Arial,Helvetica,sans-serif" font-size="9" font-weight="700" text-anchor="middle" fill="#111">${tspans}</text></g>`;
  }).join("");
}

function patchExports(){
  const original=window.svg;
  if(typeof original!=="function"||original.__glyphReadableTransitionLabels)return;
  const patched=function(){
    const stage=document.querySelector(".graph-stage"),items=stage?exportSnapshot(stage):[];
    const clusters=stage?[...stage.querySelectorAll(".transition-io-cluster")]:[];
    const markers=clusters.map(cluster=>{const marker=document.createComment("readable-transition-label");cluster.replaceWith(marker);return{cluster,marker}});
    let markup;
    try{markup=original()}finally{markers.forEach(({cluster,marker})=>marker.replaceWith(cluster))}
    if(!items.length)return markup;
    return markup.replace("</svg>",`${exportMarkup(items)}</svg>`);
  };
  patched.__glyphReadableTransitionLabels=true;
  window.svg=patched;
}

function schedule(stage=null,delay=40){
  clearTimeout(timer);
  timer=setTimeout(()=>inspect(stage||document.querySelector(".state-node")?.closest(".graph-stage")),delay);
}

for(const event of["glyph-transition-io-clusters-ready","glyph-transition-io-collision-solved","glyph-diagram-viewport-change","glyph-locale-changed"]){
  document.addEventListener(event,()=>schedule(null,0));
}
window.addEventListener("resize",()=>schedule(null,30));
new MutationObserver(()=>schedule()).observe(document.getElementById("view")||document.body,{childList:true,subtree:true,characterData:true});
patchExports();
window.glyphTransitionLabelReadability={inspect,minimumFontSize:MIN_FONT_SIZE,marker:MARKER};
schedule(null,0);
})();
</script>
"""


def enhance_transition_label_readability_html(html: str) -> str:
    """Keep every transition label fully visible and auditable at readable size."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
