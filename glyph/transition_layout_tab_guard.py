from __future__ import annotations


_MARKER = "glyph-transition-layout-tab-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-tab-guard-v1-script">
(()=>{
const MARKER="glyph-transition-layout-tab-guard-v1";
const ACTIVE_VALUE="true",INACTIVE_VALUE="inactive-tab";

function stateStages(){
  return[...document.querySelectorAll(".graph-stage")].filter(stage=>stage.querySelector(".state-node"));
}
function activeTab(){return document.querySelector(".tab.active")?.dataset.tab||"state"}
function deactivate(){
  for(const stage of stateStages()){
    if(stage.dataset.stateTransitionIRV3LabelsReady===ACTIVE_VALUE)stage.dataset.transitionTabPreviousReady=ACTIVE_VALUE;
    stage.dataset.stateTransitionIRV3LabelsReady=INACTIVE_VALUE;
    stage.dataset.transitionLayoutTab="inactive";
  }
}
function activate(){
  for(const stage of stateStages()){
    if(stage.dataset.stateTransitionIRV3LabelsReady===INACTIVE_VALUE||stage.dataset.transitionTabPreviousReady===ACTIVE_VALUE){
      stage.dataset.stateTransitionIRV3LabelsReady=ACTIVE_VALUE;
    }
    delete stage.dataset.transitionTabPreviousReady;
    stage.dataset.transitionLayoutTab="active";
  }
  window.glyphTransitionLayoutTransaction?.schedule("state-tab-activated",0);
}
function synchronize(){
  if(activeTab()==="state")activate();
  else deactivate();
}

document.addEventListener("pointerdown",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(tab?.dataset.tab!=="state")deactivate();
},true);
document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  queueMicrotask(()=>tab.dataset.tab==="state"?activate():deactivate());
},true);
new MutationObserver(()=>synchronize()).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:["class"]});
window.glyphTransitionLayoutTabGuard={marker:MARKER,synchronize};
synchronize();
})();
</script>
"""


def enhance_transition_layout_tab_guard_html(html: str) -> str:
    """Run state-transition layout work only while the state diagram tab is active."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
