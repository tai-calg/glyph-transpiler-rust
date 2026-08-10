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
let recoveryFailures=0,recoveryTimer=0,recoveryIssued=false;
let viewportFrame=0;
const metrics={dismissSuppressedReopens:0,guardRecoveries:0,recoveryCycles:0,viewportRelays:0};

function normalizeOptions(){
  for(const option of popup.querySelectorAll('[role="option"]'))option.tabIndex=-1;
}
function publishStatus(){
  normalizeOptions();
  if(popup.hidden){status.textContent="";return}
  const count=popup.querySelectorAll('[role="option"]').length;
  status.textContent=count?`${count} completion candidate${count===1?"":"s"}`:"";
}
function blockSuppressedReopen(){
  if(!suppressAutomaticReopen||popup.hidden)return;
  metrics.dismissSuppressedReopens+=1;
  completion.close();
}
const popupObserver=new MutationObserver(()=>{
  publishStatus();
  blockSuppressedReopen();
});
popupObserver.observe(popup,{childList:true,subtree:true,attributes:true,attributeFilter:["hidden"]});
publishStatus();

editor.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&!popup.hidden&&!event.isComposing){suppressAutomaticReopen=true;return}
  if((event.ctrlKey||event.metaKey)&&event.code==="Space")suppressAutomaticReopen=false;
},true);
editor.addEventListener("input",()=>{suppressAutomaticReopen=false},true);
editor.addEventListener("compositionend",()=>{suppressAutomaticReopen=false},true);

function exactSnapshot(){
  const snapshot=lexicalIndex.snapshot?.();
  return Boolean(snapshot&&Number(snapshot.revision)===Number(documentRuntime.revision()));
}
function clearRecoveryTimer(){
  if(recoveryTimer){clearTimeout(recoveryTimer);recoveryTimer=0}
}
function resetRecovery(){
  recoveryFailures=0;
  recoveryIssued=false;
  clearRecoveryTimer();
}
function recoverWorker(){
  recoveryTimer=0;
  if(exactSnapshot()){resetRecovery();return}
  const state=lexicalIndex.metrics?.()||{};
  if(state.inFlight){recoveryTimer=setTimeout(recoverWorker,250);return}
  if(recoveryFailures===1&&!recoveryIssued){
    recoveryIssued=true;
    metrics.guardRecoveries+=1;
    lexicalIndex.invalidate?.();
    recoveryTimer=setTimeout(recoverWorker,500);
  }
}
function armWorkerRecovery(){
  if(recoveryFailures===0)metrics.recoveryCycles+=1;
  recoveryFailures+=1;
  if(!recoveryTimer)recoveryTimer=setTimeout(recoverWorker,250);
}
document.addEventListener("glyph-editor-lexical-index-error",armWorkerRecovery);
document.addEventListener("glyph-editor-lexical-index-updated",event=>{
  if(event.detail?.exact)resetRecovery();
});

function relayVisualViewport(){
  if(viewportFrame)return;
  viewportFrame=requestAnimationFrame(()=>{
    viewportFrame=0;
    metrics.viewportRelays+=1;
    window.dispatchEvent(new Event("resize"));
  });
}
if(window.visualViewport){
  window.visualViewport.addEventListener("resize",relayVisualViewport,{passive:true});
  window.visualViewport.addEventListener("scroll",relayVisualViewport,{passive:true});
}

window.glyphEditorCompletionUxGuard={
  marker:MARKER,
  version:1,
  metrics:()=>({...metrics,recoveryFailures,recoveryIssued,suppressAutomaticReopen}),
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
