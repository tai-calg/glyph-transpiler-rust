from __future__ import annotations


_MARKER = "glyph-editor-identifier-highlight-v1"

_STYLE = r"""
<style id="glyph-editor-identifier-highlight-v1-style">
.editor-wrap{position:relative}
.identifier-highlight-surface{
  position:absolute;
  z-index:3;
  display:none;
  overflow:hidden;
  background:transparent;
  pointer-events:none;
}
.editor-wrap.identifier-highlight-active>.identifier-highlight-surface{display:block}
.identifier-highlight-layer{
  position:absolute;
  top:0;
  left:0;
  margin:0;
  min-width:100%;
  min-height:100%;
  padding:14px 17px 50px;
  border:0;
  white-space:pre;
  tab-size:2;
  color:transparent;
  background:transparent;
  pointer-events:none;
  user-select:none;
  font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
}
.identifier-highlight-layer mark{
  margin:0;
  padding:0;
  border-radius:3px;
  color:transparent;
  background:rgba(148,163,184,.24);
  box-shadow:0 0 0 1px rgba(148,163,184,.13);
}
.editor-wrap>.lines{
  position:relative;
  z-index:4;
}
.editor-wrap>.editor{
  position:relative;
  z-index:1;
}
.theme-monochrome .identifier-highlight-layer mark{
  background:rgba(0,0,0,.12)!important;
  box-shadow:0 0 0 1px rgba(0,0,0,.14)!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-editor-identifier-highlight-v1-script">
(()=>{
const MARKER="glyph-editor-identifier-highlight-v1";
const IDENTIFIER=/^[A-Za-z_][A-Za-z0-9_]*$/;
const SOURCE_IDENTIFIER=/[A-Za-z_][A-Za-z0-9_]*/g;
const sourceEditor=document.getElementById("editor");
if(!sourceEditor||sourceEditor.dataset.identifierHighlightReady==="true")return;
const parent=sourceEditor.parentElement;
const surface=document.createElement("div");
surface.className="identifier-highlight-surface";
const highlight=document.createElement("pre");
highlight.className="identifier-highlight-layer";
highlight.id="identifier-highlight-layer";
highlight.setAttribute("aria-hidden","true");
surface.append(highlight);
parent.insertBefore(surface,sourceEditor);
sourceEditor.dataset.identifierHighlightReady="true";
let frame=0,lastValue="",lastStart=-1,lastEnd=-1,lastFocused=false,currentIdentifier="",matchCount=0;
const esc=value=>String(value??"").replace(/[&<>]/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[char]));
function identifierAt(value,start,end,focused){
  if(!focused)return"";
  if(start!==end){
    const selected=value.slice(start,end);
    return IDENTIFIER.test(selected)?selected:"";
  }
  let left=start,right=start;
  while(left>0&&/[A-Za-z0-9_]/.test(value[left-1]))left-=1;
  while(right<value.length&&/[A-Za-z0-9_]/.test(value[right]))right+=1;
  const candidate=value.slice(left,right);
  return IDENTIFIER.test(candidate)?candidate:"";
}
function renderHtml(value,identifier){
  if(!identifier)return esc(value)||"\u200b";
  let html="",cursor=0,count=0;
  SOURCE_IDENTIFIER.lastIndex=0;
  for(let match=SOURCE_IDENTIFIER.exec(value);match;match=SOURCE_IDENTIFIER.exec(value)){
    const token=match[0],index=match.index;
    html+=esc(value.slice(cursor,index));
    if(token===identifier){html+=`<mark>${esc(token)}</mark>`;count+=1}
    else html+=esc(token);
    cursor=index+token.length;
  }
  html+=esc(value.slice(cursor));
  matchCount=count;
  return html||"\u200b";
}
function syncGeometry(){
  const parentRect=parent.getBoundingClientRect(),editorRect=sourceEditor.getBoundingClientRect();
  surface.style.left=`${editorRect.left-parentRect.left}px`;
  surface.style.top=`${editorRect.top-parentRect.top}px`;
  surface.style.width=`${editorRect.width}px`;
  surface.style.height=`${editorRect.height}px`;
  highlight.style.width=`${Math.max(sourceEditor.clientWidth,sourceEditor.scrollWidth)}px`;
  highlight.style.height=`${Math.max(sourceEditor.clientHeight,sourceEditor.scrollHeight)}px`;
  highlight.style.transform=`translate(${-sourceEditor.scrollLeft}px,${-sourceEditor.scrollTop}px)`;
}
function render(force=false){
  frame=0;
  const value=sourceEditor.value,start=sourceEditor.selectionStart||0,end=sourceEditor.selectionEnd||0,focused=document.activeElement===sourceEditor;
  if(!force&&value===lastValue&&start===lastStart&&end===lastEnd&&focused===lastFocused){syncGeometry();return}
  const identifier=identifierAt(value,start,end,focused);
  currentIdentifier=identifier;
  matchCount=0;
  highlight.innerHTML=renderHtml(value,identifier);
  const active=Boolean(focused&&identifier);
  parent.classList.toggle("identifier-highlight-active",active);
  surface.dataset.identifier=identifier;
  surface.dataset.identifierMatchCount=String(matchCount);
  sourceEditor.dataset.activeIdentifier=identifier;
  sourceEditor.dataset.identifierMatchCount=String(matchCount);
  lastValue=value;lastStart=start;lastEnd=end;lastFocused=focused;
  syncGeometry();
  document.dispatchEvent(new CustomEvent("glyph-editor-identifier-highlighted",{detail:{marker:MARKER,identifier,matchCount}}));
}
function schedule(force=false){
  if(force)lastValue="\u0000";
  if(frame)return;
  frame=requestAnimationFrame(()=>render(force));
}
for(const eventName of["input","keyup","mouseup","select","click","focus","blur"]){sourceEditor.addEventListener(eventName,()=>schedule())}
sourceEditor.addEventListener("scroll",syncGeometry,{passive:true});
document.addEventListener("selectionchange",()=>{if(document.activeElement===sourceEditor)schedule()});
const status=document.getElementById("status");
if(status)new MutationObserver(()=>schedule(true)).observe(status,{childList:true,subtree:true,attributes:true});
new ResizeObserver(()=>schedule(true)).observe(sourceEditor);
for(const eventName of["glyph-locale-changed","glyph-transition-layout-transaction-ready"]){document.addEventListener(eventName,()=>schedule(true))}
schedule(true);
window.glyphEditorIdentifierHighlight={
  marker:MARKER,
  version:2,
  identifier:()=>currentIdentifier,
  matchCount:()=>matchCount,
  refresh:()=>schedule(true),
};
})();
</script>
"""


def enhance_editor_identifier_highlight_html(html: str) -> str:
    """Highlight every exact lexical occurrence without obscuring the editor."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_editor_identifier_highlight_html"]
