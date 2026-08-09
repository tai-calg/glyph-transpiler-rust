from __future__ import annotations

from .editor_completion_context import enhance_editor_completion_context_html


_MARKER = "glyph-editor-completion-v2"

_STYLE = r"""
<style id="glyph-editor-completion-v2-style">
.glyph-completion-popup{
  position:fixed;
  z-index:80;
  min-width:210px;
  max-width:min(440px,calc(100vw - 24px));
  max-height:260px;
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
<script id="glyph-editor-completion-v2-script">
(()=>{
const MARKER="glyph-editor-completion-v2";
const MIN_PREFIX=2,MAX_RESULTS=8,QUERY_POOL=64,MAX_IDENTIFIER_TAIL=256;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
const lexicalIndex=window.GlyphEditorLexicalIndex;
const contextService=window.GlyphEditorCompletionContext;
if(!editor||!documentRuntime||!lexicalIndex||!contextService||editor.dataset.completionReady==="true")return;
const popup=document.createElement("div");
popup.id="glyph-completion-popup";popup.className="glyph-completion-popup";popup.hidden=true;
popup.setAttribute("role","listbox");popup.setAttribute("aria-label","Glyph completion");document.body.appendChild(popup);
const measure=document.createElement("span");measure.className="glyph-completion-measure";measure.setAttribute("aria-hidden","true");document.body.appendChild(measure);
editor.setAttribute("aria-autocomplete","list");editor.setAttribute("aria-controls",popup.id);editor.setAttribute("aria-expanded","false");
let candidates=[],selected=0,frame=0,lastContext=null,lastClassification=null,explicit=false,pendingAcceptance=null;
const metrics={queries:0,opens:0,accepts:0,staleAcceptRechecks:0,strictStaleAccepts:0,strictStaleDeferrals:0,contextFilteredQueries:0};
const WORD=/[A-Za-z0-9_]/;
const IDENTIFIER=/^[A-Za-z_][A-Za-z0-9_]*$/;

function contextAtCaret(){
  const source=editor.value;
  const start=editor.selectionStart||0,end=editor.selectionEnd||start;
  if(start!==end)return null;
  const caret=start;
  const lineStart=contextService.boundedLineStart(source,caret);
  if(lineStart===null)return null;
  const before=source.slice(lineStart,caret);
  if(before.includes("#"))return null;
  let left=caret,right=caret;
  while(left>lineStart&&WORD.test(source[left-1]))left-=1;
  const rightLimit=Math.min(source.length,caret+MAX_IDENTIFIER_TAIL);
  while(right<rightLimit&&WORD.test(source[right]))right+=1;
  if(right===rightLimit&&right<source.length&&WORD.test(source[right]))return null;
  const prefix=source.slice(left,caret),current=source.slice(left,right);
  if(prefix&&!/^[A-Za-z_][A-Za-z0-9_]*$/.test(prefix))return null;
  return{source,caret,left,right,prefix,current,lineStart};
}
function close(){
  candidates=[];selected=0;lastContext=null;lastClassification=null;explicit=false;
  popup.hidden=true;popup.replaceChildren();editor.setAttribute("aria-expanded","false");editor.removeAttribute("aria-activedescendant");
}
function setSelected(index){
  if(!candidates.length)return;
  selected=(index+candidates.length)%candidates.length;
  [...popup.querySelectorAll('[role="option"]')].forEach((element,position)=>element.setAttribute("aria-selected",position===selected?"true":"false"));
  const active=popup.querySelector(`[data-index="${selected}"]`);
  if(active){editor.setAttribute("aria-activedescendant",active.id);active.scrollIntoView({block:"nearest"})}
}
function displayKind(kind){return kind==="StateField"?"State field":kind||"Identifier"}
function render(){
  popup.replaceChildren();
  candidates.forEach((candidate,index)=>{
    const option=document.createElement("button");
    option.type="button";option.className="glyph-completion-option";option.id=`glyph-completion-option-${index}`;option.dataset.index=String(index);
    option.setAttribute("role","option");option.setAttribute("aria-selected",index===selected?"true":"false");
    const label=document.createElement("span");label.className="glyph-completion-label";label.textContent=candidate.text;
    const meta=document.createElement("span");meta.className="glyph-completion-meta";
    const details=[displayKind(candidate.kind)];
    if(candidate.owners?.length)details.push(candidate.owners[0]);
    if(candidate.count>1)details.push(`×${candidate.count}`);
    meta.textContent=details.join(" · ");
    option.append(label,meta);option.addEventListener("pointerdown",event=>{event.preventDefault();selected=index;accept()});popup.appendChild(option);
  });
  popup.hidden=!candidates.length;editor.setAttribute("aria-expanded",candidates.length?"true":"false");
  if(candidates.length){editor.setAttribute("aria-activedescendant",`glyph-completion-option-${selected}`);metrics.opens+=1;positionPopup()}
}
function linePrefixWidth(context){
  const style=getComputedStyle(editor);measure.style.font=style.font;measure.style.fontFamily=style.fontFamily;measure.style.fontSize=style.fontSize;
  measure.style.fontWeight=style.fontWeight;measure.style.fontStyle=style.fontStyle;measure.style.letterSpacing=style.letterSpacing;measure.style.tabSize=style.tabSize||"2";
  measure.textContent=context.source.slice(context.lineStart,context.caret)||"\u200b";return measure.getBoundingClientRect().width;
}
function positionPopup(){
  if(popup.hidden||!lastContext)return;
  const rect=editor.getBoundingClientRect(),style=getComputedStyle(editor);
  const paddingLeft=Number.parseFloat(style.paddingLeft)||0,paddingTop=Number.parseFloat(style.paddingTop)||0,lineHeight=Number.parseFloat(style.lineHeight)||20;
  const row=Math.max(0,documentRuntime.caretLine()-1);
  let left=rect.left+paddingLeft+linePrefixWidth(lastContext)-editor.scrollLeft;
  let top=rect.top+paddingTop+row*lineHeight-editor.scrollTop+lineHeight+2;
  const width=Math.max(210,Math.min(440,popup.offsetWidth||280));left=Math.max(8,Math.min(left,innerWidth-width-8));
  const height=popup.offsetHeight||170;if(top+height>innerHeight-8)top=Math.max(8,rect.top+paddingTop+row*lineHeight-editor.scrollTop-height-2);
  popup.style.left=`${left}px`;popup.style.top=`${top}px`;
}
function preferenceIndex(candidate,classification){
  const order=classification?.preferredKinds||[];
  let best=Number.MAX_SAFE_INTEGER;
  for(const kind of candidate.kinds||[candidate.kind]){const index=order.indexOf(kind);if(index>=0)best=Math.min(best,index)}
  return best;
}
function compareCandidates(left,right,classification){
  const exactLeft=classification?.exactText&&left.text===classification.exactText?1:0;
  const exactRight=classification?.exactText&&right.text===classification.exactText?1:0;
  if(exactLeft!==exactRight)return exactRight-exactLeft;
  const leftPref=preferenceIndex(left,classification),rightPref=preferenceIndex(right,classification);
  if(leftPref!==rightPref)return leftPref-rightPref;
  const scopeStart=Number(classification?.scopeStart??-1);
  const leftScope=scopeStart>=0&&left.recent>=scopeStart?1:0,rightScope=scopeStart>=0&&right.recent>=scopeStart?1:0;
  if(leftScope!==rightScope)return rightScope-leftScope;
  if(left.origin!==right.origin)return left.origin==="document"?-1:1;
  return right.recent-left.recent||right.count-left.count||left.added-right.added||(left.text<right.text?-1:left.text>right.text?1:0);
}
function mergeCandidates(documentRows,staticRows,classification,context){
  const rows=[];const seen=new Set();
  for(const row of[...documentRows,...staticRows]){
    if(!row?.text||row.text===context.current||seen.has(row.text))continue;
    if(classification?.exactText&&row.text!==classification.exactText)continue;
    seen.add(row.text);rows.push(row);
  }
  rows.sort((a,b)=>compareCandidates(a,b,classification));
  return rows.slice(0,MAX_RESULTS);
}
function update({force=false,allowEmpty=false}={}){
  frame=0;
  if(documentRuntime.compositionActive()){close();return}
  const context=contextAtCaret();if(!context){close();return}
  const classification=contextService.classify(context);
  if(classification.id==="comment"||classification.id==="unsafe-long-line"){close();return}
  if(!force&&!allowEmpty&&context.prefix.length<MIN_PREFIX){close();return}
  if(!force&&!context.prefix&&context.left<context.right){close();return}
  metrics.queries+=1;
  const queryOptions={limit:QUERY_POOL,exclude:context.current,allowContract:classification.id==="contract"};
  if(Array.isArray(classification.kinds)&&classification.kinds.length){queryOptions.kinds=classification.kinds;metrics.contextFilteredQueries+=1}
  if(classification.owner)queryOptions.owner=classification.owner;
  let rows=[];
  if(!classification.strict||!Array.isArray(classification.kinds)||classification.kinds.length){rows=lexicalIndex.query(context.prefix,context.caret,queryOptions)}
  const staticRows=contextService.staticCandidates(classification,context.prefix);
  rows=mergeCandidates(rows,staticRows,classification,context);
  if(!rows.length){close();return}
  lastContext=context;lastClassification=classification;candidates=rows;selected=0;explicit=allowEmpty||force;render();
}
function schedule(options={}){if(frame)cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>update(options))}
function inCodeOccurrence(source,text,excludeStart,excludeEnd){
  if(!IDENTIFIER.test(text))return false;
  let index=source.indexOf(text);
  while(index>=0){
    const before=index>0?source[index-1]:"",after=source[index+text.length]||"";
    const boundary=!WORD.test(before)&&!WORD.test(after);
    const lineStart=source.lastIndexOf("\n",Math.max(0,index-1))+1,hash=source.indexOf("#",lineStart);
    const code=hash<0||hash>index,outside=index+text.length<=excludeStart||index>=excludeEnd;
    if(boundary&&code&&outside)return true;
    index=source.indexOf(text,index+1);
  }
  return false;
}
function recordMatchesClassification(row,classification){
  if(!row)return false;
  if(classification?.kinds?.length&&!row.kinds.some(kind=>classification.kinds.includes(kind)))return false;
  if(classification?.owner&&!row.owners.includes(classification.owner))return false;
  if(classification?.exactText&&row.text!==classification.exactText)return false;
  return true;
}
function applyCandidate(text,context){
  if(!inCodeOccurrence(context.source,text,context.left,context.right))return false;
  documentRuntime.replaceRange(context.left,context.right,text);metrics.accepts+=1;close();editor.focus();return true;
}
function resumePendingAcceptance(){
  const pending=pendingAcceptance;if(!pending)return false;
  if(documentRuntime.revision()!==pending.revision){pendingAcceptance=null;return false}
  const snapshot=lexicalIndex.snapshot();
  if(!snapshot||Number(snapshot.revision)!==pending.revision)return false;
  const context=contextAtCaret();
  if(!context||context.caret!==pending.caret||context.left!==pending.left||context.right!==pending.right||!pending.text.startsWith(context.prefix)){pendingAcceptance=null;return false}
  const classification=contextService.classify(context);
  if(classification.id!==pending.classificationId||!recordMatchesClassification(lexicalIndex.record(pending.text),classification)){pendingAcceptance=null;return false}
  pendingAcceptance=null;
  return applyCandidate(pending.text,context);
}
function accept(){
  const candidate=candidates[selected];if(!candidate){close();return false}
  const context=contextAtCaret();if(!context||!candidate.text.startsWith(context.prefix)){close();return false}
  const classification=contextService.classify(context);
  if(classification.id!==lastClassification?.id){close();return false}
  metrics.staleAcceptRechecks+=1;
  if(candidate.origin==="document"){
    if(classification.strict){
      const snapshot=lexicalIndex.snapshot();
      if(!snapshot||Number(snapshot.revision)!==documentRuntime.revision()){
        pendingAcceptance={
          text:candidate.text,
          revision:documentRuntime.revision(),
          classificationId:classification.id,
          caret:context.caret,
          left:context.left,
          right:context.right,
        };
        metrics.strictStaleDeferrals+=1;
        close();
        lexicalIndex.refresh();
        return true;
      }
      if(!recordMatchesClassification(lexicalIndex.record(candidate.text),classification)){close();return false}
    }
    return applyCandidate(candidate.text,context);
  }
  documentRuntime.replaceRange(context.left,context.right,candidate.text);metrics.accepts+=1;close();editor.focus();return true;
}

editor.addEventListener("keydown",event=>{
  if(event.isComposing||documentRuntime.compositionActive()){pendingAcceptance=null;close();return}
  if((event.ctrlKey||event.metaKey)&&event.code==="Space"){event.preventDefault();event.stopPropagation();schedule({force:true,allowEmpty:true});return}
  if(popup.hidden)return;
  if(event.key==="ArrowDown"){event.preventDefault();event.stopPropagation();setSelected(selected+1);return}
  if(event.key==="ArrowUp"){event.preventDefault();event.stopPropagation();setSelected(selected-1);return}
  if(event.key==="Tab"||event.key==="Enter"){event.preventDefault();event.stopPropagation();accept();return}
  if(event.key==="Escape"){event.preventDefault();event.stopPropagation();pendingAcceptance=null;close()}
});
editor.addEventListener("input",event=>{if(event.isComposing)return;schedule()});
for(const eventName of["click","keyup","select"]){editor.addEventListener(eventName,event=>{if(eventName==="keyup"&&["ArrowUp","ArrowDown","Enter","Tab","Escape"].includes(event.key))return;schedule()})}
editor.addEventListener("compositionstart",()=>{pendingAcceptance=null;close()});editor.addEventListener("compositionend",()=>schedule());
editor.addEventListener("scroll",()=>{if(!popup.hidden)requestAnimationFrame(positionPopup)},{passive:true});
editor.addEventListener("blur",()=>{pendingAcceptance=null;setTimeout(()=>{if(document.activeElement!==editor)close()},0)});window.addEventListener("resize",()=>{if(!popup.hidden)positionPopup()});
document.addEventListener("selectionchange",()=>{if(document.activeElement===editor&&!popup.hidden)schedule({allowEmpty:explicit})});
document.addEventListener("glyph-editor-document-changed",()=>{if(pendingAcceptance&&documentRuntime.revision()!==pendingAcceptance.revision)pendingAcceptance=null});
document.addEventListener("glyph-editor-source-replaced",()=>{pendingAcceptance=null;close()});
document.addEventListener("glyph-editor-lexical-index-error",()=>{pendingAcceptance=null});
document.addEventListener("glyph-editor-lexical-index-updated",event=>{
  if(pendingAcceptance){if(event.detail?.exact)resumePendingAcceptance();return}
  if(document.activeElement===editor)schedule({allowEmpty:explicit});
});
editor.dataset.completionReady="true";
window.GlyphEditorCompletion={
  marker:MARKER,version:2,open:()=>schedule({force:true,allowEmpty:true}),close,accept,
  candidates:()=>candidates.map(candidate=>({...candidate,kinds:[...(candidate.kinds||[])],owners:[...(candidate.owners||[])]})),
  selected:()=>selected,context:()=>lastClassification?{...lastClassification,static:undefined}:null,metrics:()=>({...metrics,pendingAcceptance:Boolean(pendingAcceptance)}),
};
})();
</script>
"""


def enhance_editor_completion_html(html: str) -> str:
    """Add context-aware document-local completion backed by the shared index."""

    if _MARKER in html:
        return html
    html = enhance_editor_completion_context_html(html)
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_editor_completion_html"]
