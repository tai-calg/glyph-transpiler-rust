from __future__ import annotations


_MARKER = "glyph-editor-completion-ux-guard-v1"

_STYLE = r"""
<style id="glyph-editor-completion-ux-guard-v1-style">
.glyph-completion-popup{
  min-width:min(210px,calc(100vw - 16px))!important;
  max-width:min(440px,calc(100vw - 16px))!important;
  max-height:min(260px,calc(100vh - 16px))!important;
  overscroll-behavior:contain;
}
.glyph-completion-status{
  position:fixed!important;
  width:1px!important;
  height:1px!important;
  padding:0!important;
  margin:-1px!important;
  overflow:hidden!important;
  clip:rect(0 0 0 0)!important;
  clip-path:inset(50%)!important;
  white-space:nowrap!important;
  border:0!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-editor-completion-ux-guard-v1-script">
(()=>{
const MARKER="glyph-editor-completion-ux-guard-v1";
const VIEWPORT_MARGIN=8;
const MAX_RECOVERY_ATTEMPTS=3;
const editor=document.getElementById("editor");
const popup=document.getElementById("glyph-completion-popup");
const completion=window.GlyphEditorCompletion;
const lexicalIndex=window.GlyphEditorLexicalIndex;
const documentRuntime=window.GlyphEditorDocument;
if(!editor||!popup||!completion||!lexicalIndex||!documentRuntime||editor.dataset.completionUxGuardReady==="true")return;
editor.dataset.completionUxGuardReady="true";
editor.setAttribute("aria-haspopup","listbox");

const status=document.createElement("div");
status.id="glyph-completion-status";
status.className="glyph-completion-status";
status.setAttribute("role","status");
status.setAttribute("aria-live","polite");
status.setAttribute("aria-atomic","true");
document.body.appendChild(status);

let suppressAutomaticReopen=false;
let recoveryFailures=0,recoveryAttempts=0,recoveryTimer=0,recoveryIssued=false;
let viewportRelayFrame=0,viewportClampFrame=0;
const metrics={dismissSuppressedReopens:0,stalePublicationBlocks:0,guardRecoveries:0,recoveryCycles:0,recoveryExhausted:0,viewportRelays:0,viewportClamps:0};

function exactSnapshot(){
  const snapshot=lexicalIndex.snapshot?.();
  return Boolean(snapshot&&Number(snapshot.revision)===Number(documentRuntime.revision()));
}
function normalizeOptions(){
  for(const option of popup.querySelectorAll('[role="option"]'))option.tabIndex=-1;
}
function visibleViewport(){
  const visual=window.visualViewport;
  return{
    left:Number(visual?.offsetLeft||0),
    top:Number(visual?.offsetTop||0),
    width:Number(visual?.width||window.innerWidth||0),
    height:Number(visual?.height||window.innerHeight||0),
  };
}
function clampPopupToViewport(){
  viewportClampFrame=0;
  if(popup.hidden)return;
  const viewport=visibleViewport();
  const availableWidth=Math.max(1,viewport.width-VIEWPORT_MARGIN*2);
  const availableHeight=Math.max(1,viewport.height-VIEWPORT_MARGIN*2);
  popup.style.setProperty("max-width",`${availableWidth}px`,"important");
  popup.style.setProperty("max-height",`${availableHeight}px`,"important");
  const rect=popup.getBoundingClientRect();
  const minimumLeft=viewport.left+VIEWPORT_MARGIN;
  const minimumTop=viewport.top+VIEWPORT_MARGIN;
  const maximumLeft=Math.max(minimumLeft,viewport.left+viewport.width-rect.width-VIEWPORT_MARGIN);
  const maximumTop=Math.max(minimumTop,viewport.top+viewport.height-rect.height-VIEWPORT_MARGIN);
  const currentLeft=Number.parseFloat(popup.style.left);
  const currentTop=Number.parseFloat(popup.style.top);
  const baseLeft=Number.isFinite(currentLeft)?currentLeft:rect.left;
  const baseTop=Number.isFinite(currentTop)?currentTop:rect.top;
  const nextLeft=Math.max(minimumLeft,Math.min(baseLeft,maximumLeft));
  const nextTop=Math.max(minimumTop,Math.min(baseTop,maximumTop));
  if(Math.abs(nextLeft-baseLeft)>.25||Math.abs(nextTop-baseTop)>.25)metrics.viewportClamps+=1;
  popup.style.left=`${nextLeft}px`;
  popup.style.top=`${nextTop}px`;
}
function scheduleViewportClamp(){
  if(viewportClampFrame)return;
  viewportClampFrame=requestAnimationFrame(clampPopupToViewport);
}
function hideStalePublication(){
  popup.hidden=true;
  popup.replaceChildren();
  editor.setAttribute("aria-expanded","false");
  editor.removeAttribute("aria-activedescendant");
  status.textContent="";
}
function blockStalePublication(){
  if(popup.hidden||exactSnapshot())return false;
  metrics.stalePublicationBlocks+=1;
  hideStalePublication();
  return true;
}
function publishStatus(){
  normalizeOptions();
  if(popup.hidden){status.textContent="";return}
  const count=popup.querySelectorAll('[role="option"]').length;
  status.textContent=count?`${count} completion candidate${count===1?"":"s"}`:"";
  scheduleViewportClamp();
}
function blockSuppressedReopen(){
  if(!suppressAutomaticReopen||popup.hidden)return;
  metrics.dismissSuppressedReopens+=1;
  completion.close();
}
const popupObserver=new MutationObserver(()=>{
  if(blockStalePublication())return;
  publishStatus();
  blockSuppressedReopen();
});
popupObserver.observe(popup,{childList:true,subtree:true,attributes:true,attributeFilter:["hidden"]});
if(!blockStalePublication())publishStatus();

editor.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&!popup.hidden&&!event.isComposing){suppressAutomaticReopen=true;return}
  if((event.ctrlKey||event.metaKey)&&event.code==="Space")suppressAutomaticReopen=false;
},true);
editor.addEventListener("input",()=>{suppressAutomaticReopen=false},true);
editor.addEventListener("compositionend",()=>{suppressAutomaticReopen=false},true);

function clearRecoveryTimer(){
  if(recoveryTimer){clearTimeout(recoveryTimer);recoveryTimer=0}
}
function resetRecovery(){
  recoveryFailures=0;
  recoveryAttempts=0;
  recoveryIssued=false;
  clearRecoveryTimer();
}
function recoverWorker(){
  recoveryTimer=0;
  if(exactSnapshot()){resetRecovery();return}
  const state=lexicalIndex.metrics?.()||{};
  if(state.inFlight){recoveryTimer=setTimeout(recoverWorker,250);return}
  if(recoveryAttempts>=MAX_RECOVERY_ATTEMPTS){
    metrics.recoveryExhausted+=1;
    recoveryIssued=false;
    return;
  }
  recoveryAttempts+=1;
  recoveryIssued=true;
  metrics.guardRecoveries+=1;
  lexicalIndex.invalidate?.();
  recoveryTimer=setTimeout(recoverWorker,500);
}
function armWorkerRecovery(){
  if(recoveryFailures===0){metrics.recoveryCycles+=1;recoveryAttempts=0}
  recoveryFailures+=1;
  clearRecoveryTimer();
  recoveryTimer=setTimeout(recoverWorker,100);
}
document.addEventListener("glyph-editor-lexical-index-error",armWorkerRecovery);
document.addEventListener("glyph-editor-lexical-index-updated",event=>{
  if(event.detail?.exact)resetRecovery();
});

function relayVisualViewport(){
  if(viewportRelayFrame)return;
  viewportRelayFrame=requestAnimationFrame(()=>{
    viewportRelayFrame=0;
    metrics.viewportRelays+=1;
    window.dispatchEvent(new Event("resize"));
    scheduleViewportClamp();
  });
}
window.addEventListener("resize",scheduleViewportClamp,{passive:true});
if(window.visualViewport){
  window.visualViewport.addEventListener("resize",relayVisualViewport,{passive:true});
  window.visualViewport.addEventListener("scroll",relayVisualViewport,{passive:true});
}

window.glyphEditorCompletionUxGuard={
  marker:MARKER,
  version:1,
  clamp:()=>{scheduleViewportClamp()},
  metrics:()=>({...metrics,recoveryFailures,recoveryAttempts,recoveryIssued,suppressAutomaticReopen}),
};
})();
</script>
"""


def enhance_editor_completion_ux_guard_html(html: str) -> str:
    """Harden completion focus, viewport fit, dismissal, and Worker recovery UX."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_editor_completion_ux_guard_html"]
