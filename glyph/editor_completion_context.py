from __future__ import annotations


_MARKER = "glyph-editor-completion-context-v1"

_SCRIPT = r"""
<script id="glyph-editor-completion-context-v1-script">
(()=>{
const MARKER="glyph-editor-completion-context-v1";
const MAX_LINE_CONTEXT=2048;
const MAX_SCOPE_CONTEXT=4096;
const lexicalIndex=window.GlyphEditorLexicalIndex;
if(!lexicalIndex||window.GlyphEditorCompletionContext?.marker===MARKER)return;

const BUILTIN_TYPES=[
  "F","D","U","I","B","S",
  "u8","u16","u32","u64","i8","i16","i32","i64","f32","f64","bool","String","R","O","V"
];
const TOP_LEVEL_KEYWORDS=["system","machine","resource","ext"];
const SYSTEM_KEYWORDS=["entry","source","sink"];
const MACHINE_KEYWORDS=["select","action","init","next","success","failure"];
const CAPABILITY_KEYWORDS=["own","share","link"];
const EXPRESSION_KEYWORDS=["as"];
const BORROW_KEYWORDS=["mut"];
const AS_TARGETS=["share","link"];

function staticRows(values,kind="Keyword"){
  return values.map(text=>({text,kind,kinds:[kind],owners:[],origin:"static",count:0,recent:-1,added:0}));
}
function boundedLineStart(source,caret){
  const start=Math.max(0,caret-MAX_LINE_CONTEXT);
  const chunk=source.slice(start,caret);
  const newline=chunk.lastIndexOf("\n");
  if(newline<0&&start>0)return null;
  return start+newline+1;
}
function scopeBefore(source,lineStart){
  const start=Math.max(0,lineStart-MAX_SCOPE_CONTEXT);
  const truncated=start>0;
  let chunk=source.slice(start,lineStart);
  let chunkStart=start;
  if(start>0){
    const firstNewline=chunk.indexOf("\n");
    if(firstNewline<0)return {kind:"bounded-unknown",name:"",start};
    chunkStart=start+firstNewline+1;
    chunk=chunk.slice(firstNewline+1);
  }
  let absolute=chunkStart;
  let last=null;
  let sawTopLevel=false;
  for(const line of chunk.split("\n")){
    const lineStart=absolute;
    absolute+=line.length+1;
    if(!line.trim()||/^\s/.test(line))continue;
    const trimmed=line.trim();
    if(trimmed.startsWith("#"))continue;
    sawTopLevel=true;
    let match=trimmed.match(/^system\s+([A-Za-z_][A-Za-z0-9_]*)\b/);
    if(match){last={kind:"system",name:match[1],start:lineStart};continue}
    match=trimmed.match(/^machine\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/);
    if(match){last={kind:"machine",name:match[1],stateParam:match[2],start:lineStart};continue}
    match=trimmed.match(/^machine\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/);
    if(match){last={kind:"machine",name:match[1],stateParam:"",start:lineStart};continue}
    match=trimmed.match(/^[>~]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(/);
    if(match){last={kind:"function",name:match[1],start:lineStart};continue}
    match=trimmed.match(/^!\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(/);
    if(match){last={kind:"sink",name:match[1],start:lineStart};continue}
    match=trimmed.match(/^ext\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/);
    if(match){last={kind:"source",name:match[1],start:lineStart};continue}
    match=trimmed.match(/^\?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(/);
    if(match){last={kind:"temporal",name:match[1],start:lineStart};continue}
    last=null;
  }
  if(!last&&truncated&&!sawTopLevel)return {kind:"bounded-unknown",name:"",start:chunkStart};
  return last;
}
function lastTypeColon(lineBefore){
  for(let index=lineBefore.length-1;index>=0;index-=1){
    if(lineBefore[index]===":"&&lineBefore[index+1]!=="=")return index;
  }
  return-1;
}
function typeContext(lineBefore){
  const colon=lastTypeColon(lineBefore);
  if(colon<0)return null;
  const tail=lineBefore.slice(colon+1);
  if(/^\s*$/.test(tail))return"root";
  if(/\b(?:own|share|link)\s+$/.test(tail))return"qualified";
  if(/&\s*$/.test(tail))return"borrow";
  if(/&\s*mut\s+$/.test(tail))return"qualified";
  if(/[<,|]\s*$/.test(tail))return"root";
  return null;
}
function withDefaults(result,scope){
  return{
    id:"general",
    strict:false,
    kinds:null,
    owner:null,
    preferredKinds:["Binding","Parameter","Field","Function","State","Macro","Source","Sink","Type","Resource"],
    preferredText:null,
    exactText:null,
    insertPrefix:"",
    insertSuffix:"",
    excludeText:null,
    static:[],
    scope,
    scopeStart:scope?.start??-1,
    ...result,
  };
}
function classify(context){
  const source=context.source;
  const lineStart=boundedLineStart(source,context.caret);
  if(lineStart===null)return withDefaults({id:"unsafe-long-line",strict:true,kinds:[],static:[]},null);
  const lineBefore=source.slice(lineStart,context.left);
  const throughCaret=source.slice(lineStart,context.caret);
  const hash=throughCaret.indexOf("#");
  if(hash>=0)return withDefaults({id:"comment",strict:true,kinds:[],static:[]},null);
  const scope=scopeBefore(source,lineStart);
  const trimmed=throughCaret.trimStart();
  const indented=/^\s/.test(source.slice(lineStart,context.caret));

  if(context.left>0&&source[context.left-1]==="'"){
    return withDefaults({id:"contract",strict:true,kinds:["Contract"]},scope);
  }

  const resourceState=throughCaret.match(/([A-Za-z_][A-Za-z0-9_]*)\[\s*[A-Za-z0-9_]*$/);
  if(resourceState){
    return withDefaults({id:"resource-state",strict:true,kinds:["State"],owner:resourceState[1],preferredKinds:["State"]},scope);
  }

  let match=trimmed.match(/^entry\s+[A-Za-z0-9_]*$/);
  if(match&&scope?.kind==="system")return withDefaults({id:"system-entry",strict:true,kinds:["EntryFunction"],preferredKinds:["EntryFunction","Function"]},scope);
  match=trimmed.match(/^source\s+[A-Za-z0-9_]*$/);
  if(match&&scope?.kind==="system")return withDefaults({id:"system-source",strict:true,kinds:["Source"],preferredKinds:["Source"]},scope);
  match=trimmed.match(/^sink\s+[A-Za-z0-9_]*$/);
  if(match&&scope?.kind==="system")return withDefaults({id:"system-sink",strict:true,kinds:["Sink"],preferredKinds:["Sink"]},scope);

  const property=trimmed.match(/^(select|action|init|next|success|failure)\s*=\s*(.*)$/);
  if(property&&scope?.kind==="machine"){
    const machine=lexicalIndex.machineInfo(scope.name);
    const key=property[1],value=property[2];
    if((key==="select"||key==="action")&&machine?.stateType){
      let insertPrefix="";
      const qualified=value.match(/^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_]*)$/);
      if(qualified){
        if(!scope.stateParam||qualified[1]!==scope.stateParam){
          return withDefaults({id:`machine-${key}-invalid-base`,strict:true,kinds:[]},scope);
        }
      }else if(/^[A-Za-z0-9_]*$/.test(value)){
        if(scope.stateParam)insertPrefix=`${scope.stateParam}.`;
      }else{
        return withDefaults({id:`machine-${key}-expression`,strict:true,kinds:[]},scope);
      }
      return withDefaults({
        id:`machine-${key}`,
        strict:true,
        kinds:["StateField"],
        owner:machine.stateType,
        preferredKinds:["StateField"],
        insertPrefix,
        excludeText:key==="action"?(machine.selectorField||null):null,
      },scope);
    }
    if(key==="init"&&/^[A-Za-z0-9_]*$/.test(value)&&machine?.stateType){
      return withDefaults({id:"machine-init",strict:true,kinds:["Type"],preferredKinds:["Type"],exactText:machine.stateType,insertSuffix:"("},scope);
    }
    if(key==="next"&&/^[A-Za-z0-9_]*$/.test(value)){
      return withDefaults({id:"machine-next",strict:true,kinds:["EntryFunction"],preferredKinds:["EntryFunction","Function"],insertSuffix:"("},scope);
    }
    if((key==="success"||key==="failure")&&/^[A-Za-z0-9_]*$/.test(value)&&machine?.selectorType){
      return withDefaults({id:`machine-${key}`,strict:true,kinds:["State"],owner:machine.selectorType,preferredKinds:["State"]},scope);
    }
  }

  if(/\bas\s+[A-Za-z0-9_]*$/.test(trimmed)){
    return withDefaults({id:"capability-target",strict:true,kinds:[],static:staticRows(AS_TARGETS,"Capability")},scope);
  }

  const typeMode=typeContext(lineBefore);
  if(typeMode){
    return withDefaults({
      id:"type",
      strict:true,
      kinds:["Type"],
      preferredKinds:["Resource","Type"],
      static:[
        ...staticRows(BUILTIN_TYPES,"Builtin Type"),
        ...(typeMode==="root"?staticRows(CAPABILITY_KEYWORDS,"Capability"):[]),
        ...(typeMode==="borrow"?staticRows(BORROW_KEYWORDS,"Capability"):[]),
      ],
    },scope);
  }

  if(indented&&scope?.kind==="bounded-unknown"){
    return withDefaults({id:"unsafe-scope",strict:true,kinds:[],static:[]},scope);
  }
  if(indented&&scope?.kind==="system"&&/^\s*[A-Za-z0-9_]*$/.test(throughCaret)){
    return withDefaults({id:"system-keyword",strict:true,kinds:[],static:staticRows(SYSTEM_KEYWORDS)},scope);
  }
  if(indented&&scope?.kind==="machine"&&/^\s*[A-Za-z0-9_]*$/.test(throughCaret)){
    return withDefaults({id:"machine-keyword",strict:true,kinds:[],static:staticRows(MACHINE_KEYWORDS)},scope);
  }
  if(!indented&&/^\s*[A-Za-z0-9_]*$/.test(throughCaret)){
    return withDefaults({id:"top-level-keyword",strict:false,preferredKinds:["Keyword"],static:staticRows(TOP_LEVEL_KEYWORDS)},scope);
  }

  return withDefaults({static:staticRows(EXPRESSION_KEYWORDS)},scope);
}
function staticCandidates(classification,prefix){
  const text=String(prefix??"");
  return(classification?.static||[]).flatMap(row=>{
    const match=lexicalIndex.matchText?.(text,row.text);
    if(text&&!match)return[];
    return[{
      ...row,
      added:Math.max(0,row.text.length-text.length),
      matchKind:match?.kind||"empty",
      matchScore:Number(match?.score||0),
      matchEdits:Number(match?.edits||0),
    }];
  });
}

window.GlyphEditorCompletionContext={
  marker:MARKER,
  version:1,
  classify,
  staticCandidates,
  boundedLineStart,
};
})();
</script>
"""


def enhance_editor_completion_context_html(html: str) -> str:
    """Install bounded local Glyph syntax context classification for completion."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_completion_context_html"]