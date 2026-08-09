from __future__ import annotations


_MARKER = "glyph-diagram-gui-ux-guard-v1"

_STYLE = r"""
<style id="glyph-diagram-gui-ux-guard-v1-style">
.tab:focus-visible,
.state-node:focus-visible,
.transition-io-cluster:focus-visible,
.diagnostic[data-line]:focus-visible,
.analysis-item[data-line]:focus-visible{
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
const pointerSessions=new Map();
let inspectorOpener=null,restoreInspectorFocus=false,enhanceFrame=0;
const focusableEditing="input,textarea,select,[contenteditable=true]";
const pointerTargetSelector="#splitter,.canvas-shell,.state-node,.transition-io-cluster,.edge-label,.transition-label";

function activateTab(tab){
  if(!tab)return;
  tab.click();
  requestAnimationFrame(()=>{setupTabs();tab.focus({preventScroll:true})});
}
function setupTabs(){
  const group=document.querySelector(".tabs");
  const tabs=[...document.querySelectorAll(".tabs .tab")];
  if(group)group.setAttribute("role","tablist");
  for(const tab of tabs){
    const active=tab.classList.contains("active");
    tab.setAttribute("role","tab");
    tab.setAttribute("aria-selected",active?"true":"false");
    tab.setAttribute("aria-controls","view");
    tab.tabIndex=active?0:-1;
    if(tab.dataset.guiUxTabReady==="true")continue;
    tab.dataset.guiUxTabReady="true";
    tab.addEventListener("keydown",event=>{
      const items=[...document.querySelectorAll(".tabs .tab")];
      const index=items.indexOf(tab);if(index<0)return;
      let next=-1;
      if(event.key==="ArrowRight")next=(index+1)%items.length;
      else if(event.key==="ArrowLeft")next=(index-1+items.length)%items.length;
      else if(event.key==="Home")next=0;
      else if(event.key==="End")next=items.length-1;
      if(next<0)return;
      event.preventDefault();event.stopPropagation();activateTab(items[next]);
    });
    tab.addEventListener("click",()=>requestAnimationFrame(setupTabs));
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
function setupTransitionClusters(){
  for(const cluster of document.querySelectorAll(".transition-io-cluster")){
    cluster.tabIndex=0;cluster.setAttribute("role","button");cluster.setAttribute("aria-haspopup","dialog");
    const label=(cluster.dataset.ioValue||cluster.textContent||"transition").trim();
    if(label)cluster.setAttribute("aria-label",label);
    if(cluster.dataset.guiUxInspectorReady==="true")continue;
    cluster.dataset.guiUxInspectorReady="true";
    cluster.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();event.stopPropagation();
      window.glyphTransitionLabelInspector?.open?.(cluster);
    });
  }
}
function setupInspector(){
  const panel=document.querySelector(".transition-label-inspector");
  if(!panel||panel.dataset.guiUxReady==="true")return;
  panel.dataset.guiUxReady="true";
  const title=panel.querySelector(".transition-label-inspector-title");
  if(title){title.id=title.id||"glyph-transition-label-inspector-title";panel.setAttribute("aria-labelledby",title.id)}
  new MutationObserver(()=>{
    if(!panel.hidden)return;
    const opener=inspectorOpener;inspectorOpener=null;
    if(!restoreInspectorFocus){restoreInspectorFocus=false;return}
    restoreInspectorFocus=false;
    if(opener?.isConnected)requestAnimationFrame(()=>opener.focus({preventScroll:true}));
  }).observe(panel,{attributes:true,attributeFilter:["hidden"]});
}
function setupSplitter(){
  const splitter=document.getElementById("splitter");
  if(!splitter||splitter.dataset.guiUxCancelReady==="true")return;
  splitter.dataset.guiUxCancelReady="true";
  const finish=event=>{try{splitter.onpointerup?.(event)}catch{}};
  splitter.addEventListener("pointercancel",finish,true);
  splitter.addEventListener("lostpointercapture",finish,true);
}
function enhance(){
  enhanceFrame=0;setupTabs();setupLineJumps();setupStateNodes();setupTransitionClusters();setupInspector();setupSplitter();
}
function scheduleEnhance(){if(enhanceFrame)return;enhanceFrame=requestAnimationFrame(enhance)}

function modalOpen(){return document.querySelector("dialog[open]")}
document.addEventListener("keydown",event=>{
  const modal=modalOpen();if(!modal)return;
  if(event.target?.closest?.(focusableEditing))return;
  const saveShortcut=(event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s";
  const diagramZoom=(event.ctrlKey||event.metaKey)&&["+","=","-","0"].includes(event.key);
  const diagramMove=event.key.startsWith("Arrow");
  if(!saveShortcut&&!diagramZoom&&!diagramMove)return;
  if(saveShortcut)event.preventDefault();
  event.stopPropagation();
},true);

document.addEventListener("glyph-transition-label-inspector-opened",()=>{
  inspectorOpener=window.glyphTransitionLabelInspector?.current?.()||document.activeElement;
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
document.addEventListener("pointerdown",event=>{
  const panel=document.querySelector(".transition-label-inspector:not([hidden])");
  if(panel&&!panel.contains(event.target)&&!event.target?.closest?.(".transition-io-cluster"))restoreInspectorFocus=false;
  const target=event.target?.closest?.(pointerTargetSelector);if(!target)return;
  pointerSessions.set(event.pointerId,{target,pointerId:event.pointerId,clientX:event.clientX,clientY:event.clientY,button:event.button});
},true);
document.addEventListener("pointermove",event=>{
  const record=pointerSessions.get(event.pointerId);if(!record)return;record.clientX=event.clientX;record.clientY=event.clientY;
},true);
document.addEventListener("pointerup",event=>pointerSessions.delete(event.pointerId),true);
document.addEventListener("lostpointercapture",event=>pointerSessions.delete(event.pointerId),true);
document.addEventListener("pointercancel",event=>{
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

for(const eventName of["glyph-transition-layout-ready","glyph-transition-layout-transaction-ready","glyph-state-transition-ir-v3-labels-ready","glyph-locale-changed","glyph-save-state-changed"]){document.addEventListener(eventName,scheduleEnhance)}
document.addEventListener("change",scheduleEnhance);
const tabsRoot=document.querySelector(".tabs");
if(tabsRoot)new MutationObserver(setupTabs).observe(tabsRoot,{subtree:true,attributes:true,attributeFilter:["class"]});
new MutationObserver(scheduleEnhance).observe(document.getElementById("main")||document.body,{childList:true,subtree:true});
window.glyphDiagramGuiUxGuard={marker:MARKER,version:1,refresh:scheduleEnhance,activePointers:()=>pointerSessions.size};
enhance();requestAnimationFrame(setupTabs);
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
