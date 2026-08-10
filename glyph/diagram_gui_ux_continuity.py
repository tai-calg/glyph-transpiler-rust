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
const MODAL_FOCUSABLE='button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
const FOCUS_REQUEST_TTL_MS=2000;
let enhanceFrame=0,pendingNodeFocus=null,pendingNodeFocusTimer=0,pendingControlFocus=null,pendingControlFocusTimer=0;
const nodeName=node=>node?.querySelector?.(".state-name")?.textContent?.trim()||"";
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const english=()=>String(document.documentElement.lang||"ja").startsWith("en");
const machineIndex=()=>String(document.getElementById("machine-select")?.value||"0");
const diagramDigest=()=>String(document.querySelector(".state-node")?.closest(".graph-stage")?.dataset.diagramDigest||document.querySelector(".graph-stage")?.dataset.diagramDigest||"");

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
    if(element.dataset.guiUxContinuityJumpReady==="true")continue;
    element.dataset.guiUxContinuityJumpReady="true";
    element.addEventListener("keydown",event=>{
      if(event.key!=="Enter"&&event.key!==" ")return;
      event.preventDefault();event.stopImmediatePropagation();activateLineJump(element,line);
    },true);
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
function modalFocusables(modal){
  return[...modal.querySelectorAll(MODAL_FOCUSABLE)].filter(element=>{
    if(element.closest("[inert]"))return false;
    const style=getComputedStyle(element);
    return style.visibility!=="hidden"&&style.display!=="none"&&element.getClientRects().length>0;
  });
}
function trapModalTab(event,modal){
  if(event.key!=="Tab")return false;
  const items=modalFocusables(modal);
  event.preventDefault();event.stopImmediatePropagation();
  if(!items.length){
    if(!modal.hasAttribute("tabindex"))modal.tabIndex=-1;
    modal.focus({preventScroll:true});return true;
  }
  const active=document.activeElement,index=items.indexOf(active);
  let nextIndex;
  if(index<0)nextIndex=event.shiftKey?items.length-1:0;
  else nextIndex=event.shiftKey?(index-1+items.length)%items.length:(index+1)%items.length;
  items[nextIndex].focus({preventScroll:true});return true;
}
function setupSettingsFocus(){
  const button=document.getElementById("glyph-settings"),dialog=document.getElementById("glyph-settings-dialog");
  if(!button||!dialog||dialog.dataset.guiUxFocusReturnReady==="true")return;
  dialog.dataset.guiUxFocusReturnReady="true";
  if(!dialog.hasAttribute("tabindex"))dialog.tabIndex=-1;
  dialog.addEventListener("close",()=>requestAnimationFrame(()=>{
    const active=document.activeElement;
    const neutral=!active||active===document.body||active===document.documentElement||!active.isConnected||dialog.contains(active);
    if(neutral&&button.isConnected)button.focus({preventScroll:true});
  }));
}
function clearPendingNodeFocus(){
  pendingNodeFocus=null;
  if(pendingNodeFocusTimer){clearTimeout(pendingNodeFocusTimer);pendingNodeFocusTimer=0}
}
function armNodeFocus(name){
  if(!name)return;
  pendingNodeFocus={name,machineIndex:machineIndex(),diagramDigest:diagramDigest()};
  if(pendingNodeFocusTimer)clearTimeout(pendingNodeFocusTimer);
  pendingNodeFocusTimer=setTimeout(clearPendingNodeFocus,FOCUS_REQUEST_TTL_MS);
}
function restoreNodeFocus(){
  if(!pendingNodeFocus)return;
  const expected=pendingNodeFocus;
  requestAnimationFrame(()=>{
    if(pendingNodeFocus!==expected)return;
    if(machineIndex()!==expected.machineIndex||diagramDigest()!==expected.diagramDigest){clearPendingNodeFocus();return}
    const target=[...document.querySelectorAll(".state-node")].find(node=>nodeName(node)===expected.name);
    if(!target)return;
    const active=document.activeElement;
    if(active===target){clearPendingNodeFocus();return}
    const activeStateName=active?.classList?.contains("state-node")?nodeName(active):"";
    if(activeStateName===expected.name){clearPendingNodeFocus();return}
    const neutral=!active||active===document.body||active===document.documentElement||!active.isConnected;
    if(neutral)target.focus({preventScroll:true});
    clearPendingNodeFocus();
  });
}
function clearPendingControlFocus(){
  pendingControlFocus=null;
  if(pendingControlFocusTimer){clearTimeout(pendingControlFocusTimer);pendingControlFocusTimer=0}
}
function armControlFocus(target){
  if(!target||!(target.id==="machine-select"||target.id==="system-select"))return;
  pendingControlFocus={id:target.id,value:String(target.value||"")};
  if(pendingControlFocusTimer)clearTimeout(pendingControlFocusTimer);
  pendingControlFocusTimer=setTimeout(clearPendingControlFocus,FOCUS_REQUEST_TTL_MS);
  requestAnimationFrame(restoreControlFocus);
}
function restoreControlFocus(){
  if(!pendingControlFocus)return;
  const expected=pendingControlFocus,target=document.getElementById(expected.id);
  if(!target)return;
  if(String(target.value||"")!==expected.value){clearPendingControlFocus();return}
  const active=document.activeElement;
  const neutral=!active||active===document.body||active===document.documentElement||!active.isConnected;
  if(neutral)target.focus({preventScroll:true});
  clearPendingControlFocus();
}
function editorIndentBlock(editor,runtime,shift){
  const source=editor.value,start=editor.selectionStart||0,end=editor.selectionEnd||start;
  if(start===end){
    if(!shift){runtime.replaceRange(start,end,"  ");return true}
    const lineStart=source.lastIndexOf("\n",Math.max(0,start-1))+1;
    const indent=source.slice(lineStart).match(/^(?:\t| {1,2})/)?.[0]||"";
    if(!indent)return false;
    runtime.replaceRange(lineStart,lineStart+indent.length,"");
    const caret=Math.max(lineStart,start-indent.length);
    editor.setSelectionRange(caret,caret);
    return true;
  }
  const blockStart=source.lastIndexOf("\n",Math.max(0,start-1))+1;
  let probe=end;
  if(probe>blockStart&&source[probe-1]==="\n")probe-=1;
  const newlineAfter=source.indexOf("\n",probe);
  const blockEnd=newlineAfter<0?source.length:newlineAfter;
  const block=source.slice(blockStart,blockEnd);
  const replacement=block.split("\n").map(line=>shift?line.replace(/^(?:\t| {1,2})/,""):`  ${line}`).join("\n");
  if(replacement===block)return false;
  runtime.replaceRange(blockStart,blockEnd,replacement,{select:"replacement"});
  return true;
}
function handleEditorTab(event){
  if(event.key!=="Tab"||event.ctrlKey||event.metaKey||event.altKey)return;
  const editor=document.getElementById("editor"),runtime=window.GlyphEditorDocument;
  if(event.target!==editor||!runtime||event.isComposing||runtime.compositionActive?.())return;
  const completionOpen=editor.getAttribute("aria-expanded")==="true";
  if(!event.shiftKey&&completionOpen)return;
  event.preventDefault();event.stopImmediatePropagation();
  if(event.shiftKey)window.GlyphEditorCompletion?.close?.();
  editorIndentBlock(editor,runtime,event.shiftKey);
}
function enhance(){enhanceFrame=0;setupLineJumps();setupCanvasKeyboard();setupSettingsFocus();restoreNodeFocus();restoreControlFocus()}
function scheduleEnhance(){if(enhanceFrame)return;enhanceFrame=requestAnimationFrame(enhance)}

window.addEventListener("keydown",handleEditorTab,true);
window.addEventListener("keydown",event=>{
  const modal=document.querySelector("dialog[open]");
  const command=event.ctrlKey||event.metaKey;
  if(modal&&event.key==="Tab"){trapModalTab(event,modal);return}
  if(modal&&command&&event.key==="Enter"){
    event.preventDefault();event.stopImmediatePropagation();return;
  }
  if(modal&&event.key==="Escape"){
    event.stopPropagation();return;
  }
  if(modal||!event.key.startsWith("Arrow"))return;
  const node=event.target?.closest?.(".state-node");
  if(!node||document.activeElement!==node)return;
  armNodeFocus(nodeName(node));
},true);
window.addEventListener("change",event=>armControlFocus(event.target),true);

document.addEventListener("glyph-transition-layout-transaction-ready",()=>{scheduleEnhance();restoreNodeFocus();restoreControlFocus()});
document.addEventListener("glyph-transition-layout-ready",()=>{scheduleEnhance();restoreNodeFocus();restoreControlFocus()});
for(const eventName of["glyph-state-transition-ir-v3-labels-ready","glyph-locale-changed"]){document.addEventListener(eventName,scheduleEnhance)}
document.addEventListener("change",scheduleEnhance);
new MutationObserver(()=>{scheduleEnhance();restoreNodeFocus();restoreControlFocus()}).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphDiagramGuiUxContinuity={marker:MARKER,version:5,refresh:scheduleEnhance,pendingNodeFocus:()=>pendingNodeFocus?.name||"",pendingControlFocus:()=>pendingControlFocus?{...pendingControlFocus}:null};
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
