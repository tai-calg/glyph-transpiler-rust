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
  for(const stage of stateStages()){
    stage.dataset.transitionLayoutTab="inactive";
    stage.dataset.transitionLayoutState="ready";
    stage.dataset.transitionLayoutReady="true";
    stage.dataset.transitionPublicationReady="true";
  }
}
function activate(reason="state-tab-activated"){
  for(const stage of stateStages())stage.dataset.transitionLayoutTab="active";
  return window.glyphTransitionLayoutTransaction?.schedule?.(reason,0)??0;
}
function synchronize(){
  return activeTab()==="state"?activate("state-tab-synchronized"):deactivate("state-tab-synchronized");
}
document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  if(tab.dataset.tab==="state")requestAnimationFrame(()=>activate("state-tab-activated"));
  else deactivate("state-tab-deactivated");
},true);
document.addEventListener("change",event=>{
  if(event.target?.id==="machine-select")requestAnimationFrame(()=>activate("machine-change"));
});
window.glyphTransitionLayoutTabGuard={marker:MARKER,version:3,synchronize,activate,deactivate};
})();
</script>
"""


def enhance_transition_layout_tab_guard_html(html: str) -> str:
    """Cancel stale work on I/O and restart a bounded state render on return."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
