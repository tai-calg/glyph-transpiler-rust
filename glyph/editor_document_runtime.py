from __future__ import annotations


_MARKER = "glyph-editor-document-runtime-v1"
_SAVE_CONTROLLER_MARKER = "glyph-save-triggered-rendering-v4"
_SAVE_INPUT_LISTENER = '''editor.addEventListener("input",()=>{
 dirty=true;
 updateUi();
});'''
_OPTIMIZED_SAVE_INPUT_LISTENER = '''let editorDirtyUiPresented=false;
document.addEventListener("glyph-save-state-changed",event=>{
 editorDirtyUiPresented=String(event.detail?.persistence||"")!=="saved";
});
editor.addEventListener("input",()=>{
 dirty=true;
 if(!editorDirtyUiPresented){
  editorDirtyUiPresented=true;
  updateUi();
 }
});'''

_SCRIPT = r"""
<script id="glyph-editor-document-runtime-v1-script">
(()=>{
const MARKER="glyph-editor-document-runtime-v1";
const editor=document.getElementById("editor");
const lines=document.getElementById("lines");
const meta=document.getElementById("editor-meta");
if(!editor||!lines||editor.dataset.documentRuntimeReady==="true")return;
const descriptor=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value");
const nativeSetRangeText=HTMLTextAreaElement.prototype.setRangeText;
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
let caretLineValid=true;
let beforePlan=null;
let syntheticPlan=null;
let deferredRecountTimer=0;
let deferredCaretTimer=0;
let suppressValueHook=false;
let suppressTrackedInput=false;
let compositionActive=false;
const metrics={fullLineRecounts:1,caretFullScans:1,incrementalCaretMoves:0,incrementalInputs:0,sourceReplacements:0,programmaticRangeEdits:0,lineSuffixMutations:0};

function fullLineText(count){return Array.from({length:Math.max(1,count)},(_,index)=>index+1).join("\n")}
function renderLines(force=false){
  if(!force&&renderedLineCount===lineCount)return;
  const target=Math.max(1,lineCount);
  const node=lines.childNodes.length===1&&lines.firstChild?.nodeType===3?lines.firstChild:null;
  if(!force&&node&&renderedLineCount>=1){
    if(target>renderedLineCount){
      let suffix="";
      for(let number=renderedLineCount+1;number<=target;number+=1)suffix+=`\n${number}`;
      if(suffix){node.appendData(suffix);metrics.lineSuffixMutations+=1}
    }else if(target<renderedLineCount){
      let removeLength=0;
      for(let number=target+1;number<=renderedLineCount;number+=1)removeLength+=1+String(number).length;
      if(removeLength>0){node.deleteData(Math.max(0,node.length-removeLength),removeLength);metrics.lineSuffixMutations+=1}
    }
  }else{
    lines.textContent=fullLineText(target);
  }
  if(meta)meta.textContent=`${target} lines`;
  renderedLineCount=target;
}
function lineAt(position){
  metrics.caretFullScans+=1;
  return countNewlines(textValue(),0,Math.max(0,position))+1;
}
function lineFromKnownCaret(position){
  if(!caretLineValid)return null;
  const target=Math.max(0,Number(position)||0);
  if(target===knownCaret)return caretLine;
  const source=textValue();
  if(target>knownCaret)return caretLine+countNewlines(source,knownCaret,target);
  return Math.max(1,caretLine-countNewlines(source,target,knownCaret));
}
function syncCaretFromSelection(force=false){
  const next=editor.selectionStart||0;
  if(!force&&caretLineValid&&next===knownCaret)return;
  if(!force&&caretLineValid){
    const nextLine=lineFromKnownCaret(next);
    knownCaret=next;
    caretLine=nextLine??caretLine;
    caretLineValid=nextLine!==null;
    metrics.incrementalCaretMoves+=1;
    return;
  }
  knownCaret=next;
  caretLine=lineAt(next);
  caretLineValid=true;
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
function cancelDeferredReconciles(){
  if(deferredRecountTimer){clearTimeout(deferredRecountTimer);deferredRecountTimer=0}
  if(deferredCaretTimer){clearTimeout(deferredCaretTimer);deferredCaretTimer=0}
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
  let startLine=lineFromKnownCaret(selectionStart);
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
  if(suppressTrackedInput){suppressTrackedInput=false;beforePlan=null;syntheticPlan=null;return}
  const plan=syntheticPlan||beforePlan;
  syntheticPlan=null;
  beforePlan=null;
  revision+=1;
  metrics.incrementalInputs+=1;
  knownCaret=editor.selectionStart||0;
  if(plan?.known){
    const delta=plan.insertedNewlines-plan.removedNewlines;
    lineCount=Math.max(1,lineCount+delta);
    if(plan.startLine!==null){
      caretLine=Math.max(1,plan.startLine+countNewlines(textValue(),plan.start,knownCaret));
      caretLineValid=true;
    }else{
      caretLineValid=false;
      scheduleCaretReconcile();
    }
    if(delta!==0)renderLines();
  }else{
    caretLineValid=false;
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
editor.addEventListener("compositionend",()=>{compositionActive=false;syncCaretFromSelection();dispatch("glyph-editor-composition-changed",{active:false})});
document.addEventListener("selectionchange",()=>{if(document.activeElement===editor)syncCaretFromSelection()});
for(const eventName of["keyup","click","select"]){editor.addEventListener(eventName,()=>syncCaretFromSelection())}

Object.defineProperty(editor,"value",{
  configurable:true,
  enumerable:true,
  get(){return descriptor.get.call(editor)},
  set(next){
    const value=String(next??"");
    const previous=descriptor.get.call(editor);
    descriptor.set.call(editor,value);
    if(suppressValueHook)return;
    if(value===previous){syncCaretFromSelection();return}
    cancelDeferredReconciles();
    revision+=1;
    metrics.sourceReplacements+=1;
    lineCount=countNewlines(value)+1;
    metrics.fullLineRecounts+=1;
    renderLines();
    knownCaret=editor.selectionStart||0;
    caretLine=countNewlines(value,0,knownCaret)+1;
    caretLineValid=true;
    metrics.caretFullScans+=1;
    beforePlan=null;syntheticPlan=null;
    dispatch("glyph-editor-source-replaced",{sourceLength:value.length});
  },
});

if(typeof nativeSetRangeText==="function"){
  Object.defineProperty(editor,"setRangeText",{
    configurable:true,
    value:function(...args){
      const previous=textValue();
      suppressValueHook=true;
      try{nativeSetRangeText.apply(editor,args)}finally{suppressValueHook=false}
      const value=textValue();
      if(value===previous){syncCaretFromSelection();return}
      cancelDeferredReconciles();
      revision+=1;
      metrics.programmaticRangeEdits+=1;
      lineCount=countNewlines(value)+1;
      metrics.fullLineRecounts+=1;
      renderLines();
      knownCaret=editor.selectionStart||0;
      caretLine=countNewlines(value,0,knownCaret)+1;
      caretLineValid=true;
      metrics.caretFullScans+=1;
      beforePlan=null;syntheticPlan=null;
      dispatch("glyph-editor-source-replaced",{sourceLength:value.length,rangeEdit:true});
      suppressTrackedInput=true;
      let event;
      const replacement=String(args[0]??"");
      try{event=new InputEvent("input",{bubbles:true,inputType:"insertReplacementText",data:replacement})}
      catch{event=new Event("input",{bubbles:true})}
      try{editor.dispatchEvent(event)}finally{suppressTrackedInput=false}
    },
  });
}

const legacySyncLines=globalThis.syncLines;
globalThis.syncLines=()=>renderLines();

function replaceRange(start,end,replacement,{select="end"}={}){
  const source=textValue();
  const left=Math.max(0,Math.min(source.length,Number(start)||0));
  const right=Math.max(left,Math.min(source.length,Number(end)||left));
  const text=String(replacement??"");
  const startLine=lineFromKnownCaret(left);
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


def _optimize_save_input_listener(html: str) -> str:
    """Update save-state chrome only when it does not already show local edits."""

    if _SAVE_CONTROLLER_MARKER not in html:
        return html
    count = html.count(_SAVE_INPUT_LISTENER)
    if count != 1:
        raise ValueError(f"save input listener anchor changed: expected 1, got {count}")
    return html.replace(_SAVE_INPUT_LISTENER, _OPTIMIZED_SAVE_INPUT_LISTENER, 1)


def enhance_editor_document_runtime_html(html: str) -> str:
    """Install shared editor state and keep ordinary typing on a bounded sync path."""

    if _MARKER in html:
        return html
    html = _optimize_save_input_listener(html)
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_document_runtime_html"]