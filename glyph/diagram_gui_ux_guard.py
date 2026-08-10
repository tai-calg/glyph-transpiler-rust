from __future__ import annotations


_MARKER = "glyph-diagram-gui-ux-guard-v1"

_STYLE = r"""
<style id="glyph-diagram-gui-ux-guard-v1-style">
.tab:focus-visible,
.state-node:focus-visible,
.transition-io-cluster:focus-visible,
.diagnostic[data-line]:focus-visible,
.analysis-item[data-line]:focus-visible,
.splitter:focus-visible{
  outline:2px solid var(--blue);
  outline-offset:2px;
}
.transition-io-cluster[role="button"]{cursor:pointer!important}
@media(max-width:680px){
  main{
    grid-template-columns:1fr!important;
    grid-template-rows:minmax(220px,42%) minmax(0,1fr)!important;
  }
  .splitter{display:none!important}
  .editor-pane,.viewer{height:auto!important;min-height:0!important}
  header{padding:6px 8px!important;gap:6px!important}
  header .brand{display:none!important}
  .viewer-head{min-height:auto!important;padding:6px 8px!important}
  .view-body{padding:10px!important}
}
@media(max-width:680px) and (max-height:560px){
  main{grid-template-rows:minmax(150px,45%) minmax(0,1fr)!important}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-gui-ux-guard-v1-script">
(()=>{
const MARKER="glyph-diagram-gui-ux-guard-v1";
if(window.glyphDiagramGuiUxGuard?.marker===MARKER)return;
const pointerSessions=new Map(),FOCUS_REQUEST_TTL_MS=2000;
let inspectorOpener=null,inspectorOpenerIdentity=null,restoreInspectorFocus=false,enhanceFrame=0,pendingClusterFocus=null,pendingClusterFocusTimer=0;
const focusableEditing="input,textarea,select,[contenteditable=true]";
const pointerTargetSelector="#splitter,.canvas-shell,.state-node,.transition-io-cluster,.edge-label,.transition-label";
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const machineIndex=()=>String(document.getElementById("machine-select")?.value||"0");
const clusterDigest=cluster=>String(cluster?.closest?.(".graph-stage")?.dataset.diagramDigest||"");

function activateTab(tab){
  if(!tab)return;
  tab.click();
  requestAnimationFrame(()=>{setupTabs();tab.focus({preventScroll:true})});
}
function setupTabs(){
  const group=document.querySelector(".tabs");
  const tabs=[...document.querySelectorAll(".tabs .tab")];
  const panel=document.getElementById("view");
  if(group)group.setAttribute("role","tablist");
  let activeId="";
  tabs.forEach((tab,index)=>{
    const active=tab.classList.contains("active");
    tab.id=tab.id||`glyph-diagram-tab-${tab.dataset.tab||index}`;
    tab.setAttribute("role","tab");
    tab.setAttribute("aria-selected",active?"true":"false");
    tab.setAttribute("aria-controls","view");
    tab.tabIndex=active?0:-1;
    if(active)activeId=tab.id;
    if(tab.dataset.guiUxTabReady==="true")return;
    tab.dataset.guiUxTabReady="true";
    tab.addEventListener("keydown",event=>{
      const items=[...document.querySelectorAll(".tabs .tab")];
      const itemIndex=items.indexOf(tab);if(itemIndex<0)return;
      let next=-1;
      if(event.key==="ArrowRight")next=(itemIndex+1)%items.length;
      else if(event.key==="ArrowLeft")next=(itemIndex-1+items.length)%items.length;
      else if(event.key==="Home")next=0;
      else if(event.key==="End")next=items.length-1;
      if(next<0)return;
      event.preventDefault();event.stopPropagation();activateTab(items[next]);
    });
    tab.addEventListener("click",()=>requestAnimationFrame(setupTabs));
  });
  if(panel){
    panel.setAttribute("role","tabpanel");
    if(activeId)panel.setAttribute("aria-labelledby",activeId);
    else panel.removeAttribute("aria-labelledby");
  }
}
function setupLineJumps(){
  for(const element of document.querySelectorAll(".diagnostic[data-line],.analysis-item[data-line]")){
    if(Number(element.dataset.line||0)<=0)continue;
    element.tabIndex=0;element.setAttribute("role","button");
    if(element.dataset.guiUxJumpReady==="true")continue;
    element.dataset.guiUxJumpReady="true";
    element.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();event.stopPropagation();element.click();
    });
  }
}
function setupStateNodes(){
  for(const node of document.querySelectorAll(".state-node")){
    node.tabIndex=0;node.setAttribute("role","button");
    const name=node.querySelector(".state-name")?.textContent?.trim()||"state";
    node.setAttribute("aria-label",name);
    if(node.dataset.guiUxNodeReady==="true")continue;
    node.dataset.guiUxNodeReady="true";
    node.addEventListener("focus",()=>{
      document.querySelector(".state-node.selected-node")?.classList.remove("selected-node");
      node.classList.add("selected-node");
    });
    node.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      const line=Number(node.dataset.line||0);if(line<=0||typeof globalThis.jumpToLine!=="function")return;
      event.preventDefault();event.stopPropagation();globalThis.jumpToLine(line);
    });
  }
}
function clearPendingClusterFocus(){
  pendingClusterFocus=null;
  if(pendingClusterFocusTimer){clearTimeout(pendingClusterFocusTimer);pendingClusterFocusTimer=0}
}
function armClusterFocus(cluster){
  const id=cluster?.dataset.transitionId||"";
  if(!id){clearPendingClusterFocus();return}
  pendingClusterFocus={id,machineIndex:machineIndex(),diagramDigest:clusterDigest(cluster)};
  if(pendingClusterFocusTimer)clearTimeout(pendingClusterFocusTimer);
  pendingClusterFocusTimer=setTimeout(clearPendingClusterFocus,FOCUS_REQUEST_TTL_MS);
}
function restoreClusterFocus(){
  if(!pendingClusterFocus)return;
  const expected=pendingClusterFocus;
  requestAnimationFrame(()=>{
    if(pendingClusterFocus!==expected)return;
    if(machineIndex()!==expected.machineIndex){clearPendingClusterFocus();return}
    const cluster=[...document.querySelectorAll(".transition-io-cluster")].find(item=>item.dataset.transitionId===expected.id);
    if(!cluster)return;
    if(clusterDigest(cluster)!==expected.diagramDigest){clearPendingClusterFocus();return}
    clearPendingClusterFocus();setupTransitionClusters();cluster.focus({preventScroll:true});
  });
}
function setupTransitionClusters(){
  for(const cluster of document.querySelectorAll(".transition-io-cluster")){
    cluster.tabIndex=0;cluster.setAttribute("role","button");cluster.setAttribute("aria-haspopup","dialog");
    cluster.setAttribute("aria-keyshortcuts","Enter ArrowUp ArrowDown ArrowLeft ArrowRight Delete");
    const label=(cluster.dataset.ioValue||cluster.textContent||"transition").trim();
    if(label)cluster.setAttribute("aria-label",label);
    if(cluster.dataset.guiUxInspectorReady==="true")continue;
    cluster.dataset.guiUxInspectorReady="true";
    cluster.addEventListener("keydown",event=>{
      const adapter=window.glyphTransitionLayoutInteractionAdapter;
      if(event.key.startsWith("Arrow")){
        const step=event.shiftKey?12:4;
        const dx=event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0;
        const dy=event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0;
        event.preventDefault();event.stopPropagation();
        armClusterFocus(cluster);
        Promise.resolve(adapter?.keyboardNudge?.(cluster,dx,dy)).finally(restoreClusterFocus);
        return;
      }
      if(event.key==="Delete"){
        event.preventDefault();event.stopPropagation();
        armClusterFocus(cluster);
        Promise.resolve(adapter?.resetCluster?.(cluster)).finally(restoreClusterFocus);
        return;
      }
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();event.stopPropagation();
      window.glyphTransitionLabelInspector?.open?.(cluster);
    });
  }
}
function inspectorIdentityFor(opener){
  const id=opener?.dataset?.transitionId||"";
  return id?{id,machineIndex:machineIndex(),diagramDigest:clusterDigest(opener)}:null;
}
function restoreInspectorOpener(opener,identity){
  requestAnimationFrame(()=>{
    if(opener?.isConnected){opener.focus({preventScroll:true});return}
    if(!identity||machineIndex()!==identity.machineIndex)return;
    const replacement=[...document.querySelectorAll(".transition-io-cluster")].find(item=>item.dataset.transitionId===identity.id);
    if(!replacement||clusterDigest(replacement)!==identity.diagramDigest)return;
    setupTransitionClusters();replacement.focus({preventScroll:true});
  });
}
function setupInspector(){
  const panel=document.querySelector(".transition-label-inspector");
  if(!panel||panel.dataset.guiUxReady==="true")return;
  panel.dataset.guiUxReady="true";
  const title=panel.querySelector(".transition-label-inspector-title");
  if(title){title.id=title.id||"glyph-transition-label-inspector-title";panel.setAttribute("aria-labelledby",title.id)}
  new MutationObserver(()=>{
    if(!panel.hidden)return;
    const opener=inspectorOpener,identity=inspectorOpenerIdentity;
    inspectorOpener=null;inspectorOpenerIdentity=null;
    if(!restoreInspectorFocus){restoreInspectorFocus=false;return}
    restoreInspectorFocus=false;
    restoreInspectorOpener(opener,identity);
  }).observe(panel,{attributes:true,attributeFilter:["hidden"]});
}
function editorPercent(){
  const raw=getComputedStyle(document.documentElement).getPropertyValue("--editor").trim();
  const parsed=Number.parseFloat(raw);
  if(Number.isFinite(parsed))return clamp(parsed,25,70);
  const main=document.getElementById("main"),editor=document.querySelector(".editor-pane");
  return main&&editor&&main.clientWidth?clamp(editor.getBoundingClientRect().width/main.clientWidth*100,25,70):42;
}
function publishSplitter(splitter,value){
  const next=clamp(value,25,70);
  document.documentElement.style.setProperty("--editor",`${next}%`);
  splitter.setAttribute("aria-valuenow",String(Math.round(next)));
  splitter.setAttribute("aria-valuetext",`${Math.round(next)}% source editor`);
  window.dispatchEvent(new Event("resize"));
}
function setupSplitter(){
  const splitter=document.getElementById("splitter");
  if(!splitter)return;
  splitter.tabIndex=0;splitter.setAttribute("role","separator");splitter.setAttribute("aria-orientation","vertical");
  splitter.setAttribute("aria-label","Resize source and diagram panes");splitter.setAttribute("aria-valuemin","25");splitter.setAttribute("aria-valuemax","70");
  splitter.setAttribute("aria-valuenow",String(Math.round(editorPercent())));
  if(splitter.dataset.guiUxCancelReady==="true")return;
  splitter.dataset.guiUxCancelReady="true";
  const finish=event=>{try{splitter.onpointerup?.(event)}catch{}};
  splitter.addEventListener("pointercancel",finish,true);
  splitter.addEventListener("lostpointercapture",finish,true);
  splitter.addEventListener("keydown",event=>{
    let next=null,current=editorPercent(),step=event.shiftKey?5:2;
    if(event.key==="ArrowLeft")next=current-step;
    else if(event.key==="ArrowRight")next=current+step;
    else if(event.key==="Home")next=25;
    else if(event.key==="End")next=70;
    if(next===null)return;
    event.preventDefault();event.stopPropagation();publishSplitter(splitter,next);
  });
}
function setupSettings(){
  const button=document.getElementById("glyph-settings"),dialog=document.getElementById("glyph-settings-dialog");
  if(button&&dialog){button.setAttribute("aria-haspopup","dialog");button.setAttribute("aria-controls",dialog.id)}
  if(!dialog)return;
  const heading=dialog.querySelector("h1,h2,h3");
  if(heading){heading.id=heading.id||"glyph-settings-title";dialog.setAttribute("aria-labelledby",heading.id)}
}
function enhance(){
  enhanceFrame=0;setupTabs();setupLineJumps();setupStateNodes();setupTransitionClusters();setupInspector();setupSplitter();setupSettings();restoreClusterFocus();
}
function scheduleEnhance(){if(enhanceFrame)return;enhanceFrame=requestAnimationFrame(enhance)}

function modalOpen(){return document.querySelector("dialog[open]")}
window.addEventListener("keydown",event=>{
  const modal=modalOpen();if(!modal)return;
  const saveShortcut=(event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s";
  const diagramZoom=(event.ctrlKey||event.metaKey)&&["+","=","-","0"].includes(event.key);
  if(saveShortcut||diagramZoom){event.preventDefault();event.stopPropagation();return}
  if(event.target?.closest?.(focusableEditing))return;
  if(event.key.startsWith("Arrow"))event.stopPropagation();
},true);

document.addEventListener("glyph-transition-label-inspector-opened",()=>{
  inspectorOpener=window.glyphTransitionLabelInspector?.current?.()||document.activeElement;
  inspectorOpenerIdentity=inspectorIdentityFor(inspectorOpener);
  restoreInspectorFocus=false;setupInspector();
  const panel=document.querySelector(".transition-label-inspector:not([hidden])");
  requestAnimationFrame(()=>panel?.querySelector(".transition-label-inspector-close")?.focus({preventScroll:true}));
});
document.addEventListener("keydown",event=>{
  if(event.key!=="Escape")return;
  const panel=document.querySelector(".transition-label-inspector:not([hidden])");
  if(panel&&!modalOpen())restoreInspectorFocus=true;
},true);
document.addEventListener("click",event=>{
  if(event.target?.closest?.(".transition-label-inspector-close"))restoreInspectorFocus=true;
},true);
window.addEventListener("pointerdown",event=>{
  const panel=document.querySelector(".transition-label-inspector:not([hidden])");
  if(panel&&!panel.contains(event.target)&&!event.target?.closest?.(".transition-io-cluster"))restoreInspectorFocus=false;
  const target=event.target?.closest?.(pointerTargetSelector);if(!target)return;
  pointerSessions.set(event.pointerId,{target,pointerId:event.pointerId,clientX:event.clientX,clientY:event.clientY,button:event.button});
},true);
window.addEventListener("pointermove",event=>{
  const record=pointerSessions.get(event.pointerId);if(!record)return;record.clientX=event.clientX;record.clientY=event.clientY;
},true);
window.addEventListener("pointerup",event=>pointerSessions.delete(event.pointerId),true);
window.addEventListener("lostpointercapture",event=>{
  const record=pointerSessions.get(event.pointerId);pointerSessions.delete(event.pointerId);
  const node=record?.target?.closest?.(".state-node");
  if(!node?.classList.contains("dragging"))return;
  queueMicrotask(()=>{
    if(!node.isConnected||!node.classList.contains("dragging"))return;
    node.dispatchEvent(new PointerEvent("pointercancel",{bubbles:true,cancelable:true,pointerId:record.pointerId,button:record.button,clientX:record.clientX,clientY:record.clientY}));
  });
},true);
window.addEventListener("pointercancel",event=>{
  const record=pointerSessions.get(event.pointerId);pointerSessions.delete(event.pointerId);
  const legacyLabel=record?.target?.closest?.(".edge-label,.transition-label");
  if(!legacyLabel?.classList.contains("dragging-label"))return;
  queueMicrotask(()=>{
    if(!legacyLabel.isConnected||!legacyLabel.classList.contains("dragging-label"))return;
    legacyLabel.dispatchEvent(new PointerEvent("pointerup",{bubbles:true,cancelable:true,pointerId:record.pointerId,button:0,clientX:record.clientX,clientY:record.clientY}));
  });
},true);
window.addEventListener("blur",()=>{
  for(const record of [...pointerSessions.values()]){
    const target=record.target;if(!target?.isConnected)continue;
    const legacyLabel=target.closest?.(".edge-label,.transition-label");
    const type=legacyLabel?.classList.contains("dragging-label")?"pointerup":"pointercancel";
    try{target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:record.pointerId,button:record.button,clientX:record.clientX,clientY:record.clientY}))}catch{}
  }
  pointerSessions.clear();
});

document.addEventListener("glyph-transition-layout-transaction-ready",()=>{scheduleEnhance();restoreClusterFocus()});
for(const eventName of["glyph-transition-layout-ready","glyph-state-transition-ir-v3-labels-ready","glyph-locale-changed","glyph-save-state-changed"]){document.addEventListener(eventName,scheduleEnhance)}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select")clearPendingClusterFocus();scheduleEnhance()});
const tabsRoot=document.querySelector(".tabs");
if(tabsRoot)new MutationObserver(setupTabs).observe(tabsRoot,{subtree:true,attributes:true,attributeFilter:["class"]});
new MutationObserver(scheduleEnhance).observe(document.getElementById("main")||document.body,{childList:true,subtree:true});
window.glyphDiagramGuiUxGuard={marker:MARKER,version:4,refresh:scheduleEnhance,activePointers:()=>pointerSessions.size,pendingClusterFocus:()=>pendingClusterFocus?{...pendingClusterFocus}:null};
enhance();requestAnimationFrame(enhance);
})();
</script>
"""


def enhance_diagram_gui_ux_guard_html(html: str) -> str:
    """Harden keyboard, focus, pointer-cancellation, modal, and narrow-window UX."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_diagram_gui_ux_guard_html"]
