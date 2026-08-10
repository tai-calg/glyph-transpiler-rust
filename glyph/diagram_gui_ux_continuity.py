from __future__ import annotations


_MARKER = "glyph-diagram-gui-ux-continuity-v1"

_STYLE = r"""
<style id="glyph-diagram-gui-ux-continuity-v1-style">
.graph-node[data-line]:focus-visible,
.type-card[data-line]:focus-visible,
.edge-label[data-line]:focus-visible{
  outline:2px solid var(--blue);
  outline-offset:2px;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-gui-ux-continuity-v1-script">
(()=>{
const MARKER="glyph-diagram-gui-ux-continuity-v1";
if(window.glyphDiagramGuiUxContinuity?.marker===MARKER)return;
const LINE_JUMP_SELECTOR=".diagnostic[data-line],.analysis-item[data-line],.graph-node[data-line],.type-card[data-line],.edge-label[data-line]";
let enhanceFrame=0,pendingNodeFocusName="",pendingNodeFocusTimer=0;
const nodeName=node=>node?.querySelector?.(".state-name")?.textContent?.trim()||"";
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const english=()=>String(document.documentElement.lang||"ja").startsWith("en");

function lineJumpLabel(element,line){
  const subject=(element.getAttribute("title")||element.querySelector?.(".node-name,.type-name")?.textContent||element.textContent||"").trim().replace(/\s+/g," ");
  const prefix=english()?`Source line ${line}`:`ソース ${line} 行目`;
  return subject?`${subject} · ${prefix}`:prefix;
}
function ownLocalizedLabel(element,value){
  if(!element.getAttribute("aria-label"))element.dataset.guiUxContinuityLabel="true";
  if(element.dataset.guiUxContinuityLabel==="true")element.setAttribute("aria-label",value);
}
function activateLineJump(element,line){
  if(typeof globalThis.jumpToLine==="function"){globalThis.jumpToLine(line);return}
  element.click();
}
function setupLineJumps(){
  for(const element of document.querySelectorAll(LINE_JUMP_SELECTOR)){
    const line=Number(element.dataset.line||0);if(line<=0)continue;
    element.tabIndex=0;element.setAttribute("role","button");
    ownLocalizedLabel(element,lineJumpLabel(element,line));
    if(element.dataset.guiUxJumpReady==="true")continue;
    element.dataset.guiUxJumpReady="true";
    element.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();event.stopPropagation();activateLineJump(element,line);
    });
  }
}
function setupCanvasKeyboard(){
  for(const shell of document.querySelectorAll(".canvas-shell")){
    shell.tabIndex=0;shell.setAttribute("role","region");
    shell.setAttribute("aria-keyshortcuts","ArrowUp ArrowDown ArrowLeft ArrowRight");
    ownLocalizedLabel(shell,english()?"Diagram canvas; use Arrow keys to pan":"図キャンバス。矢印キーで移動");
    if(shell.dataset.guiUxKeyboardPanReady==="true")continue;
    shell.dataset.guiUxKeyboardPanReady="true";
    shell.addEventListener("keydown",event=>{
      if(event.target!==shell||event.ctrlKey||event.metaKey||event.altKey)return;
      const step=event.shiftKey?160:48;
      let dx=0,dy=0;
      if(event.key==="ArrowLeft")dx=-step;
      else if(event.key==="ArrowRight")dx=step;
      else if(event.key==="ArrowUp")dy=-step;
      else if(event.key==="ArrowDown")dy=step;
      else return;
      const nextLeft=clamp(shell.scrollLeft+dx,0,Math.max(0,shell.scrollWidth-shell.clientWidth));
      const nextTop=clamp(shell.scrollTop+dy,0,Math.max(0,shell.scrollHeight-shell.clientHeight));
      if(nextLeft===shell.scrollLeft&&nextTop===shell.scrollTop)return;
      event.preventDefault();event.stopPropagation();
      shell.scrollLeft=nextLeft;shell.scrollTop=nextTop;
    });
  }
}
function setupSettingsFocus(){
  const button=document.getElementById("glyph-settings"),dialog=document.getElementById("glyph-settings-dialog");
  if(!button||!dialog||dialog.dataset.guiUxFocusReturnReady==="true")return;
  dialog.dataset.guiUxFocusReturnReady="true";
  dialog.addEventListener("close",()=>requestAnimationFrame(()=>{
    const active=document.activeElement;
    const neutral=!active||active===document.body||active===document.documentElement||!active.isConnected||dialog.contains(active);
    if(neutral&&button.isConnected)button.focus({preventScroll:true});
  }));
}
function clearPendingNodeFocus(){
  pendingNodeFocusName="";
  if(pendingNodeFocusTimer){clearTimeout(pendingNodeFocusTimer);pendingNodeFocusTimer=0}
}
function armNodeFocus(name){
  if(!name)return;
  pendingNodeFocusName=name;
  if(pendingNodeFocusTimer)clearTimeout(pendingNodeFocusTimer);
  pendingNodeFocusTimer=setTimeout(clearPendingNodeFocus,2000);
}
function restoreNodeFocus(){
  if(!pendingNodeFocusName)return;
  const expected=pendingNodeFocusName;
  requestAnimationFrame(()=>{
    if(pendingNodeFocusName!==expected)return;
    const target=[...document.querySelectorAll(".state-node")].find(node=>nodeName(node)===expected);
    if(!target)return;
    const active=document.activeElement;
    if(active===target){clearPendingNodeFocus();return}
    const activeStateName=active?.classList?.contains("state-node")?nodeName(active):"";
    if(activeStateName===expected){clearPendingNodeFocus();return}
    const neutral=!active||active===document.body||active===document.documentElement||!active.isConnected;
    if(neutral)target.focus({preventScroll:true});
    clearPendingNodeFocus();
  });
}
function enhance(){enhanceFrame=0;setupLineJumps();setupCanvasKeyboard();setupSettingsFocus();restoreNodeFocus()}
function scheduleEnhance(){if(enhanceFrame)return;enhanceFrame=requestAnimationFrame(enhance)}

window.addEventListener("keydown",event=>{
  const modal=document.querySelector("dialog[open]");
  const command=event.ctrlKey||event.metaKey;
  if(modal&&command&&event.key==="Enter"){
    event.preventDefault();event.stopImmediatePropagation();return;
  }
  if(modal||!event.key.startsWith("Arrow"))return;
  const node=event.target?.closest?.(".state-node");
  if(!node||document.activeElement!==node)return;
  armNodeFocus(nodeName(node));
},true);

document.addEventListener("glyph-transition-layout-transaction-ready",()=>{scheduleEnhance();restoreNodeFocus()});
document.addEventListener("glyph-transition-layout-ready",()=>{scheduleEnhance();restoreNodeFocus()});
for(const eventName of["glyph-state-transition-ir-v3-labels-ready","glyph-locale-changed"]){document.addEventListener(eventName,scheduleEnhance)}
document.addEventListener("change",scheduleEnhance);
new MutationObserver(()=>{scheduleEnhance();restoreNodeFocus()}).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphDiagramGuiUxContinuity={marker:MARKER,version:1,refresh:scheduleEnhance,pendingNodeFocus:()=>pendingNodeFocusName};
enhance();requestAnimationFrame(enhance);
})();
</script>
"""


def enhance_diagram_gui_ux_continuity_html(html: str) -> str:
    """Close residual keyboard ownership and focus-continuity gaps in Studio."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_diagram_gui_ux_continuity_html"]
