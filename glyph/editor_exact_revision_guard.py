from __future__ import annotations


_MARKER = "glyph-editor-exact-revision-guard-v1"

_SCRIPT = r"""
<script id="glyph-editor-exact-revision-guard-v1-script">
(()=>{
const MARKER="glyph-editor-exact-revision-guard-v1";
const editor=document.getElementById("editor");
const lexicalIndex=window.GlyphEditorLexicalIndex;
const completion=window.GlyphEditorCompletion;
const highlightApi=window.glyphEditorIdentifierHighlight;
const documentRuntime=window.GlyphEditorDocument;
const popup=document.getElementById("glyph-completion-popup");
if(!editor||!lexicalIndex||!completion||!highlightApi||!documentRuntime||editor.dataset.exactRevisionGuardReady==="true")return;
editor.dataset.exactRevisionGuardReady="true";
const parent=editor.parentElement;
const surface=parent?.querySelector(".identifier-highlight-surface");
const metrics={completionInvalidations:0,highlightInvalidations:0,staleUiObservations:0,staleAcceptBlocks:0};

function exactSnapshot(){
  const snapshot=lexicalIndex.snapshot?.();
  return Boolean(snapshot&&Number(snapshot.revision)===Number(documentRuntime.revision()));
}
function completionNeedsExactSnapshot(){
  return completion.candidates?.().some(candidate=>candidate?.origin==="document")===true;
}
function clearHighlightDom(){
  const active=Boolean(
    editor.dataset.activeIdentifier
    || editor.dataset.identifierMatchCount!=="0"
    || parent?.classList.contains("identifier-highlight-active")
  );
  if(active)metrics.highlightInvalidations+=1;
  parent?.classList.remove("identifier-highlight-active");
  if(surface){surface.dataset.identifier="";surface.dataset.identifierMatchCount="0"}
  editor.dataset.activeIdentifier="";
  editor.dataset.identifierMatchCount="0";
}
function hideCompletionPublication(){
  if(!popup||popup.hidden||!completionNeedsExactSnapshot())return;
  metrics.completionInvalidations+=1;
  // Preserve the controller's candidate/revalidation state. Only the stale visual
  // publication is invalidated; strict accept() may still defer to an exact snapshot.
  popup.hidden=true;
  popup.replaceChildren();
  editor.setAttribute("aria-expanded","false");
  editor.removeAttribute("aria-activedescendant");
  const status=document.getElementById("glyph-completion-status");
  if(status)status.textContent="";
}
function invalidateVisibleDocumentState(){
  hideCompletionPublication();
  clearHighlightDom();
}
function verifyVisibleExactness(){
  if(exactSnapshot())return;
  const stalePopup=Boolean(popup&&!popup.hidden&&completionNeedsExactSnapshot());
  const staleHighlight=Boolean(editor.dataset.activeIdentifier||parent?.classList.contains("identifier-highlight-active"));
  if(stalePopup||staleHighlight){
    metrics.staleUiObservations+=1;
    invalidateVisibleDocumentState();
  }
}

for(const eventName of[
  "glyph-editor-document-changed",
  "glyph-editor-source-replaced",
  "glyph-editor-lexical-index-invalidated",
  "glyph-editor-lexical-index-error",
  "glyph-editor-lexical-index-recovery-exhausted",
]){
  document.addEventListener(eventName,invalidateVisibleDocumentState);
}
document.addEventListener("glyph-editor-lexical-index-updated",verifyVisibleExactness);

const originalAccept=completion.accept?.bind(completion);
if(originalAccept)completion.accept=()=>{
  if(!completionNeedsExactSnapshot()||exactSnapshot())return originalAccept();
  const context=completion.context?.();
  // Strict contexts intentionally retain the existing deferred exact-snapshot
  // validation path. Non-strict document candidates must never be accepted stale.
  if(context?.strict)return originalAccept();
  metrics.staleAcceptBlocks+=1;
  hideCompletionPublication();
  return false;
};

const originalIdentifier=highlightApi.identifier?.bind(highlightApi);
const originalMatchCount=highlightApi.matchCount?.bind(highlightApi);
if(originalIdentifier)highlightApi.identifier=()=>exactSnapshot()?originalIdentifier():"";
if(originalMatchCount)highlightApi.matchCount=()=>exactSnapshot()?originalMatchCount():0;

window.glyphEditorExactRevisionGuard={
  marker:MARKER,
  version:1,
  exact:exactSnapshot,
  invalidate:invalidateVisibleDocumentState,
  metrics:()=>({...metrics}),
};
verifyVisibleExactness();
})();
</script>
"""


def enhance_editor_exact_revision_guard_html(html: str) -> str:
    """Synchronously hide document-derived editor UI whenever lexical state is stale."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_exact_revision_guard_html"]
