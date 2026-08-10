from __future__ import annotations


_MARKER = "glyph-editor-completion-performance-v1"

_SCRIPT = r"""
<script id="glyph-editor-completion-performance-v1-script">
(()=>{
const MARKER="glyph-editor-completion-performance-v1";
function install(){
  const editor=document.getElementById("editor");
  const documentRuntime=window.GlyphEditorDocument;
  const lexicalIndex=window.GlyphEditorLexicalIndex;
  if(!editor||!documentRuntime||!lexicalIndex||editor.dataset.completionPerformanceReady==="true")return;
  let timer=0,lastInputAt=0,burst=0;
  const metrics={refreshes:0,scheduled:0,cancelled:0,lastDelayMs:0,peakBurst:0};
  const clear=()=>{if(timer){clearTimeout(timer);timer=0;metrics.cancelled+=1}};
  const adaptiveDelay=()=>{
    const now=performance.now();
    const delta=lastInputAt?now-lastInputAt:Number.POSITIVE_INFINITY;
    lastInputAt=now;
    burst=delta<45?Math.min(4,burst+1):0;
    metrics.peakBurst=Math.max(metrics.peakBurst,burst);
    if(burst>=3)return 20;
    if(burst>=1)return 12;
    return 6;
  };
  const schedule=delay=>{
    clear();metrics.scheduled+=1;metrics.lastDelayMs=delay;
    timer=setTimeout(()=>{
      timer=0;
      if(documentRuntime.compositionActive())return;
      if(lexicalIndex.refresh?.()){metrics.refreshes+=1}
    },delay);
  };
  document.addEventListener("glyph-editor-document-changed",event=>{
    if(event.detail?.composing)return;
    schedule(adaptiveDelay());
  });
  document.addEventListener("glyph-editor-composition-changed",event=>{
    if(event.detail?.active===false){burst=0;schedule(6)}
  });
  document.addEventListener("glyph-editor-source-replaced",()=>{clear();burst=0;lastInputAt=0});
  editor.dataset.completionPerformanceReady="true";
  window.GlyphEditorCompletionPerformance={marker:MARKER,metrics:()=>({...metrics,burst,pending:Boolean(timer)})};
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",install,{once:true});else install();
})();
</script>
"""


def enhance_editor_completion_performance_html(html: str) -> str:
    """Accelerate exact lexical refresh while leaving recovery ownership unchanged."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_completion_performance_html"]
