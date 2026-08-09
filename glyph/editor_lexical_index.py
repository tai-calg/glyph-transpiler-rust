from __future__ import annotations


_MARKER = "glyph-editor-lexical-index-v2"

LEXICAL_WORKER_JS = r"""(()=>{
const isStart=code=>(code>=65&&code<=90)||(code>=97&&code<=122)||code===95;
const isPart=code=>isStart(code)||(code>=48&&code<=57);
const KIND_PRIORITY=["Resource","Type","StateField","State","Field","Function","EntryFunction","Source","Sink","Temporal","Machine","System","Macro","Binding","Parameter","Contract","Identifier"];

function stripComments(source){
  return source.split("\n").map(line=>{
    const hash=line.indexOf("#");
    return hash<0?line:line.slice(0,hash);
  }).join("\n");
}
function findMatching(text,start,left="(",right=")"){
  if(start<0||text[start]!==left)return-1;
  let depth=0;
  for(let index=start;index<text.length;index+=1){
    if(text[index]===left)depth+=1;
    else if(text[index]===right){depth-=1;if(depth===0)return index}
  }
  return-1;
}
function splitTopLevel(text,separator){
  const output=[];
  let start=0,round=0,brace=0,angle=0,bracket=0;
  for(let index=0;index<text.length;index+=1){
    const ch=text[index];
    if(ch==="(")round+=1;else if(ch===")")round=Math.max(0,round-1);
    else if(ch==="{")brace+=1;else if(ch==="}")brace=Math.max(0,brace-1);
    else if(ch==="<")angle+=1;else if(ch===">")angle=Math.max(0,angle-1);
    else if(ch==="[")bracket+=1;else if(ch==="]")bracket=Math.max(0,bracket-1);
    else if(ch===separator&&round===0&&brace===0&&angle===0&&bracket===0){output.push(text.slice(start,index).trim());start=index+1}
  }
  output.push(text.slice(start).trim());
  return output;
}
function topLevelIndex(text,target){
  let round=0,brace=0,angle=0,bracket=0;
  for(let index=0;index<text.length;index+=1){
    const ch=text[index];
    if(ch==="(")round+=1;else if(ch===")")round=Math.max(0,round-1);
    else if(ch==="{")brace+=1;else if(ch==="}")brace=Math.max(0,brace-1);
    else if(ch==="<")angle+=1;else if(ch===">")angle=Math.max(0,angle-1);
    else if(ch==="[")bracket+=1;else if(ch==="]")bracket=Math.max(0,bracket-1);
    else if(ch===target&&round===0&&brace===0&&angle===0&&bracket===0)return index;
  }
  return-1;
}
function directTypeName(raw){
  const match=String(raw||"").trim().match(/^([A-Za-z_][A-Za-z0-9_]*)$/);
  return match?match[1]:"";
}
function parseNamedFields(body){
  const fields=[];
  const pending=[];
  for(const part of splitTopLevel(body,",")){
    const item=part.trim();
    if(!item)continue;
    const colon=topLevelIndex(item,":");
    if(colon<0){
      if(/^[A-Za-z_][A-Za-z0-9_]*$/.test(item))pending.push(item);
      continue;
    }
    const name=item.slice(0,colon).trim();
    const type=item.slice(colon+1).trim();
    const names=[...pending,name];
    pending.length=0;
    for(const fieldName of names){if(/^[A-Za-z_][A-Za-z0-9_]*$/.test(fieldName))fields.push({name:fieldName,type:directTypeName(type)})}
  }
  return fields;
}
function lineEnd(text,index){const newline=text.indexOf("\n",index);return newline<0?text.length:newline}
function nextTopLevelLine(text,index){
  let cursor=lineEnd(text,index);
  while(cursor<text.length){
    const start=cursor+1;
    const end=lineEnd(text,start);
    const line=text.slice(start,end);
    if(line.trim()&&!/^\s/.test(line))return start;
    cursor=end;
  }
  return text.length;
}
function primaryKind(kinds){
  for(const kind of KIND_PRIORITY){if(kinds.includes(kind))return kind}
  return"Identifier";
}

self.onmessage=event=>{
  const payload=event.data||{};
  const revision=Number(payload.revision||0);
  const source=String(payload.source||"");
  const table=new Map();
  const metadata=new Map();
  const metaFor=text=>{
    let row=metadata.get(text);
    if(!row){row={kinds:new Set(),owners:new Set(),ownerKinds:new Map()};metadata.set(text,row)}
    return row;
  };
  const mark=(text,kind,owner="")=>{
    if(!text)return;
    const meta=metaFor(text);meta.kinds.add(kind);
    if(owner){
      meta.owners.add(owner);
      let kinds=meta.ownerKinds.get(owner);
      if(!kinds){kinds=new Set();meta.ownerKinds.set(owner,kinds)}
      kinds.add(kind);
    }
  };

  let index=0,comment=false;
  while(index<source.length){
    const code=source.charCodeAt(index);
    if(code===10){comment=false;index+=1;continue}
    if(code===35){comment=true;index+=1;continue}
    if(!isStart(code)){index+=1;continue}
    const start=index;
    index+=1;
    while(index<source.length&&isPart(source.charCodeAt(index)))index+=1;
    const text=source.slice(start,index);
    let row=table.get(text);
    if(!row){row={all:[],code:[]};table.set(text,row)}
    row.all.push(start);
    if(!comment)row.code.push(start);
  }

  const codeSource=stripComments(source);
  const sumVariants=new Map();
  const productFields=new Map();
  const machineRecords=[];

  let match;
  const productRe=/^\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  while((match=productRe.exec(codeSource))!==null){
    const name=match[1];mark(name,"Type");
    const open=codeSource.indexOf("(",match.index);
    const close=findMatching(codeSource,open);
    if(close<0)continue;
    const fields=parseNamedFields(codeSource.slice(open+1,close));
    const fieldMap={};
    for(const field of fields){fieldMap[field.name]=field.type;mark(field.name,"Field",name)}
    productFields.set(name,fieldMap);
    productRe.lastIndex=close+1;
  }

  const sumRe=/^\+\s*([A-Za-z_][A-Za-z0-9_]*)\s*=([^\n]*)/gm;
  while((match=sumRe.exec(codeSource))!==null){
    const name=match[1];mark(name,"Type");
    const variants=[];
    for(const part of splitTopLevel(match[2],"|")){
      const variant=part.match(/^([A-Za-z_][A-Za-z0-9_]*)/)?.[1]||"";
      if(variant){variants.push(variant);mark(variant,"State",name)}
    }
    sumVariants.set(name,variants);
  }

  const aliasRe=/^=\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/gm;
  while((match=aliasRe.exec(codeSource))!==null)mark(match[1],"Type");

  const resourceRe=/^resource\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*<[^>\n]*>)?\s*\[/gm;
  while((match=resourceRe.exec(codeSource))!==null){
    const name=match[1];mark(name,"Resource");mark(name,"Type");
    const open=codeSource.indexOf("[",match.index);
    const close=findMatching(codeSource,open,"[","]");
    if(close<0)continue;
    for(const part of splitTopLevel(codeSource.slice(open+1,close),"|")){
      const state=part.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)/)?.[1]||"";
      if(state)mark(state,"State",name);
    }
    resourceRe.lastIndex=close+1;
  }

  for(const [owner,fields] of productFields.entries()){
    for(const [field,type] of Object.entries(fields)){if(type&&sumVariants.has(type))mark(field,"StateField",owner)}
  }

  const functionRe=/^([>!~?])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  while((match=functionRe.exec(codeSource))!==null){
    const marker=match[1],name=match[2];
    const kind=marker==="!"?"Sink":marker==="?"?"Temporal":"Function";
    mark(name,kind);
    if(marker===">")mark(name,"EntryFunction");
    const open=codeSource.indexOf("(",match.index),close=findMatching(codeSource,open);
    if(close>=0){for(const field of parseNamedFields(codeSource.slice(open+1,close)))mark(field.name,"Parameter",name);functionRe.lastIndex=close+1}
  }
  const extRe=/^ext\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  while((match=extRe.exec(codeSource))!==null){
    const name=match[1];mark(name,"Source");
    const open=codeSource.indexOf("(",match.index),close=findMatching(codeSource,open);
    if(close>=0){for(const field of parseNamedFields(codeSource.slice(open+1,close)))mark(field.name,"Parameter",name);extRe.lastIndex=close+1}
  }

  const rawMacroRe=/^@([A-Z][A-Z0-9_]*)(?=[ \t]|=|$)/gm;
  while((match=rawMacroRe.exec(codeSource))!==null){if(match[1]!=="A"&&match[1]!=="E")mark(match[1],"Macro")}
  const astMacroRe=/^@([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  while((match=astMacroRe.exec(codeSource))!==null){if(match[1]!=="A"&&match[1]!=="E")mark(match[1],"Macro")}
  const bindingRe=/^[ \t]+([A-Za-z_][A-Za-z0-9_]*)\s*:=/gm;
  while((match=bindingRe.exec(codeSource))!==null)mark(match[1],"Binding");
  const systemRe=/^system\s+([A-Za-z_][A-Za-z0-9_]*)\b/gm;
  while((match=systemRe.exec(codeSource))!==null)mark(match[1],"System");

  const contractRe=/^'[@>!?]?\s*([A-Za-z_][A-Za-z0-9_]*)\b/gm;
  while((match=contractRe.exec(codeSource))!==null)mark(match[1],"Contract");

  const machineRe=/^machine\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/gm;
  while((match=machineRe.exec(codeSource))!==null){
    const name=match[1];mark(name,"Machine");
    const open=codeSource.indexOf("(",match.index),close=findMatching(codeSource,open);
    if(close<0)continue;
    const params=parseNamedFields(codeSource.slice(open+1,close));
    for(const param of params)mark(param.name,"Parameter",name);
    const stateParam=params[0]||null;
    const stateType=stateParam?.type||"";
    const bodyEnd=nextTopLevelLine(codeSource,close);
    const body=codeSource.slice(close+1,bodyEnd);
    const select=body.match(/^[ \t]+select\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)/m);
    const selectorField=select?.[2]||"";
    const selectorType=stateType&&selectorField?(productFields.get(stateType)?.[selectorField]||""):"";
    machineRecords.push({name,stateType,selectorField,selectorType});
    machineRe.lastIndex=close+1;
  }
  machineRecords.sort((left,right)=>left.name<right.name?-1:left.name>right.name?1:0);

  const names=[...table.keys()].sort();
  let allLength=0,codeLength=0;
  for(const name of names){const row=table.get(name);allLength+=row.all.length;codeLength+=row.code.length}
  const positions=new Int32Array(allLength),codePositions=new Int32Array(codeLength),records=[];
  let allOffset=0,codeOffset=0;
  for(const text of names){
    const row=table.get(text),meta=metadata.get(text);
    positions.set(row.all,allOffset);codePositions.set(row.code,codeOffset);
    const kinds=meta?[...meta.kinds]:["Identifier"];
    if(!kinds.length)kinds.push("Identifier");
    const owners=meta?[...meta.owners]:[];
    const ownerKinds=meta?Object.fromEntries([...meta.ownerKinds.entries()].map(([owner,set])=>[owner,[...set]])):{};
    records.push({text,allOffset,allCount:row.all.length,codeOffset,codeCount:row.code.length,kinds,owners,ownerKinds,kind:primaryKind(kinds)});
    allOffset+=row.all.length;codeOffset+=row.code.length;
  }
  self.postMessage({type:"snapshot",revision,sourceLength:source.length,records,positions,codePositions,machineRecords},[positions.buffer,codePositions.buffer]);
};
})();
"""

_SCRIPT = r"""
<script id="glyph-editor-lexical-index-v2-script">
(()=>{
const MARKER="glyph-editor-lexical-index-v2";
const DEBOUNCE_MS=120;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
if(!editor||!documentRuntime||editor.dataset.lexicalIndexReady==="true")return;
let worker=null,snapshot=null,inFlight=null,pending=null,timer=0,restartCount=0,minimumRevision=0;
const metrics={buildsSent:0,buildsCompleted:0,staleAccepted:0,staleDiscarded:0,maxPendingDepth:0,workerRestarts:0};

const emit=(name,detail={})=>document.dispatchEvent(new CustomEvent(name,{detail:{marker:MARKER,...detail}}));
function lowerBound(values,target,selector=value=>value){
  let low=0,high=values.length;
  while(low<high){const middle=(low+high)>>1;if(selector(values[middle])<target)low=middle+1;else high=middle}
  return low;
}
function lastBefore(values,target){
  let low=0,high=values.length;
  while(low<high){const middle=(low+high)>>1;if(values[middle]<target)low=middle+1;else high=middle}
  return low>0?values[low-1]:-1;
}
function ensureWorker(){
  if(worker)return worker;
  try{worker=new Worker("/assets/editor-lexical-worker.js")}catch(error){emit("glyph-editor-lexical-index-error",{message:String(error?.message||error)});return null}
  worker.onmessage=event=>{
    const result=event.data||{};
    if(result.type!=="snapshot")return;
    const completed=inFlight;inFlight=null;metrics.buildsCompleted+=1;
    const currentRevision=documentRuntime.revision();
    if(Number(result.revision)<minimumRevision){metrics.staleDiscarded+=1}
    else if(!snapshot||Number(result.revision)>=Number(snapshot.revision)){
      snapshot=result;
      if(result.revision<currentRevision)metrics.staleAccepted+=1;
      emit("glyph-editor-lexical-index-updated",{revision:result.revision,currentRevision,exact:result.revision===currentRevision});
    }else metrics.staleDiscarded+=1;
    const next=pending;pending=null;
    if(next&&Number(next.revision)>Number(completed?.revision||-1))send(next);
  };
  worker.onerror=event=>{
    const message=String(event?.message||"lexical index worker failed");
    try{worker?.terminate()}catch{}
    worker=null;inFlight=null;pending=null;snapshot=null;emit("glyph-editor-lexical-index-error",{message});
    if(restartCount<1){restartCount+=1;metrics.workerRestarts+=1;setTimeout(()=>schedule({immediate:true,invalidate:true}),100)}
  };
  return worker;
}
function send(request){const active=ensureWorker();if(!active)return;inFlight=request;metrics.buildsSent+=1;active.postMessage(request)}
function buildRequest(){return{revision:documentRuntime.revision(),source:editor.value}}
function schedule({immediate=false,invalidate=false}={}){
  clearTimeout(timer);timer=0;
  if(invalidate){minimumRevision=documentRuntime.revision();snapshot=null;emit("glyph-editor-lexical-index-invalidated",{revision:minimumRevision})}
  const run=()=>{timer=0;const request=buildRequest();if(inFlight){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}send(request)};
  if(immediate)run();else timer=setTimeout(run,DEBOUNCE_MS);
}
function record(name){
  if(!snapshot)return null;
  const text=String(name||"");
  const index=lowerBound(snapshot.records,text,row=>row.text);
  const row=snapshot.records[index];
  return row?.text===text?row:null;
}
function machineInfo(name){
  if(!snapshot)return null;
  const text=String(name||"");
  const records=snapshot.machineRecords||[];
  const index=lowerBound(records,text,row=>row.name);
  const row=records[index];
  return row?.name===text?row:null;
}
function allPositions(row){return row&&snapshot?snapshot.positions.subarray(row.allOffset,row.allOffset+row.allCount):new Int32Array()}
function codePositionsFor(row){return row&&snapshot?snapshot.codePositions.subarray(row.codeOffset,row.codeOffset+row.codeCount):new Int32Array()}
function query(prefix,caret,{limit=8,exclude="",kinds=null,owner=null,allowContract=false}={}){
  if(!snapshot)return[];
  const text=String(prefix??"");
  const records=snapshot.records;
  const kindSet=Array.isArray(kinds)&&kinds.length?new Set(kinds):null;
  let start=text?lowerBound(records,text,row=>row.text):0;
  const rows=[];
  for(let index=start;index<records.length;index+=1){
    const row=records[index];
    if(text&&!row.text.startsWith(text))break;
    if(row.codeCount<=0||row.text===exclude)continue;
    const ownedKinds=owner?(row.ownerKinds?.[owner]||[]):null;
    if(owner&&!ownedKinds.length)continue;
    const candidateKinds=owner?ownedKinds:row.kinds;
    if(kindSet&&!candidateKinds.some(kind=>kindSet.has(kind)))continue;
    if(!allowContract&&row.kinds.length===1&&row.kinds[0]==="Contract")continue;
    const positions=codePositionsFor(row);
    rows.push({
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent:lastBefore(positions,Number(caret)||0),added:Math.max(0,row.text.length-text.length),
    });
  }
  rows.sort((a,b)=>b.recent-a.recent||b.count-a.count||a.added-b.added||(a.text<b.text?-1:a.text>b.text?1:0));
  return rows.slice(0,Math.max(1,limit));
}

document.addEventListener("glyph-editor-document-changed",event=>{if(event.detail?.composing)return;schedule()});
document.addEventListener("glyph-editor-source-replaced",()=>schedule({immediate:true,invalidate:true}));
document.addEventListener("glyph-editor-composition-changed",event=>{if(event.detail?.active===false)schedule()});
editor.dataset.lexicalIndexReady="true";
window.GlyphEditorLexicalIndex={
  marker:MARKER,version:2,snapshot:()=>snapshot,record,machineInfo,allPositions,codePositions:codePositionsFor,query,
  refresh:()=>schedule({immediate:true}),invalidate:()=>schedule({immediate:true,invalidate:true}),
  metrics:()=>({...metrics,inFlight:Boolean(inFlight),pending:Boolean(pending)}),
};
schedule({immediate:true,invalidate:true});
})();
</script>
"""


def enhance_editor_lexical_index_html(html: str) -> str:
    """Install a coalesced Worker-backed lexical and lightweight symbol index."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["LEXICAL_WORKER_JS", "enhance_editor_lexical_index_html"]