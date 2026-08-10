from __future__ import annotations


_MARKER = "glyph-diagram-identity-stamp-v1"

_SCRIPT = r"""
<script id="glyph-diagram-identity-stamp-v1-script">
(()=>{
const MARKER="glyph-diagram-identity-stamp-v1";
if(window.glyphDiagramIdentityStamp?.marker===MARKER)return;
let frame=0;
function currentDigest(){
  const state=typeof snapshot==="object"&&snapshot?snapshot:null;
  return String(state?.rendered_digest||state?.digest||"source");
}
function stamp(){
  frame=0;
  const digest=currentDigest();
  for(const stage of document.querySelectorAll(".graph-stage"))stage.dataset.diagramDigest=digest;
  return digest;
}
function schedule(){if(frame)return;frame=requestAnimationFrame(stamp)}
const view=document.getElementById("view")||document.body;
new MutationObserver(schedule).observe(view,{childList:true,subtree:true});
for(const eventName of[
  "glyph-transition-layout-ready",
  "glyph-transition-layout-transaction-ready",
  "glyph-state-transition-ir-v3-labels-ready",
  "glyph-save-state-changed",
])document.addEventListener(eventName,schedule);
window.glyphDiagramIdentityStamp={marker:MARKER,version:1,digest:currentDigest,refresh:schedule};
stamp();requestAnimationFrame(stamp);
})();
</script>
"""


def enhance_diagram_identity_stamp_html(html: str) -> str:
    """Stamp the currently rendered compiler digest onto every diagram stage."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_diagram_identity_stamp_html"]
