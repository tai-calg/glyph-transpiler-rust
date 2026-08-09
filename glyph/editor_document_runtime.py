from __future__ import annotations


_MARKER = "glyph-editor-document-runtime-v1"

_SCRIPT = r"""
<script id="glyph-editor-document-runtime-v1-script">
(()=>{
const MARKER="glyph-editor-document-runtime-v1";
const editor=document.getElementById("editor");
const lines=document.getElementById("lines");
const meta=document.getElementById("editor-meta");
if(!editor||!lines||editor.dataset.documentRuntimeReady==="true")return;
const descriptor=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value");
if(!descriptor?.get||!descriptor?.set)return;
const countNewlines=(value,start=0,end=value.length)=>{
  let count=0;
  for(let index=Math.max(0,start);index<Math.min(value.length,end);index+=1){if(value.charCodeAt(index)===10)count+=1}
  return count;
};
const textValue=()=>descriptor.get.call(editor);
let revision=0;
let lineCount=countNewlines(textValue())+1;
let renderedLineCount=-1;
let knownCaret=editor.selectionStart||0;
let caretLine=countNewlines(textValue(),0,knownCaret)+1;
let beforePlan=null;
let syntheticPlan=null;
let deferredRecountTimer=0;
let deferredCaretTimer=0;
let suppressValueHook=false;
let compositionActive=false;
const metrics={fullLineRecounts:1,caretFullScans:1,incrementalInputs:0,sourceReplacements:0};

function renderLines(force=false){
  if(!force&&renderedLineCount===lineCount)return;
  lines.textContent=Array.from({length:Math.max(1,lineCount)},(_,index)=>index+1).join("\n");
  if(meta)meta.textContent=`${Math.max(1,lineCount)} lines`;
  renderedLineCount=lineCount;
}
function lineAt(position){
  metrics.caretFullScans+=1;
  return countNewlines(textValue(),0,Math.max(0,position))+1;
}
function syncCaretFromSelection(force=false){
  const next=editor.selectionStart||0;
  if(!force&&next===knownCaret)return;
  knownCaret=next;
  caretLine=lineAt(next);
}
function scheduleCaretReconcile(){
  if(deferredCaretTimer)return;
  deferredCaretTimer=setTimeout(()=>{
    deferredCaretTimer=0;
    syncCaretFromSelection(true);
    dispatch("glyph-editor-caret-reconciled",{caret:knownCaret,caretLine});
  },0);
}
function dispatch(name,detail={}){
  document.dispatchEvent(new CustomEvent(name,{detail:{marker:MARKER,revision,lineCount,...detail}}));
}
function scheduleFullLineRecount(){
  if(deferredRecountTimer)return;
  deferredRecountTimer=setTimeout(()=>{
    deferredRecountTimer=0;
    lineCount=countNewlines(textValue())+1;
    metrics.fullLineRecounts+=1;
    renderLines();
    syncCaretFromSelection(true);
    dispatch("glyph-editor-line-index-reconciled",{deferred:true});
  },0);
}
function insertedTextFor(event){
  const type=String(event?.inputType||"");
  if(type==="insertLineBreak"||type==="insertParagraph")return"\n";
  if(type.startsWith("delete")||type.startsWith("history"))return type.startsWith("delete")?"":null;
  if(typeof event?.data==="string")return event.data;
  const transfer=event?.dataTransfer;
  if(transfer&&typeof transfer.getData==="function"){
    const text=transfer.getData("text/plain");
    if(typeof text==="string")return text;
  }
  return null;
}
function makePlan(event){
  const selectionStart=editor.selectionStart||0,selectionEnd=editor.selectionEnd||selectionStart;
  let start=selectionStart,end=selectionEnd;
  const source=textValue();
  const inserted=insertedTextFor(event);
  const type=String(event?.inputType||"");
  let known=inserted!==null&&!type.startsWith("history");
  let startLine=selectionStart===knownCaret?caretLine:null;
  if(type.startsWith("delete")&&start===end){
    if(type==="deleteContentBackward"&&start>0){
      start-=1;
      if(startLine!==null&&source.charCodeAt(start)===10)startLine=Math.max(1,startLine-1);
    }else if(type==="deleteContentForward"&&end<source.length){
      end+=1;
    }else known=false;
  }
  return{
    start,end,startLine,known,
    removedNewlines:known?countNewlines(source,start,end):0,
    insertedNewlines:known?countNewlines(inserted):0,
  };
}
function applyInput(event){
  const plan=syntheticPlan||beforePlan;
  syntheticPlan=null;
  beforePlan=null;
  revision+=1;
  metrics.incrementalInputs+=1;
  knownCaret=editor.selectionStart||0;
  if(plan?.known){
    const delta=plan.insertedNewlines-plan.removedNewlines;
    lineCount=Math.max(1,lineCount+delta);
    if(plan.startLine!==null)caretLine=Math.max(1,plan.startLine+plan.insertedNewlines);
    else scheduleCaretReconcile();
    if(delta!==0)renderLines();
  }else{
    scheduleFullLineRecount();
  }
  dispatch("glyph-editor-document-changed",{
    inputType:String(event?.inputType||""),
    sourceLength:textValue().length,
    composing:Boolean(event?.isComposing||compositionActive),
  });
}

editor.addEventListener("beforeinput",event=>{beforePlan=makePlan(event)});
editor.addEventListener("input",applyInput);
editor.addEventListener("compositionstart",()=>{compositionActive=true;dispatch("glyph-editor-composition-changed",{active:true})});
editor.addEventListener("compositionend",()=>{compositionActive=false;syncCaretFromSelection(true);dispatch("glyph-editor-composition-changed",{active:false})});
document.addEventListener("selectionchange",()=>{if(document.activeElement===editor)syncCaretFromSelection()});

Object.defineProperty(editor,"value",{
  configurable:true,
  enumerable:true,
  get(){return descriptor.get.call(editor)},
  set(next){
    const value=String(next??"");
    const previous=descriptor.get.call(editor);
    descriptor.set.call(editor,value);
    if(suppressValueHook||value===previous)return;
    revision+=1;
    metrics.sourceReplacements+=1;
    lineCount=countNewlines(value)+1;
    metrics.fullLineRecounts+=1;
    renderLines();
    knownCaret=editor.selectionStart||0;
    caretLine=countNewlines(value,0,knownCaret)+1;
    metrics.caretFullScans+=1;
    beforePlan=null;syntheticPlan=null;
    dispatch("glyph-editor-source-replaced",{sourceLength:value.length});
  },
});

const legacySyncLines=globalThis.syncLines;
globalThis.syncLines=()=>renderLines();

function replaceRange(start,end,replacement,{select="end"}={}){
  const source=textValue();
  const left=Math.max(0,Math.min(source.length,Number(start)||0));
  const right=Math.max(left,Math.min(source.length,Number(end)||left));
  const text=String(replacement??"");
  const startLine=left===knownCaret?caretLine:null;
  syntheticPlan={
    start:left,end:right,startLine,known:true,
    removedNewlines:countNewlines(source,left,right),
    insertedNewlines:countNewlines(text),
  };
  suppressValueHook=true;
  try{descriptor.set.call(editor,source.slice(0,left)+text+source.slice(right))}finally{suppressValueHook=false}
  const caret=left+text.length;
  if(select==="replacement")editor.setSelectionRange(left,caret);
  else editor.setSelectionRange(caret,caret);
  let event;
  try{event=new InputEvent("input",{bubbles:true,inputType:"insertReplacementText",data:text})}
  catch{event=new Event("input",{bubbles:true})}
  editor.dispatchEvent(event);
  return{start:left,end:right,caret};
}
function replaceSource(source){editor.value=String(source??"")}

renderLines(true);
editor.dataset.documentRuntimeReady="true";
window.GlyphEditorDocument={
  marker:MARKER,
  version:1,
  revision:()=>revision,
  lineCount:()=>lineCount,
  caretLine:()=>caretLine,
  compositionActive:()=>compositionActive,
  replaceRange,
  replaceSource,
  syncLines:()=>renderLines(true),
  metrics:()=>({...metrics}),
  legacySyncLines,
};
dispatch("glyph-editor-document-runtime-ready",{sourceLength:textValue().length});
})();
</script>
"""


def enhance_editor_document_runtime_html(html: str) -> str:
    """Install the shared editor document state without adding synchronous full scans."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_document_runtime_html"]
