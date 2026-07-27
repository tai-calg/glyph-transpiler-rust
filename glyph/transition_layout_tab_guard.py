from __future__ import annotations


_MARKER = "glyph-transition-layout-tab-guard-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-tab-guard-v1-script">
(()=>{
const MARKER="glyph-transition-layout-tab-guard-v1";
const ACTIVE_VALUE="true",INACTIVE_VALUE="inactive-tab";
let bypass=false,switching=false;

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
async function waitForSettlement(){
  for(let attempt=0;attempt<120;attempt+=1){
    const stages=stateStages();
    if(!stages.length)return;
    const settled=stages.every(stage=>["ready","failed",undefined].includes(stage.dataset.transitionLayoutState));
    if(settled)return;
    await new Promise(resolve=>setTimeout(resolve,16));
  }
}
async function switchAfterSettlement(tab){
  if(switching)return;
  switching=true;
  try{
    await waitForSettlement();
    deactivate();
    bypass=true;
    tab.click();
  }finally{
    bypass=false;
    switching=false;
  }
}

document.addEventListener("click",event=>{
  const tab=event.target?.closest?.(".tab[data-tab]");
  if(!tab)return;
  if(bypass){
    if(tab.dataset.tab!=="state")deactivate();
    return;
  }
  if(tab.dataset.tab==="state"){
    queueMicrotask(activate);
    setTimeout(activate,40);
    return;
  }
  event.preventDefault();
  event.stopImmediatePropagation();
  switchAfterSettlement(tab).catch(error=>console.error("transition tab switch failed",error));
},true);
window.glyphTransitionLayoutTabGuard={marker:MARKER,synchronize};
})();
</script>
"""


def enhance_transition_layout_tab_guard_html(html: str) -> str:
    """Run state-transition layout work only while the state diagram tab is active."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
