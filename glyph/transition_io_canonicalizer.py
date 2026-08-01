from __future__ import annotations


_MARKER = "glyph-transition-io-canonicalizer-v1"

_SCRIPT = r"""
<script id="glyph-transition-io-canonicalizer-v1-script">
(()=>{
const MARKER="glyph-transition-io-canonicalizer-v1";
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
function canonical(cluster){
  const io=cluster.querySelectorAll(':scope .transition-io-node[data-io-kind="io"]');
  const legacy=cluster.querySelectorAll(':scope .transition-io-node[data-io-kind="input"],:scope .transition-io-node[data-io-kind="output"]');
  return io.length===1&&legacy.length===0&&Boolean(cluster.querySelector(":scope > .transition-io-main"));
}
function normalize(cluster){
  if(canonical(cluster))return false;
  const value=cluster.dataset.ioValue||cluster.dataset.fullLabel||cluster.textContent?.trim()||"";
  cluster.innerHTML=`<div class="transition-io-main"><div class="transition-io-node io" data-io-kind="io" title="${esc(value)}"><span class="transition-io-value">${esc(value)}</span></div></div>`;
  cluster.dataset.ioValue=value;
  cluster.dataset.fullLabel=value;
  cluster.dataset.ioCanonical="true";
  return true;
}
function apply(stage=document.querySelector(".state-node")?.closest(".graph-stage")){
  if(!stage||!stage.isConnected)return 0;
  const changed=[...stage.querySelectorAll(".transition-io-cluster")].reduce((count,cluster)=>count+Number(normalize(cluster)),0);
  stage.dataset.transitionIoCanonical="true";
  if(changed){
    window.glyphTransitionReadableLayout?.apply?.(stage);
    window.glyphTransitionIoClusters?.reroute?.(stage);
    window.glyphTransitionLayoutTransaction?.schedule?.("canonical-transition-io",0);
  }
  return changed;
}
document.addEventListener("glyph-transition-io-clusters-ready",()=>apply());
const view=document.getElementById("view");
if(view)new MutationObserver(records=>{
  if(records.some(record=>[...record.addedNodes].some(node=>node.nodeType===1&&(node.matches?.(".transition-io-cluster")||node.querySelector?.(".transition-io-cluster")))))requestAnimationFrame(()=>apply());
}).observe(view,{childList:true,subtree:true});
window.glyphTransitionIoCanonicalizer=Object.freeze({marker:MARKER,version:1,apply});
requestAnimationFrame(()=>apply());
})();
</script>
"""


def enhance_transition_io_canonicalizer_html(html: str) -> str:
    """Remove legacy split Input/Output nodes from live transition clusters."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
