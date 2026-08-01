from __future__ import annotations


_MARKER = "glyph-transition-layout-tab-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-tab-guard-v1-script">
(()=>{
const MARKER="glyph-transition-layout-tab-guard-v1";

function activeTab(){return document.querySelector(".tab.active")?.dataset.tab||"state"}
function stateStages(){
  return[...document.querySelectorAll(".graph-stage")].filter(stage=>stage.querySelector(".state-node"));
}
function deactivate(reason="inactive-tab"){
  window.glyphTransitionLayoutTransaction?.cancel?.(reason);
  window.glyphLayoutPublicationCertificate?.cancel?.(reason);
  for(const stage of stateStages()){
    stage.dataset.transitionLayoutTab="inactive";
    stage.dataset.transitionPublicationReady="false";
    stage.dataset.renderStableState="inactive";
  }
}
function activate(reason="state-tab-activated"){
  for(const stage of stateStages()){
    stage.dataset.transitionLayoutTab="active";
    delete stage.dataset.transitionLayoutCancellation;
  }
  window.glyphTransitionLayoutTransaction?.schedule?.(reason,0);
}
function synchronize(){
  if(activeTab()==="state")activate("state-tab-synchronized");
  else deactivate("state-tab-synchronized");
}

document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  if(tab.dataset.tab==="state"){
    requestAnimationFrame(()=>activate("state-tab-activated"));
  }else{
    deactivate("state-tab-deactivated");
  }
},true);
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select")requestAnimationFrame(()=>activate("machine-change"));
});
window.glyphTransitionLayoutTabGuard={marker:MARKER,version:2,synchronize,activate,deactivate};
})();
</script>
"""


def enhance_transition_layout_tab_guard_html(html: str) -> str:
    """Cancel state-layout work immediately when leaving the State tab."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
