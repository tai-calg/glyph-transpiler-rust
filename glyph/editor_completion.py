from __future__ import annotations


_MARKER = "glyph-editor-completion-v1"

_STYLE = r"""
<style id="glyph-editor-completion-v1-style">
.glyph-completion-popup{
  position:fixed;
  z-index:80;
  min-width:180px;
  max-width:min(420px,calc(100vw - 24px));
  max-height:240px;
  overflow:auto;
  border:1px solid var(--line);
  border-radius:8px;
  background:var(--panel,#fff);
  color:var(--text);
  box-shadow:0 12px 32px rgba(0,0,0,.22);
  padding:4px;
}
.glyph-completion-popup[hidden]{display:none}
.glyph-completion-option{
  display:flex;
  align-items:center;
  gap:12px;
  width:100%;
  border:0;
  border-radius:6px;
  background:transparent;
  color:inherit;
  padding:6px 8px;
  text-align:left;
  font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
}
.glyph-completion-option[aria-selected="true"]{background:rgba(88,166,255,.16)}
.glyph-completion-option:hover{background:rgba(88,166,255,.11)}
.glyph-completion-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.glyph-completion-meta{margin-left:auto;color:var(--muted);font-size:10px;white-space:nowrap}
.glyph-completion-measure{position:fixed;left:-10000px;top:-10000px;visibility:hidden;white-space:pre;pointer-events:none}
</style>
"""

_SCRIPT = r"""
<script id="glyph-editor-completion-v1-script">
(()=>{
const MARKER="glyph-editor-completion-v1";
const MIN_PREFIX=2,MAX_RESULTS=8;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
const lexicalIndex=window.GlyphEditorLexicalIndex;
if(!editor||!documentRuntime||!lexicalIndex||editor.dataset.completionReady==="true")return;
const popup=document.createElement("div");
popup.id="glyph-completion-popup";
popup.className="glyph-completion-popup";
popup.hidden=true;
popup.setAttribute("role","listbox");
popup.setAttribute("aria-label","Glyph completion");
document.body.appendChild(popup);
const measure=document.createElement("span");
measure.className="glyph-completion-measure";
measure.setAttribute("aria-hidden","true");
document.body.appendChild(measure);
editor.setAttribute("aria-autocomplete","list");
editor.setAttribute("aria-controls",popup.id);
editor.setAttribute("aria-expanded","false");
let candidates=[],selected=0,frame=0,lastContext=null,explicit=false;
const metrics={queries:0,opens:0,accepts:0,staleAcceptRechecks:0};
const WORD=/[A-Za-z0-9_]/;
const IDENTIFIER=/^[A-Za-z_][A-Za-z0-9_]*$/;

function contextAtCaret({allowEmpty=false}={}){
  const source=editor.value;
  const start=editor.selectionStart||0,end=editor.selectionEnd||start;
  if(start!==end)return null;
  const caret=start;
  const lineStart=source.lastIndexOf("\n",Math.max(0,caret-1))+1;
  const hash=source.indexOf("#",lineStart);
  if(hash>=0&&hash<caret)return null;
  let left=caret,right=caret;
  while(left>lineStart&&WORD.test(source[left-1]))left-=1;
  while(right<source.length&&WORD.test(source[right]))right+=1;
  const prefix=source.slice(left,caret),current=source.slice(left,right);
  if(prefix&&!/^[A-Za-z_][A-Za-z0-9_]*$/.test(prefix))return null;
  if(!allowEmpty&&prefix.length<MIN_PREFIX)return null;
  if(!prefix&&left<right&&!allowEmpty)return null;
  return{source,caret,left,right,prefix,current,lineStart};
}
function close(){
  candidates=[];selected=0;lastContext=null;explicit=false;
  popup.hidden=true;popup.replaceChildren();
  editor.setAttribute("aria-expanded","false");
  editor.removeAttribute("aria-activedescendant");
}
function setSelected(index){
  if(!candidates.length)return;
  selected=(index+candidates.length)%candidates.length;
  [...popup.querySelectorAll('[role="option"]')].forEach((element,position)=>element.setAttribute("aria-selected",position===selected?"true":"false"));
  const active=popup.querySelector(`[data-index="${selected}"]`);
  if(active){editor.setAttribute("aria-activedescendant",active.id);active.scrollIntoView({block:"nearest"})}
}
function render(){
  popup.replaceChildren();
  candidates.forEach((candidate,index)=>{
    const option=document.createElement("button");
    option.type="button";option.className="glyph-completion-option";
    option.id=`glyph-completion-option-${index}`;option.dataset.index=String(index);
    option.setAttribute("role","option");option.setAttribute("aria-selected",index===selected?"true":"false");
    const label=document.createElement("span");label.className="glyph-completion-label";label.textContent=candidate.text;
    const meta=document.createElement("span");meta.className="glyph-completion-meta";meta.textContent=`×${candidate.count}`;
    option.append(label,meta);
    option.addEventListener("pointerdown",event=>{event.preventDefault();selected=index;accept()});
    popup.appendChild(option);
  });
  popup.hidden=!candidates.length;
  editor.setAttribute("aria-expanded",candidates.length?"true":"false");
  if(candidates.length){editor.setAttribute("aria-activedescendant",`glyph-completion-option-${selected}`);metrics.opens+=1;positionPopup()}
}
function linePrefixWidth(context){
  const style=getComputedStyle(editor);
  measure.style.font=style.font;
  measure.style.fontFamily=style.fontFamily;
  measure.style.fontSize=style.fontSize;
  measure.style.fontWeight=style.fontWeight;
  measure.style.fontStyle=style.fontStyle;
  measure.style.letterSpacing=style.letterSpacing;
  measure.style.tabSize=style.tabSize||"2";
  measure.textContent=context.source.slice(context.lineStart,context.caret)||"\u200b";
  return measure.getBoundingClientRect().width;
}
function positionPopup(){
  if(popup.hidden||!lastContext)return;
  const rect=editor.getBoundingClientRect(),style=getComputedStyle(editor);
  const paddingLeft=Number.parseFloat(style.paddingLeft)||0,paddingTop=Number.parseFloat(style.paddingTop)||0;
  const lineHeight=Number.parseFloat(style.lineHeight)||20;
  const row=Math.max(0,documentRuntime.caretLine()-1);
  let left=rect.left+paddingLeft+linePrefixWidth(lastContext)-editor.scrollLeft;
  let top=rect.top+paddingTop+row*lineHeight-editor.scrollTop+lineHeight+2;
  const width=Math.max(180,Math.min(420,popup.offsetWidth||260));
  left=Math.max(8,Math.min(left,innerWidth-width-8));
  const height=popup.offsetHeight||160;
  if(top+height>innerHeight-8)top=Math.max(8,rect.top+paddingTop+row*lineHeight-editor.scrollTop-height-2);
  popup.style.left=`${left}px`;popup.style.top=`${top}px`;
}
function update({force=false,allowEmpty=false}={}){
  frame=0;
  if(documentRuntime.compositionActive()){close();return}
  const context=contextAtCaret({allowEmpty});
  if(!context){close();return}
  metrics.queries+=1;
  const rows=lexicalIndex.query(context.prefix,context.caret,{limit:MAX_RESULTS,exclude:context.current});
  if(!rows.length){close();return}
  lastContext=context;candidates=rows;selected=0;explicit=allowEmpty||force;
  render();
}
function schedule(options={}){
  if(frame)cancelAnimationFrame(frame);
  frame=requestAnimationFrame(()=>update(options));
}
function inCodeOccurrence(source,text,excludeStart,excludeEnd){
  if(!IDENTIFIER.test(text))return false;
  let index=source.indexOf(text);
  while(index>=0){
    const before=index>0?source[index-1]:"",after=source[index+text.length]||"";
    const boundary=!WORD.test(before)&&!WORD.test(after);
    const lineStart=source.lastIndexOf("\n",Math.max(0,index-1))+1;
    const hash=source.indexOf("#",lineStart);
    const code=hash<0||hash>index;
    const outside=index+text.length<=excludeStart||index>=excludeEnd;
    if(boundary&&code&&outside)return true;
    index=source.indexOf(text,index+1);
  }
  return false;
}
function accept(){
  const candidate=candidates[selected];
  if(!candidate){close();return false}
  const context=contextAtCaret({allowEmpty:explicit});
  if(!context||!candidate.text.startsWith(context.prefix)){close();return false}
  metrics.staleAcceptRechecks+=1;
  if(!inCodeOccurrence(context.source,candidate.text,context.left,context.right)){close();return false}
  documentRuntime.replaceRange(context.left,context.right,candidate.text);
  metrics.accepts+=1;
  close();
  editor.focus();
  return true;
}

editor.addEventListener("keydown",event=>{
  if(event.isComposing||documentRuntime.compositionActive()){close();return}
  if((event.ctrlKey||event.metaKey)&&event.code==="Space"){
    event.preventDefault();event.stopPropagation();schedule({force:true,allowEmpty:true});return;
  }
  if(popup.hidden)return;
  if(event.key==="ArrowDown"){event.preventDefault();event.stopPropagation();setSelected(selected+1);return}
  if(event.key==="ArrowUp"){event.preventDefault();event.stopPropagation();setSelected(selected-1);return}
  if(event.key==="Tab"||event.key==="Enter"){event.preventDefault();event.stopPropagation();accept();return}
  if(event.key==="Escape"){event.preventDefault();event.stopPropagation();close()}
});
editor.addEventListener("input",event=>{if(event.isComposing)return;schedule()});
for(const eventName of["click","keyup","select"]){editor.addEventListener(eventName,event=>{if(eventName==="keyup"&&["ArrowUp","ArrowDown","Enter","Tab","Escape"].includes(event.key))return;schedule()})}
editor.addEventListener("compositionstart",close);
editor.addEventListener("compositionend",()=>schedule());
editor.addEventListener("scroll",()=>{if(!popup.hidden)requestAnimationFrame(positionPopup)},{passive:true});
editor.addEventListener("blur",()=>setTimeout(()=>{if(document.activeElement!==editor)close()},0));
window.addEventListener("resize",()=>{if(!popup.hidden)positionPopup()});
document.addEventListener("selectionchange",()=>{if(document.activeElement===editor&&!popup.hidden)schedule({allowEmpty:explicit})});
document.addEventListener("glyph-editor-source-replaced",close);
document.addEventListener("glyph-editor-lexical-index-updated",()=>{if(document.activeElement===editor)schedule({allowEmpty:explicit})});
editor.dataset.completionReady="true";
window.GlyphEditorCompletion={
  marker:MARKER,
  version:1,
  open:()=>schedule({force:true,allowEmpty:true}),
  close,
  accept,
  candidates:()=>candidates.map(candidate=>({...candidate})),
  selected:()=>selected,
  metrics:()=>({...metrics}),
};
})();
</script>
"""


def enhance_editor_completion_html(html: str) -> str:
    """Add document-local prefix completion backed by the shared lexical index."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_editor_completion_html"]
